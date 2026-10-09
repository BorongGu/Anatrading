"""Current daily source quantity against strictly preceding source dates."""
from bisect import bisect_left

from .price_channel import _source_date
from .store import _identity
from .volume_at_time import _comparison, _quantity


_METHOD = "prior-source-daily-volume-v1"


def _daily_quantity(rows):
    if len(rows) != 1:
        return None, "duplicate_date"
    if rows[0]["label"] is None:
        return None, "unlocated_label"
    return _quantity(rows)


def daily_volume_report(query, context, lookback=20):
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
    quantities = {day: _daily_quantity(rows) for day, rows in days.items()}

    def calculate(row):
        reason = "unsupported_period" if context["metadata"].get("period") != "1d" else (
            "unlocated_label" if row["label"] is None else None)
        if reason:
            return dict(ordinal=row["ordinal"], history_dates=[],
                        **_comparison((None, reason), [], [], lookback))
        day = _source_date(row)
        position = bisect_left(dates, day)
        history = dates[max(0, position - lookback):position]
        return dict(ordinal=row["ordinal"], history_dates=history,
                    **_comparison(quantities[day], [quantities[d] for d in history], history, lookback))

    identity = dict(method_id=_METHOD, query_id=query["query_id"],
                    context_query_id=context["query_id"], lookback=lookback)
    return dict(**identity, volume_id=_identity(identity), qualification="conditional_source_values",
                lookback_unit="readable_source_dates",
                assumptions=["constant_quantity_scale", "comparable_share_basis"],
                unknowns=["calendar", "coverage", "bar_closure", "quantity_unit", "share_basis", "known_at"],
                unreadable_date_rows=unreadable, context_unlocated_rows=len(context["unlocated"]),
                display_policy=dict(places=4, rounding="half_even"),
                rows=[calculate(row) for row in query["rows"]],
                unlocated=[calculate(row) for row in query["unlocated"]])
