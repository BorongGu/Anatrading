"""Prior-date source price ranges, without path or trading inference."""
from bisect import bisect_left
from datetime import date

from .candle_geometry import geometry_row
from .numeric import decimal_text, decimal_value, exact_sum
from .store import _identity


_METHOD = "prior-source-price-channel-v1"


def _source_date(row):
    if row["label"] is not None:
        return row["label"][:10]
    token = row.get("tokens", {}).get("source_date") or row.get("tokens", {}).get("date")
    if isinstance(token, str) and len(token) == 8 and token.isascii() and token.isdigit():
        token = f"{token[:4]}-{token[4:6]}-{token[6:]}"
    try:
        return date.fromisoformat(token.replace("/", "-") if isinstance(token, str) else token).isoformat()
    except (ValueError, TypeError):
        return None


def _member(day, rows):
    result = dict(date=day, ordinals=[row["ordinal"] for row in rows], high=None, low=None, reason=None)
    if len(rows) != 1:
        result["reason"] = "duplicate_date"
    elif rows[0]["label"] is None:
        result["reason"] = "unlocated_label"
    else:
        result["reason"] = geometry_row(rows[0])["reason"]
        if result["reason"] is None:
            result.update(high=decimal_text(decimal_value(rows[0]["values"]["high"])),
                          low=decimal_text(decimal_value(rows[0]["values"]["low"])))
    return result


def channel_report(query, context, lookback=20):
    if type(lookback) is not int or not 2 <= lookback <= 252:
        raise ValueError("invalid_lookback")
    if query["snapshot_id"] != context["snapshot_id"]:
        raise ValueError("context_snapshot_mismatch")
    days = {}
    unreadable = 0
    for row in (*context["rows"], *context["unlocated"]):
        day = _source_date(row)
        if day is None:
            unreadable += 1
        else:
            days.setdefault(day, []).append(row)
    dates = sorted(days)
    members = {day: _member(day, rows) for day, rows in days.items()}

    def calculate(row):
        result = dict(ordinal=row["ordinal"], history_dates=[], members=[], upper=None, lower=None,
                      width=None, range_relation=None, close_relation=None, touch_upper=None,
                      touch_lower=None, reason=None, comparison_reason=None)
        if context["metadata"].get("period") != "1d":
            result["reason"] = "unsupported_period"
            return result
        if row["label"] is None:
            result["reason"] = "unlocated_label"
            return result
        day = _source_date(row)
        position = bisect_left(dates, day)
        history = dates[max(0, position - lookback):position]
        result.update(history_dates=history, members=[members[d] for d in history])
        result["reason"] = ("history_insufficient" if len(history) < lookback else
                            next((members[d]["reason"] for d in history if members[d]["reason"]), None))
        if result["reason"]:
            return result
        upper = max(decimal_value(members[d]["high"]) for d in history)
        lower = min(decimal_value(members[d]["low"]) for d in history)
        result.update(upper=decimal_text(upper), lower=decimal_text(lower),
                      width=decimal_text(exact_sum((upper, lower.copy_negate()))))
        result["comparison_reason"] = members[day]["reason"]
        if result["comparison_reason"]:
            return result
        high, low, close = [decimal_value(row["values"][key]) for key in ("high", "low", "close")]
        above, below = high > upper, low < lower
        result.update(range_relation="both" if above and below else "upper_only" if above else "lower_only" if below else "neither",
                      close_relation="above" if close > upper else "below" if close < lower else
                      "touch_both" if close == upper == lower else "touch_upper" if close == upper else
                      "touch_lower" if close == lower else "inside",
                      touch_upper=high == upper, touch_lower=low == lower)
        return result

    identity = dict(method_id=_METHOD, query_id=query["query_id"], context_query_id=context["query_id"], lookback=lookback)
    return dict(**identity, channel_id=_identity(identity), qualification="conditional_source_values",
                lookback_unit="readable_source_dates", assumptions=["constant_price_scale", "comparable_adjustment_basis"],
                unknowns=["calendar", "coverage", "bar_closure", "adjustment", "known_at", "intrabar_path"],
                unreadable_date_rows=unreadable, context_unlocated_rows=len(context["unlocated"]),
                rows=[calculate(row) for row in query["rows"]],
                unlocated=[calculate(row) for row in query["unlocated"]])
