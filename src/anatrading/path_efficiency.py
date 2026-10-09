"""Exact source close-path efficiency; no latent-noise or trading inference."""
from bisect import bisect_left
from decimal import Decimal
from fractions import Fraction

from .numeric import decimal_text, exact_sum
from .price_channel import _source_date
from .store import _identity
from .true_range import _price
from .volume_at_time import _fraction


_METHOD = "source-close-path-efficiency-v1"


def _member(day, rows):
    result = dict(date=day, ordinals=[row["ordinal"] for row in rows], close=None, reason=None)
    reason = "duplicate_date" if len(rows) != 1 else "unlocated_label" if rows[0]["label"] is None else None
    if reason:
        result["reason"] = reason
        return result
    values = rows[0]["values"]
    close, reason = _price(values.get("close"), "missing_close")
    high, _ = _price(values.get("high"), "missing_hl")
    low, _ = _price(values.get("low"), "missing_hl")
    if close is not None and high is not None and low is not None and low <= high and not low <= close <= high:
        reason = "close_outside_range"
    result.update(close=None if reason else decimal_text(close), reason=reason)
    return result


def efficiency_report(query, context, lookback=10):
    if type(lookback) is not int or not 2 <= lookback <= 252:
        raise ValueError("invalid_lookback")
    if query["snapshot_id"] != context["snapshot_id"]:
        raise ValueError("context_snapshot_mismatch")
    days, unreadable = {}, 0
    for row in (*context["rows"], *context["unlocated"]):
        day = _source_date(row)
        if day is None:
            unreadable += 1
        else:
            days.setdefault(day, []).append(row)
    dates = sorted(days)
    members = {day: _member(day, rows) for day, rows in days.items()}

    def calculate(row):
        result = dict(ordinal=row["ordinal"], window_dates=[], members=[], net_change=None,
                      path_length=None, direction=None, efficiency=None, reason=None)
        reason = "unsupported_period" if context["metadata"].get("period") != "1d" else (
            "unlocated_label" if row["label"] is None else None)
        if reason:
            result["reason"] = reason
            return result
        day = _source_date(row)
        position = bisect_left(dates, day)
        window = dates[max(0, position - lookback):position + 1]
        result.update(window_dates=window, members=[members[d] for d in window])
        reason = members[day]["reason"] or ("history_insufficient" if len(window) < lookback + 1 else None)
        reason = reason or next((members[d]["reason"] for d in window if members[d]["reason"]), None)
        if reason:
            result["reason"] = reason
            return result
        values = [Decimal(members[d]["close"]) for d in window]
        net = exact_sum((values[-1], values[0].copy_negate()))
        path = exact_sum(exact_sum((b, a.copy_negate())).copy_abs() for a, b in zip(values, values[1:]))
        ratio = Fraction(net.copy_abs()) / Fraction(path) if path else Fraction(0)
        result.update(net_change=decimal_text(net), path_length=decimal_text(path),
                      direction="up" if net > 0 else "down" if net < 0 else "flat",
                      efficiency=_fraction(ratio.numerator, ratio.denominator),
                      reason=None if path else "zero_path_convention")
        return result

    identity = dict(method_id=_METHOD, query_id=query["query_id"], context_query_id=context["query_id"], lookback=lookback)
    return dict(**identity, efficiency_id=_identity(identity), qualification="conditional_source_values",
                lookback_unit="source_date_changes", flat_policy="zero_with_explicit_reason",
                assumptions=["constant_price_scale", "comparable_adjustment_basis"],
                unknowns=["calendar", "coverage", "bar_closure", "adjustment", "known_at", "intrabar_path"],
                unreadable_date_rows=unreadable, context_unlocated_rows=len(context["unlocated"]),
                display_policy=dict(places=4, rounding="half_even"),
                rows=[calculate(row) for row in query["rows"]],
                unlocated=[calculate(row) for row in query["unlocated"]])
