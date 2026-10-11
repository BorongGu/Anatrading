"""Independent adversarial acceptance checks for the research implementation.

Synthetic sources only. These checks do not establish real-source compatibility
or predictive usefulness.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import localcontext
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
