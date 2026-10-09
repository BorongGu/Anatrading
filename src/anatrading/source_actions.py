"""Link frozen source action dates to selected daily records, without adjustments."""
from collections import Counter
from datetime import date, timedelta
import hashlib
from pathlib import Path
import re

from .formats import _http_json
from .models import DecodeError
from .price_channel import _source_date
from .store import _identity
from .tdx_acquisition import AcquireError
from .tdx_reference import _request, reference_view


def captured_actions(root, capture_id):
    if type(capture_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", capture_id):
        raise AcquireError("invalid_reference_capture")
    base = (Path(root).resolve() / "acquisition/reference").resolve()
    folder = (base / capture_id).resolve()
    if not folder.is_relative_to(base):
        raise AcquireError("invalid_reference_capture")
    try:
        request_raw = (folder / "request.json").read_bytes()
        raw = (folder / "response.bin").read_bytes()
        capture = _http_json((folder / "capture.json").read_bytes())
        if (capture.get("capture_id") != capture_id or capture.get("status") != "received"
                or capture.get("http_status") != 200
                or hashlib.sha256(request_raw).hexdigest() != capture.get("request_sha256")
                or hashlib.sha256(raw).hexdigest() != capture.get("response_sha256")):
            raise AcquireError("reference_capture_mismatch")
        request = _http_json(request_raw)
        if request.get("method") == "get_trading_calendar":
            raise AcquireError("reference_capture_not_actions")
        params = request["params"]
        target = params["stock_code"]
        start, end = (date.fromisoformat(params[key][:8]).isoformat() for key in ("start_time", "end_time"))
        if request != _request("actions", target, start, end) or not isinstance(capture.get("captured_at"), str):
            raise ValueError
    except AcquireError:
        raise
    except OSError:
        raise AcquireError("reference_capture_unavailable") from None
    except (DecodeError, KeyError, TypeError, ValueError):
        raise AcquireError("invalid_reference_capture") from None
    result = reference_view(raw, kind="actions", target=target, start="0001-01-01", end="9999-12-31")
    return dict(**result, capture_selection=dict(start=start, end=end),
                **{key: capture[key] for key in ("capture_id", "captured_at", "request_sha256", "response_sha256")})


def action_captures(root):
    base = Path(root).resolve() / "acquisition/reference"
    result = []
    if not base.exists():
        return result
    for folder in sorted(base.iterdir()):
        if not folder.is_dir() or not re.fullmatch(r"[0-9a-f]{32}", folder.name):
            continue
        try:
            report = captured_actions(root, folder.name)
            result.append(dict(capture_id=folder.name, status="received", target=report["target"],
                               captured_at=report["captured_at"], selection=report["capture_selection"],
                               returned_count=report["returned_count"], response_sha256=report["response_sha256"]))
        except AcquireError as error:
            if error.code != "reference_capture_not_actions":
                result.append(dict(capture_id=folder.name, status="unavailable", error_code=error.code))
    return result


def action_window(query, reference, start, end):
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first.isoformat() != start or last.isoformat() != end or first >= last:
            raise ValueError
    except (ValueError, TypeError):
        raise AcquireError("invalid_action_window") from None
    if query["metadata"].get("period") != "1d" or reference.get("kind") != "actions":
        raise AcquireError("invalid_action_window")
    # Replayed capture views retain the original response's full date arrays.
    if start < reference["selection"]["start"] or end > reference["selection"]["end"]:
        raise AcquireError("action_reference_window_unavailable")
    dates, unreadable = {}, []
    for row in (*query["rows"], *query["unlocated"]):
        day = _source_date(row)
        if day is None:
            unreadable.append(row["ordinal"])
        else:
            dates.setdefault(day, []).append(row)
    rows = []
    cutoff = query["selection"].get("cutoff")
    for event in reference["rows"]:
        if not start < event["date"] <= end:
            continue
        matches = dates.get(event["date"], [])
        outside = cutoff is not None and event["date"] > cutoff[:10]
        reason = ("outside_query_cutoff" if outside else "not_returned_by_query" if not matches else
                  "duplicate_query_date" if len(matches) > 1 else "unlocated_query_label" if matches[0]["label"] is None else None)
        rows.append(dict(**event, query_ordinals=[] if outside else [row["ordinal"] for row in matches], link_reason=reason))
    requested = reference.get("capture_selection", reference["selection"])
    in_range = requested["start"] <= (first + timedelta(days=1)).isoformat() and end <= requested["end"]
    identity = dict(method_id="source-action-window-v1", query_id=query["query_id"],
                    capture_id=reference["capture_id"], start_exclusive=start, end_inclusive=end,
                    request_sha256=reference["request_sha256"], response_sha256=reference["response_sha256"],
                    captured_at=reference["captured_at"])
    return dict(**identity, action_window_id=_identity(identity), qualification="retrospective_source_records",
                target=reference["target"], pairing_status="assumed_text_match", coverage="unverified",
                capture_selection=requested, request_range_status="within_requested_range" if in_range else "range_not_requested",
                observation_status="returned_records" if rows else "no_returned_records",
                returned_count=reference["returned_count"], selected_count=len(rows), rows=rows,
                duplicate_selected_date_rows=sum(count - 1 for count in Counter(row["date"] for row in rows).values()),
                unreadable_query_date_ordinals=unreadable, historical_available_at=None, standard_units="unverified")
