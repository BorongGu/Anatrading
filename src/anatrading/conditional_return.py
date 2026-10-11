"""Conditional, retrospective wealth from explicitly caller-declared inputs.

No source certification, event parsing, I/O, or actual trading simulation. See
research 040 for the two distinct holdings rules and deliberately narrow scope.
Values are Decimal results rounded in a private 50-digit context, not exact
rationals. Dates are closing observation dates in one caller-declared currency.
"""
from dataclasses import asdict, dataclass
from datetime import date
from decimal import (
    Context, Decimal, DecimalException, DivisionByZero, Inexact, InvalidOperation,
    Overflow, ROUND_HALF_EVEN, localcontext,
)

from .numeric import NumericError, decimal_value


FIXED_SHARES_CASH = "fixed_shares_cash"
EX_DATE_CLOSE_REINVESTMENT = "ex_date_close_reinvestment"
MAX_PRICES = 20_000
MAX_EVENTS = 19_999
_KIND = "ordinary_cash_and_share_distribution"
_ENTITLEMENT = "all_current_shares"
_ZERO = Decimal(0)
_ONE = Decimal(1)


class ConditionalReturnError(ValueError):
    """One invalid request; no partial or silently event-filtered report."""

    def __init__(self, code: str, field: str):
        self.code, self.field = code, field
        super().__init__(f"{code}: {field}")


@dataclass(frozen=True)
class RawClose:
    day: date
    close: Decimal | str


@dataclass(frozen=True)
class StandardEvent:
    event_id: str
    effective_date: date
    cash_per_old_share: Decimal | str
    bonus_per_old_share: Decimal | str
    capitalization_per_old_share: Decimal | str
    payment_date: date | None
    shares_effective_date: date | None
    shares_tradable_date: date | None
    kind: str
    entitlement: str
    evidence_ref: str


@dataclass(frozen=True)
class InputDeclaration:
    security_id: str
    currency: str
    start: date
    end: date
    prices_unadjusted: bool
    events_complete: bool
    initial_no_unsettled_rights: bool
    price_evidence_ref: str
    event_evidence_ref: str


def _fail(code, field):
    raise ConditionalReturnError(code, field)


def _date(value, field):
    if type(value) is not date:
        _fail("invalid_date", field)
    return value


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        _fail("invalid_text", field)


def _number(value, field, *, positive=False):
    if not isinstance(value, (str, Decimal)):
        _fail("numeric_type", field)
    try:
        number = decimal_value(value)
    except NumericError as error:
        raise ConditionalReturnError(error.code, field) from error
    if number < 0 or (positive and number == 0):
        _fail("numeric_sign", field)
    return number


def _inputs(prices, events, declaration, method):
    if method not in (FIXED_SHARES_CASH, EX_DATE_CLOSE_REINVESTMENT):
        _fail("unsupported_method", "method")
    for values, field, limit in ((prices, "prices", MAX_PRICES), (events, "events", MAX_EVENTS)):
        if not isinstance(values, (tuple, list)):
            _fail("invalid_type", field)
        if len(values) > limit:
            _fail("input_limit", field)
    if not prices:
        _fail("empty_prices", "prices")
    if not isinstance(declaration, InputDeclaration):
        _fail("invalid_type", "declaration")
    for field in ("security_id", "currency", "price_evidence_ref", "event_evidence_ref"):
        _text(getattr(declaration, field), f"declaration.{field}")
    for field in ("prices_unadjusted", "events_complete", "initial_no_unsettled_rights"):
        if getattr(declaration, field) is not True:
            _fail("declaration_required", f"declaration.{field}")
    start = _date(declaration.start, "declaration.start")
    end = _date(declaration.end, "declaration.end")

    prepared_prices, price_days = [], set()
    previous = None
    for i, row in enumerate(prices):
        field = f"prices[{i}]"
        if not isinstance(row, RawClose):
            _fail("invalid_type", field)
        day = _date(row.day, f"{field}.day")
        if previous is not None and day <= previous:
            _fail("date_order", f"{field}.day")
        close = _number(row.close, f"{field}.close", positive=True)
        prepared_prices.append((day, close))
        price_days.add(day)
        previous = day
    if prepared_prices[0][0] != start or prepared_prices[-1][0] != end:
        _fail("coverage_mismatch", "declaration")

    prepared_events, ids = [], set()
    previous = None
    for i, event in enumerate(events):
        field = f"events[{i}]"
        if not isinstance(event, StandardEvent):
            _fail("invalid_type", field)
        _text(event.event_id, f"{field}.event_id")
        _text(event.evidence_ref, f"{field}.evidence_ref")
        if event.event_id in ids:
            _fail("duplicate_event_id", f"{field}.event_id")
        ids.add(event.event_id)
        if event.kind != _KIND:
            _fail("unsupported_event_kind", f"{field}.kind")
        if event.entitlement != _ENTITLEMENT:
            _fail("unsupported_entitlement", f"{field}.entitlement")
        day = _date(event.effective_date, f"{field}.effective_date")
        if not start < day <= end:
            _fail("event_outside_window", f"{field}.effective_date")
        if previous is not None and day <= previous:
            _fail("event_date_order", f"{field}.effective_date")
        if day not in price_days:
            _fail("missing_event_close", f"{field}.effective_date")
        previous = day
        cash, bonus, capital = (
            _number(getattr(event, name), f"{field}.{name}")
            for name in ("cash_per_old_share", "bonus_per_old_share", "capitalization_per_old_share")
        )
        if cash == bonus == capital == 0:
            _fail("empty_event", field)
        if cash:
            if _date(event.payment_date, f"{field}.payment_date") < day:
                _fail("payment_before_event", f"{field}.payment_date")
        elif event.payment_date is not None:
            _fail("unexpected_payment_date", f"{field}.payment_date")
        for name in ("shares_effective_date", "shares_tradable_date"):
            value = getattr(event, name)
            if bonus or capital:
                if _date(value, f"{field}.{name}") != day:
                    _fail("unsupported_share_timing", f"{field}.{name}")
            elif value is not None:
                _fail("unexpected_share_date", f"{field}.{name}")
        prepared_events.append((event, cash, bonus, capital))
    return prepared_prices, prepared_events


def _balance(total, change, field):
    """Do not lose a frozen entitlement when classifying cash or receivables."""
    try:
        with localcontext() as context:
            context.traps[Inexact] = True
            return total + change
    except Inexact as error:
        raise ConditionalReturnError("arithmetic_resolution", field) from error


def _calculate(prices, events, method):
    fixed = method == FIXED_SHARES_CASH
    shares, cash, receivables = _ONE, _ZERO, _ZERO
    pending = {}
    # Effective-date order does not imply payment order. Payment-only dates need
    # no price; their classification appears at the next observed closing date.
    schedule = sorted(((event.payment_date, event.event_id) for event, amount, _, _ in events
                       if amount and event.payment_date > event.effective_date),
                      key=lambda item: item[0]) if fixed else []
    payment_index = event_index = 0
    rows, ledger = [], []
    initial_value = prices[0][1]

    def settle(day):
        nonlocal payment_index, cash, receivables
        payments = []
        while payment_index < len(schedule):
            payment_date, event_id = schedule[payment_index]
            if payment_date > day:
                break
            amount = pending.pop(event_id)
            cash = _balance(cash, amount, f"events.{event_id}.cash")
            receivables = _balance(receivables, -amount, f"events.{event_id}.receivables")
            payments.append(dict(event_id=event_id, payment_date=payment_date, amount=amount))
            payment_index += 1
        return payments

    for day, close in prices:
        payments = settle(day)
        contribution = None
        if event_index < len(events) and events[event_index][0].effective_date == day:
            event, dividend, bonus, capital = events[event_index]
            before = shares
            entitlement = before * dividend
            base_shares = before * (_ONE + bonus + capital)
            reinvested = _ZERO if fixed else entitlement / close
            shares = base_shares + reinvested
            if fixed and dividend:
                if event.payment_date == day:
                    # Immediately settled rights need not be combined with old
                    # unpaid rights, which could create avoidable rounding.
                    cash = _balance(cash, entitlement, f"events.{event.event_id}.cash")
                    payments.append(dict(event_id=event.event_id, payment_date=day, amount=entitlement))
                else:
                    pending[event.event_id] = entitlement
                    receivables = _balance(receivables, entitlement, f"events.{event.event_id}.receivables")
            contribution = dict(
                event_id=event.event_id, effective_date=day, evidence_ref=event.evidence_ref,
                shares_before=before, shares_after=shares, cash_entitlement=entitlement,
                bonus_shares=before * bonus, capitalization_shares=before * capital,
                reinvested_shares=reinvested, payment_date=event.payment_date,
            )
            ledger.append(contribution)
            event_index += 1
        stock_value = shares * close
        wealth = stock_value + cash + receivables if fixed else stock_value
        rows.append(dict(
            day=day, close=close, shares=shares, stock_value=stock_value,
            cash=cash if fixed else None, receivables=receivables if fixed else None,
            wealth=wealth, cumulative_return=wealth / initial_value - _ONE,
            event=contribution, payments=payments,
        ))
    return rows, ledger


def conditional_return_report(prices, events, *, declaration, method):
    """Calculate one explicitly selected holdings rule or reject the request.

    Inputs are bounded lists/tuples, with strict dates and exact DECIMAL(38,18)
    strings/Decimals. No conversion of supplied source/event claims into verified
    facts occurs. Start at one share and zero unsettled rights; require exact
    declaration coverage. Every effective event must have a closing observation.

    Fixed holdings value each frozen right at pre-tax face value, zero interest,
    no default/revision. Reinvestment consumes it at the effective day's close,
    allows fractional shares and advance use of receivables, and ignores payment
    as a further wealth event. Neither path is a prediction or execution result.
    Fixed cash/receivable sums must retain their frozen amounts within 50 digits;
    otherwise the entire request fails with arithmetic_resolution. Share changes,
    reinvestment and wealth valuation retain the stated 50-digit rounding rule.
    """
    context = Context(prec=50, rounding=ROUND_HALF_EVEN, Emin=-999999, Emax=999999,
                      capitals=1, clamp=0, flags=[],
                      traps=[InvalidOperation, DivisionByZero, Overflow])
    try:
        with localcontext(context):
            prepared_prices, prepared_events = _inputs(prices, events, declaration, method)
            rows, ledger = _calculate(prepared_prices, prepared_events, method)
    except DecimalException as error:
        raise ConditionalReturnError("arithmetic_range", "calculation") from error
    return dict(
        method=method,
        numeric_context=dict(precision=50, rounding="ROUND_HALF_EVEN", Emin=-999999, Emax=999999),
        declaration=asdict(declaration),
        assumptions=dict(
            input_status="caller_declared_unverified", initial_shares=_ONE,
            taxes="zero", fees="zero", interest="zero", default="none",
            entitlement="all_current_shares", fractional_shares=True,
            receivable_valuation="pre_tax_face_value" if method == FIXED_SHARES_CASH else None,
            reinvestment="none" if method == FIXED_SHARES_CASH else "effective_date_close",
            advance_use_of_receivables=method == EX_DATE_CLOSE_REINVESTMENT,
        ),
        rows=rows, events=ledger,
    )
