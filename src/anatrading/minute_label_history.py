"""Finite retrospective source-label endpoint records, without grid/risk claims.

Pure Query/Row transformation. Source dates precede endpoint qualification, so
failed dates never disappear from the five-date window. See research/045.
"""
from datetime import datetime
from fractions import Fraction
import json
import re

from .numeric import NumericError, decimal_value
from .pair_research import _claim, symbol_identity
from .research_series import _source_date, source_rejection, strict_date
from .store import _identity


METHOD_ID = "minute-source-label-history-v1"
MAX_ROWS = 20_000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
_IDENTITY_CHECKS = {"source_code", "source_venue", "declared_instrument", "declared_venue", "instrument_identity"}
_ADJUSTMENT_CHECKS = {"source_adjustflag", "source_adjustment", "declared_adjustment"}
_SCALE_CHECKS = {"price_scale", "price_scaling", "same_price_scale"}
_LABEL_CHECKS = {"label", "source_date_range", "label_semantics", "source_label"}


def _clock(value):
    if not isinstance(value, str) or re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value) is None:
        raise ValueError("invalid_endpoint_selection")
    return int(value[:2]) * 60 + int(value[3:])


def endpoint_selection(source_date, start_clock, end_clock, cutoff=None):
    """Validate explicit canonical labels; never infer endpoints or a session."""
    strict_date(source_date, "invalid_endpoint_selection")
    minutes = _clock(end_clock) - _clock(start_clock)
    as_of = source_date + "T" + end_clock
    if minutes <= 0 or cutoff is not None and cutoff < as_of:
        raise ValueError("invalid_endpoint_selection")
    return as_of, minutes


def signed_fraction(value):
    """Eight-place half-even display, rounded on magnitude then signed.

    Fraction is authoritative, including a negative value rounding to zero.
    No Decimal division/subtraction and no nonnegative quantity formatter.
    """
    value = Fraction(value)
    scaled, remainder = divmod(abs(value.numerator) * 100_000_000, value.denominator)
    if 2 * remainder > value.denominator or (2 * remainder == value.denominator and scaled % 2):
        scaled += 1
    sign = "-" if value < 0 and scaled else ""
    return dict(numerator=str(value.numerator), denominator=str(value.denominator),
                display=f"{sign}{scaled // 100_000_000}.{scaled % 100_000_000:08d}")


def _located(row):
    label = row.get("label")
    if not isinstance(label, str) or re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}", label) is None:
        return None
    try:
        datetime.fromisoformat(label)
    except ValueError:
        return None
    return label


def _day(row):
    label = row.get("label")
    if isinstance(label, str):
        try:
            return strict_date(label[:10])
        except ValueError:
            pass
    return _source_date(row)


def _failed(checks):
    return {check.get("name") for check in checks if check.get("outcome") == "fail"}


def _check_conflict(checks, *, endpoint=False):
    failed = _failed(checks)
    if failed & _IDENTITY_CHECKS:
        return "source_identity_conflict"
    if failed & _ADJUSTMENT_CHECKS:
        return "source_adjustment_check_failed"
    if failed & _SCALE_CHECKS:
        return "price_scale_conflict"
    if failed & _LABEL_CHECKS:
        return "source_label_conflict"
    if endpoint and "structure" in failed:
        return "source_structure_failed"
    if endpoint and "numeric.close" in failed:
        return "invalid_close"
    return None


def _batch_conflict(query):
    if source_rejection(query):
        return "source_quarantined"
    reason = _check_conflict(query.get("batch_checks", ()), endpoint=True)
    if reason:
        return reason
    try:
        symbol_identity(query)
    except ValueError as error:
        if str(error) == "research_identity_conflict":
            return "source_identity_conflict"
        # Unknown security identity is disclosed, never upgraded to verified.
    contract = query.get("manifest", {}).get("contract", {})
    evidence = contract.get("price_scaling", {})
    if evidence.get("status") in {"conflict", "failed", "rejected"}:
        return "price_scale_conflict"
    return None


def _day_identity_conflict(rows, metadata):
    """Compare every explicit source/declaration alias, even without batch ID.

    Missing claims stay unknown. Repository identity normalization recognises
    embedded markets and venue aliases; known contradictions cannot hide in an
    alias or be washed out by an absent batch-level claim.
    """
    codes, venues = set(), set()

    def collect(code, venue):
        try:
            normalized_code, normalized_venue = _claim(code, venue)
        except ValueError as error:
            return str(error) == "research_identity_conflict"
        if normalized_code is not None:
            codes.add(normalized_code)
        if normalized_venue is not None:
            venues.add(normalized_venue)
        return len(codes) > 1 or len(venues) > 1

    declaration = metadata.get("interpretation", {})
    if not isinstance(declaration, dict):
        declaration = {}
    if (collect(metadata.get("source_code"), metadata.get("source_venue"))
            or collect(declaration.get("instrument"), declaration.get("venue"))):
        return True
    for row in rows:
        tokens = row.get("tokens", {})
        for code in ("code", "source_code"):
            for venue in ("venue", "source_venue"):
                if collect(tokens.get(code), tokens.get(venue)):
                    return True
    return False


def _day_conflict(rows, metadata):
    """Known conflicts anywhere within this source day remain relevant.

    Unrelated bad-price/quantity records do not govern two-endpoint division.
    Rows on other days never enter this function.
    """
    if _day_identity_conflict(rows, metadata):
        return "source_identity_conflict"
    for row in rows:
        reason = _check_conflict(row.get("checks", ()))
        if reason:
            return reason
        tokens = row.get("tokens", {})
        for token, claim in (("adjustflag", "source_adjustflag"),
                             ("source_adjustment", "source_adjustment")):
            if tokens.get(token) is not None and metadata.get(claim) is not None and tokens[token] != metadata[claim]:
                return "source_adjustment_conflict"
    for field, reason in (("price_scale", "price_scale_conflict"), ("price_unit", "price_scale_conflict"),
                          ("adjustflag", "source_adjustment_conflict"),
                          ("source_adjustment", "source_adjustment_conflict"),
                          ("label_semantics", "source_label_conflict")):
        claims = {row.get("tokens", {}).get(field) for row in rows} - {None, ""}
        if len(claims) > 1:
            return reason
    return None


def minute_label_history(query, context, source_date, start_clock, end_clock):
    """Return explicit endpoint records from a complete bounded source prefix."""
    if len(context.get("rows", ())) + len(context.get("unlocated", ())) > MAX_ROWS:
        raise ValueError("query_row_limit")
    for key in ("snapshot_id", "batch_id", "manifest", "metadata", "batch_checks"):
        if query.get(key) != context.get(key):
            raise ValueError("context_source_mismatch")
    if context.get("metadata", {}).get("period") not in {"1m", "5m"}:
        raise ValueError("unsupported_period")
    as_of, minutes = endpoint_selection(source_date, start_clock, end_clock,
                                         query.get("selection", {}).get("cutoff"))
    selection = context.get("selection", {})
    if (selection.get("ordinal_start") is not None or selection.get("ordinal_end") is not None
            or selection.get("cutoff") is not None and selection["cutoff"] < as_of):
        raise ValueError("incomplete_source_context")
    if not any(_day(row) == source_date for row in (*query.get("rows", ()), *query.get("unlocated", ()))):
        raise ValueError("invalid_endpoint_selection")
    days, unknown = {}, []
    for row in (*context.get("rows", ()), *context.get("unlocated", ())):
        day, label = _day(row), _located(row)
        if label is not None and label > as_of or day is not None and day > source_date:
            continue
        if day is None:
            unknown.append(row["ordinal"])
        else:
            days.setdefault(day, []).append(row)
    history_dates = sorted(day for day in days if day < source_date)[-5:]
    status = "unresolved_dates" if unknown else "complete" if len(history_dates) == 5 else "insufficient"
    batch_reason = _batch_conflict(context)
    records = []
    current_semantics = {row.get("tokens", {}).get("label_semantics")
                         for row in days.get(source_date, [])} - {None, ""}
    for day in [source_date, *history_dates]:
        rows = days.get(day, [])
        start = [row for row in rows if _located(row) == day + "T" + start_clock]
        end = [row for row in rows if _located(row) == day + "T" + end_clock]
        unknown_clock = [row["ordinal"] for row in rows if _located(row) is None]
        reason = batch_reason
        reason = reason or ("endpoint_uniqueness_unknown" if unknown_clock else None)
        reason = reason or ("missing_endpoint" if not start or not end else None)
        reason = reason or ("duplicate_endpoint" if len(start) > 1 or len(end) > 1 else None)
        reason = reason or _day_conflict(rows, context.get("metadata", {}))
        day_semantics = {row.get("tokens", {}).get("label_semantics") for row in rows} - {None, ""}
        if current_semantics and day_semantics and current_semantics != day_semantics:
            reason = reason or "source_label_conflict"
        change = None
        if reason is None:
            values = []
            for row in (start[0], end[0]):
                reason = _check_conflict(row.get("checks", ()), endpoint=True)
                value = row.get("values", {}).get("close")
                if reason:
                    break
                if value is None:
                    reason = "missing_close"
                    break
                try:
                    value = Fraction(decimal_value(value))
                except NumericError:
                    reason = "invalid_close"
                    break
                if value <= 0:
                    reason = "nonpositive_close"
                    break
                values.append(value)
            if reason is None:
                change = values[1] / values[0] - 1
        records.append(dict(source_date=day, kind="current" if day == source_date else "history",
                            start=start, end=end, unknown_clock_ordinals=unknown_clock,
                            reason=reason, change=None if change is None else signed_fraction(change),
                            magnitude=None if change is None else signed_fraction(abs(change))))
    manifest = context.get("manifest", {})
    result = dict(method_id=METHOD_ID, snapshot_id=query["snapshot_id"], batch_id=query["batch_id"],
                  query_id=query["query_id"], context_query_id=context["query_id"],
                  raw_sha256=manifest.get("raw_sha256"), versions=manifest.get("versions"),
                  metadata=context["metadata"], contract=manifest.get("contract"),
                  batch_checks=context.get("batch_checks", []),
                  source_date=source_date, start_clock=start_clock, end_clock=end_clock,
                  as_of_label=as_of, lookback=5, nominal_minutes=minutes,
                  history_dates=history_dates, window_status=status, unknown_date_ordinals=unknown,
                  missing_history_dates=None if unknown else 5 - len(history_dates),
                  assumption="same_price_scale_between_endpoints",
                  qualification="retrospective_source_endpoint_arithmetic",
                  display_policy=dict(places=8, rounding="half_even"), days=records)
    result["history_id"] = _identity(result)
    if len(json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")) > MAX_RESPONSE_BYTES:
        raise ValueError("response_limit")
    return result
