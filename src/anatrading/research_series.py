"""Pure, strict daily source normalization for compact research reports.

A date group is one source observation slot. Explicit bad and duplicate groups
stay in the sequence; an absent calendar date is never synthesized. Dated raw
errors retain their slot without acquiring valid-observation qualification.
"""
from datetime import date

from .numeric import NumericError, decimal_value


MAX_RESEARCH_ROWS = 20_000
_PRICE_FIELDS = ("open", "high", "low", "close")


def strict_date(value, code="invalid_date"):
    """Return a canonical ISO day, rejecting compact, week and datetime forms."""
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except (TypeError, ValueError):
        raise ValueError(code) from None
    return value


def _located_date(row):
    try:
        return strict_date(row.get("label"))
    except ValueError:
        return None


def _source_date(row):
    located = _located_date(row)
    if located is not None:
        return located
    tokens = row.get("tokens") or {}
    token = tokens.get("source_date") or tokens.get("date")
    if isinstance(token, str):
        if len(token) == 8 and token.isascii() and token.isdigit():
            token = f"{token[:4]}-{token[4:6]}-{token[6:]}"
        else:
            token = token.replace("/", "-")
    try:
        return strict_date(token)
    except ValueError:
        return None


def _source_rows(query):
    return (*query.get("rows", ()), *query.get("unlocated", ()))


def source_rejection(query):
    """An explicitly quarantined source cannot gain research qualification."""
    if query.get("metadata", {}).get("quarantined") is True or any(
        check.get("name") == "known_negative_sample" and check.get("outcome") == "fail"
        for check in query.get("batch_checks", ())
    ):
        return "known_negative_source"
    return None


def _source_conflict(row, metadata):
    tokens = row.get("tokens") or {}
    failed = {check.get("name") for check in row.get("checks", ()) if check.get("outcome") == "fail"}
    if ("source_code" in failed or tokens.get("code") is not None and metadata.get("source_code") is not None
            and tokens["code"] != metadata["source_code"]):
        return "source_identity_conflict"
    if (tokens.get("adjustflag") is not None and metadata.get("source_adjustflag") is not None
            and tokens["adjustflag"] != metadata["source_adjustflag"]):
        return "source_adjustment_conflict"
    if failed & {"source_adjustflag", "source_adjustment"}:
        return "source_adjustment_check_failed"
    return None


def _bar(day, rows, metadata, rejected):
    result = dict(date=day, ordinal=rows[0].get("ordinal") if len(rows) == 1 else None,
                  **dict.fromkeys(_PRICE_FIELDS), reason=None)
    if len(rows) != 1:
        result["reason"] = "duplicate_date"
        return result
    row = rows[0]
    if _located_date(row) is None:
        result["reason"] = "unlocated_label"
        return result
    raw = row.get("values") or {}
    # Retain parseable prices from rejected observations for inspection. Only
    # their research eligibility changes; original rows/checks are untouched.
    reason = rejected or _source_conflict(row, metadata)
    for key in _PRICE_FIELDS:
        if raw.get(key) is None:
            reason = reason or "missing_ohlc"
            continue
        try:
            result[key] = decimal_value(raw[key])
        except NumericError:
            reason = reason or "invalid_price"
    if reason is None:
        opening, high, low, close = (result[key] for key in _PRICE_FIELDS)
        if any(value <= 0 for value in (opening, high, low, close)):
            reason = "invalid_price"
        elif not (low <= opening <= high and low <= close <= high):
            reason = "invalid_ohlc"
    result["reason"] = reason
    return result


def daily_bars(query):
    """Return ascending date-group dictionaries with exact Decimal OHLC values.

    Requires the full daily prefix from the frozen source. Unknown dates are
    disclosed separately by daily_coverage; they cannot be assigned a made-up
    position in a recurrence. Volume and amount do not govern price validity.
    """
    if query.get("metadata", {}).get("period") != "1d":
        raise ValueError("unsupported_period")
    rows = _source_rows(query)
    if len(rows) > MAX_RESEARCH_ROWS:
        raise ValueError("research_row_limit")
    selection = query.get("selection") or {}
    if selection.get("ordinal_start") is not None or selection.get("ordinal_end") is not None:
        raise ValueError("ordinal_window_not_supported")
    cutoff = selection.get("cutoff")
    if cutoff is not None:
        strict_date(cutoff, "invalid_cutoff")
    grouped = {}
    for row in rows:
        day = _source_date(row)
        if day is not None and (cutoff is None or day <= cutoff):
            grouped.setdefault(day, []).append(row)
    rejected = source_rejection(query)
    return [_bar(day, grouped[day], query["metadata"], rejected) for day in sorted(grouped)]


def daily_coverage(query, bars=None):
    """Counts never silently qualify an unlocatable source as complete."""
    if bars is None:
        bars = daily_bars(query)
    rows = _source_rows(query)
    unlocated = sum(_located_date(row) is None for row in rows)
    batch_unlocated = query.get("counts", {}).get("batch_unlocated_rows", unlocated)
    return dict(source_rows=len(rows), date_groups=len(bars),
                valid_groups=sum(bar["reason"] is None for bar in bars),
                invalid_groups=sum(bar["reason"] is not None for bar in bars),
                duplicate_groups=sum(bar["reason"] == "duplicate_date" for bar in bars),
                unlocated_rows=unlocated,
                unreadable_date_rows=sum(_source_date(row) is None for row in rows),
                batch_unlocated_rows=batch_unlocated,
                coverage_known=unlocated == 0 and batch_unlocated == 0)
