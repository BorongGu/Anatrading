"""Exact source values and explicitly bounded decimal arithmetic."""

from collections.abc import Iterable
from decimal import (
    Context,
    Decimal,
    Inexact,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Rounded,
    localcontext,
)


class NumericError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _number(value: str | Decimal | int, *, allow_text: bool) -> Decimal:
    allowed = (str, Decimal, int) if allow_text else (Decimal, int)
    if isinstance(value, bool) or not isinstance(value, allowed):
        raise NumericError("numeric_type")
    try:
        number = Decimal(value, context=Context(traps=[InvalidOperation]))
    except InvalidOperation as error:
        raise NumericError("invalid_decimal") from error
    if not number.is_finite():
        raise NumericError("nonfinite")
    return number


def decimal_value(value: str | Decimal | int) -> Decimal:
    """Accept only values exactly representable as DECIMAL(38,18)."""
    number = _number(value, allow_text=True)
    if number.is_zero():
        return Decimal(0)
    sign, digits, exponent = number.as_tuple()
    end = len(digits)
    while digits[end - 1] == 0:
        end -= 1
        exponent += 1
    digits = digits[:end]
    if exponent < -18:
        raise NumericError("decimal_scale")
    if len(digits) + exponent > 20:
        raise NumericError("decimal_range")
    return Decimal((sign, digits, exponent))


def integer_value(value: str | Decimal | int) -> int:
    """Accept an exact nonnegative signed-64-bit integer."""
    number = _number(value, allow_text=True)
    if number < 0 or number > 9223372036854775807:
        raise NumericError("integer_range")
    if number != number.to_integral_value():
        raise NumericError("integer_fraction")
    return int(number)


def decimal_text(value: Decimal | int) -> str:
    """Render exact values, including wider summaries, without exponent notation."""
    number = _number(value, allow_text=False)
    if number.is_zero():
        return "0"
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def exact_sum(values: Iterable[Decimal | int]) -> Decimal:
    """Sum in order; reject any rounded intermediate result or context overflow."""
    context = Context(
        prec=128,
        rounding=ROUND_HALF_EVEN,
        traps=[Inexact, Rounded, Overflow, InvalidOperation],
    )
    try:
        with localcontext(context):
            total = Decimal(0)
            for value in values:
                total += _number(value, allow_text=False)
            return total
    except Overflow as error:
        raise NumericError("sum_range") from error
    except (Inexact, Rounded) as error:
        raise NumericError("sum_precision") from error
