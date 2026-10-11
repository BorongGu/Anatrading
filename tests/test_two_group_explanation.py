"""Synthetic source-panel, precision, causality and owner-boundary checks for 043."""
import asyncio
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json
import math

import pytest

from anatrading.two_group_explanation import two_group_report, _fit, _log
from test_peer_relative_research import source_query, recount, fail, capture
from test_research_api import client_for
from anatrading.store import EvidenceStore


def fixture(n=62, members=4):
    dates = [(date(2026, 1, 1)+timedelta(days=t)).isoformat() for t in range(n)]
    queries = []
    for i in range(members):
        with localcontext() as context:
            context.prec = 80
            price = Decimal(100)
            prices = [price]
            for t in range(1, n):
                factor = Decimal(str(.004*math.sin(t*.7)*(1+i/10) + .003*math.cos(t*.4)*(1 if i < members//2 else -1)))
                price = (price*factor.exp()).quantize(Decimal('0.000000000000000001'))
                prices.append(price)
        queries.append(source_query(f'{600000+i}.SH', prices, dates))
    ids = [q['snapshot_id'] for q in queries]
    return queries, {'A': ids[:members//2], 'B': ids[members//2:]}, dates


def run(q, groups, dates):
    return two_group_report(q, groups, dates[60], dates[61])


def test_full_panel_decomposition_input_order_and_source_evidence():
    q, groups, dates = fixture()
    before = deepcopy(q)
    r = run(q, groups, dates)
    assert r['status'] == 'complete'
    assert r['counts'] == dict(selected=4, source_complete=4, model_available=4)
    assert r['training_dates'] == dates[:61]
    assert q == before
    assert r['limitations']['trading_calendar'] == 'unknown'
    for member in r['members']:
        model = member['model']
        assert math.isclose(member['raw_change'], model['explained']+model['residual'], abs_tol=1e-16)
        assert math.isclose(model['explained'], model['baseline']+sum(model['contributions']), abs_tol=1e-16)
        assert len(member['training_endpoints']) == 62
        assert member['training_endpoints'][0]['close_exact'] == '100'
    reversed_report = run(list(reversed(q)), {key: list(reversed(value)) for key, value in groups.items()}, dates)
    assert reversed_report['analysis_id'] == r['analysis_id']
    assert reversed_report['members'] == list(reversed(r['members']))
    json.dumps(r, allow_nan=False)


@pytest.mark.parametrize('mode', ['training_missing', 'current_missing', 'bad_label', 'conflict', 'unknown', 'duplicate', 'bad_price', 'token_mismatch', 'global_adjustment'])
def test_source_failure_closes_whole_panel_and_retains_rows(mode):
    q, groups, dates = fixture()
    if mode == 'training_missing':
        q[0]['rows'].pop(20)
    elif mode == 'current_missing':
        q[0]['rows'].pop()
    elif mode == 'bad_label':
        row = q[0]['rows'].pop(20); row['label'] = None; q[0]['unlocated'].append(row)
    elif mode == 'conflict':
        q[0]['rows'][20]['tokens']['source_date'] = dates[21]
    elif mode == 'unknown':
        row = q[0]['rows'].pop(20); row['label'] = None; row['tokens']['source_date'] = '?'; q[0]['unlocated'].append(row)
    elif mode == 'duplicate':
        row = deepcopy(q[0]['rows'][20]); row['ordinal'] = 999; q[0]['rows'].append(row)
    elif mode == 'bad_price':
        q[0]['rows'][20]['values']['close'] = '-1'
    elif mode == 'token_mismatch':
        q[0]['rows'][20]['tokens']['close'] = '99'
    else:
        q[0]['metadata']['requested_adjustment'] = 'qfq'
    recount(q[0])
    r = run(q, groups, dates)
    assert r['status'] == 'unavailable'
    assert len(r['members']) == 4
    assert r['counts']['model_available'] == 0
    assert all(m['model'] is None and 'source_panel_unavailable' in m['reasons'] for m in r['members'])
    assert r['members'][1]['raw_change'] is not None


def test_union_includes_invalid_label_date_and_does_not_skip_intermediate_point():
    q, groups, dates = fixture()
    # Original requested current interval has an intervening source date.
    r = two_group_report(q, groups, dates[59], dates[61])
    assert 'current_interval_not_adjacent' in r['reasons']
    assert 'training_window_incomplete' in r['reasons']
    row = q[0]['rows'].pop(60); row['label'] = None; q[0]['unlocated'].append(row); recount(q[0])
    r = two_group_report(q, groups, dates[59], dates[61])
    assert 'current_interval_not_adjacent' in r['reasons']


def test_known_outside_bad_record_disclosed_unknown_future_revokes_and_valid_future_preserves():
    q, groups, dates = fixture(n=64)
    r = run(q, groups, dates)
    q[0]['rows'][-1]['values']['close'] = '-1'
    fail(q[0]['rows'][-1], 'ohlc_bounds')
    bad = run(q, groups, dates)
    assert [m['model'] for m in bad['members']] == [m['model'] for m in r['members']]
    assert bad['members'][0]['anomalies']['total'] == 1
    q[0]['rows'][-1]['tokens']['source_date'] = '?'
    assert run(q, groups, dates)['status'] == 'unavailable'
    q2, g2, d2 = fixture()
    # Prefix fixture has different source IDs but identical selected numeric outputs.
    assert [m['model'] for m in run(q2, g2, d2)['members']] == [m['model'] for m in r['members']]


def test_current_target_change_never_enters_own_factors_or_fit():
    q, groups, dates = fixture()
    r = run(q, groups, dates)
    row = q[0]['rows'][-1]
    for key in ('open', 'high', 'low', 'close'):
        row['values'][key] = '120'; row['tokens'][key] = '120'
    changed = run(q, groups, dates)
    left, right = r['members'][0]['model'], changed['members'][0]['model']
    for key in ('baseline', 'contributions', 'explained', 'gamma', 'factor_mean', 'factor_sd', 'current_factor', 'current_z', 'rank_ratio'):
        assert left[key] == right[key]
    assert changed['members'][0]['raw_change'] != r['members'][0]['raw_change']
    assert changed['members'][1]['model']['current_factor'] != r['members'][1]['model']['current_factor']


def test_event_uses_whole_training_span_and_scope_remains_explicit():
    q, groups, dates = fixture()
    event = dict(symbol='600000.SH', snapshot_id=q[0]['snapshot_id'], start_date=dates[2], end_date=dates[3],
                 kind='halt', evidence_refs=[dict(source_id='synthetic-event', version='1', declared_by='project_test')])
    r = two_group_report(q, groups, dates[60], dates[61], events=[event])
    assert r['status'] == 'unavailable'
    assert 'halted_endpoint_source_value' in r['reasons']


def test_precision_equal_minimum_difference_and_extreme_legal_ratio():
    assert _log(Decimal('1'), Decimal('1')) == 0
    for a, b in [('99999999999999999999.999999999999999998','99999999999999999999.999999999999999999'), ('0.000000000000000001','99999999999999999999.999999999999999999')]:
        value = _log(Decimal(a), Decimal(b))
        with localcontext() as context:
            context.prec = 120
            expected = (Decimal(b)/Decimal(a)).ln()
        assert float(value) != 0
        assert float(value) == float(expected)


def test_fit_constant_collinear_swap_and_centered_large_mean():
    a = [Decimal(i % 7) / 100 for i in range(61)]
    b = [Decimal((i*3) % 11) / 100 for i in range(61)]
    with localcontext() as context:
        context.prec = 80
        y = [Decimal('0.012')+2*x-3*z for x, z in zip(a, b)]
        r = _fit(y, [a,b]); swap = _fit(y, [b,a])
        assert abs(r['residual']) < 1e-14
        assert math.isclose(r['explained'], swap['explained'], abs_tol=1e-14)
        large = _fit(y, [[x+Decimal('1e30') for x in a], [x-Decimal('1e30') for x in b]])
        assert large['explained'] == r['explained']
    for columns, reason in [([a,a], 'factor_rank_unavailable'), ([a,[Decimal(1)]*61], 'factor_scale_too_small')]:
        with pytest.raises(ValueError, match=reason): _fit(y, columns)


def test_numerical_failure_is_per_row_not_source_panel(monkeypatch):
    import anatrading.two_group_explanation as module
    q, groups, dates = fixture()
    original = module._fit
    count = 0
    def one_failure(*args):
        nonlocal count
        count += 1
        if count == 1: raise ValueError('numerical_unstable')
        return original(*args)
    monkeypatch.setattr(module, '_fit', one_failure)
    r = run(q, groups, dates)
    assert r['status'] == 'partial'
    assert r['counts'] == dict(selected=4, source_complete=4, model_available=3)
    assert r['members'][0]['model'] is None
    assert r['members'][0]['raw_change'] is not None


def test_group_validation_and_output_limit(monkeypatch):
    import anatrading.two_group_explanation as module
    q, groups, dates = fixture()
    with pytest.raises(ValueError, match='invalid_groups'):
        run(q, {'A': groups['A'], 'B': groups['A']}, dates)
    with pytest.raises(ValueError, match='invalid_groups'):
        run(q, {'A': groups['A'][:1], 'B': groups['A'][1:]+groups['B']}, dates)
    monkeypatch.setattr(module, 'MAX_RESULT_BYTES', 100)
    with pytest.raises(ValueError, match='explanation_result_limit'):
        run(q, groups, dates)


def test_api_synthetic_store_full_source_budget_then_load_and_input_order(tmp_path, monkeypatch):
    q, groups, dates = fixture(n=64)
    ids = []
    with EvidenceStore(tmp_path / 'synthetic') as store:
        for query in q:
            ids.append(store.import_bytes(capture(query['metadata']['source_code'],
                      [r['values']['close'] for r in query['rows']], dates), 'tencent-daily-capture-v1')['snapshot_id'])
    reads = []
    count, load = EvidenceStore.query_row_count, EvidenceStore._research_query
    def count_spy(self, sid, **kwargs):
        reads.append(('count', sid, kwargs.get('cutoff'))); return count(self, sid, **kwargs)
    def load_spy(self, sid, **kwargs):
        reads.append(('load', sid, kwargs.get('cutoff'))); return load(self, sid, **kwargs)
    monkeypatch.setattr(EvidenceStore, 'query_row_count', count_spy)
    monkeypatch.setattr(EvidenceStore, '_research_query', load_spy)
    params = dict(snapshot_ids=','.join(ids), group_a=','.join(ids[:2]), group_b=','.join(ids[2:]), current_start=dates[60], current_end=dates[61])
    async def scenario():
        async with client_for(tmp_path / 'synthetic') as client:
            response = await client.get('/api/research/two-group-explanation', params=params)
            assert response.status_code == 200, response.text
            report = response.json()
            assert report['status'] == 'complete'
            assert [m['snapshot_id'] for m in report['members']] == ids
            assert [r[0] for r in reads] == ['count']*4+['load']*4
            assert all(r[2] is None for r in reads)
            reads.clear()
            response = await client.get('/api/research/two-group-explanation', params={**params, 'group_b': params['group_a']})
            assert response.status_code == 400
            assert not reads
    asyncio.run(scenario())


def test_global_row_adjustment_failure_outside_window_closes_panel():
    q, groups, dates = fixture(n=64)
    fail(q[0]['rows'][-1], 'source_adjustment')
    r = run(q, groups, dates)
    assert r['status'] == 'unavailable'
    assert 'global_source_conflict' in r['reasons']


def test_current_identity_conflict_retains_price_facts_but_not_attributed_change():
    q, groups, dates = fixture()
    q[0]['rows'][-1]['tokens']['code'] = '600099.SH'
    r = run(q, groups, dates)
    assert r['members'][0]['raw_change'] is None
    assert r['members'][0]['endpoints']['end']['close_exact'] is not None
    assert r['status'] == 'unavailable'


def test_bounded_outside_anomalies_are_counted_without_losing_source_locations():
    q, groups, dates = fixture(n=100)
    for row in q[0]['rows'][62:]:
        fail(row, 'ohlc_bounds')
    report = run(q, groups, dates)
    assert report['status'] == 'complete'
    anomalies = report['members'][0]['anomalies']
    assert anomalies['total'] == 38
    assert anomalies['counts'] == {'ohlc_bounds': 38}
    assert len(anomalies['examples']) == 20 and anomalies['truncated']
    assert len(report['members'][0]['training_endpoints']) == 62


def test_full_source_budget_finishes_all_counts_before_rejection():
    from anatrading.research_api import _load
    class Store:
        counted = []
        def query_row_count(self, sid, *, cutoff):
            assert cutoff is None
            self.counted.append(sid)
            return 20001 if sid == 'a' else 1
        def _research_query(self, *args, **kwargs):
            pytest.fail('Source must not load after budget rejection')
    store = Store()
    with pytest.raises(ValueError, match='research_row_limit'):
        _load(store, ['a','b','c','d'], None, ValueError)
    assert store.counted == ['a','b','c','d']
