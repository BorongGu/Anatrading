"""Same-cutoff source-window calculations, independent denominators and ranks."""
from copy import deepcopy
from decimal import localcontext
import math

import pytest

from anatrading.universe_research import universe_report
from test_pair_research import query


def report(*queries, cutoff='2026-01-06', lookback=5):
    return universe_report(list(queries), cutoff, lookback)


@pytest.mark.parametrize('cutoff', [None, '20260106', '2026-1-6', '2026-02-30', '2026-01-06T00:00'])
def test_cutoff_is_strict_date(cutoff):
    with pytest.raises(ValueError, match='invalid_label_cutoff'):
        report(query([1] * 6), query([2] * 6, '000001.SZ'), cutoff=cutoff)


@pytest.mark.parametrize('lookback', [True, 1, 253, 5.0])
def test_invalid_window(lookback):
    with pytest.raises(ValueError, match='invalid_lookback'):
        report(query([1] * 6), query([2] * 6, '000001.SZ'), lookback=lookback)


def test_collection_requires_distinct_identifiable_two_to_fifty_members():
    for qs in [[], [query([1])], [query([1], f'{i:06d}.SH') for i in range(51)]]:
        with pytest.raises(ValueError, match='research_invalid_member_count'):
            universe_report(qs, '2026-01-06', 5)
    with pytest.raises(ValueError, match='research_duplicate_symbol'):
        report(query([1]), query([2], snapshot='other'))
    unidentified = query([2])
    unidentified['metadata'] = dict(period='1d')
    with pytest.raises(ValueError, match='research_identity_unavailable'):
        report(query([1]), unidentified)


def test_hand_momentum_sample_volatility_and_window_maximum_drawdown():
    prices = [10, 20, 15, 12, 18, 15]
    value = report(query(prices), query([1] * 6, '000001.SZ'))
    row = next(r for r in value['members'] if r['identity']['symbol'] == '600001.SH')
    returns = [math.log(b) - math.log(a) for a, b in zip(prices, prices[1:])]
    mean = sum(returns) / 5
    assert row['momentum'] == pytest.approx(0.5)
    assert row['volatility'] == pytest.approx(math.sqrt(sum((v - mean)**2 for v in returns) / 4))
    assert row['max_drawdown'] == pytest.approx(-0.4)
    assert row['start_date'] == '2026-01-01' and row['end_date'] == '2026-01-06'
    assert row['n_prices'] == 6 and row['n_returns'] == 5
    breadth = value['breadth']
    assert breadth['positive'] == 1 and breadth['zero'] == 1 and breadth['negative'] == 0
    assert breadth['positive_momentum_fraction'] == 0.5
    assert breadth['momentum_valid'] == breadth['volatility_valid'] == breadth['max_drawdown_valid'] == 2


def test_missing_cutoff_duplicate_bad_and_short_history_are_never_imputed():
    missing = query([1] * 5, '000001.SZ')
    duplicate = query([1] * 6, '000002.SZ')
    duplicate['rows'].append(deepcopy(duplicate['rows'][-1]))
    bad = query([1, 1, 0, 1, 1, 2], '000003.SZ')
    short = query([1, 2], '000004.SZ', dates=['2026-01-05', '2026-01-06'])
    value = report(missing, duplicate, bad, short)
    by_id = {r['identity']['symbol']: r for r in value['members']}
    assert by_id['000001.SZ']['momentum_reason'] == 'cutoff_missing'
    assert by_id['000002.SZ']['momentum_reason'] == 'duplicate_date'
    assert by_id['000003.SZ']['momentum_reason'] == 'invalid_price'
    assert by_id['000004.SZ']['momentum_reason'] == 'history_insufficient'
    assert all(r['momentum'] is None and r['rank'] is None for r in value['members'])
    assert value['breadth']['positive_momentum_fraction'] is None
    assert value['breadth']['selected'] == 4 and value['breadth']['cutoff_present'] == 3
    assert value['breadth']['cutoff_valid'] == 2
    assert value['breadth']['metrics']['momentum'] == dict(eligible=0, missing=1, invalid=2, short_history=1)


def test_stable_competition_ranks_and_selected_order_invariance():
    qs = [query([1, 1, 1, 1, 1, 2], '600003.SH'), query([10, 10, 10, 10, 10, 20], '600002.SH'),
          query([1, 1, 1, 1, 1, 1], '600001.SH'), query([2, 2, 2, 2, 2, 1], '600004.SH')]
    value = report(*qs)
    assert [r['identity']['symbol'] for r in value['members']] == ['600002.SH', '600003.SH', '600001.SH', '600004.SH']
    assert [r['rank'] for r in value['members']] == [1, 1, 3, 4]
    assert report(*reversed(qs)) == value
    assert value['breadth']['positive'] == 2 and value['breadth']['negative'] == 1


def test_different_real_start_dates_and_fixed_cutoff_ignore_future():
    a = query([1, 1, 1, 1, 1, 2, 999], '600001.SH')
    b = query([1, 1, 1, 1, 1, 2], '600002.SH', dates=['2025-12-01', '2025-12-05', '2025-12-10', '2025-12-20', '2026-01-01', '2026-01-06'])
    before = deepcopy((a, b))
    value = report(a, b)
    assert {r['start_date'] for r in value['members']} == {'2026-01-01', '2025-12-01'}
    assert all(r['momentum'] == 1 for r in value['members'])
    a['rows'] = a['rows'][:-1]
    assert report(a, b) == value
    assert b == before[1]
    with localcontext() as ctx:
        ctx.prec = 2
        assert report(a, b) == value


def test_metrics_are_counted_independently_even_on_numeric_failure(monkeypatch):
    import anatrading.universe_research as module
    original = module._volatility
    monkeypatch.setattr(module, '_volatility', lambda prices: (None, 'numerical_failure'))
    value = report(query([1] * 6), query([2] * 6, '000001.SZ'))
    assert value['breadth']['momentum_valid'] == value['breadth']['max_drawdown_valid'] == 2
    assert value['breadth']['volatility_valid'] == 0
    assert all(r['rank'] == 1 for r in value['members'])
    monkeypatch.setattr(module, '_volatility', original)


def test_declared_members_and_unlocated_coverage_not_sector_inference():
    a, b = query([1] * 6), query([2] * 6, '000001.SZ')
    a['metadata'] = dict(period='1d', interpretation=dict(instrument='600001.SH', venue='SH'))
    a['unlocated'] = [dict(ordinal=99, label=None, tokens={}, values={})]
    value = report(a, b)
    assert value['membership'] == 'selected_sample_no_historical_sector_inference'
    assert value['breadth']['coverage_unknown'] == 1
    assert value['members'][0]['identity']['qualification'] in {'declared', 'source_claim'}
    assert 'verified' not in str(value['members'][0]['identity'])


def test_tiny_distinct_source_changes_do_not_create_float_ties_or_false_zero():
    a = query(['10000000000000000000'] * 5 + ['10000000000000000001'], '600001.SH')
    b = query(['10000000000000000000'] * 5 + ['10000000000000000002'], '600002.SH')
    value = report(a, b)
    assert [r['rank'] for r in value['members']] == [1, 2]
    assert [r['momentum'] for r in value['members']] == [2e-19, 1e-19]
    assert value['breadth']['positive'] == 2 and value['breadth']['zero'] == 0


def test_scale_invariance_and_flat_path_valid_zero_volatility():
    prices = [10, 20, 15, 12, 18, 15]
    a, b = query(prices), query([2] * 6, '000001.SZ')
    original = report(a, b)
    scaled = report(query([v * 100 for v in prices]), query([20] * 6, '000001.SZ'))
    for old, new in zip(original['members'], scaled['members']):
        for key in ('momentum', 'volatility', 'max_drawdown'):
            assert old[key] == pytest.approx(new[key], abs=1e-14)
    flat = next(r for r in original['members'] if r['identity']['symbol'] == '000001.SZ')
    assert flat['volatility'] == flat['max_drawdown'] == 0
    assert flat['volatility_reason'] is None


def test_bad_slot_inside_window_is_not_replaced_with_older_history():
    a = query([100, 1, 2, 3, 4, 5, 6])
    a['rows'][2]['values']['high'] = None
    value = report(a, query([1]*7, '000001.SZ'), cutoff='2026-01-07')
    row = next(r for r in value['members'] if r['identity']['symbol'] == '600001.SH')
    assert row['start_date'] == '2026-01-02'
    assert row['momentum'] is None and row['momentum_reason'] == 'missing_ohlc'


def test_invalid_label_cannot_be_filtered_as_a_known_future_date():
    a, b = query([1] * 6), query([2] * 6, '000001.SZ')
    a['rows'][2].update(label='2026-13-30', tokens={'source_date': '20260103'})
    value = report(a, b)
    row = next(r for r in value['members'] if r['identity']['symbol'] == '600001.SH')
    assert row['momentum_reason'] == 'unlocated_label'
    assert row['coverage']['unlocated_rows'] == 1


def test_distinct_metric_category_counts_are_conserved():
    a, b, c = query([1]*6), query([2]*5, '000001.SZ'), query([2]*6, '000002.SZ')
    c['rows'][3]['values']['close'] = '0'
    value = report(a, b, c)
    for counts in value['breadth']['metrics'].values():
        assert sum(counts.values()) == 3
        assert counts == dict(eligible=1, missing=1, invalid=1, short_history=0)
