"""Synthetic cash/share rights only; no real-source qualification."""
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from fractions import Fraction

import pytest

from anatrading.conditional_return import (
    ConditionalReturnError, EX_DATE_CLOSE_REINVESTMENT, FIXED_SHARES_CASH,
    InputDeclaration, RawClose, StandardEvent, conditional_return_report,
)


def day(n):
    return date(2025, 1, n)


def prices(*values):
    return [RawClose(day(i + 1), str(value)) for i, value in enumerate(values)]


def event(n=2, cash="10", bonus="0", capital="0", payment=5, **changes):
    shares = Decimal(bonus) + Decimal(capital) != 0
    return replace(StandardEvent(
        event_id=f"synthetic-{n}", effective_date=day(n), cash_per_old_share=cash,
        bonus_per_old_share=bonus, capitalization_per_old_share=capital,
        payment_date=day(payment) if payment else None,
        shares_effective_date=day(n) if shares else None,
        shares_tradable_date=day(n) if shares else None,
        kind="ordinary_cash_and_share_distribution", entitlement="all_current_shares",
        evidence_ref="synthetic hand calculation",
    ), **changes)


def declaration(values):
    return InputDeclaration(
        security_id="synthetic-only", currency="CNY", start=values[0].day,
        end=values[-1].day, prices_unadjusted=True, events_complete=True,
        initial_no_unsettled_rights=True, price_evidence_ref="synthetic prices",
        event_evidence_ref="synthetic complete events",
    )


def run(values, events=(), method=FIXED_SHARES_CASH, **changes):
    return conditional_return_report(values, events, method=method,
                                     declaration=replace(declaration(values), **changes))


def near(actual, exact):
    assert abs(Fraction(actual) - Fraction(exact)) < Fraction(1, 10**46)


@pytest.mark.parametrize("changes", [
    {"kind": "rights_subscription"}, {"kind": None}, {"entitlement": "partial"},
    {"entitlement": None}, {"cash_per_old_share": None}, {"cash_per_old_share": -1},
    {"cash_per_old_share": "-1"}, {"cash_per_old_share": "NaN"},
    {"cash_per_old_share": "Infinity"}, {"cash_per_old_share": 0.1},
    {"cash_per_old_share": True}, {"bonus_per_old_share": "-1"},
    {"capitalization_per_old_share": "-1"}, {"payment_date": None},
    {"payment_date": day(1)}, {"payment_date": "2025-01-05"},
    {"shares_effective_date": day(2)}, {"shares_tradable_date": day(2)},
    {"effective_date": day(1)}, {"effective_date": day(5)},
    {"effective_date": datetime(2025, 1, 2)}, {"event_id": ""},
    {"evidence_ref": ""}, {"cash_per_old_share": "1e-19"},
    {"cash_per_old_share": "1e20"},
])
def test_invalid_events_fail_whole_request(changes):
    with pytest.raises(ConditionalReturnError) as error:
        run(prices(100, 90, 99), [event(**changes)])
    assert error.value.code and error.value.field


@pytest.mark.parametrize("changes", [
    {"prices_unadjusted": False}, {"prices_unadjusted": 1},
    {"events_complete": False}, {"initial_no_unsettled_rights": False},
    {"start": day(2)}, {"end": day(4)}, {"currency": ""},
    {"security_id": ""}, {"price_evidence_ref": ""}, {"event_evidence_ref": ""},
])
def test_no_implicit_declarations(changes):
    with pytest.raises(ConditionalReturnError):
        run(prices(100, 90, 99), [event()], **changes)


@pytest.mark.parametrize("value", [None, 1, True, 1.0, "0", "-1", "NaN", "1e20", "1e-19"])
def test_bad_price(value):
    with pytest.raises(ConditionalReturnError):
        run([RawClose(day(1), "100"), RawClose(day(2), value)])


def test_duplicate_unsorted_missing_and_empty_events_fail():
    values = prices(100, 90, 80)
    bad_sets = [
        [event(), event(3, event_id="synthetic-2")], [event(), event()],
        [event(3), event()], [event(cash="0", payment=None)],
        [event(cash="0")],
        [event(cash="0", bonus="1", payment=None, shares_tradable_date=day(3))],
    ]
    for events in bad_sets:
        with pytest.raises(ConditionalReturnError):
            run(values, events)
    with pytest.raises(ConditionalReturnError):
        run([values[0], values[2]], [event()])
    for invalid in [[values[1], values[0]], [values[0], values[0]]]:
        with pytest.raises(ConditionalReturnError):
            run(invalid)


def test_two_return_methods_diverge_after_cash_event():
    values = prices(100, 90, 99)
    fixed = run(values, [event()])
    reinvested = run(values, [event()], EX_DATE_CLOSE_REINVESTMENT)
    assert fixed["rows"][-1]["cumulative_return"] == Decimal(".09")
    near(reinvested["rows"][-1]["cumulative_return"], Fraction(1, 10))
    for report in [fixed, reinvested]:
        near(report["rows"][1]["wealth"], 100)
    assert fixed["rows"][-1]["receivables"] == 10
    assert fixed["rows"][-1]["cash"] == 0
    assert reinvested["rows"][-1]["cash"] is None
    assert reinvested["rows"][-1]["receivables"] is None


def test_consecutive_events_use_each_methods_own_old_shares():
    values = prices(100, 90, 80, 88)
    events = [event(), event(3)]
    fixed = run(values, events)
    reinvested = run(values, events, EX_DATE_CLOSE_REINVESTMENT)
    assert fixed["rows"][-1]["cumulative_return"] == Decimal(".08")
    near(reinvested["rows"][-1]["cumulative_return"], Fraction(1, 10))
    assert fixed["events"][1]["cash_entitlement"] == 10
    near(reinvested["events"][1]["cash_entitlement"], Fraction(100, 9))
    near(reinvested["rows"][-1]["shares"], Fraction(5, 4))


def test_cash_uses_old_shares_and_payment_does_not_use_later_shares():
    values = prices(100, 45, "22.5", "22.5", "22.5")
    events = [event(bonus=".5", capital=".5"),
              event(3, cash="0", bonus="1", payment=None)]
    result = run(values, events)
    assert result["events"][0]["cash_entitlement"] == 10
    assert result["rows"][1]["wealth"] == 100
    assert result["rows"][-1]["shares"] == 4
    assert result["rows"][-1]["cash"] == 10
    assert result["rows"][-1]["receivables"] == 0
    assert result["rows"][-1]["wealth"] == 100


def test_reverse_payment_order_and_days_without_quotes():
    values = [RawClose(day(i), str(p)) for i, p in [(1, 100), (2, 90), (3, 81), (5, 81), (7, 81)]]
    events = [event(payment=6), event(3, cash="9", payment=4)]
    fixed = run(values, events)
    rows = fixed["rows"]
    assert (rows[2]["cash"], rows[2]["receivables"]) == (0, 19)
    assert (rows[3]["cash"], rows[3]["receivables"]) == (9, 10)
    assert (rows[4]["cash"], rows[4]["receivables"]) == (19, 0)
    assert rows[3]["payments"][0]["payment_date"] == day(4)
    assert all(row["wealth"] == 100 for row in rows)
    reinvested = run(values, events, EX_DATE_CLOSE_REINVESTMENT)
    assert reinvested["rows"][2]["shares"] == reinvested["rows"][-1]["shares"]
    assert all(not row["payments"] for row in reinvested["rows"])


@pytest.mark.parametrize("method", [FIXED_SHARES_CASH, EX_DATE_CLOSE_REINVESTMENT])
def test_future_append_does_not_rewrite_past(method):
    old = prices(100, 90, 90)
    full = prices(100, 90, 90, 40, 44)
    first = event(payment=5)
    before = run(old, [first], method)
    after = run(full, [first, event(4, cash="10", bonus="1", payment=4)], method)
    assert before["rows"] == after["rows"][:len(old)]
    assert before["events"] == after["events"][:1]


def test_same_day_payment_and_split_retains_price_loss():
    fixed = run(prices(100, 45), [event(bonus="1", payment=2)])
    assert fixed["rows"][-1]["cash"] == 10
    assert fixed["rows"][-1]["receivables"] == 0
    assert fixed["rows"][-1]["wealth"] == 100
    for method in [FIXED_SHARES_CASH, EX_DATE_CLOSE_REINVESTMENT]:
        result = run(prices(100, 48), [event(cash="0", bonus="1", payment=None)], method)
        assert result["rows"][-1]["cumulative_return"] == Decimal("-.04")


def test_no_events_single_point_and_explicit_decimal_context():
    for method in [FIXED_SHARES_CASH, EX_DATE_CLOSE_REINVESTMENT]:
        assert run(prices(100), method=method)["rows"][0]["cumulative_return"] == 0
        assert run(prices(100, 101), method=method)["rows"][-1]["cumulative_return"] == Decimal(".01")
    values, events = prices(100, 90, 80, 88), [event(), event(3)]
    normal = run(values, events, EX_DATE_CLOSE_REINVESTMENT)
    with localcontext() as context:
        context.prec = 3
        context.rounding = ROUND_DOWN
        context.Emax, context.Emin = 2, -2
        context.traps[Inexact] = True
        assert run(values, events, EX_DATE_CLOSE_REINVESTMENT) == normal
    assert normal["numeric_context"]["precision"] == 50
    assert normal["numeric_context"]["rounding"] == "ROUND_HALF_EVEN"


def test_bad_method_and_missing_price_rows_fail():
    with pytest.raises(ConditionalReturnError):
        run(prices(100), method="total_return")
    with pytest.raises(ConditionalReturnError):
        conditional_return_report([], [], declaration=declaration(prices(100)),
                                  method=FIXED_SHARES_CASH)


@pytest.mark.parametrize("field", ["prices", "events"])
def test_input_count_limit_is_checked_before_processing(field):
    values, events = prices(100), []
    if field == "prices":
        values *= 20_001
    else:
        events = [event()] * 20_000
    with pytest.raises(ConditionalReturnError) as error:
        run(values, events)
    assert error.value.code == "input_limit"
    assert error.value.field == field


def test_decimal_boundaries_keep_exact_input_value():
    values = [RawClose(day(1), Decimal("99999999999999999999.999999999999999999")),
              RawClose(day(2), "0.000000000000000001")]
    result = run(values)
    assert result["rows"][0]["close"] == values[0].close
    assert result["rows"][1]["close"] == Decimal(values[1].close)


@pytest.mark.parametrize("first_payment, lost_balance", [(7, "receivables"), (2, "cash")])
def test_unrepresentable_frozen_rights_sum_fails_instead_of_losing_small_right(first_payment, lost_balance):
    values = prices(100, 100, 100, 100, 100, 100)
    events = [event(cash="1e-18", payment=first_payment),
              event(3, cash="0", bonus="9999999999999999999", payment=None),
              event(4, cash="0", bonus="9999999999999999999", payment=None),
              event(5, cash="1e19", payment=6)]
    with pytest.raises(ConditionalReturnError) as error:
        run(values, events)
    assert error.value.code == "arithmetic_resolution"
    assert error.value.field.endswith(lost_balance)
