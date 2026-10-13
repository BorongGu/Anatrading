"""Exact fixed-20 source close dispersion, with certified numeric envelopes.

Pure descriptive report for a trusted full-prefix query. Source references are
claims already checked by its caller, never authentication of arbitrary input.
"""
from copy import deepcopy
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from math import isqrt

from .numeric import NumericError, decimal_text, decimal_value
from .pair_research import symbol_identity
from .research_series import MAX_RESEARCH_ROWS, daily_bars, daily_coverage, source_rejection, strict_date


_METHOD = 'source-close-dispersion20-population-v1'
_ADAPTER = 'daily-bars-strict-positive-v1'
_NUMERIC = 'integer-moments-isqrt36-v1'
_RESULTS = ('sum_u', 'sum_squares_u', 'dispersion_numerator', 'mean_exact',
            'variance_exact', 'sigma', 'envelope_lower', 'envelope_upper')


def _decimal(coefficient, exponent):
    # Tuple construction is exact even under hostile caller contexts; in
    # particular do not apply Decimal unary minus to a derived coefficient.
    return Decimal((int(coefficient < 0), tuple(map(int, str(abs(coefficient)))), exponent))


def _interval(lower, upper):
    """Closed numeric enclosure on a 1e-36 grid, not a confidence interval."""
    lo, hi = _decimal(lower, -36), _decimal(upper, -36)
    with localcontext(Context(prec=128, rounding=ROUND_HALF_EVEN)):
        left, right = (value.quantize(Decimal('0.0001')) for value in (lo, hi))
        agrees = left == right
        display = ('0.0000' if left.is_zero() else format(left, '.4f')) if agrees else None
    return dict(lower=decimal_text(lo), upper=decimal_text(hi), exact=lower == upper,
                display=display, display_reason=None if agrees else 'ambiguous_display_rounding')


def _units(value):
    number = decimal_value(value)
    if number < 0:
        raise NumericError('negative_price')
    if number.is_zero():
        return 0
    _, digits, exponent = number.as_tuple()
    coefficient = 0
    for digit in digits:
        coefficient = coefficient * 10 + digit
    return coefficient * 10**(exponent + 18)


def exact_window(closes):
    """Describe exactly twenty nonnegative DECIMAL(38,18) source prices.

    This mathematical domain includes zero; the report adapter separately
    preserves daily_bars' strict-positive, full-OHLC source qualification.
    """
    if not isinstance(closes, (list, tuple)) or len(closes) != 20:
        raise ValueError('invalid_window_length')
    units = [_units(value) for value in closes]
    total, squares = sum(units), sum(value * value for value in units)
    dispersion = 20 * squares - total * total
    if dispersion < 0:
        raise ArithmeticError('negative_dispersion_internal_failure')
    radicand = 25 * dispersion * 10**32
    lower = isqrt(radicand)
    upper = lower if lower * lower == radicand else lower + 1
    mean36 = 5 * total * 10**16
    return dict(sum_u=str(total), sum_squares_u=str(squares), dispersion_numerator=str(dispersion),
                mean_exact=decimal_text(_decimal(5 * total, -20)),
                variance_exact=decimal_text(_decimal(25 * dispersion, -40)),
                sigma=_interval(lower, upper),
                envelope_lower=_interval(mean36 - 2 * upper, mean36 - 2 * lower),
                envelope_upper=_interval(mean36 + 2 * lower, mean36 + 2 * upper))


def _request(query):
    if not isinstance(query, dict) or any(
        not isinstance(query.get(key), dict) for key in ('selection', 'metadata', 'manifest')
    ) or any(not isinstance(query.get(key), (list, tuple)) for key in ('rows', 'unlocated')):
        raise ValueError('invalid_dispersion_query')
    references = [query.get(key) for key in ('snapshot_id', 'batch_id', 'query_id')]
    references += [query['manifest'].get(key) for key in ('raw_sha256', 'source_contract_id')]
    if any(not isinstance(value, str) or not value for value in references) or query['selection'].get('mode') != 'retrospective':
        raise ValueError('invalid_dispersion_query')
    if len(query['rows']) + len(query['unlocated']) > MAX_RESEARCH_ROWS:
        raise ValueError('research_row_limit')
    return symbol_identity(query)


def _window_row(bars, position):
    """The single shared position projection for both public report shapes."""
    bar = bars[position]
    start = max(0, position - 19)
    window = bars[start:position + 1]
    invalid = [dict(position=start + offset, date=member['date'], ordinal=member['ordinal'], reason=member['reason'])
           for offset, member in enumerate(window) if member['reason'] is not None]
    reason = 'history_insufficient' if len(window) < 20 else 'invalid_window' if invalid else None
    result = dict.fromkeys(_RESULTS) if reason else exact_window([member['close'] for member in window])
    return dict(position=position, date=bar['date'], ordinal=bar['ordinal'],
               close=decimal_text(bar['close']) if bar['close'] is not None else None,
               source_reason=bar['reason'], window_start_position=start,
               window_end_position=position, window_count=len(window), invalid_members=invalid,
               status='unavailable' if reason else 'computed', reason=reason, **result)


def _header(query, symbol, coverage):
    identity = {key: query[key] for key in ('snapshot_id', 'batch_id', 'query_id')}
    identity.update({key: query['manifest'][key] for key in ('raw_sha256', 'source_contract_id')})
    identity.update(selection=deepcopy(query['selection']), symbol_identity=symbol,
                    source_qualification=deepcopy(query['manifest'].get('qualification')))
    return dict(identity=identity, method_id=_METHOD, adapter_id=_ADAPTER, numeric_policy_id=_NUMERIC,
                parameters=dict(window=20, current_inclusive=True, variance_divisor=20, sigma_multiplier=2),
                coverage=coverage,
                numeric_kind='exact_integer_moments_with_certified_decimal_enclosures',
                source_numeric_kind='exact_decimal_text',
                qualification=('source_rejected' if source_rejection(query) else
                               'conditional_source_observations' if coverage['coverage_known'] else 'source_coverage_unknown'),
                units=dict(mean='source_price', variance='source_price_squared', sigma='source_price', envelope='source_price'),
                limitations=['retrospective_source_version', 'calendar_and_coverage_unverified',
                             'adjustment_and_corporate_actions_unverified', 'historical_availability_unverified',
                             'close_finality_unverified', 'strict_positive_full_ohlc_adapter',
                             'fixed_engineering_parameters_not_calibrated', 'numeric_enclosures_not_probability_intervals',
                             'no_prediction_or_trading_return_claim'])


def dispersion_report(query):
    """Offline full report, retaining every original field and window."""
    symbol = _request(query)
    bars = daily_bars(query)
    return dict(**_header(query, symbol, daily_coverage(query, bars)),
                series=[_window_row(bars, position) for position in range(len(bars))])


def selected_dispersion_report(query, date=None):
    """One exact source date, or the latest group including invalid groups.

    Source normalization and coverage inspect the whole trusted prefix. Only
    the selected position is projected; no full historical report is built.
    """
    if date is not None:
        strict_date(date, 'invalid_research_date')
    symbol = _request(query)
    cutoff = query['selection'].get('cutoff')
    if date is not None and cutoff is not None and date > cutoff:
        raise ValueError('invalid_research_date')
    bars = daily_bars(query)
    position = (len(bars) - 1 if bars else None) if date is None else next(
        (i for i, bar in enumerate(bars) if bar['date'] == date), None)
    selected = _window_row(bars, position) if position is not None else None
    members = [] if selected is None else [
        dict(position=i, date=bars[i]['date'], ordinal=bars[i]['ordinal'],
             close=decimal_text(bars[i]['close']) if bars[i]['close'] is not None else None,
             source_reason=bars[i]['reason'])
        for i in range(selected['window_start_position'], position + 1)]
    return dict(**_header(query, symbol, daily_coverage(query, bars)),
                view_method_id='selected-source-close-dispersion20-v1',
                selection=dict(date_requested=date, resolved_date=selected['date'] if selected else None,
                               policy='latest_source_date' if date is None else 'exact_source_date'),
                selected=selected, members=members,
                status=selected['status'] if selected else 'unavailable',
                reason=selected['reason'] if selected else 'no_date_groups' if not bars else 'date_not_present')
