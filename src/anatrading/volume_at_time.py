"""Exact, retrospective comparisons of received source quantities at fixed clocks."""
from bisect import bisect_left
from datetime import date
from fractions import Fraction

from .numeric import NumericError, integer_value
from .store import _identity


_METHOD = "source-volume-at-time-v1"
# Observed in the real 600059 minute capture; exchange completeness is unverified.
_CLOCKS = tuple(f"{minute // 60:02d}:{minute % 60:02d}"
                for minute in (*range(571, 691), *range(781, 901)))


def _fraction(numerator, denominator):
    value = Fraction(numerator, denominator)
    rounded, remainder = divmod(value.numerator * 10000, value.denominator)
    if remainder * 2 > value.denominator or (remainder * 2 == value.denominator and rounded % 2):
        rounded += 1
    return dict(numerator=str(value.numerator), denominator=str(value.denominator),
                display=f"{rounded // 10000}.{rounded % 10000:04d}")


def _source_date(row):
    if row["label"] is not None:
        return row["label"][:10]
    token = row.get("tokens", {}).get("source_date") or row.get("tokens", {}).get("date")
    try:
        return date.fromisoformat(token.replace("/", "-") if isinstance(token, str) else token).isoformat()
    except (ValueError, TypeError):
        return None


def _quantity(rows):
    if not rows:
        return None, "missing_slot"
    if len(rows) != 1:
        return None, "duplicate_slot"
    value = rows[0]["values"].get("volume")
    if value is None:
        return None, "missing_quantity"
    try:
        return integer_value(value), None
    except NumericError:
        return None, "invalid_quantity"


def _comparison(current, history, dates, lookback):
    value, current_reason = current
    result = dict(current=None if value is None else str(value), baseline_sum=None,
                  baseline_mean=None, ratio=None, reason=None,
                  members=[dict(date=day, value=None if item[0] is None else str(item[0]), reason=item[1])
                           for day, item in zip(dates, history)])
    reason = current_reason or ("history_insufficient" if len(dates) < lookback else None)
    reason = reason or next((item[1] for item in history if item[1]), None)
    if reason:
        result["reason"] = reason
        return result
    total = sum(item[0] for item in history)
    result.update(baseline_sum=str(total), baseline_mean=_fraction(total, lookback))
    if total == 0:
        result["reason"] = "zero_baseline"
    else:
        result["ratio"] = _fraction(value * lookback, total)
    return result


def volume_report(query, context, lookback=20):
    if type(lookback) is not int or not 2 <= lookback <= 252:
        raise ValueError("invalid_lookback")
    if query["snapshot_id"] != context["snapshot_id"]:
        raise ValueError("context_snapshot_mismatch")
    days = {}
    for row in (*context["rows"], *context["unlocated"]):
        day = _source_date(row)
        if day is not None:
            slots = days.setdefault(day, {})
            if row["label"] is not None:
                slots.setdefault(row["label"][11:], []).append(row)
    dates = sorted(days)
    quantities, cumulative = {}, {}
    for day, slots in days.items():
        quantities[day], cumulative[day] = {}, {}
        total, prefix_reason = 0, None
        for clock in _CLOCKS:
            value, reason = _quantity(slots.get(clock, []))
            quantities[day][clock] = value, reason
            prefix_reason = prefix_reason or reason
            if prefix_reason is None:
                total += value
            cumulative[day][clock] = (total if prefix_reason is None else None), prefix_reason

    def calculate(row):
        result = dict(ordinal=row["ordinal"], history_dates=[], regular=None, cumulative=None, reason=None)
        if context["metadata"].get("period") != "1m":
            result["reason"] = "unsupported_period"
        elif row["label"] is None:
            result["reason"] = "unlocated_label"
        elif row["label"][11:] not in _CLOCKS:
            result["reason"] = "outside_observed_template"
        else:
            day, clock = row["label"][:10], row["label"][11:]
            position = bisect_left(dates, day)
            history = dates[max(0, position - lookback):position]
            result["history_dates"] = history
            for name, values in (("regular", quantities), ("cumulative", cumulative)):
                result[name] = _comparison(values[day][clock], [values[d][clock] for d in history], history, lookback)
        return result

    identity = dict(method_id=_METHOD, query_id=query["query_id"],
                    context_query_id=context["query_id"], lookback=lookback)
    return dict(**identity, volume_id=_identity(identity), qualification="conditional_source_values",
                template_id="observed-600059-240-clocks-v1", lookback_unit="observed_source_dates",
                assumptions=["constant_quantity_scale", "comparable_share_basis"],
                unknowns=["calendar", "coverage", "bar_closure", "quantity_unit", "share_basis", "known_at"],
                excluded_unlocated_rows=len(context["unlocated"]),
                outside_template_rows=sum(row["label"][11:] not in _CLOCKS for row in context["rows"]),
                display_policy=dict(places=4, rounding="half_even"),
                rows=[calculate(row) for row in query["rows"]],
                unlocated=[calculate(row) for row in query["unlocated"]])
