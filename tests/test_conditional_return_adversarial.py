"""Independent, synthetic-only share/cash oracles for the conditional core."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta
from decimal import (
    Context, Decimal, DivisionByZero, FloatOperation, Inexact, InvalidOperation,
    Overflow, ROUND_FLOOR, Rounded, Underflow, getcontext, localcontext,
)
from fractions import Fraction
from math import prod

import pytest

from anatrading.conditional_return import (
    ConditionalReturnError, EX_DATE_CLOSE_REINVESTMENT, FIXED_SHARES_CASH,
    InputDeclaration, RawClose, StandardEvent, conditional_return_report,
)


ORIGIN = date(2026, 1, 1)
METHODS = (FIXED_SHARES_CASH, EX_DATE_CLOSE_REINVESTMENT)
UNSET = object()


def day(offset):
    return ORIGIN + timedelta(days=offset)


def prices_at(items):
    return [RawClose(day(offset), close) for offset, close in items]


def declaration(prices):
    return InputDeclaration(
        security_id="SYNTHETIC-EQUITY", currency="CNY",
        start=prices[0].day, end=prices[-1].day,
        prices_unadjusted=True, events_complete=True,
        initial_no_unsettled_rights=True,
        price_evidence_ref="independent synthetic prices",
        event_evidence_ref="independent synthetic complete event list",
    )


def event(offset, *, event_id=None, cash="1", bonus="0", capital="0", pay=UNSET):
    payment = (day(offset) if Fraction(cash) else None) if pay is UNSET else (
        None if pay is None else day(pay))
    shares_day = day(offset) if Fraction(bonus) + Fraction(capital) else None
    return StandardEvent(
        event_id=event_id or f"synthetic-event-{offset}", effective_date=day(offset),
        cash_per_old_share=cash, bonus_per_old_share=bonus,
        capitalization_per_old_share=capital, payment_date=payment,
        shares_effective_date=shares_day, shares_tradable_date=shares_day,
        kind="ordinary_cash_and_share_distribution",
        entitlement="all_current_shares", evidence_ref="synthetic event, not market evidence",
    )


def run(prices, events, method, stated=None):
    return conditional_return_report(
        prices, events, declaration=stated or declaration(prices), method=method,
    )


def close_to_fraction(actual, expected):
    assert isinstance(actual, Decimal)
    assert actual.is_finite()
    # A small independent arithmetic check; no product rounding/helper reuse.
    assert abs(Fraction(actual) - expected) <= Fraction(1, 10**43) * max(1, abs(expected))


def check_closed_form(prices, events, method, result):
    """Products and independently accrued amounts, not the product state loop."""
    close = {point.day: Fraction(point.close) for point in prices}
    multipliers = {
        item.event_id: 1 + Fraction(item.bonus_per_old_share)
        + Fraction(item.capitalization_per_old_share) for item in events
    }
    initial = Fraction(prices[0].close)
    assert len(result["rows"]) == len(prices)
    for point, row in zip(prices, result["rows"], strict=True):
        active = [item for item in events if item.effective_date <= point.day]
        fixed_amounts = {
            item.event_id: Fraction(item.cash_per_old_share) * prod(
                multipliers[prior.event_id] for prior in events
                if prior.effective_date < item.effective_date
            ) for item in active
        }
        if method == FIXED_SHARES_CASH:
            shares = Fraction(prod(multipliers[item.event_id] for item in active))
            cash = sum((fixed_amounts[item.event_id] for item in active
                        if item.payment_date is not None and item.payment_date <= point.day), Fraction(0))
            due = sum((fixed_amounts[item.event_id] for item in active
                       if item.payment_date is not None and item.payment_date > point.day), Fraction(0))
            close_to_fraction(row["cash"], cash)
            close_to_fraction(row["receivables"], due)
        else:
            shares = Fraction(prod(
                multipliers[item.event_id] + Fraction(item.cash_per_old_share)
                / close[item.effective_date] for item in active
            ))
            cash = due = Fraction(0)
            assert row["cash"] is None and row["receivables"] is None
            assert row["payments"] == []
        stock_value = shares * close[point.day]
        wealth = stock_value + cash + due
        assert row["day"] == point.day
        close_to_fraction(row["close"], close[point.day])
        close_to_fraction(row["shares"], shares)
        close_to_fraction(row["stock_value"], stock_value)
        close_to_fraction(row["wealth"], wealth)
        close_to_fraction(row["cumulative_return"], wealth / initial - 1)


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("closes, actions", [
    ([(0, "100"), (1, "90"), (2, "99")], [event(1, cash="10", pay=5)]),
    ([(0, "100"), (1, "90"), (2, "80"), (3, "88")],
     [event(1, cash="10", pay=5), event(2, cash="10", pay=4)]),
    ([(0, "10"), (1, "4.5"), (2, "5")], [event(1, cash="1", bonus="1")]),
    ([(0, "100"), (1, "48")], [event(1, cash="0", bonus="1")]),
    ([(0, "10"), (1, "9.7"), (2, "9.9")], [event(1, cash="0.30")]),
    ([(0, "10.25"), (2, "10.5"), (7, "8.75")], []),
    ([(0, "10")], []),
])
def test_independent_rational_paths(method, closes, actions):
    prices = prices_at(closes)
    result = run(prices, actions, method)
    check_closed_form(prices, actions, method, result)


@pytest.mark.parametrize("method, expected", [
    (FIXED_SHARES_CASH, Fraction(9, 100)),
    (EX_DATE_CLOSE_REINVESTMENT, Fraction(1, 10)),
])
def test_dividend_reference_day_does_not_hide_later_method_difference(method, expected):
    prices = prices_at([(0, "100"), (1, "90"), (2, "99")])
    rows = run(prices, [event(1, cash="10")], method)["rows"]
    close_to_fraction(rows[1]["cumulative_return"], Fraction(0))
    close_to_fraction(rows[2]["cumulative_return"], expected)


def test_reverse_and_missing_quote_payment_dates_do_not_revalue_rights():
    prices = prices_at([(0, "20"), (1, "9"), (2, "8"), (4, "8"), (6, "8")])
    actions = [event(1, cash="2", bonus="1", pay=5), event(2, cash="1", pay=3)]
    result = run(prices, actions, FIXED_SHARES_CASH)
    check_closed_form(prices, actions, FIXED_SHARES_CASH, result)
    rows = result["rows"]
    assert rows[2]["receivables"] == 4
    assert (rows[3]["cash"], rows[3]["receivables"]) == (2, 2)
    assert (rows[4]["cash"], rows[4]["receivables"]) == (4, 0)
    # No fabricated quote/valuation on payment days 3 or 5.
    assert [row["day"] for row in rows] == [point.day for point in prices]
    assert len(rows[3]["payments"]) == len(rows[4]["payments"]) == 1


def test_same_day_old_payment_and_new_combined_event_use_old_shares_once():
    prices = prices_at([(0, "20"), (1, "19"), (2, "9"), (3, "10")])
    actions = [event(1, cash="1", pay=2), event(2, cash="1", bonus="1", pay=2)]
    result = run(prices, actions, FIXED_SHARES_CASH)
    check_closed_form(prices, actions, FIXED_SHARES_CASH, result)
    assert result["rows"][2]["cash"] == 2
    assert result["rows"][2]["receivables"] == 0
    assert len(result["rows"][2]["payments"]) == 2


def test_unrepresentable_pending_sum_is_rejected_before_small_right_disappears():
    prices = prices_at([(i, "1") for i in range(6)])
    large = "99999999999999999999"
    actions = [
        event(1, cash="0.000000000000000001", pay=10),
        event(2, cash="0", bonus=large), event(3, cash="0", bonus=large),
        event(4, cash=large, pay=5),
    ]
    with pytest.raises(ConditionalReturnError) as caught:
        run(prices, actions, FIXED_SHARES_CASH)
    assert caught.value.code == "arithmetic_resolution"


def test_immediately_paid_large_right_preserves_small_unpaid_right():
    prices = prices_at([(i, "1") for i in range(6)])
    large = "99999999999999999999"
    actions = [
        event(1, cash="0.000000000000000001", pay=10),
        event(2, cash="0", bonus=large), event(3, cash="0", bonus=large),
        event(4, cash=large, pay=4),
    ]
    result = run(prices, actions, FIXED_SHARES_CASH)
    check_closed_form(prices, actions, FIXED_SHARES_CASH, result)
    assert result["rows"][4]["receivables"] == Decimal("1e-18")
    assert len(result["rows"][4]["payments"]) == 1


def test_due_history_is_paid_before_new_event_adds_an_unrelated_receivable():
    prices = prices_at([(i, "1") for i in range(6)])
    large = "99999999999999999999"
    actions = [
        event(1, cash="0.000000000000000001", pay=4),
        event(2, cash="0", bonus=large), event(3, cash="0", bonus=large),
        event(4, cash=large, pay=10),
    ]
    result = run(prices, actions, FIXED_SHARES_CASH)
    check_closed_form(prices, actions, FIXED_SHARES_CASH, result)
    assert result["rows"][4]["cash"] == Decimal("1e-18")
    assert len(result["rows"][4]["payments"]) == 1


def test_second_reinvested_distribution_has_its_own_share_basis():
    prices = prices_at([(0, "100"), (1, "90"), (2, "80"), (3, "88")])
    actions = [event(1, cash="10", pay=3), event(2, cash="10", pay=4)]
    fixed = run(prices, actions, FIXED_SHARES_CASH)
    reinvested = run(prices, actions, EX_DATE_CLOSE_REINVESTMENT)
    close_to_fraction(fixed["rows"][2]["event"]["cash_entitlement"], Fraction(10))
    close_to_fraction(reinvested["rows"][2]["event"]["cash_entitlement"], Fraction(100, 9))
    close_to_fraction(fixed["rows"][-1]["cumulative_return"], Fraction(2, 25))
    close_to_fraction(reinvested["rows"][-1]["cumulative_return"], Fraction(1, 10))


@pytest.mark.parametrize("method", METHODS)
def test_future_events_and_payments_cannot_mutate_past_rows(method):
    prefix = prices_at([(0, "10"), (1, "9"), (2, "10")])
    actions = [event(1, cash="1", pay=5)]
    before = run(prefix, actions, method)
    frozen = deepcopy(before)
    extended = prefix + prices_at([(4, "8"), (6, "8.5")])
    result = run(extended, actions + [event(4, cash="2", pay=6)], method)
    assert before == frozen
    assert result["rows"][:len(prefix)] == frozen["rows"]


@pytest.mark.parametrize("method", METHODS)
def test_caller_context_and_input_mutation_cannot_change_result(method):
    prices = prices_at([(0, "100"), (1, "90"), (2, "80"), (3, "88")])
    actions = [event(1, cash="10", pay=3), event(2, cash="10", pay=4)]
    stated = declaration(prices)
    originals = deepcopy((prices, actions, stated))
    expected = run(prices, actions, method, stated)
    hostile = Context(prec=3, rounding=ROUND_FLOOR, Emin=-3, Emax=3,
                      traps=[Inexact, Rounded, Overflow, Underflow, InvalidOperation,
                             DivisionByZero, FloatOperation])
    with localcontext(hostile):
        old_flags = getcontext().flags.copy()
        actual = run(prices, actions, method, stated)
        assert getcontext().flags == old_flags
    assert actual == expected
    assert (prices, actions, stated) == originals
    actual["rows"][0]["shares"] = Decimal("999")
    assert run(prices, actions, method, stated) == expected


@pytest.mark.parametrize("bad_close", [
    "0", "-1", "NaN", "Infinity", "1e20", "1e-19", "not-a-price",
    True, 10, 10.5, None,
])
def test_bad_prices_are_not_silently_coerced(bad_close):
    prices = prices_at([(0, "10"), (1, bad_close)])
    with pytest.raises(ConditionalReturnError) as caught:
        run(prices, [], FIXED_SHARES_CASH)
    assert caught.value.code and caught.value.field


@pytest.mark.parametrize("changes", [
    {"kind": "rights_issue"}, {"entitlement": "some_shares"},
    {"cash_per_old_share": "-0.1"}, {"cash_per_old_share": 1},
    {"cash_per_old_share": True}, {"cash_per_old_share": "NaN"},
    {"bonus_per_old_share": "-1"}, {"capitalization_per_old_share": "Infinity"},
    {"payment_date": None}, {"payment_date": day(0)},
    {"event_id": ""}, {"evidence_ref": ""},
    {"effective_date": day(0)}, {"effective_date": day(7)},
    {"effective_date": datetime(2026, 1, 2)},
    {"shares_effective_date": day(1)},
    {"cash_per_old_share": "0"},
])
def test_bad_event_is_whole_call_failure(changes):
    prices = prices_at([(0, "10"), (1, "9"), (2, "8")])
    actions = [replace(event(1), **changes)]
    with pytest.raises(ConditionalReturnError) as caught:
        run(prices, actions, FIXED_SHARES_CASH)
    assert caught.value.code and caught.value.field


@pytest.mark.parametrize("changes", [
    {"shares_effective_date": day(2)}, {"shares_tradable_date": day(2)},
    {"shares_effective_date": None}, {"shares_tradable_date": None},
    {"payment_date": day(1)},
])
def test_delayed_or_ambiguous_share_eligibility_is_rejected(changes):
    prices = prices_at([(0, "10"), (1, "5"), (2, "5")])
    action = replace(event(1, cash="0", bonus="1"), **changes)
    with pytest.raises(ConditionalReturnError):
        run(prices, [action], FIXED_SHARES_CASH)


@pytest.mark.parametrize("changes", [
    {"prices_unadjusted": False}, {"events_complete": False},
    {"initial_no_unsettled_rights": False}, {"events_complete": 1},
    {"start": day(1)}, {"end": day(3)}, {"security_id": ""},
    {"currency": ""}, {"price_evidence_ref": ""}, {"event_evidence_ref": ""},
])
def test_declarations_are_required_not_inferred(changes):
    prices = prices_at([(0, "10"), (1, "9"), (2, "8")])
    stated = replace(declaration(prices), **changes)
    with pytest.raises(ConditionalReturnError):
        run(prices, [], FIXED_SHARES_CASH, stated)


@pytest.mark.parametrize("kind", ["duplicate_price", "reverse_prices", "missing_event_close",
                                   "duplicate_id", "duplicate_date", "reverse_events"])
def test_order_and_identity_are_not_repaired(kind):
    prices = prices_at([(0, "10"), (1, "9"), (2, "8"), (4, "7")])
    actions = [event(1), event(2)]
    if kind == "duplicate_price":
        prices.insert(2, prices[1])
    elif kind == "reverse_prices":
        prices[1], prices[2] = prices[2], prices[1]
    elif kind == "missing_event_close":
        prices.pop(1)
    elif kind == "duplicate_id":
        actions[1] = replace(actions[1], event_id=actions[0].event_id)
    elif kind == "duplicate_date":
        actions[1] = replace(actions[1], effective_date=actions[0].effective_date)
    else:
        actions.reverse()
    with pytest.raises(ConditionalReturnError):
        run(prices, actions, FIXED_SHARES_CASH)


def test_unknown_method_and_empty_prices_fail_explicitly():
    prices = prices_at([(0, "10")])
    with pytest.raises(ConditionalReturnError):
        run(prices, [], "total_return")
    with pytest.raises(ConditionalReturnError):
        conditional_return_report([], [], declaration=declaration(prices), method=FIXED_SHARES_CASH)


def test_datetime_price_label_is_not_silently_treated_as_a_date():
    prices = prices_at([(0, "10"), (1, "9")])
    prices[1] = replace(prices[1], day=datetime(2026, 1, 2))
    with pytest.raises(ConditionalReturnError):
        run(prices, [], FIXED_SHARES_CASH)


def test_price_budget_rejects_before_computation():
    prices = [RawClose(day(i), "1") for i in range(20_001)]
    with pytest.raises(ConditionalReturnError):
        run(prices, [], FIXED_SHARES_CASH)
