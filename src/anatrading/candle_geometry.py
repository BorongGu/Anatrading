"""Exact single-bar source geometry, without cross-bar or trading inference."""
from fractions import Fraction

from .numeric import NumericError, decimal_text, decimal_value, exact_sum
from .store import _identity


_METHOD = "source-candle-geometry-v1"
_LENGTHS = ("range", "body", "upper_shadow", "lower_shadow")
_RATIOS = ("body", "upper_shadow", "lower_shadow", "close_location")


def _ratio(part, whole):
    value = Fraction(part) / Fraction(whole)
    numerator, denominator = value.numerator, value.denominator
    hundredths, remainder = divmod(numerator * 10000, denominator)
    if remainder * 2 > denominator or (remainder * 2 == denominator and hundredths % 2):
        hundredths += 1
    return dict(numerator=str(numerator), denominator=str(denominator),
                percent_display=f"{hundredths // 100}.{hundredths % 100:02d}")


def ohlc_values(row):
    """Validate the shared price bounds without calculating unused geometry ratios."""
    prices = [row["values"].get(key) for key in ("open", "high", "low", "close")]
    if any(value is None for value in prices):
        return None, "missing_ohlc"
    try:
        opening, high, low, close = [decimal_value(value) for value in prices]
    except NumericError:
        return None, "invalid_price"
    if any(value < 0 for value in (opening, high, low, close)):
        return None, "negative_price"
    if not (low <= opening <= high and low <= close <= high):
        return None, "invalid_ohlc"
    return (opening, high, low, close), None


def geometry_row(row):
    result = dict(ordinal=row["ordinal"], status="not_evaluated", reason=None, direction=None,
                  **dict.fromkeys(_LENGTHS), ratios=dict.fromkeys(_RATIOS), ratio_reason=None)
    prices, result["reason"] = ohlc_values(row)
    if result["reason"]:
        return result
    opening, high, low, close = prices
    lengths = dict(range=exact_sum((high, low.copy_negate())),
                   body=exact_sum((close, opening.copy_negate())).copy_abs(),
                   upper_shadow=exact_sum((high, max(opening, close).copy_negate())),
                   lower_shadow=exact_sum((min(opening, close), low.copy_negate())))
    result.update(status="computed", direction="up" if close > opening else "down" if close < opening else "equal",
                  **{key: decimal_text(value) for key, value in lengths.items()})
    if lengths["range"].is_zero():
        result["ratio_reason"] = "zero_range"
    else:
        parts = {key: lengths[key] for key in _RATIOS if key != "close_location"}
        parts["close_location"] = exact_sum((close, low.copy_negate()))
        result["ratios"] = {key: _ratio(value, lengths["range"]) for key, value in parts.items()}
    return result


def geometry_report(query):
    return dict(method_id=_METHOD, query_id=query["query_id"],
                geometry_id=_identity(dict(query_id=query["query_id"], method_id=_METHOD)),
                qualification="source_observation_description",
                source_qualification=query["manifest"]["qualification"],
                assumption="same_price_scale_within_row",
                display_policy=dict(percent_places=2, rounding="half_even"),
                rows=[geometry_row(row) for row in query["rows"]],
                unlocated=[geometry_row(row) for row in query["unlocated"]])
