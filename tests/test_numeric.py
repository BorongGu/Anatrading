from decimal import Decimal, Inexact, InvalidOperation, ROUND_DOWN, localcontext

import pytest

from anatrading.numeric import (
    NumericError,
    decimal_text,
    decimal_value,
    exact_sum,
    integer_value,
)


MAX_DECIMAL_TEXT = "99999999999999999999.999999999999999999"
MAX_BIGINT = 9223372036854775807


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (MAX_DECIMAL_TEXT, MAX_DECIMAL_TEXT),
        (Decimal(MAX_DECIMAL_TEXT), MAX_DECIMAL_TEXT),
        ("-" + MAX_DECIMAL_TEXT, "-" + MAX_DECIMAL_TEXT),
        (99999999999999999999, "99999999999999999999"),
        ("0.000000000000000001", "0.000000000000000001"),
        ("1.2300000000000000000000", "1.23"),
        ("1.23e2", "123"),
        (Decimal("37.020000457763671875"), "37.020000457763671875"),
        (0, "0"),
        ("-0.000", "0"),
        ("0e-999999999", "0"),
    ],
)
def test_decimal_values_are_exact_at_default_precision(value, expected):
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_DOWN
        result = decimal_value(value)
    assert isinstance(result, Decimal)
    assert result == Decimal(expected)
    assert result.as_tuple() == Decimal(expected).as_tuple()


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (True, "numeric_type"),
        (False, "numeric_type"),
        (1.0, "numeric_type"),
        (None, "numeric_type"),
        (b"1", "numeric_type"),
        ("", "invalid_decimal"),
        ("1,000", "invalid_decimal"),
        ("bad", "invalid_decimal"),
        ("NaN", "nonfinite"),
        (Decimal("sNaN"), "nonfinite"),
        ("Infinity", "nonfinite"),
        ("-Infinity", "nonfinite"),
        ("1e20", "decimal_range"),
        ("-1e20", "decimal_range"),
        (10**20, "decimal_range"),
        ("1e999999999", "decimal_range"),
        ("1e-19", "decimal_scale"),
        ("1.0000000000000000001", "decimal_scale"),
        ("1.00000011920928955078125", "decimal_scale"),
    ],
)
def test_decimal_rejects_unrepresentable_values(value, code):
    with localcontext() as context:
        context.prec = 28
        with pytest.raises(NumericError) as caught:
            decimal_value(value)
    assert caught.value.code == code
    assert str(caught.value) == code


@pytest.mark.parametrize("parse", [decimal_value, integer_value])
def test_invalid_token_is_independent_of_the_callers_trap(parse):
    with localcontext() as context:
        context.traps[InvalidOperation] = False
        with pytest.raises(NumericError, match="invalid_decimal"):
            parse("bad")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, 0),
        ("-0.000", 0),
        ("1.0000", 1),
        (Decimal("1e3"), 1000),
        (9007199254740991, 9007199254740991),
        (9007199254740992, 9007199254740992),
        ("9007199254740993", 9007199254740993),
        (Decimal("9223372036854775807"), MAX_BIGINT),
        (MAX_BIGINT, MAX_BIGINT),
    ],
)
def test_integer_values_are_exact(value, expected):
    result = integer_value(value)
    assert type(result) is int
    assert result == expected


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (True, "numeric_type"),
        (1.0, "numeric_type"),
        (None, "numeric_type"),
        ("", "invalid_decimal"),
        (Decimal("NaN"), "nonfinite"),
        ("Infinity", "nonfinite"),
        (-1, "integer_range"),
        (MAX_BIGINT + 1, "integer_range"),
        ("9223372036854775808", "integer_range"),
        ("1e999999999", "integer_range"),
        ("1.1", "integer_fraction"),
        (Decimal("1e-19"), "integer_fraction"),
    ],
)
def test_integer_rejects_inexact_or_out_of_range_values(value, code):
    with pytest.raises(NumericError) as caught:
        integer_value(value)
    assert caught.value.code == code


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal(MAX_DECIMAL_TEXT), MAX_DECIMAL_TEXT),
        (Decimal("1.2300000000000000000000"), "1.23"),
        (Decimal("0.00100"), "0.001"),
        (Decimal("1E+4"), "10000"),
        (1200, "1200"),
        (Decimal("-12.3000"), "-12.3"),
        (Decimal("-0.000"), "0"),
        (0, "0"),
        (100000000000000000000, "100000000000000000000"),
        (Decimal("1e-19"), "0.0000000000000000001"),
    ],
)
def test_decimal_text_is_fixed_point_without_rounding(value, expected):
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_DOWN
        assert decimal_text(value) == expected


@pytest.mark.parametrize("value", [True, 1.0, "1", None])
def test_decimal_text_rejects_unsupported_types(value):
    with pytest.raises(NumericError, match="numeric_type"):
        decimal_text(value)


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity")])
def test_decimal_text_rejects_nonfinite_values(value):
    with pytest.raises(NumericError, match="nonfinite"):
        decimal_text(value)


def test_exact_sum_empty_and_mixed_values():
    assert exact_sum([]) == Decimal("0")
    assert exact_sum(iter([Decimal("0.1"), Decimal("0.2"), 3])) == Decimal("3.3")


def test_exact_sum_can_exceed_the_single_value_column():
    with localcontext() as context:
        context.prec = 28
        result = exact_sum([Decimal(MAX_DECIMAL_TEXT), Decimal("1e-18")])
    assert isinstance(result, Decimal)
    assert result == Decimal("100000000000000000000")
    assert decimal_text(result) == "100000000000000000000"
    with pytest.raises(NumericError, match="decimal_range"):
        decimal_value(result)


def test_exact_sum_keeps_a_wide_integer_and_small_fraction():
    values = (value for value in [10**40, Decimal("0.000000000000000001")])
    assert exact_sum(values) == Decimal("10000000000000000000000000000000000000000.000000000000000001")


@pytest.mark.parametrize(
    "values",
    [
        [Decimal("1e128"), 1],
        [Decimal("9" * 128), 1],
        [Decimal("9e999999"), Decimal("9e999999")],
    ],
)
def test_exact_sum_rejects_inexact_and_rounded_only_results(values):
    with pytest.raises(NumericError, match="sum_precision"):
        exact_sum(values)


def test_exact_sum_reports_context_overflow():
    with pytest.raises(NumericError, match="sum_range"):
        exact_sum([Decimal("1e1000000")])


@pytest.mark.parametrize("value", [None, True, 1.0, "1"])
def test_exact_sum_never_silently_ignores_unsupported_values(value):
    with pytest.raises(NumericError, match="numeric_type"):
        exact_sum([Decimal("1"), value, Decimal("2")])


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("-Infinity")])
def test_exact_sum_rejects_nonfinite_inputs(value):
    with pytest.raises(NumericError, match="nonfinite"):
        exact_sum([value])


def test_exact_sum_uses_its_own_context_and_restores_the_caller():
    with localcontext() as context:
        context.prec = 28
        context.rounding = ROUND_DOWN
        context.Emax = 9
        context.flags[Inexact] = True
        flags = dict(context.flags)
        result = exact_sum([Decimal(MAX_DECIMAL_TEXT), Decimal("1e-18")])
        assert result == Decimal("1e20")
        assert context.prec == 28
        assert context.rounding == ROUND_DOWN
        assert context.Emax == 9
        assert dict(context.flags) == flags
