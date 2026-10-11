"""Same-cutoff selected-sample descriptions without inferred sector membership."""
from fractions import Fraction
import math

from .pair_research import symbol_identity
from .research_series import daily_bars, daily_coverage, strict_date


_METRICS = ('momentum', 'volatility', 'max_drawdown')


def _float_fraction(value):
    try:
        estimate = float(value)
        return (estimate, None) if math.isfinite(estimate) else (None, 'numerical_failure')
    except (OverflowError, ValueError):
        return None, 'numerical_failure'


def _volatility(prices):
    try:
        floats = [float(price) for price in prices]
        if any(not math.isfinite(p) or p <= 0 for p in floats):
            return None, 'numerical_failure'
        logs = [math.log(p) for p in floats]
        returns = [b-a for a, b in zip(logs, logs[1:])]
        mean = math.fsum(returns) / len(returns)
        value = math.sqrt(math.fsum((r-mean)**2 for r in returns) / (len(returns)-1))
        return (value, None) if math.isfinite(value) else (None, 'numerical_failure')
    except (OverflowError, ValueError):
        return None, 'numerical_failure'


def _at_cutoff(query, cutoff):
    # Preserve every undatable row; only known later dates may be removed.
    def included(row):
        try:
            return strict_date(row.get('label')) <= cutoff
        except ValueError:
            return True
    rows = [row for row in query['rows'] if included(row)]
    return dict(query, rows=rows, selection=dict(query.get('selection', {}), cutoff=cutoff))


def universe_report(queries, cutoff, lookback=20):
    if type(lookback) is not int or not 2 <= lookback <= 252:
        raise ValueError('invalid_lookback')
    strict_date(cutoff, 'invalid_label_cutoff')
    if not isinstance(queries, (list, tuple)) or not 2 <= len(queries) <= 50:
        raise ValueError('research_invalid_member_count')
    identities = [symbol_identity(q) for q in queries]
    if len({item["market"] for item in identities}) != 1:
        raise ValueError("research_market_mismatch")
    if len({i['symbol'] for i in identities}) != len(identities):
        raise ValueError('research_duplicate_symbol')
    if len({q.get('snapshot_id') for q in queries}) != len(queries):
        raise ValueError('research_duplicate_snapshot')
    selected = [_at_cutoff(q, cutoff) for q in queries]
    if sum(len(q['rows']) + len(q.get('unlocated', [])) for q in selected) > 200000:
        raise ValueError('research_total_row_limit')
    members, exact_momenta = [], {}
    for q, identity in zip(selected, identities):
        bars = daily_bars(q)
        coverage = daily_coverage(q, bars)
        target = bars[-1] if bars and bars[-1]['date'] == cutoff else None
        window = bars[-(lookback+1):] if target is not None else []
        row = dict(identity=identity, snapshot_id=q.get('snapshot_id'),
                   cutoff_present=target is not None, cutoff_valid=target is not None and target['reason'] is None,
                   start_date=window[0]['date'] if window else None, end_date=cutoff,
                   n_prices=sum(b['reason'] is None for b in window), n_returns=0,
                   rank=None, coverage=coverage)
        reason = ('cutoff_missing' if target is None else target['reason'] or
                  ('history_insufficient' if len(window) < lookback+1 else
                   next((b['reason'] for b in window if b['reason']), None)))
        for metric in _METRICS:
            row[metric], row[metric+'_reason'] = None, reason
        row['n_returns'] = sum(a['reason'] is None and b['reason'] is None for a, b in zip(window, window[1:]))
        if reason is None:
            prices = [b['close'] for b in window]
            momentum = Fraction(prices[-1]) / Fraction(prices[0]) - 1
            row['momentum'], row['momentum_reason'] = _float_fraction(momentum)
            if row['momentum'] is not None:
                exact_momenta[identity['symbol']] = momentum
            row['volatility'], row['volatility_reason'] = _volatility(prices)
            peak, drawdown = prices[0], Fraction(0)
            for price in prices:
                peak = max(peak, price)
                drawdown = min(drawdown, Fraction(price) / Fraction(peak) - 1)
            row['max_drawdown'], row['max_drawdown_reason'] = _float_fraction(drawdown)
        members.append(row)
    # Rank exact source ratios, so binary rounding cannot create false ties.
    members.sort(key=lambda r: (r['momentum'] is None,
                               -exact_momenta.get(r['identity']['symbol'], Fraction(0)),
                               r['identity']['symbol']))
    previous, rank = None, None
    for position, row in enumerate(members, 1):
        if row['momentum'] is None:
            continue
        value = exact_momenta[row['identity']['symbol']]
        if previous is None or value != previous:
            rank = position
        row['rank'], previous = rank, value
    n = len(members)
    counts = {}
    for metric in _METRICS:
        count = dict(eligible=0, missing=0, invalid=0, short_history=0)
        for row in members:
            reason = row[metric+'_reason']
            category = ('eligible' if row[metric] is not None else 'missing' if reason == 'cutoff_missing'
                        else 'short_history' if reason == 'history_insufficient' else 'invalid')
            count[category] += 1
        counts[metric] = count
    positive = sum(m > 0 for m in exact_momenta.values())
    zero = sum(m == 0 for m in exact_momenta.values())
    negative = sum(m < 0 for m in exact_momenta.values())
    valid = counts['momentum']['eligible']
    present, cutoff_valid = sum(r['cutoff_present'] for r in members), sum(r['cutoff_valid'] for r in members)
    breadth = dict(selected=n, cutoff_present=present, cutoff_valid=cutoff_valid,
                   momentum_valid=valid, volatility_valid=counts['volatility']['eligible'],
                   max_drawdown_valid=counts['max_drawdown']['eligible'],
                   positive=positive, zero=zero, negative=negative,
                   positive_momentum_fraction=positive / valid if valid else None,
                   momentum_coverage=valid / n, cutoff_coverage=cutoff_valid / n,
                   coverage_unknown=sum(not r['coverage']['coverage_known'] for r in members), metrics=counts)
    return dict(members=members, breadth=breadth, cutoff=cutoff,
                parameters=dict(lookback=lookback, volatility_ddof=1), estimate_type='float64',
                window_unit='source_date_groups', window_price_count=lookback+1,
                membership='selected_sample_no_historical_sector_inference',
                qualification='conditional_located_source_values',
                units=dict(momentum='source_close_change', volatility='log_return_per_source_interval',
                           max_drawdown='nonpositive_close_path_drawdown'),
                ranking='momentum_descending_competition_then_symbol')
