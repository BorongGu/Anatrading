"""Independent adversarial acceptance checks for the research implementation.

Synthetic sources only. These checks do not establish real-source compatibility
or predictive usefulness.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
import json
import random

import pytest

from anatrading.event_study import event_report
from anatrading.pair_research import pair_report, _price_statistics, _return_statistics
from anatrading.research_series import daily_bars
from anatrading.signal_research import signal_report
from anatrading.store import EvidenceStore
from anatrading.universe_research import universe_report
from test_formats import bao_payload


def query(prices, symbol='600001.SH', start=date(2026, 1, 1)):
    return dict(snapshot_id=symbol, query_id=symbol, metadata=dict(period='1d', source_code=symbol),
                rows=[dict(ordinal=i+1, label=(start+timedelta(days=i)).isoformat(), tokens={},
                           values={k: str(p) for k in ('open', 'high', 'low', 'close')})
                      for i, p in enumerate(prices)], unlocated=[])


def test_conflicting_row_instrument_cannot_be_researched_as_envelope_security(tmp_path):
    records = [[f'2021-02-{i+21:02}', 'sz.000001' if i == 2 else 'sh.600001',
                *([str(p)] * 4), '100', '1000', '3']
               for i, p in enumerate([10, 11, 999, 12, 13, 14])]
    with EvidenceStore(tmp_path) as store:
        sid = store.import_bytes(bao_payload(records, code='sh.600001'), 'baostock-decoded-v0.9.4')['snapshot_id']
        q = store.query(sid)
    assert next(c for c in q['rows'][2]['checks'] if c['name'] == 'source_code')['outcome'] == 'fail'
    result = signal_report(q, lookback=2, horizon=1)
    row = result['series'][2]
    assert row['status'] == 'invalid'
    assert row['reason'] is not None and row['breakout'] is None
    assert result['series'][3]['segment_id'] != result['series'][1]['segment_id']
    assert all(event['date'] != q['rows'][2]['label'] for event in result['events']['rows'])


def test_random_events_match_naive_full_window_oracle():
    rng = random.Random(7080)
    for trial in range(30):
        q = query([rng.randint(1, 40) for _ in range(70)])
        for i in rng.sample(range(70), 8):
            q['rows'][i]['values']['close'] = '0'
        for i in rng.sample(range(70), 4):
            q['rows'].append(deepcopy(q['rows'][i]))
        bars = daily_bars(q)
        lookback = rng.randint(2, 12)
        horizon = rng.choice([1, 5, 10, 20])
        test_start = bars[35]['date']
        result = event_report(bars, lookback, horizon, test_start)
        last = None
        expected = []
        for i, b in enumerate(bars):
            computable = i >= lookback and all(x['reason'] is None for x in bars[i-lookback:i+1])
            signal = b['close'] > max(x['high'] for x in bars[i-lookback:i]) if computable else None
            assert result['signals'][i]['breakout'] is signal
            if signal:
                selected = last is None or i > last+horizon
                if selected:
                    last = i
                if i+horizon >= len(bars):
                    status = 'immature'
                elif bars[i]['date'] < test_start <= bars[i+horizon]['date']:
                    status = 'purged'
                elif any(x['reason'] is not None for x in bars[i:i+horizon+1]):
                    status = 'invalid'
                else:
                    status = 'valid'
                if not selected:
                    status = 'overlap_excluded'
                expected.append((i, selected, status))
        assert [(e['index'], e['selected'], e['evaluation_status']) for e in result['rows']] == expected
        for group in [result, *result['partitions'].values()]:
            c = group['counts']
            assert c['raw_events'] == sum(c[k] for k in ['valid','invalid','immature','purged','overlap_excluded'])
            bc = group['baseline']['counts']
            assert bc['candidate_dates'] == sum(bc[k] for k in ['valid','invalid','immature','purged'])


def test_all_decimal_source_extremes_remain_finite_across_modules():
    prices = ['0.000000000000000001', '99999999999999999999.999999999999999999'] * 20
    a, b = query(prices), query(prices[::-1], '000001.SZ')
    with localcontext() as ctx:
        ctx.prec = 2
        reports = [signal_report(a, lookback=2, horizon=1), pair_report(a,b,5),
                   universe_report([a,b], a['rows'][-1]['label'], 5)]
    for report in reports:
        json.dumps(report, allow_nan=False)
    assert all(r['status'] != 'invalid' for r in reports[0]['series'])
    assert all(r['reason'] is None for r in reports[1]['series'])


def test_event_positive_counts_use_exact_decimal_changes_before_float_estimation():
    # Above float64 resolution but within exact DECIMAL(38,18).
    q = query(['1', '1', '1.000000000000000001', '1.000000000000000002'])
    result = signal_report(q, lookback=2, horizon=1)['events']
    assert result['counts']['valid'] == 1
    assert result['statistics']['positive_count'] == 1
    assert result['statistics']['mean'] > 0


def test_universe_rank_does_not_create_binary64_ties():
    a = query(['1', '1', '1.000000000000000001'], '600002.SH')
    b = query(['1', '1', '1.000000000000000002'], '600001.SH')
    result = universe_report([a,b], '2026-01-03', 2)
    assert [r['identity']['symbol'] for r in result['members']] == ['600001.SH', '600002.SH']
    assert [r['rank'] for r in result['members']] == [1,2]
    assert result['breadth']['positive'] == 2


def test_pair_exact_threshold_and_nearby_variance_reasons():
    # Symmetric vectors give sample variance exactly s**2 for length five.
    for scale, invalid in [(1e-8 * .999, True), (1e-8 * 1.001, False)]:
        values = [-scale, -scale, 0., scale, scale]
        result = _return_statistics(values, values)
        assert (result['return_beta'] is None) is invalid
        assert (result['return_correlation'] is None) is invalid
    for scale, invalid in [(1e-6 * .999, True), (1e-6 * 1.001, False)]:
        values = [-scale, -scale, 0., scale, scale]
        result = _price_statistics(values, [2*x for x in values], 1., 2.)
        assert (result['log_price_beta'] is None) is invalid
        if not invalid:
            assert result['deviation_reason'] == 'residual_scale_too_small'


def test_research_http_source_integrity_and_local_boundary(tmp_path):
    import asyncio
    from test_research_api import seed, client_for
    root = tmp_path / 'store'
    ids = seed(root, 30)
    with EvidenceStore(root) as store:
        q = store.query(ids[0])
        sha = q['manifest']['raw_sha256']
        path = store.root / 'raw' / sha[:2] / sha
        original = path.read_bytes()
    async def scenario():
        async with client_for(root) as client:
            routes = [('/api/research/single/' + ids[0], {}),
                      ('/api/research/pair', dict(left=ids[0],right=ids[1],cutoff='2025-01-30')),
                      ('/api/research/universe',dict(snapshot_ids=','.join(ids),cutoff='2025-01-30'))]
            for route, params in routes:
                good = await client.get(route, params=params)
                assert good.status_code == 200
                for headers in [{'Origin':'https://untrusted.invalid'}, {'Host':'untrusted.invalid'}]:
                    response = await client.get(route, params=params, headers=headers)
                    assert response.status_code == 403
                    assert response.headers['cache-control'] == 'no-store'
            # Same size raw mutation, after successful requests, must still fail.
            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            for route, params in routes:
                response = await client.get(route, params=params)
                assert response.status_code == 409
                assert response.json() == {'error':'raw_object_corrupt'}
                assert response.headers['cache-control'] == 'no-store'
    asyncio.run(scenario())


def test_research_total_budget_rejected_before_any_materialization(tmp_path, monkeypatch):
    import asyncio
    from test_research_api import seed, client_for
    root = tmp_path / 'store'
    seed(root, 6)
    count_calls = []
    def count(self, sid, cutoff=None):
        count_calls.append((sid, cutoff))
        return 20_000
    def forbidden(*args, **kwargs):
        raise AssertionError('Over-total-budget research materialized observations')
    monkeypatch.setattr(EvidenceStore, 'query_row_count', count)
    monkeypatch.setattr(EvidenceStore, 'query', forbidden)
    monkeypatch.setattr(EvidenceStore, '_research_query', forbidden)
    ids = [f'{i:064x}' for i in range(11)]
    async def scenario():
        async with client_for(root) as client:
            response = await client.get('/api/research/universe', params=dict(snapshot_ids=','.join(ids), cutoff='2025-01-06'))
            assert response.status_code == 400
            assert response.json() == {'error':'research_row_limit'}
    asyncio.run(scenario())
    assert count_calls == [(sid, '2025-01-06') for sid in ids]


def test_universe_same_market_gate_allows_china_venues_and_rejects_mixed_market():
    china = [query([1,2,3], symbol) for symbol in ['600001.SH','000001.SZ','830001.BJ']]
    result = universe_report(china, '2026-01-03', 2)
    assert result['breadth']['momentum_valid'] == 3
    for symbol in ['AAPL.NASDAQ','00700.HK']:
        with pytest.raises(ValueError, match='^research_market_mismatch$'):
            universe_report([china[0], query([1,2,3],symbol)], '2026-01-03',2)


def _projection_sources(store):
    """Mixed source failures made through normal decoding; no DB repair path."""
    snapshots = []
    for side, symbol in enumerate(['sh.600001', 'sz.000001']):
        records = []
        for i in range(34):
            day = (date(2026, 1, 1) + timedelta(days=i)).isoformat()
            price = str(Decimal(20 + side) + Decimal(i) / 100)
            row = [day, symbol, *([price] * 4), '9223372036854775807',
                   '99999999999999999999.999999999999999999', '3']
            if i == 8:
                row[1] = 'sh.699999'
            if i == 13:
                row[5] = '0'
            if i == 17:
                row[0] = day.replace('-', '/')  # Located only from the raw token.
            if i == 18:
                row[0] = 'not-a-date'
            if i == 24:
                row[6], row[7] = 'bad', 'bad'  # Price-only eligibility stays intact.
            records.append(row)
        records.append(deepcopy(records[11]))
        records.append(['2026/12/31', symbol, *(['1'] * 4), '0', '0', '3'])
        records.reverse()  # Source order cannot be mistaken for chronological order.
        snapshots.append(store.import_bytes(bao_payload(records, code=symbol),
                         'baostock-decoded-v0.9.4')['snapshot_id'])
    return snapshots


def _independent_projection(full):
    keys = ['snapshot_id','batch_id','manifest','metadata','batch_checks','selection','query_id','counts']
    expected = {key: deepcopy(full[key]) for key in keys}
    expected['read_projection'] = 'daily_ohlc_input_v1'
    for scope in ['rows','unlocated']:
        expected[scope] = []
        for row in full[scope]:
            projected = {key: deepcopy(row[key]) for key in ['ordinal','label','tokens','checks']}
            projected['values'] = {key: None if row['values'][key] is None else Decimal(row['values'][key])
                                   for key in ['open','high','low','close']}
            expected[scope].append(projected)
    return expected


def test_compact_projection_matches_independent_reference_and_complete_reports(tmp_path):
    from anatrading.research_api import _calculate
    from anatrading.research_series import daily_coverage
    from anatrading.workbench import _RequestError
    with EvidenceStore(tmp_path) as store:
        ids = _projection_sources(store)
        for cutoff in [None, '2025-12-31', '2026-01-18', '2026-01-27', '2026-02-03', '2027-01-01']:
            full = [store.query(sid, cutoff=cutoff) for sid in ids]
            with localcontext() as ctx:
                ctx.prec = 2
                compact = [store._research_query(sid, cutoff=cutoff) for sid in ids]
                assert compact == [_independent_projection(q) for q in full]
                for original, projected in zip(full, compact):
                    assert daily_bars(projected) == daily_bars(original)
                    assert daily_coverage(projected) == daily_coverage(original)
                for horizon in [1, 5, 10, 20]:
                    params = dict(cutoff=cutoff, lookback=2, horizon=horizon, test_start='2026-01-16')
                    assert _calculate('single', compact[:1], params, _RequestError) == _calculate('single', full[:1], params, _RequestError)
                params = dict(cutoff=cutoff, lookback=5)
                assert _calculate('pair', compact, params, _RequestError) == _calculate('pair', full, params, _RequestError)
                if cutoff is not None:
                    assert _calculate('universe', compact, params, _RequestError) == _calculate('universe', full, params, _RequestError)
            assert [store.query(sid, cutoff=cutoff) for sid in ids] == full


def test_compact_reads_leave_public_export_bytes_and_parquet_unchanged(tmp_path):
    from pathlib import Path
    import pyarrow.parquet as pq
    with EvidenceStore(tmp_path / 'store') as store:
        sid = _projection_sources(store)[0]
        selection = dict(cutoff='2026-02-03')
        before = store.query(sid, **selection)
        json_before = store.export_json(sid, tmp_path / 'before.json', **selection)
        parquet_before = store.export_parquet(sid, tmp_path / 'before.parquet', **selection)
        before_bytes = Path(json_before['path']).read_bytes()
        before_table = pq.read_table(parquet_before['path'])
        for _ in range(3):
            projected = store._research_query(sid, **selection)
            assert projected['query_id'] == before['query_id']
            signal_report(projected, lookback=2)
        assert store.query(sid, **selection) == before
        json_after = store.export_json(sid, tmp_path / 'after.json', **selection)
        parquet_after = store.export_parquet(sid, tmp_path / 'after.parquet', **selection)
        assert Path(json_after['path']).read_bytes() == before_bytes
        assert json_after['query_id'] == json_before['query_id']
        assert json_after['sha256'] == json_before['sha256']
        assert pq.read_table(parquet_after['path']).equals(before_table, check_metadata=True)
        assert parquet_after['query_id'] == parquet_before['query_id']
        assert parquet_after['sha256'] == parquet_before['sha256']


@pytest.mark.parametrize('bad_checks', [
    '[{"name":"source_code"}]', '[{"outcome":"fail"}]',
    '[{"name":"source_code","outcome":"PRIVATE_BAD_OUTCOME"}]',
    '{}', '[null]', 'null', 'PRIVATE_BROKEN_JSON',
])
def test_compact_damaged_checks_cannot_turn_into_qualified_http_result(tmp_path, bad_checks):
    import asyncio
    from test_research_api import client_for
    root = tmp_path / 'store'
    with EvidenceStore(root) as store:
        sid = _projection_sources(store)[0]
        q = store.query(sid)
        store.db.execute('UPDATE observations SET checks_json=? WHERE batch_id=? AND ordinal=3',
                         [bad_checks, q['batch_id']])
    async def scenario():
        async with client_for(root) as client:
            response = await client.get('/api/research/single/' + sid)
            assert response.status_code == 500
            assert response.json() == {'error': 'internal_error'}
            assert 'PRIVATE' not in response.text
    asyncio.run(scenario())
