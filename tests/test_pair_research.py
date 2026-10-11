"""Cross-stock formulas, aligned intervals and explicit failure boundaries."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
import math

import pytest

from anatrading.pair_research import pair_report, symbol_identity


def query(prices, symbol='600001.SH', *, dates=None, snapshot=None):
    dates = dates or [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(len(prices))]
    return dict(snapshot_id=snapshot or symbol, query_id='q-' + symbol,
                metadata=dict(period='1d', source_code=symbol), unlocated=[],
                rows=[dict(ordinal=i + 1, label=day, tokens={},
                           values={field: str(price) if price is not None else None
                                   for field in ('open', 'high', 'low', 'close')})
                      for i, (day, price) in enumerate(zip(dates, prices))])


def pair(left, right, lookback=5):
    return pair_report(query(left), query(right, '000001.SZ'), lookback)


def reference(x, y):
    mx, my = sum(x) / len(x), sum(y) / len(y)
    xx = sum((v - mx) ** 2 for v in x)
    yy = sum((v - my) ** 2 for v in y)
    xy = sum((a - mx) * (b - my) for a, b in zip(x, y))
    beta = xy / xx
    scale = math.sqrt(sum(((b - my) - beta * (a - mx)) ** 2 for a, b in zip(x, y)) / (len(x) - 2))
    return my - beta * mx, beta, scale, xy / math.sqrt(xx * yy)


@pytest.mark.parametrize('lookback', [True, 4, 253, 5.0, None])
def test_invalid_window_rejected(lookback):
    with pytest.raises(ValueError, match='invalid_lookback'):
        pair([1] * 8, [2] * 8, lookback)


@pytest.mark.parametrize('symbol,reason', [('600001.SH', 'research_duplicate_symbol'),
                                         ('ABC', 'research_market_unknown'),
                                         ('AAPL.NASDAQ', 'research_market_mismatch')])
def test_duplicate_unknown_and_different_markets_rejected(symbol, reason):
    with pytest.raises(ValueError, match=reason):
        pair_report(query([1] * 7), query([2] * 7, symbol, snapshot='other'), 5)


def test_identity_normalizes_claims_without_promoting_declarations():
    q = query([1], 'sh.600001')
    q['metadata']['interpretation'] = dict(instrument='600001.SH', venue='SH')
    before = deepcopy(q)
    ident = symbol_identity(q)
    assert ident['symbol'] == '600001.SH' and ident['market'] == 'CN_A'
    assert ident['qualification'] == 'source_claim_and_declared'
    assert q == before
    q['metadata'] = dict(period='1d', interpretation=dict(instrument='000001', venue='SZ'))
    assert symbol_identity(q)['qualification'] == 'declared'
    q['metadata']['source_code'] = '600001.SH'
    with pytest.raises(ValueError, match='research_identity_conflict'):
        symbol_identity(q)


def test_prior_price_ols_and_inclusive_return_window_match_independent_formula():
    a, b = [10, 11, 9, 12, 13, 19], [20, 21, 23, 22, 26, 24]
    result = pair(a, b)
    row = result['series'][-1]
    x, y = list(map(math.log, b)), list(map(math.log, a))
    alpha, beta, scale, _ = reference(x[:-1], y[:-1])
    rx, ry = [x[i] - x[i-1] for i in range(1, 6)], [y[i] - y[i-1] for i in range(1, 6)]
    _, rbeta, _, corr = reference(rx, ry)
    assert row['log_price_alpha'] == pytest.approx(alpha)
    assert row['log_price_beta'] == pytest.approx(beta)
    assert row['residual_scale'] == pytest.approx(scale)
    assert row['residual_deviation'] == pytest.approx((y[-1] - alpha - beta*x[-1]) / scale)
    assert row['return_beta'] == pytest.approx(rbeta)
    assert row['return_correlation'] == pytest.approx(corr)
    assert row['n_prices'] == row['n_returns'] == 5
    assert row['price_end_date'] == '2026-01-05'
    assert row['returns_end_date'] == row['date'] == '2026-01-06'
    assert result['return_window_includes_current'] is True
    assert result['price_window_includes_current'] is False
    altered = pair(a[:-1] + [999], b)['series'][-1]
    assert altered['log_price_beta'] == row['log_price_beta']
    assert altered['residual_scale'] == row['residual_scale']
    assert altered['return_correlation'] != row['return_correlation']


def test_align_before_returns_discloses_unequal_source_coverage():
    left = query([10, 30, 40], dates=['2026-01-01', '2026-01-03', '2026-01-04'])
    right = query([20, 80, 60, 80], '000001.SZ')
    report = pair_report(left, right, 5)
    row = report['series'][1]
    assert row['return_start_date'] == '2026-01-01'
    assert row['left_log_return'] == pytest.approx(math.log(3))
    assert row['right_log_return'] == pytest.approx(math.log(3))
    assert row['right_skipped_dates'] == 1 and row['left_skipped_dates'] == 0
    assert row['coverage_reason'] == 'unequal_source_coverage'
    assert report['alignment']['right_only_dates'] == 1
    assert report['alignment']['common_dates'] == 3


def test_bad_and_duplicate_shared_dates_break_windows_keep_baseline():
    left, right = query([10, 12, 15, 0, 18, 19, 20, 21, 23, 25]), query([20, 21, 23, 24, 25, 26, 28, 29, 31, 33], '000001.SZ')
    left['rows'].append(deepcopy(left['rows'][5]))
    rows = pair_report(left, right, 5)['series']
    assert rows[3]['reason'] == 'invalid_price'
    assert rows[4]['left_log_return'] is None
    assert rows[5]['reason'] == 'duplicate_date'
    assert rows[6]['left_log_return'] is None
    assert rows[-1]['return_correlation'] is None
    assert rows[-1]['n_returns'] == 3
    assert rows[-1]['relative_strength'] == pytest.approx((25 / 10) / (33 / 20) - 1)


def test_perfect_fit_only_disables_deviation_and_one_constant_side_preserves_beta():
    row = pair([1, 4, 9, 16, 25, 36], [1, 2, 3, 4, 5, 6])['series'][-1]
    assert row['log_price_beta'] == pytest.approx(2)
    assert row['return_beta'] == pytest.approx(2)
    assert row['return_correlation'] == pytest.approx(1)
    assert row['residual_deviation'] is None and row['deviation_reason'] == 'residual_scale_too_small'
    flat_y = pair([2] * 6, [1, 2, 3, 4, 5, 6])['series'][-1]
    assert flat_y['return_beta'] == 0
    assert flat_y['return_correlation'] is None
    assert flat_y['correlation_reason'] == 'return_variance_too_small'
    flat_x = pair([1, 2, 3, 4, 5, 6], [2] * 6)['series'][-1]
    assert flat_x['log_price_beta'] is None and flat_x['return_beta'] is None


def test_prefix_future_mutation_scale_and_input_immutability():
    left = query([10, 12, 11, 15, 14, 19, 16, 21, 17])
    right = query([20, 23, 21, 24, 26, 25, 27, 29, 30], '000001.SZ')
    before = deepcopy((left, right))
    full = pair_report(left, right, 5)
    for i in range(1, 10):
        a, b = deepcopy(left), deepcopy(right)
        a['rows'], b['rows'] = a['rows'][:i], b['rows'][:i]
        assert pair_report(a, b, 5)['series'] == full['series'][:i]
    assert (left, right) == before
    for q, scale in [(left, Decimal('1000')), (right, Decimal('0.001'))]:
        for r in q['rows']:
            r['values'] = {k: str(Decimal(v) * scale) for k, v in r['values'].items()}
    scaled = pair_report(left, right, 5)
    for a, b in zip(full['series'], scaled['series']):
        for key in ['return_correlation', 'return_beta', 'log_price_beta', 'residual_scale', 'residual_deviation', 'relative_strength']:
            assert a[key] == pytest.approx(b[key], abs=1e-10) if a[key] is not None else b[key] is None
    with localcontext() as ctx:
        ctx.prec = 2
        low_precision = pair_report(left, right, 5)
    assert low_precision == scaled


def test_unknown_coverage_is_disclosed_and_no_nan_json():
    import json
    left, right = query([1] * 6), query([2] * 6, '000001.SZ')
    left['unlocated'] = [dict(ordinal=9, label=None, tokens={}, values={})]
    report = pair_report(left, right, 5)
    assert report['alignment']['left']['unlocated_rows'] == 1
    assert report['alignment']['coverage_known'] is False
    assert report['series'][-1]['coverage_reason'] == 'date_set_integrity_unknown'
    json.dumps(report, allow_nan=False)


@pytest.mark.parametrize('factor,blocked', [(0.99, True), (1.0, True), (1.01, False)])
def test_exact_price_sample_variance_threshold_and_neighbors(factor, blocked):
    from anatrading.pair_research import _price_statistics
    a = 1e-6 * factor
    x = [-a, a, -a, a, 0.0]
    row = _price_statistics(x, [1., 2., 3., 4., 5.], 0., 2.)
    assert (row['log_price_beta'] is None) is blocked
    if blocked:
        assert row['price_regression_reason'] == 'price_variance_too_small'


@pytest.mark.parametrize('factor,blocked', [(0.99, True), (1.0, True), (1.01, False)])
def test_exact_return_sample_variance_threshold_and_neighbors(factor, blocked):
    from anatrading.pair_research import _centered, _return_statistics
    a, b = 1e-8 * factor, math.nextafter(1e-8, 0.0) * factor
    x = [-a, a, -b, b, 0.0]
    if factor == 1:
        assert _centered(x)[2] / 4 == 1e-16
    row = _return_statistics(x, [1., 2., 3., 4., 5.])
    assert (row['return_beta'] is None) is blocked
    assert (row['return_correlation'] is None) is blocked


@pytest.mark.parametrize('factor,blocked', [(0.99, True), (1.0, True), (1.01, False)])
def test_exact_residual_scale_threshold_and_neighbors(factor, blocked):
    from anatrading.pair_research import _price_statistics
    a = math.sqrt(3) * 1e-10 / 2 * factor
    row = _price_statistics([-2., -1., 0., 1., 2.], [a, -a, -a, a, 0.], 0., 0.)
    if factor == 1:
        assert row['residual_scale'] == 1e-10
    assert (row['residual_deviation'] is None) is blocked
    assert row['log_price_beta'] == 0


def test_beijing_and_shanghai_are_compatible_but_not_same_security():
    a, b = query([1, 3, 2, 4, 3, 5], '600001.SH'), query([2, 3, 4, 3, 5, 6], '830001.BJ')
    report = pair_report(a, b, 5)
    assert report['roles']['left']['market'] == report['roles']['right']['market'] == 'CN_A'
    assert report['series'][-1]['return_correlation'] is not None


def test_swap_roles_matches_independent_ols_not_relabeling():
    a, b = query([10, 11, 9, 12, 13, 19]), query([20, 21, 23, 22, 26, 24], '000001.SZ')
    forward, reverse = pair_report(a, b, 5)['series'][-1], pair_report(b, a, 5)['series'][-1]
    assert forward['return_correlation'] == pytest.approx(reverse['return_correlation'])
    assert forward['log_price_beta'] != pytest.approx(1/reverse['log_price_beta'])
    x, y = [math.log(float(r['values']['close'])) for r in a['rows'][:-1]], [math.log(float(r['values']['close'])) for r in b['rows'][:-1]]
    assert reverse['log_price_beta'] == pytest.approx(reference(x, y)[1])


def test_random_windows_match_independent_reference():
    import random
    rng = random.Random(719)
    a, b = [], []
    left, right = 3., 2.
    for _ in range(80):
        left, right = left+rng.uniform(-.02, .02), right+rng.uniform(-.015, .015)
        a.append(f'{math.exp(left):.12f}')
        b.append(f'{math.exp(right):.12f}')
    for window in (5, 20, 50):
        rows = pair(a, b, window)['series']
        for i in range(window, len(rows)):
            x = list(map(lambda z: math.log(float(z)), b[i-window:i]))
            y = list(map(lambda z: math.log(float(z)), a[i-window:i]))
            alpha, beta, scale, _ = reference(x, y)
            assert rows[i]['log_price_beta'] == pytest.approx(beta, abs=1e-11)
            assert rows[i]['residual_scale'] == pytest.approx(scale, abs=1e-11)
            assert rows[i]['residual_deviation'] == pytest.approx((math.log(float(a[i]))-alpha-beta*math.log(float(b[i]))) / scale, abs=1e-10)


def test_minute_and_differing_cutoff_rejected():
    left, right = query([1]), query([2], '000001.SZ')
    right['metadata']['period'] = '1m'
    with pytest.raises(ValueError, match='unsupported_period'):
        pair_report(left, right, 5)
    right['metadata']['period'] = '1d'
    right['selection'] = dict(cutoff='2026-01-01')
    with pytest.raises(ValueError, match='research_cutoff_mismatch'):
        pair_report(left, right, 5)


def test_future_mutation_cannot_change_prior_series_and_restored_segment_recovers():
    left, right = query([10, 12, 0, 15, 14, 19, 16, 21, 17, 25]), query([20, 23, 21, 24, 26, 25, 27, 29, 30, 28], '000001.SZ')
    original = pair_report(left, right, 5)['series']
    assert original[7]['return_correlation'] is None
    assert original[8]['return_correlation'] is not None
    left['rows'][-1]['values'] = dict.fromkeys(('open', 'high', 'low', 'close'), '99999')
    assert pair_report(left, right, 5)['series'][:-1] == original[:-1]


def test_baseline_is_first_common_valid_date_and_dated_error_keeps_slot():
    left, right = query([0, 10, 12, 15, 16, 17]), query([20, 21, 23, 24, 25, 26], '000001.SZ')
    bad = left['rows'].pop(2)
    bad['label'], bad['tokens'] = None, {'source_date': '20260103'}
    left['unlocated'] = [bad]
    result = pair_report(left, right, 5)
    assert result['baseline'] == dict(date='2026-01-02', left_close='10', right_close='21')
    assert result['series'][2]['reason'] == 'unlocated_label'
    assert result['series'][3]['left_log_return'] is None
    assert result['series'][-1]['relative_strength'] == pytest.approx((17/10)/(26/21)-1)


def test_price_coefficients_survive_bad_current_but_deviation_is_unavailable():
    value = pair([10, 11, 9, 12, 13, 0], [20, 21, 23, 22, 26, 24])['series'][-1]
    assert value['log_price_beta'] is not None
    assert value['residual_scale'] is not None
    assert value['residual_deviation'] is None
    assert value['deviation_reason'] == 'invalid_current_pair'
    assert value['return_correlation'] is None


def test_distinct_venue_identity_is_not_collapsed_into_market_bucket():
    result = pair_report(query([1, 2, 3, 2, 3, 4], '000001.SH'), query([2, 3, 2, 3, 4, 5], '000001.SZ'), 5)
    assert result['roles']['left']['symbol'] != result['roles']['right']['symbol']
    assert result['roles']['left']['market'] == result['roles']['right']['market']
