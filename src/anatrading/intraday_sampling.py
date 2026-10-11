"""Bounded retrospective 1/5-slot diagnostics; no market calendar or execution claims.

The expected grid, never the last observed row, determines the comparison end.
This module performs no storage, network, clock, HTTP, or UI operations. See
docs/research/028-intraday-research-candidates.md section 4.4 for its contract.
"""
from datetime import date, datetime, timedelta
import hashlib
import json
import math
import re

from .numeric import NumericError, decimal_value
from .pair_research import symbol_identity
from .research_series import _source_conflict, source_rejection


METHOD_ID = "minute-source-sampling-diagnostic-v1"
MAX_SOURCE_ROWS = 20_000
MAX_SEGMENTS = 8
MAX_EXPECTED_SLOTS = 1_440
MAX_AUXILIARY_BYTES = 16 * 1024
_PRICE_FIELDS = ("open", "high", "low", "close")
_EVIDENCE_STATUSES = {"verified", "declared", "unknown"}
_DECLARERS = {"source_document", "client_observation", "user_declaration", "project_template"}
_LABEL_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}\Z")
_HEX_RE = re.compile(r"[0-9a-f]{64}\Z")
_ZONE_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_+.\-]*(?:/[A-Za-z0-9][A-Za-z0-9_+.\-]*)*\Z")
_IDENTITY_CHECKS = {"declared_instrument", "declared_venue", "source_code", "instrument_identity"}
_ADJUSTMENT_CHECKS = {"source_adjustflag", "source_adjustment", "declared_adjustment"}
_PARSE_CHECKS = {"structure", "label", "source_date_range", "ohlc_bounds", "nonnegative_prices",
                 *("numeric." + field for field in _PRICE_FIELDS)}


def _canonical(value, limit=None):
    """Match the repository's canonical JSON without importing storage modules."""
    chunks, size = [], 0
    try:
        encoder = json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False,
                                   separators=(",", ":"))
        for chunk in encoder.iterencode(value):
            part = chunk.encode("utf-8")
            size += len(part)
            if limit is not None and size > limit:
                raise ValueError("auxiliary_input_limit")
            chunks.append(part)
    except (TypeError, OverflowError, RecursionError, UnicodeError) as exc:
        raise ValueError("invalid_auxiliary_input") from exc
    return b"".join(chunks)


def _identity(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def _keys(value, expected, code):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise ValueError(code)


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def _enum(value, choices):
    return isinstance(value, str) and value in choices


def _day(value, code):
    try:
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(code) from None
    return value


def _label(value, code="invalid_label"):
    if not isinstance(value, str) or _LABEL_RE.fullmatch(value) is None:
        raise ValueError(code)
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M")
    except ValueError:
        raise ValueError(code) from None


def _refs(refs, required=False):
    if not isinstance(refs, list) or required and not refs:
        raise ValueError("invalid_evidence_refs")
    for ref in refs:
        _keys(ref, ("source_id", "version", "declared_by"), "invalid_evidence_refs")
        if not _text(ref["source_id"]) or not _text(ref["version"]) or not _enum(ref["declared_by"], _DECLARERS):
            raise ValueError("invalid_evidence_refs")


def _checks(checks):
    if not isinstance(checks, (list, tuple)) or any(not isinstance(c, dict) or not isinstance(c.get("name"), str) for c in checks):
        raise ValueError("invalid_source_checks")
    return {c.get("name") for c in checks if c.get("outcome") == "fail"}


def _batch_rejection(query):
    failed = _checks(query.get("batch_checks", []))
    rejection = source_rejection(query)
    if rejection:
        raise ValueError(rejection)
    if failed & _IDENTITY_CHECKS:
        raise ValueError("source_identity_conflict")
    if failed & _ADJUSTMENT_CHECKS:
        raise ValueError("source_adjustment_check_failed")
    if failed & _PARSE_CHECKS:
        raise ValueError("source_parse_check_failed")


def _descriptor(descriptor, query, instrument):
    _keys(descriptor, ("schema_version", "snapshot_id", "symbol", "market", "source_date",
                       "clock_basis", "label_semantics", "timezone", "segments", "evidence_refs"),
          "invalid_descriptor")
    if (type(descriptor["schema_version"]) is not int or descriptor["schema_version"] != 1
            or descriptor["clock_basis"] != "source_label"
            or descriptor["label_semantics"] != "declared_end_label"):
        raise ValueError("invalid_descriptor")
    if (descriptor["snapshot_id"] != query["snapshot_id"] or descriptor["symbol"] != instrument["symbol"]
            or descriptor["market"] != instrument["market"]):
        raise ValueError("descriptor_source_mismatch")
    day = _day(descriptor["source_date"], "invalid_source_date")
    _refs(descriptor["evidence_refs"])
    timezone = descriptor["timezone"]
    _keys(timezone, ("name", "evidence_status", "evidence_refs"), "invalid_timezone")
    status = timezone["evidence_status"]
    if not _enum(status, _EVIDENCE_STATUSES) or timezone["name"] is None and status != "unknown":
        raise ValueError("invalid_timezone")
    if timezone["name"] is not None:
        # A source declaration, not a machine-dependent tzdata lookup. No clock
        # conversion occurs and even a plausible spelling gains no certification.
        if (not isinstance(timezone["name"], str) or len(timezone["name"]) > 128
                or _ZONE_NAME_RE.fullmatch(timezone["name"]) is None):
            raise ValueError("invalid_timezone")
    _refs(timezone["evidence_refs"], required=status != "unknown")
    segments = descriptor["segments"]
    if not isinstance(segments, list) or not 1 <= len(segments) <= MAX_SEGMENTS:
        raise ValueError("segment_limit")
    total, previous_end, names, bounds = 0, None, set(), []
    for segment in segments:
        _keys(segment, ("segment_id", "first_label", "last_label", "step_seconds", "stage",
                        "stage_evidence_status", "evidence_refs"), "invalid_segment")
        name = segment["segment_id"]
        if not _text(name) or name in names:
            raise ValueError("invalid_segment_id")
        names.add(name)
        if (type(segment["step_seconds"]) is not int or segment["step_seconds"] != 60
                or not _enum(segment["stage"], {"continuous", "auction", "mixed", "unknown"})
                or not _enum(segment["stage_evidence_status"], _EVIDENCE_STATUSES)):
            raise ValueError("invalid_segment")
        _refs(segment["evidence_refs"], required=segment["stage_evidence_status"] != "unknown")
        start, end = _label(segment["first_label"]), _label(segment["last_label"])
        if (start.date().isoformat() != day or end.date().isoformat() != day or end < start
                or previous_end is not None and start <= previous_end):
            raise ValueError("invalid_segment_grid")
        count = int((end - start).total_seconds() // 60) + 1
        total += count
        if total > MAX_EXPECTED_SLOTS:
            raise ValueError("expected_slot_limit")
        bounds.append((segment, start, count))
        previous_end = end
    return bounds


def _source_day(row):
    label = row.get("label")
    if isinstance(label, str):
        try:
            return _day(label[:10], "invalid_source_date")
        except ValueError:
            pass
    token = row.get("tokens", {}).get("source_date") or row.get("tokens", {}).get("date")
    if isinstance(token, str):
        if len(token) == 8 and token.isascii() and token.isdigit():
            token = f"{token[:4]}-{token[4:6]}-{token[6:]}"
        else:
            token = token.replace("/", "-")
        try:
            return _day(token, "invalid_source_date")
        except ValueError:
            pass
    return None


def _eligibility(row, metadata, *, unlocated=False):
    failed = _checks(row.get("checks", []))
    conflict = _source_conflict(row, metadata)
    if conflict:
        return conflict
    if failed & _IDENTITY_CHECKS:
        return "source_identity_conflict"
    if failed & _ADJUSTMENT_CHECKS:
        return "source_adjustment_check_failed"
    # A failed label check describes the unknown location itself. It is not a
    # contradictory source identity/structural claim and must remain reportable.
    parse_checks = _PARSE_CHECKS - {"label"} if unlocated else _PARSE_CHECKS
    if failed & parse_checks:
        return "source_parse_check_failed"
    return None


def _price(row, metadata):
    reason = _eligibility(row, metadata)
    if reason:
        return None, reason
    raw = row.get("values")
    if not isinstance(raw, dict) or any(raw.get(key) is None for key in _PRICE_FIELDS):
        return None, "missing_ohlc"
    try:
        opening, high, low, close = (decimal_value(raw[key]) for key in _PRICE_FIELDS)
    except NumericError:
        return None, "invalid_price"
    if any(value <= 0 for value in (opening, high, low, close)):
        return None, "invalid_price"
    if not low <= opening <= high or not low <= close <= high:
        return None, "invalid_ohlc"
    return close, None


def _closure(mapping, ordinals):
    if not isinstance(mapping, dict):
        raise ValueError("invalid_closure_annotation")
    for key, value in mapping.items():
        if (not isinstance(key, str) or re.fullmatch(r"[1-9][0-9]*", key) is None
                or len(key) > 20 or int(key) not in ordinals):
            raise ValueError("invalid_closure_ordinal")
        _keys(value, ("status", "evidence_refs"), "invalid_closure_annotation")
        if value["status"] != "unclosed":
            raise ValueError("invalid_closure_annotation")
        _refs(value["evidence_refs"], required=True)


def _square(value):
    squared = value * value
    if not math.isfinite(squared):
        raise ArithmeticError("numerical_failure")
    if value != 0 and squared == 0:
        raise ArithmeticError("numerical_underflow")
    return squared


def _estimates(prices):
    floats = [float(price) for price in prices]
    if any(not math.isfinite(value) or value <= 0 for value in floats):
        raise ArithmeticError("numerical_failure")
    logs = [math.log(value) for value in floats]
    if any(not math.isfinite(value) for value in logs):
        raise ArithmeticError("numerical_failure")
    for i in range(1, len(prices)):
        if prices[i] != prices[i - 1] and (floats[i] == floats[i - 1] or logs[i] == logs[i - 1]):
            raise ArithmeticError("precision_loss")
    for i in range(5, len(prices), 5):
        if prices[i] != prices[i - 5] and logs[i] == logs[i - 5]:
            raise ArithmeticError("precision_loss")
    fine = math.fsum(_square(logs[i] - logs[i - 1]) for i in range(1, len(logs)))
    coarse = math.fsum(_square(logs[i] - logs[i - 5]) for i in range(5, len(logs), 5))
    net = logs[-1] - logs[0]
    if prices[-1] != prices[0] and net == 0:
        raise ArithmeticError("precision_loss")
    if not all(math.isfinite(value) for value in (fine, coarse, net)):
        raise ArithmeticError("numerical_failure")
    # All five fine increments telescope to their coarse increment. Scale the
    # tolerance to the computed quantities; never alter values to pass the bound.
    tolerance = 64 * math.ulp(1.) * (coarse + 5 * fine)
    if coarse > 5 * fine + tolerance:
        raise ArithmeticError("numerical_failure")
    ratio, ratio_reason = None, "zero_scale" if coarse == 0 else None
    if coarse > 0:
        ratio = fine / coarse
        if not math.isfinite(ratio):
            ratio, ratio_reason = None, "ratio_out_of_range"
    return dict(rv_1_same=fine, rv_5=coarse, net_log_change=net,
                sensitivity_ratio=ratio, ratio_reason=ratio_reason,
                n_returns_1=len(prices) - 1, n_returns_5=(len(prices) - 1) // 5,
                estimate_scope="source_template_only")


def _slot(label, rows, metadata, closure):
    ordinals = sorted(row["ordinal"] for row in rows)
    close, reason = None, None
    if not rows:
        reason = "missing_slot"
    elif len(rows) != 1:
        reason = "duplicate_slot"
    else:
        close, reason = _price(rows[0], metadata)
    unclosed = any(str(ordinal) in closure for ordinal in ordinals)
    if unclosed and reason is None:
        reason = "unclosed_comparison_slot"
    return dict(label=label, ordinals=ordinals, close=close, reason=reason, unclosed=unclosed)


def _counts(slots):
    return dict(expected_slots=len(slots), observed_slots=sum(bool(s["ordinals"]) for s in slots),
                valid_slots=sum(s["reason"] is None for s in slots),
                missing_slots=sum(not s["ordinals"] for s in slots),
                duplicate_slots=sum(len(s["ordinals"]) > 1 for s in slots),
                invalid_slots=sum(s["reason"] not in (None, "missing_slot", "duplicate_slot", "unclosed_comparison_slot")
                                  for s in slots),
                unclosed_slots=sum(s["unclosed"] for s in slots))


def _segment_report(segment, start, count, cutoff, grouped, metadata, closure, coverage_unknown):
    k = min(count - 1, int((cutoff - start).total_seconds() // 60))
    k = max(k, -1)
    m = 5 * (k // 5) if k >= 0 else None
    labels = [(start + timedelta(minutes=i)).isoformat(timespec="minutes") for i in range(count)]
    # No future value, eligibility, or closure can enter current slot states.
    slots = [_slot(label, grouped.get(label, []), metadata, closure) for label in labels[:k + 1]]
    common = slots[:m + 1] if m is not None else []
    tail = slots[m + 1:] if m is not None else []
    invalid = any(s["reason"] is not None for s in common)
    coverage = ("incomplete_declared_grid" if invalid else "unknown" if coverage_unknown
                else "complete_declared_grid")
    closure_status = "unclosed" if any(s["unclosed"] for s in common) else "unknown"
    reason = ("not_started" if k < 0 else "insufficient_common_span" if m < 5 else
              "invalid_comparison_grid" if invalid else "source_coverage_unknown" if coverage_unknown else None)
    main, subset, numerical_reason = None, None, None
    if m is not None and m >= 5 and not invalid:
        try:
            values = _estimates([s["close"] for s in common])
            if coverage_unknown:
                values["estimate_scope"] = "located_source_subset"
                subset = values
            else:
                main = values
        except (ArithmeticError, ValueError) as exc:
            numerical_reason = str(exc) if str(exc) in {"precision_loss", "numerical_underflow"} else "numerical_failure"
            reason = numerical_reason
    end = labels[m] if m is not None else None
    observed = [s["label"] for s in slots if s["ordinals"]]
    trace = [dict(segment_id=segment["segment_id"], label=s["label"], ordinals=s["ordinals"],
                  scope="comparison" if i <= m else "tail", reason=s["reason"])
             for i, s in enumerate(slots)]
    return dict(segment_id=segment["segment_id"], first_label=segment["first_label"],
                last_label=segment["last_label"], stage=segment["stage"],
                stage_evidence_status=segment["stage_evidence_status"], cutoff=cutoff.isoformat(timespec="minutes"),
                k=k, m=m, comparison_start_label=labels[0] if k >= 0 else None, comparison_end_label=end,
                last_observed_label=observed[-1] if observed else None,
                counts=_counts(common), tail=dict(first_label=tail[0]["label"] if tail else None,
                                                 last_label=tail[-1]["label"] if tail else None, counts=_counts(tail)),
                head_omission=dict(kind="first_open_to_close", end_label=labels[0]),
                cutoff_delay_nominal_minutes=int((cutoff - _label(end)).total_seconds() // 60) if end else None,
                coverage_status=coverage, closure_status=closure_status, historical_availability="unverified",
                main_values=main, located_subset_values=subset, reason=reason, numerical_reason=numerical_reason), trace


def intraday_sampling_report(query, descriptor, *, cutoff, closure_by_ordinal=None):
    """One date of fixed-source 1/5 nominal-slot diagnostics, without mutation.

    Invalid request/descriptor/source eligibility raises a stable ValueError.
    Slot-level gaps/failures and numerical failures remain in the returned report.
    A missing final expected close can never shorten the requested comparison.
    """
    if not isinstance(query, dict) or not isinstance(query.get("metadata"), dict):
        raise ValueError("invalid_query")
    rows, unlocated = query.get("rows", []), query.get("unlocated", [])
    if not isinstance(rows, (list, tuple)) or not isinstance(unlocated, (list, tuple)):
        raise ValueError("invalid_query")
    if len(rows) + len(unlocated) > MAX_SOURCE_ROWS:
        raise ValueError("research_row_limit")
    metadata = query["metadata"]
    if metadata.get("period") != "1m":
        raise ValueError("unsupported_period")
    for field in ("snapshot_id", "query_id"):
        if not isinstance(query.get(field), str) or _HEX_RE.fullmatch(query[field]) is None:
            raise ValueError("invalid_source_id")
    selection = query.get("selection") or {}
    if not isinstance(selection, dict):
        raise ValueError("invalid_selection")
    if selection.get("ordinal_start") is not None or selection.get("ordinal_end") is not None:
        raise ValueError("ordinal_window_not_supported")
    cutoff_time = _label(cutoff, "invalid_cutoff")
    if selection.get("cutoff") is not None and selection["cutoff"] != cutoff:
        raise ValueError("input_cutoff_mismatch")
    _batch_rejection(query)
    instrument = symbol_identity(query)
    closure = {} if closure_by_ordinal is None else closure_by_ordinal
    _canonical(dict(descriptor=descriptor, closure_by_ordinal=closure), MAX_AUXILIARY_BYTES)
    bounds = _descriptor(descriptor, query, instrument)
    day = descriptor["source_date"]
    if cutoff[:10] != day:
        raise ValueError("invalid_cutoff")
    source_rows = (*rows, *unlocated)
    ordinals = set()
    for row in source_rows:
        if (not isinstance(row, dict) or type(row.get("ordinal")) is not int or row["ordinal"] <= 0
                or row["ordinal"] in ordinals):
            raise ValueError("invalid_source_ordinal")
        if not isinstance(row.get("tokens", {}), dict):
            raise ValueError("invalid_query")
        ordinals.add(row["ordinal"])
    _closure(closure, ordinals)
    grouped, excluded, unknown_ordinals = {}, [], []
    malformed_labels = 0
    for row in source_rows:
        label = row.get("label")
        try:
            _label(label)
        except ValueError:
            malformed_labels += 1
            located_day = _source_day(row)
            unknown = located_day is None or located_day == day
            if unknown:
                # A reliably different date is outside this single-date input.
                # Within/possibly within it, conflicts cannot be laundered into
                # conditional subset output; ordinary label failure stays unknown.
                failure = _eligibility(row, metadata, unlocated=True)
                if failure:
                    raise ValueError(failure)
                unknown_ordinals.append(row["ordinal"])
            excluded.append(dict(ordinal=row["ordinal"], reason="unlocated_coverage_unknown" if unknown else "other_source_date"))
            continue
        if label[:10] != day or label > cutoff:
            excluded.append(dict(ordinal=row["ordinal"], reason="other_source_date" if label[:10] != day else "future_not_used"))
            continue
        grouped.setdefault(label, []).append(row)
    counts = query.get("counts") or {}
    if not isinstance(counts, dict):
        raise ValueError("invalid_source_counts")
    batch_unknown = counts.get("batch_unlocated_rows", malformed_labels)
    if type(batch_unknown) is not int or batch_unknown < 0:
        raise ValueError("invalid_source_counts")
    undetailed_unknown = max(0, batch_unknown - malformed_labels)
    unknown = bool(unknown_ordinals or undetailed_unknown)
    segments, trace, used = [], [], set()
    for segment, start, count in bounds:
        result, slot_trace = _segment_report(segment, start, count, cutoff_time, grouped, metadata, closure, unknown)
        segments.append(result)
        trace.extend(slot_trace)
        used.update(item["label"] for item in slot_trace)
    for label, members in grouped.items():
        if label not in used:
            excluded.extend(dict(ordinal=row["ordinal"], reason="outside_declared_segments") for row in members)
    descriptor_id = _identity(descriptor)
    parameters = dict(source_date=day, cutoff=cutoff, nominal_steps=[1, 5], descriptor_id=descriptor_id,
                      closure_by_ordinal=closure, mode="retrospective", scope="source_template_only")
    inputs = [dict(snapshot_id=query["snapshot_id"], query_id=query["query_id"])]
    identity = dict(method_id=METHOD_ID, inputs=inputs, parameters=parameters)
    # The JSON round-trip returns independent mutable containers, preserving inputs.
    return json.loads(_canonical(dict(**identity, analysis_id=_identity(identity), descriptor_id=descriptor_id,
        descriptor=descriptor, identity=instrument, mode="retrospective", scope="source_template_only",
        numeric_kind="estimate_float64", units=dict(rv="log_return_squared", net_log_change="log_return",
                                                   sensitivity_ratio="dimensionless"),
        segments=segments, slot_trace=trace, excluded=sorted(excluded, key=lambda r: r["ordinal"]),
        coverage=dict(source_rows=len(source_rows), unlocated_ordinals=sorted(unknown_ordinals),
                      batch_unlocated_rows=batch_unknown, undetailed_unlocated_rows=undetailed_unknown),
        limitations=["source_template_only", "retrospective_source_version", "closure_unknown",
                     "timezone_name_declaration_only",
                     "historical_availability_unverified", "transaction_coverage_unverified",
                     "adjustment_and_corporate_actions_unverified", "no_noise_identification",
                     "no_prediction_or_trading_return_claim"])))
