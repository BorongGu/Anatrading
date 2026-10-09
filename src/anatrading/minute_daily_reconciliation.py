"""Retrospective source arithmetic, without unit or coverage certification."""
from collections import Counter
from decimal import Decimal

from .numeric import NumericError, decimal_text, decimal_value, exact_sum, integer_value
from .price_channel import _source_date
from .store import _identity
from .volume_at_time import _CLOCKS


def _field(row, field):
    value = row["values"].get(field)
    if value is None:
        return None, "missing_field"
    try:
        value = integer_value(value) if field == "volume" else decimal_value(value)
        if value < 0:
            return None, "invalid_field"
        return value, None
    except NumericError:
        return None, "invalid_field"


def _groups(query):
    days, unreadable = {}, []
    for row in (*query["rows"], *query["unlocated"]):
        day = _source_date(row)
        if day is None:
            unreadable.append(row["ordinal"])
        else:
            days.setdefault(day, []).append(row)
    for rows in days.values():
        rows.sort(key=lambda row: row["ordinal"])
    return days, unreadable


def _comparison(minute, daily, field, minute_reason, daily_reason, multiplier):
    minute_values = [_field(row, field) for row in minute]
    minute_reason = minute_reason or next((reason for _, reason in minute_values if reason), None)
    total = None if minute_reason else exact_sum(value for value, _ in minute_values)
    daily_value, field_reason = _field(daily[0], field) if not daily_reason else (None, None)
    daily_reason = daily_reason or field_reason
    difference = None
    if total is not None and daily_value is not None and multiplier is not None:
        # Only powers of ten are supported; tuple construction avoids ambient rounding.
        sign, digits, exponent = total.as_tuple()
        scaled = Decimal((sign, digits, exponent + (4 if multiplier == 10000 else 0)))
        difference = decimal_text(exact_sum((scaled, Decimal(daily_value).copy_negate())))
    return dict(selected_minute_sum=None if total is None else decimal_text(total),
                daily_source_value=None if daily_value is None else decimal_text(daily_value),
                difference=difference, minute_reason=minute_reason, daily_reason=daily_reason)


def reconciliation_report(minute_query, daily_query, amount_multiplier=None):
    if amount_multiplier is not None and (type(amount_multiplier) is not int or amount_multiplier not in {1, 10000}):
        raise ValueError("invalid_amount_multiplier")
    if minute_query["metadata"].get("period") != "1m" or daily_query["metadata"].get("period") != "1d":
        raise ValueError("background_period_mismatch")
    minutes, minute_unknown = _groups(minute_query)
    daily, daily_unknown = _groups(daily_query)
    days = []
    for day, rows in sorted(minutes.items()):
        clocks = Counter(row["label"][11:] for row in rows if row["label"] is not None)
        unlocated = [row["ordinal"] for row in rows if row["label"] is None]
        duplicates = sorted(clock for clock, count in clocks.items() if count > 1)
        minute_reason = ("date_membership_unknown" if minute_unknown else
                         "unlocated_clock" if unlocated else "duplicate_clock" if duplicates else None)
        daily_rows = daily.get(day, [])
        daily_reason = ("date_membership_unknown" if daily_unknown else "missing_date" if not daily_rows else
                        "duplicate_date" if len(daily_rows) != 1 else
                        "unlocated_date" if daily_rows[0]["label"] is None else None)
        days.append(dict(source_date=day, selected_count=len(rows), minute_ordinals=[row["ordinal"] for row in rows],
                         daily_ordinals=[row["ordinal"] for row in daily_rows],
                         coverage=dict(template_slots=len(_CLOCKS), observed_template_slots=len(set(clocks) & set(_CLOCKS)),
                                       missing_clocks=[clock for clock in _CLOCKS if clock not in clocks],
                                       extra_clocks=sorted(set(clocks) - set(_CLOCKS)), duplicate_clocks=duplicates,
                                       unlocated_clock_ordinals=unlocated),
                         quantity=_comparison(rows, daily_rows, "volume", minute_reason, daily_reason, 1),
                         amount=_comparison(rows, daily_rows, "amount", minute_reason, daily_reason, amount_multiplier)))
    identity = dict(method_id="selected-minute-daily-source-reconciliation-v1",
                    minute_query_id=minute_query["query_id"], daily_query_id=daily_query["query_id"],
                    amount_multiplier=amount_multiplier)
    return dict(**identity, reconciliation_id=_identity(identity),
                qualification="retrospective_source_arithmetic", pairing_status="assumed_text_match",
                minute_snapshot_id=minute_query["snapshot_id"], daily_snapshot_id=daily_query["snapshot_id"],
                minute_selection=minute_query["selection"], daily_selection=daily_query["selection"],
                template_id="observed-600059-240-clocks-v1", quantity_scale_status="assumed_common_scale",
                amount_scale_status="unselected" if amount_multiplier is None else "assumed_user_multiplier",
                difference_direction="selected_minute_sum_times_multiplier_minus_daily_source_value",
                unknowns=["quantity_unit", "amount_unit", "trade_coverage", "bar_closure", "known_at", "share_basis"],
                unreadable_minute_date_ordinals=minute_unknown, unreadable_daily_date_ordinals=daily_unknown, days=days)
