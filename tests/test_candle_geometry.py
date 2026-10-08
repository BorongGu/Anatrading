"""Exact per-source-bar geometry; synthetic cases are mathematical boundaries only."""
from copy import deepcopy
from decimal import Decimal, Inexact, Rounded, ROUND_UP, localcontext
from fractions import Fraction

import pytest

from anatrading.candle_geometry import geometry_report, geometry_row
from anatrading.store import _identity


def source_row(opening="2", high="4", low="1", close="3", *, ordinal=1):
    return {"ordinal": ordinal, "values": {"open": opening, "high": high, "low": low,
                                            "close": close, "volume": "100", "amount": "300"}}


@pytest.mark.parametrize("field,value,reason", [
    ("open", None, "missing_ohlc"), ("close", None, "missing_ohlc"),
    ("open", True, "invalid_price"), ("open", 2.0, "invalid_price"),
    ("open", "NaN", "invalid_price"), ("open", "sNaN", "invalid_price"),
    ("open", "Infinity", "invalid_price"), ("open", Decimal("-Infinity"), "invalid_price"),
    ("open", "oops", "invalid_price"), ("open", "0.0000000000000000001", "invalid_price"),
    ("open", "100000000000000000000", "invalid_price"),
    ("low", "-1", "negative_price"), ("open", "-1", "negative_price"),
    ("high", "0", "invalid_ohlc"), ("low", "5", "invalid_ohlc"),
    ("open", "5", "invalid_ohlc"), ("close", "0", "invalid_ohlc"),
])
def test_invalid_prices_keep_source_and_clear_all_derived_values(field, value, reason):
    source = source_row()
    source["values"][field] = value
    before = deepcopy(source)
    result = geometry_row(source)
    assert result == {"ordinal": 1, "status": "not_evaluated", "reason": reason,
                      "direction": None, "range": None, "body": None, "upper_shadow": None,
                      "lower_shadow": None, "ratios": dict.fromkeys(
                          ("body", "upper_shadow", "lower_shadow", "close_location")),
                      "ratio_reason": None}
    assert source == before


def test_error_precedence_and_missing_key():
    source = source_row(opening="bad", low="-1", close=None)
    assert geometry_row(source)["reason"] == "missing_ohlc"
    source["values"]["close"] = "3"
    assert geometry_row(source)["reason"] == "invalid_price"
    source["values"]["open"] = "2"
    assert geometry_row(source)["reason"] == "negative_price"
    del source["values"]["high"]
    assert geometry_row(source)["reason"] == "missing_ohlc"


def ratio(numerator, denominator, percent):
    return {"numerator": str(numerator), "denominator": str(denominator), "percent_display": percent}


def test_thirds_hand_calculation_and_fixed_fields():
    result = geometry_row(source_row())
    assert result == {"ordinal": 1, "status": "computed", "reason": None, "direction": "up",
                      "range": "3", "body": "1", "upper_shadow": "1", "lower_shadow": "1",
                      "ratios": {"body": ratio(1, 3, "33.33"), "upper_shadow": ratio(1, 3, "33.33"),
                                 "lower_shadow": ratio(1, 3, "33.33"),
                                 "close_location": ratio(2, 3, "66.67")}, "ratio_reason": None}
    assert sum(Fraction(int(result["ratios"][name]["numerator"]),
                        int(result["ratios"][name]["denominator"]))
               for name in ("body", "upper_shadow", "lower_shadow")) == 1


@pytest.mark.parametrize("opening,high,low,close,direction,body,upper,lower,position", [
    ("3", "4", "1", "2", "down", "1", "1", "1", ratio(1, 3, "33.33")),
    ("2", "4", "1", "2", "equal", "0", "2", "1", ratio(1, 3, "33.33")),
    ("0", "3", "0", "3", "up", "3", "0", "0", ratio(1, 1, "100.00")),
    ("3", "3", "0", "0", "down", "3", "0", "0", ratio(0, 1, "0.00")),
])
def test_direction_zero_body_and_real_zero_prices(opening, high, low, close, direction, body, upper, lower, position):
    result = geometry_row(source_row(opening, high, low, close))
    assert result["status"] == "computed" and result["direction"] == direction
    assert (result["body"], result["upper_shadow"], result["lower_shadow"]) == (body, upper, lower)
    assert result["ratios"]["close_location"] == position
    for name in ("body", "upper_shadow", "lower_shadow"):
        if result[name] == "0":
            assert result["ratios"][name] == ratio(0, 1, "0.00")


@pytest.mark.parametrize("price", ["0", "2.5000", Decimal("99999999999999999999.999999999999999999")])
def test_zero_range_has_no_defined_ratios(price):
    result = geometry_row(source_row(price, price, price, price))
    assert result["status"] == "computed" and result["reason"] is None
    assert result["direction"] == "equal"
    assert [result[key] for key in ("range", "body", "upper_shadow", "lower_shadow")] == ["0"] * 4
    assert result["ratios"] == dict.fromkeys(("body", "upper_shadow", "lower_shadow", "close_location"))
    assert result["ratio_reason"] == "zero_range"


@pytest.mark.parametrize("numerator,expected", [(1, "0.00"), (3, "0.02"), (5, "0.02"), (7, "0.04"),
                                              (19997, "99.98"), (19999, "100.00")])
def test_percent_half_even_ties_without_adjustment(numerator, expected):
    result = geometry_row(source_row(0, 20000, 0, numerator))
    assert result["ratios"]["body"]["percent_display"] == expected
    assert result["ratios"]["close_location"]["percent_display"] == expected
    assert Fraction(int(result["ratios"]["body"]["numerator"]),
                    int(result["ratios"]["body"]["denominator"])) == Fraction(numerator, 20000)


@pytest.mark.parametrize("denominator,expected", [(19999, "0.01"), (20001, "0.00")])
def test_percent_rounding_each_side_of_half_cent(denominator, expected):
    result = geometry_row(source_row(0, denominator, 0, 1))
    assert result["ratios"]["body"] == ratio(1, denominator, expected)


def test_exact_max_precision_under_adversarial_decimal_context():
    source = source_row("99999999999999999999.999999999999999997",
                        "99999999999999999999.999999999999999999",
                        "99999999999999999999.999999999999999996",
                        "99999999999999999999.999999999999999998")
    with localcontext() as context:
        context.prec = 1
        context.Emin = -1
        context.Emax = 1
        context.rounding = ROUND_UP
        context.traps[Inexact] = True
        context.traps[Rounded] = True
        before = (context.prec, context.Emin, context.Emax, context.rounding,
                  dict(context.traps), dict(context.flags))
        result = geometry_row(source)
        assert result["range"] == "0.000000000000000003"
        assert [result[name] for name in ("body", "upper_shadow", "lower_shadow")] == ["0.000000000000000001"] * 3
        assert result["ratios"]["body"] == ratio(1, 3, "33.33")
        assert (context.prec, context.Emin, context.Emax, context.rounding,
                dict(context.traps), dict(context.flags)) == before


def test_ratio_integer_strings_keep_38_digit_denominator():
    result = geometry_row(source_row("0", "99999999999999999999.999999999999999999", "0", "0.000000000000000001"))
    assert result["ratios"]["body"] == ratio(1, "99999999999999999999999999999999999999", "0.00")
    assert result["ratios"]["lower_shadow"] == ratio(0, 1, "0.00")


def test_quantity_checks_do_not_block_exact_price_geometry():
    source = source_row()
    source["values"].update(volume=None, amount="-123")
    source["checks"] = [{"code": "volume_missing", "status": "conditional_failure"},
                        {"code": "amount_negative", "status": "conditional_failure"}]
    assert geometry_row(source) == geometry_row(source_row())


@pytest.mark.parametrize("prices,lengths", [
    (("14", "18", "12", "16"), ("6", "2", "2", "2")),
    ((Decimal("0.2"), Decimal("0.4"), Decimal("0.1"), Decimal("0.3")), ("0.3", "0.1", "0.1", "0.1")),
])
def test_common_positive_scaling_and_translation_preserve_ratios(prices, lengths):
    original = geometry_row(source_row())
    transformed = geometry_row(source_row(*prices))
    assert transformed["direction"] == original["direction"]
    assert transformed["ratios"] == original["ratios"]
    assert tuple(transformed[key] for key in ("range", "body", "upper_shadow", "lower_shadow")) == lengths


def test_report_preserves_scopes_source_qualification_and_identity_without_mutation():
    query = {"query_id": "a" * 64, "manifest": {"qualification": "source_semantics_incomplete"},
             "rows": [source_row(ordinal=3), source_row(ordinal=1)],
             "unlocated": [source_row(ordinal=2)]}
    before = deepcopy(query)
    report = geometry_report(query)
    assert set(report) == {"method_id", "query_id", "geometry_id", "qualification", "source_qualification",
                           "assumption", "display_policy", "rows", "unlocated"}
    assert report["method_id"] == "source-candle-geometry-v1"
    assert report["query_id"] == query["query_id"]
    assert report["geometry_id"] == _identity({"query_id": query["query_id"], "method_id": report["method_id"]})
    assert report["qualification"] == "source_observation_description"
    assert report["source_qualification"] == query["manifest"]["qualification"]
    assert report["assumption"] == "same_price_scale_within_row"
    assert report["display_policy"] == {"percent_places": 2, "rounding": "half_even"}
    assert [entry["ordinal"] for entry in report["rows"]] == [3, 1]
    assert [entry["ordinal"] for entry in report["unlocated"]] == [2]
    assert query == before
    future = deepcopy(query)
    future["query_id"] = "b" * 64
    future["rows"].append(source_row("999", "999", "999", "999", ordinal=4))
    future_report = geometry_report(future)
    assert future_report["rows"][:2] == report["rows"]
    assert future_report["unlocated"] == report["unlocated"]
    assert future_report["geometry_id"] != report["geometry_id"]
    source_version = deepcopy(query)
    source_version["query_id"] = "c" * 64
    assert geometry_report(source_version)["geometry_id"] not in (report["geometry_id"], future_report["geometry_id"])
