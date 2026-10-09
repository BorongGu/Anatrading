"""Source true ranges and Wilder smoothing with directed numerical bounds."""
from decimal import Context, Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_EVEN, localcontext

from .numeric import NumericError, decimal_text, decimal_value, exact_sum
from .price_channel import _source_date
from .store import _identity


_METHOD = "source-wilder-range-v1"
_ROUNDINGS = (ROUND_HALF_EVEN, ROUND_FLOOR, ROUND_CEILING)


def _price(value, missing):
    if value is None:
        return None, missing
    try:
        number = decimal_value(value)
    except NumericError:
        return None, "invalid_price"
    return (None, "negative_price") if number < 0 else (number, None)


def _bar(rows):
    result = dict(ordinals=[row["ordinal"] for row in rows], high=None, low=None, close=None,
                  range_reason=None, close_reason=None)
    reason = "duplicate_date" if len(rows) != 1 else "unlocated_label" if rows[0]["label"] is None else None
    if reason:
        result.update(range_reason=reason, close_reason=reason)
        return result
    values = rows[0]["values"]
    high, high_reason = _price(values.get("high"), "missing_hl")
    low, low_reason = _price(values.get("low"), "missing_hl")
    close, close_reason = _price(values.get("close"), "missing_close")
    range_reason = high_reason or low_reason or ("invalid_hl" if low > high else None)
    if close is not None and ((high is not None and close > high) or (low is not None and close < low)):
        close_reason = "close_outside_range"
    result.update(high=high, low=low, close=close, range_reason=range_reason, close_reason=close_reason)
    return result


def _divide(numerator, denominator, rounding):
    with localcontext(Context(prec=64, rounding=rounding)):
        return numerator / denominator


def _step(previous, current, period):
    values = []
    for value, rounding in zip(previous, _ROUNDINGS):
        with localcontext(Context(prec=64, rounding=rounding)):
            values.append(((period - 1) * value + current) / period)
    return tuple(values)


def _estimate(values):
    value, lower, upper = values
    with localcontext(Context(prec=128, rounding=ROUND_HALF_EVEN)):
        low_display, high_display = [format(v.quantize(Decimal("0.0001")), "f") for v in (lower, upper)]
    return dict(value=decimal_text(value), lower=decimal_text(lower), upper=decimal_text(upper),
                display=low_display if low_display == high_display else None,
                display_reason=None if low_display == high_display else "ambiguous_display_rounding")


def _empty(row):
    return dict(ordinal=row["ordinal"], previous_date=None, previous_ordinals=[],
                components=dict(high_low=None, high_previous_close=None, low_previous_close=None),
                tr=None, tr_reason=None, atr=None, atr_reason="history_insufficient", atr_blocked_date=None,
                prior_atr=None, tr_over_prior_atr=None, ratio_reason="prior_atr_unavailable")


def range_report(query, context, period=14):
    if type(period) is not int or not 1 <= period <= 252:
        raise ValueError("invalid_period")
    if query["snapshot_id"] != context["snapshot_id"]:
        raise ValueError("context_snapshot_mismatch")
    days, unreadable, excluded = {}, 0, 0
    cutoff = context.get("selection", {}).get("cutoff")
    for row in (*context["rows"], *context["unlocated"]):
        day = _source_date(row)
        if day is None:
            unreadable += 1
        elif row["label"] is None and cutoff is not None and day > cutoff[:10]:
            excluded += 1
        else:
            days.setdefault(day, []).append(row)
    dates = sorted(days)
    bars = {day: _bar(rows) for day, rows in days.items()}
    results, seed, seed_dates = {}, [], []
    previous_atr, blocked_date = None, None
    if context["metadata"].get("period") == "1d":
        for index, day in enumerate(dates):
            bar = bars[day]
            result = _empty(days[day][0])
            previous_day = dates[index-1] if index else None
            previous_bar = bars[previous_day] if previous_day is not None else None
            result.update(previous_date=previous_day, previous_ordinals=previous_bar["ordinals"] if previous_bar else [],
                          prior_atr=_estimate(previous_atr) if previous_atr is not None else None)
            reason = bar["range_reason"]
            if not reason:
                result["components"]["high_low"] = decimal_text(exact_sum((bar["high"], bar["low"].copy_negate())))
                reason = "no_previous_date" if previous_bar is None else (
                    "previous_" + previous_bar["close_reason"] if previous_bar["close_reason"] else None)
            result["tr_reason"] = reason
            current = None
            if reason is None:
                for key, value in (("high_previous_close", bar["high"]), ("low_previous_close", bar["low"])):
                    result["components"][key] = decimal_text(exact_sum((value, previous_bar["close"].copy_negate())).copy_abs())
                current = max(Decimal(value) for value in result["components"].values())
                result["tr"] = decimal_text(current)
            if index:
                if reason:
                    blocked_date = blocked_date or day
                if blocked_date:
                    previous_atr = None
                    result.update(atr_reason="invalid_history", atr_blocked_date=blocked_date)
                else:
                    if previous_atr is None:
                        seed.append(current)
                        seed_dates.append(day)
                        if len(seed) == period:
                            total = exact_sum(seed)
                            previous_atr = tuple(_divide(total, period, rounding) for rounding in _ROUNDINGS)
                    else:
                        previous_atr = _step(previous_atr, current, period)
                    if previous_atr is not None:
                        result.update(atr=_estimate(previous_atr), atr_reason=None)
            if reason:
                result["ratio_reason"] = reason
            elif result["prior_atr"] is not None:
                prior = result["prior_atr"]
                if Decimal(prior["upper"]) == 0:
                    result["ratio_reason"] = "zero_prior_atr"
                elif Decimal(prior["lower"]) <= 0:
                    result["ratio_reason"] = "prior_atr_not_positive"
                else:
                    values = tuple(_divide(current, Decimal(prior[key]), rounding) for key, rounding in
                                   (("value", ROUND_HALF_EVEN), ("upper", ROUND_FLOOR), ("lower", ROUND_CEILING)))
                    result.update(tr_over_prior_atr=_estimate(values), ratio_reason=None)
            results[day] = result

    def selected(row):
        result = _empty(row)
        if context["metadata"].get("period") != "1d":
            result.update(tr_reason="unsupported_period", atr_reason="unsupported_period", ratio_reason="unsupported_period")
        elif row["label"] is None:
            result.update(tr_reason="unlocated_label", atr_reason="unlocated_label", ratio_reason="unlocated_label")
        else:
            result = dict(results[_source_date(row)], ordinal=row["ordinal"])
        return result

    identity = dict(method_id=_METHOD, query_id=query["query_id"], context_query_id=context["query_id"], period=period)
    return dict(**identity, range_id=_identity(identity), qualification="conditional_source_values",
                predecessor_policy="previous_readable_source_date", first_tr="undefined_without_previous_close",
                seed_policy="first_period_subsequent_tr_mean", invalid_history_policy="no_implicit_reseed",
                seed_previous_date=dates[0] if dates else None, seed_dates=seed_dates,
                assumptions=["constant_price_scale", "comparable_adjustment_basis"],
                unknowns=["calendar", "coverage", "bar_closure", "adjustment", "known_at"],
                numerical_policy=dict(significant_digits=64, estimate_rounding="half_even", bounds="directed_each_operation",
                                      bounds_meaning="numerical_error_only", display_places=4, display_rounding="half_even_if_endpoints_agree"),
                unreadable_date_rows=unreadable, context_unlocated_rows=len(context["unlocated"]), excluded_after_cutoff_unlocated=excluded,
                rows=[selected(row) for row in query["rows"]], unlocated=[selected(row) for row in query["unlocated"]])
