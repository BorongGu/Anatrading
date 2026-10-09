"""Capture native reference arrays and apply a local inclusive date window."""
from collections import Counter
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import uuid

from . import tdx_acquisition as acquisition
from .formats import _http_json
from .models import DecodeError
from .numeric import NumericError, decimal_value


_FIELDS = ("Bonus", "AllotPrice", "ShareBonus", "Allotment")
_TYPES = {"1": "除权除息", "11": "扩缩股", "15": "重新调整"}


def _request(kind, target, start, end):
    try:
        if any(type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value) for value in (start, end)):
            raise ValueError
        first, last = date.fromisoformat(start), date.fromisoformat(end)
        if first > last:
            raise ValueError
        if kind == "calendar" and target == "SH":
            method, parameters = "get_trading_calendar", dict(market="SH")
        elif kind == "actions" and type(target) is str and re.fullmatch(r"[0-9]{6}\.(SH|SZ|BJ)", target):
            method, parameters = "get_divid_factors", dict(stock_code=target)
        else:
            raise ValueError
    except (ValueError, TypeError):
        raise acquisition.AcquireError("invalid_tdx_reference_request") from None
    parameters.update(start_time=start.replace("-", "") + "000000", end_time=end.replace("-", "") + "235959")
    return dict(id=1, method=method, params=parameters)


def reference_view(raw, *, kind, target, start, end):
    request = _request(kind, target, start, end)
    try:
        response = _http_json(raw)
        result = response.get("result")
        if type(response.get("id")) is not int or response["id"] != 1 or type(result) is not dict:
            raise ValueError
        if result.get("ErrorId") != "0":
            raise acquisition.AcquireError("tdx_reference_unavailable")
        dates = result.get("Date")
        empty_shape = None
        if kind == "actions" and "Date" not in result and result.get("Value") == [] and result.get("Type", []) == []:
            dates, empty_shape = [], "value_only_empty"
        if type(dates) is not list:
            raise ValueError
        if kind == "calendar" and any(type(d) is not str for d in dates):
            raise ValueError
        if kind == "calendar" and len(set(dates)) != len(dates):
            raise ValueError
        if kind == "actions":
            types, values = result.get("Type", []), result.get("Value", [])
            if type(types) is not list or type(values) is not list or len(types) != len(dates) or len(values) != len(dates):
                raise ValueError
        rows, before, after = [], 0, 0
        for i, token in enumerate(dates):
            if type(token) is not str or not re.fullmatch(r"[0-9]{8}", token):
                raise ValueError
            day = date.fromisoformat(f"{token[:4]}-{token[4:6]}-{token[6:]}").isoformat()
            row = dict(ordinal=i + 1, date=day, source_date=token)
            if kind == "actions":
                if type(types[i]) is not str or not types[i] or type(values[i]) is not list or len(values[i]) != 4:
                    raise ValueError
                for value in values[i]:
                    if type(value) is not str:
                        raise ValueError
                    decimal_value(value)
                row.update(source_type=types[i], type_name=_TYPES.get(types[i]), values=dict(zip(_FIELDS, values[i])))
            # Validate every original record, including records outside the display window.
            if day < start:
                before += 1
            elif day > end:
                after += 1
            else:
                rows.append(row)
    except (ValueError, TypeError, DecodeError, NumericError):
        raise acquisition.AcquireError("invalid_tdx_reference_response") from None
    return dict(method_id="tdx-reference-view-v1", kind=kind, target=target, source_method=request["method"],
                selection=dict(start=start, end=end), qualification="unverified_source_reference", coverage="unverified",
                returned_count=len(dates), selected_count=len(rows), before_start=before, after_end=after,
                duplicate_date_rows=sum(count - 1 for count in Counter(dates).values()), rows=rows,
                empty_shape=empty_shape, historical_available_at=None, standard_units="unverified")


def read_reference(root, client_directory, *, kind, target, start, end):
    request = _request(kind, target, start, end)
    identity = acquisition._client_identity(Path(client_directory).resolve())
    body = json.dumps(request, separators=(",", ":")).encode("utf-8")
    status, raw = acquisition._http(17709, "POST", "/", body, {"Content-Type": "application/json"}, budget=10)
    captured_at = datetime.now(timezone.utc).isoformat()
    folder = Path(root).resolve() / "acquisition" / "reference" / uuid.uuid4().hex
    folder.mkdir(parents=True)
    (folder / "request.json").write_bytes(body)
    (folder / "response.bin").write_bytes(raw)
    capture = dict(capture_id=folder.name, captured_at=captured_at, client_identity=identity, http_status=status,
                   request_sha256=hashlib.sha256(body).hexdigest(), response_sha256=hashlib.sha256(raw).hexdigest(),
                   evidence_directory=str(folder), status="received")
    try:
        if status != 200:
            raise acquisition.AcquireError("tdx_reference_unavailable")
        report = dict(**reference_view(raw, kind=kind, target=target, start=start, end=end), **capture)
    except acquisition.AcquireError as error:
        capture.update(status="rejected", error_code=error.code)
        (folder / "capture.json").write_text(json.dumps(capture, ensure_ascii=False), encoding="utf-8")
        raise
    (folder / "capture.json").write_text(json.dumps(capture, ensure_ascii=False), encoding="utf-8")
    (folder / "report.json").write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return report
