"""Bounded, causal cross-stock descriptions on exact common source dates.

The two regressions have different windows and meanings: price OLS uses only
prior prices; return OLS includes the current common-date interval. Neither
confers cointegration, trading or historical-availability qualification.
"""
from fractions import Fraction
import math
import re

from .numeric import decimal_text
from .research_series import daily_bars, daily_coverage


PRICE_VARIANCE_FLOOR = 1e-12
RETURN_VARIANCE_FLOOR = 1e-16
RESIDUAL_SCALE_FLOOR = 1e-10
_MARKETS = {'SH': 'CN_A', 'SZ': 'CN_A', 'BJ': 'CN_A', 'HK': 'HK',
            'NYSE': 'US', 'NASDAQ': 'US', 'AMEX': 'US'}
_VENUES = {'SSE': 'SH', 'XSHG': 'SH', 'SZSE': 'SZ', 'XSHE': 'SZ',
           'BSE': 'BJ', 'HKEX': 'HK', 'SEHK': 'HK', 'XHKG': 'HK',
           'XNAS': 'NASDAQ', 'XNYS': 'NYSE'}


def _venue(value):
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip().upper()
    return _VENUES.get(value, value)


def _claim(value, venue=None):
    """Parse declared syntax only; do not infer a venue from a numeric code."""
    venue = _venue(venue)
    if not isinstance(value, str) or not value.strip():
        return None, venue
    value = value.strip().upper()
    code, embedded = value, None
    parts = value.split('.')
    if len(parts) >= 2 and _venue(parts[-1]) in _MARKETS:
        code, embedded = '.'.join(parts[:-1]), _venue(parts[-1])
    elif len(parts) >= 2 and _venue(parts[0]) in _MARKETS:
        code, embedded = '.'.join(parts[1:]), _venue(parts[0])
    elif re.fullmatch(r'(SH|SZ|BJ)[0-9]{6}', value):
        code, embedded = value[2:], value[:2]
    if embedded is not None and venue is not None and embedded != venue:
        raise ValueError('research_identity_conflict')
    venue = embedded or venue
    if not re.fullmatch(r'[A-Z0-9][A-Z0-9.-]{0,31}', code):
        raise ValueError('research_identity_unavailable')
    if venue in {'SH', 'SZ', 'BJ'} and not re.fullmatch(r'[0-9]{6}', code):
        raise ValueError('research_identity_unavailable')
    return code, venue


def symbol_identity(query):
    """Normalize source/declaration claims while retaining their qualification."""
    metadata = query.get('metadata', {})
    declaration = metadata.get('interpretation', {})
    if not isinstance(declaration, dict):
        raise ValueError('research_identity_unavailable')
    source_code, source_venue = _claim(metadata.get('source_code'), metadata.get('source_venue'))
    declared_code, declared_venue = _claim(declaration.get('instrument'), declaration.get('venue'))
    if (source_code and declared_code and source_code != declared_code
            or source_venue and declared_venue and source_venue != declared_venue):
        raise ValueError('research_identity_conflict')
    code, venue = source_code or declared_code, source_venue or declared_venue
    if code is None:
        raise ValueError('research_identity_unavailable')
    if venue not in _MARKETS:
        raise ValueError('research_market_unknown')
    if venue in {'SH', 'SZ', 'BJ'} and not re.fullmatch(r'[0-9]{6}', code):
        raise ValueError('research_identity_unavailable')
    source = bool(source_code)
    declared = bool(declared_code or declared_venue and not source_venue)
    qualification = ('source_claim_and_declared' if source and declared else
                     'source_claim' if source else 'declared')
    return dict(symbol=f'{code}.{venue}', code=code, venue=venue,
                market=_MARKETS[venue], qualification=qualification)


def _log_close(bar):
    if bar['reason']:
        return None
    try:
        value = float(bar['close'])
        return math.log(value) if math.isfinite(value) and value > 0 else None
    except (ValueError, OverflowError, TypeError):
        return None


def _centered(values):
    mean = math.fsum(values) / len(values)
    centered = [value - mean for value in values]
    return mean, centered, math.fsum(value * value for value in centered)


def _return_statistics(x, y):
    """Independent metric reasons: a constant Y still permits a zero beta."""
    result = dict(return_correlation=None, return_beta=None,
                  correlation_reason=None, return_beta_reason=None)
    _, xc, xx = _centered(x)
    _, yc, yy = _centered(y)
    xy = math.fsum(a * b for a, b in zip(xc, yc))
    if not all(math.isfinite(v) for v in (xx, yy, xy)):
        result.update(correlation_reason='numerical_failure', return_beta_reason='numerical_failure')
        return result
    xsmall, ysmall = xx / (len(x) - 1) <= RETURN_VARIANCE_FLOOR, yy / (len(y) - 1) <= RETURN_VARIANCE_FLOOR
    if xsmall:
        result['return_beta_reason'] = 'return_variance_too_small'
    else:
        beta = xy / xx
        if math.isfinite(beta):
            result['return_beta'] = beta
        else:
            result['return_beta_reason'] = 'numerical_failure'
    if xsmall or ysmall:
        result['correlation_reason'] = 'return_variance_too_small'
    else:
        corr = xy / (math.sqrt(xx) * math.sqrt(yy))
        if not math.isfinite(corr) or abs(corr) > 1 + 1e-12:
            result['correlation_reason'] = 'numerical_failure'
        else:
            result['return_correlation'] = min(1.0, max(-1.0, corr))
    return result


def _price_statistics(x, y, current_x, current_y):
    result = dict(log_price_alpha=None, log_price_beta=None, residual_scale=None,
                  residual_deviation=None, price_regression_reason=None, deviation_reason=None)
    mx, xc, xx = _centered(x)
    my, yc, _ = _centered(y)
    if xx / (len(x) - 1) <= PRICE_VARIANCE_FLOOR:
        result.update(price_regression_reason='price_variance_too_small', deviation_reason='price_variance_too_small')
        return result
    beta = math.fsum(a * b for a, b in zip(xc, yc)) / xx
    alpha = my - beta * mx
    # Centered residuals avoid subtracting two large log-price intercept terms.
    sse = math.fsum((b - beta * a) ** 2 for a, b in zip(xc, yc))
    scale = math.sqrt(sse / (len(x) - 2))
    if not all(math.isfinite(v) for v in (alpha, beta, scale)):
        result.update(price_regression_reason='numerical_failure', deviation_reason='numerical_failure')
        return result
    result.update(log_price_alpha=alpha, log_price_beta=beta, residual_scale=scale)
    if current_x is None or current_y is None:
        result['deviation_reason'] = 'invalid_current_pair'
    elif scale <= RESIDUAL_SCALE_FLOOR:
        result['deviation_reason'] = 'residual_scale_too_small'
    else:
        deviation = ((current_y - my) - beta * (current_x - mx)) / scale
        if math.isfinite(deviation):
            result['residual_deviation'] = deviation
        else:
            result['deviation_reason'] = 'numerical_failure'
    return result


def pair_report(left_query, right_query, lookback=20):
    """Describe left (Y) against right (X); callers bind version/cutoff identity."""
    if type(lookback) is not int or not 5 <= lookback <= 252:
        raise ValueError('invalid_lookback')
    left_id, right_id = symbol_identity(left_query), symbol_identity(right_query)
    if left_id['symbol'] == right_id['symbol']:
        raise ValueError('research_duplicate_symbol')
    if left_query.get('snapshot_id') == right_query.get('snapshot_id'):
        raise ValueError('research_duplicate_snapshot')
    if left_id['market'] != right_id['market']:
        raise ValueError('research_market_mismatch')
    if left_query.get('selection', {}).get('cutoff') != right_query.get('selection', {}).get('cutoff'):
        raise ValueError('research_cutoff_mismatch')
    left, right = daily_bars(left_query), daily_bars(right_query)
    left_coverage, right_coverage = daily_coverage(left_query, left), daily_coverage(right_query, right)
    lm, rm = {b['date']: (i, b) for i, b in enumerate(left)}, {b['date']: (i, b) for i, b in enumerate(right)}
    dates = sorted(lm.keys() & rm.keys())
    coverage_known = left_coverage['coverage_known'] and right_coverage['coverage_known']
    paired, baseline, series = [], None, []
    # Each retained date is a slot, including invalid/duplicate pairs.
    for day in dates:
        li, lb = lm[day]
        ri, rb = rm[day]
        y, x = _log_close(lb), _log_close(rb)
        reason = lb['reason'] or rb['reason'] or ('numerical_failure' if x is None or y is None else None)
        if baseline is None and reason is None:
            baseline = dict(date=day, left_close=decimal_text(lb['close']), right_close=decimal_text(rb['close']))
        previous = paired[-1] if paired else None
        valid_return = previous is not None and reason is None and previous['reason'] is None
        skipped_l = li - previous['li'] - 1 if previous else 0
        skipped_r = ri - previous['ri'] - 1 if previous else 0
        paired.append(dict(x=x, y=y, reason=reason, li=li, ri=ri,
                           rx=x-previous['x'] if valid_return else None,
                           ry=y-previous['y'] if valid_return else None,
                           unequal=bool(skipped_l or skipped_r)))
        i = len(paired) - 1
        history = paired[max(0, i-lookback):i]
        returns = paired[max(1, i-lookback+1):i+1]
        coverage_window = paired[max(1, i-lookback+1):i+1]
        coverage_reason = ('date_set_integrity_unknown' if not coverage_known else
                           'unequal_source_coverage' if any(p['unequal'] for p in coverage_window) else None)
        row = dict(date=day, left_ordinal=lb['ordinal'], right_ordinal=rb['ordinal'],
                   reason=reason, return_start_date=dates[i-1] if previous else None,
                   left_log_return=paired[-1]['ry'], right_log_return=paired[-1]['rx'],
                   left_skipped_dates=skipped_l, right_skipped_dates=skipped_r,
                   n_prices=sum(p['reason'] is None for p in history),
                   n_returns=sum(p['rx'] is not None for p in returns),
                   price_start_date=dates[max(0, i-lookback)] if history else None,
                   price_end_date=dates[i-1] if history else None,
                   returns_start_date=dates[max(0, i-lookback)] if returns else None,
                   returns_end_date=day if returns else None, coverage_reason=coverage_reason,
                   return_correlation=None, return_beta=None, log_price_alpha=None, log_price_beta=None,
                   residual_scale=None, residual_deviation=None, relative_strength=None,
                   correlation_reason=None, return_beta_reason=None, price_regression_reason=None,
                   deviation_reason=None, relative_strength_reason=reason)
        if baseline is not None and reason is None:
            relative = (Fraction(lb['close']) * Fraction(baseline['right_close'])
                        / (Fraction(rb['close']) * Fraction(baseline['left_close'])) - 1)
            try:
                value = float(relative)
                if math.isfinite(value):
                    row['relative_strength'] = value
                else:
                    row['relative_strength_reason'] = 'numerical_failure'
            except OverflowError:
                row['relative_strength_reason'] = 'numerical_failure'
        elif reason is None:
            row['relative_strength_reason'] = 'baseline_unavailable'
        price_reason = ('history_insufficient' if len(history) < lookback else
                        'invalid_price_window' if any(p['reason'] for p in history) else None)
        if price_reason:
            row.update(price_regression_reason=price_reason, deviation_reason=reason or price_reason)
        else:
            row.update(_price_statistics([p['x'] for p in history], [p['y'] for p in history], x, y))
        returns_reason = ('history_insufficient' if len(returns) < lookback else
                          'invalid_return_window' if any(p['rx'] is None for p in returns) else None)
        if returns_reason:
            row.update(correlation_reason=returns_reason, return_beta_reason=returns_reason)
        else:
            row.update(_return_statistics([p['rx'] for p in returns], [p['ry'] for p in returns]))
        series.append(row)
    return dict(series=series, alignment=dict(left=left_coverage, right=right_coverage,
                left_only_dates=len(lm.keys() - rm.keys()), right_only_dates=len(rm.keys() - lm.keys()),
                common_dates=len(dates), valid_common_dates=sum(p['reason'] is None for p in paired),
                coverage_known=coverage_known), roles=dict(left=left_id, right=right_id),
                regression_direction='left_Y_on_right_X', baseline=baseline,
                parameters=dict(lookback=lookback, price_variance_floor=PRICE_VARIANCE_FLOOR,
                                return_variance_floor=RETURN_VARIANCE_FLOOR, residual_scale_floor=RESIDUAL_SCALE_FLOOR),
                estimate_type='float64', return_unit='common_source_date_interval',
                price_window_includes_current=False, return_window_includes_current=True,
                qualification='conditional_located_source_values',
                units=dict(log_price_beta='log_price_elasticity', return_beta='common_interval_return_beta',
                           residual_scale='log_price', residual_deviation='prior_residual_scale_multiple',
                           relative_strength='relative_normalized_price_change'))
