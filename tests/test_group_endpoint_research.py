"""Synthetic, independent exact controls for the explicit common-endpoint group."""
import asyncio
from copy import deepcopy
from fractions import Fraction
import json

import pytest

from anatrading.peer_relative_research import group_endpoint_report, _source, _group_exact
from anatrading.store import EvidenceStore
from test_peer_relative_research import A, B, FMT, source_query, capture, recount, fail, event
from test_research_api import client_for


def queries(changes=(1, 1, 1, 1, 6)):
    return [source_query(f'{600000+i}.SH', ['100', str(100 + Fraction(str(change)))])
            for i, change in enumerate(changes)]


def ratio(value):
    return None if value is None else Fraction(int(value['numerator']), int(value['denominator']))


def run(q, **kwargs):
    return group_endpoint_report(q, A, B, **kwargs)


@pytest.mark.parametrize('defect,code', [
    ('counts', 'invalid_counts'), ('ordinal', 'invalid_source_ordinal'),
    ('checks', 'invalid_source_checks'), ('semantics', 'invalid_query'),
    ('adjustment_field', 'invalid_query'), ('interpretation', 'invalid_query'),
])
@pytest.mark.parametrize('early', ['qualification', 'negative'])
def test_rejected_source_cannot_hide_later_structural_failure(defect, code, early):
    q = queries()
    if early == 'qualification': q[0]['manifest']['qualification'] = 'unsupported'
    else: q[0]['batch_checks'].append(dict(name='known_negative_sample', outcome='fail'))
    if defect == 'counts': q[0]['counts']['selected_rows'] = 99
    elif defect == 'ordinal': q[0]['rows'][1]['ordinal'] = q[0]['rows'][0]['ordinal']
    elif defect == 'checks': q[0]['rows'][1]['checks'] = 'bad'
    elif defect == 'semantics': q[0]['manifest']['contract']['source_semantics'] = {'fields': []}
    elif defect == 'adjustment_field': q[0]['manifest']['contract']['source_semantics'] = {'fields': {'adjustment': []}}
    else: q[0]['metadata']['interpretation'] = []
    with pytest.raises(ValueError, match=f'^{code}$'): run(q)


def test_old_source_error_priority_is_preserved():
    q = queries()[0]
    q['manifest']['qualification'] = 'unsupported'; q['counts']['selected_rows'] = 99
    with pytest.raises(ValueError, match='^unsupported_source$'): _source(q)
    q = queries()[0]
    q['manifest']['contract']['source_semantics'] = {'fields': {'price_unit': {'value': 'USD'}, 'adjustment': []}}
    with pytest.raises(ValueError, match='^scope_conflict$'): _source(q)


def test_source_rejection_is_not_unchecked_missing_endpoints_or_zero_anomalies():
    q = queries(); q[0]['metadata']['requested_adjustment'] = 'qfq'
    r = run(q); m = next(m for m in r['members'] if m['snapshot_id'] == q[0]['snapshot_id'])
    assert r['counts'] == dict(selected=5, valid=4, missing=1)
    assert m['evaluation'] == 'not_evaluated'
    assert m['endpoints'] is None and m['anomalies'] is None and m['source_change'] is None
    assert m['reasons'] == ['source_adjustment_conflict']
    assert all(v is None for v in r['summary'].values())
    q[0]['metadata']['requested_symbol'] = '600099.SH'
    m = next(m for m in run(q)['members'] if m['snapshot_id'] == q[0]['snapshot_id'])
    assert m['symbol'] is None and m['reasons'] == ['source_identity_conflict']


@pytest.mark.parametrize('which', [0, 1])
@pytest.mark.parametrize('member', range(5))
def test_missing_endpoint_keeps_member_denominator_and_never_rolls_back(which, member):
    q = queries(); q[member]['rows'].pop(which); recount(q[member])
    r = run(q)
    assert r['counts'] == dict(selected=5, valid=4, missing=1)
    assert len(r['members']) == 5 and r['summary_reason'] == 'incomplete_group'
    assert all(v is None for v in r['summary'].values())
    m = next(m for m in r['members'] if m['snapshot_id'] == q[member]['snapshot_id'])
    assert m['source_change'] is None and 'missing_endpoint' in m['reasons']


@pytest.mark.parametrize('changes,expected', [
    ((1, 1, 1, 1, 6), (Fraction(2,100), Fraction(1,100), Fraction(1,100), Fraction(1,100))),
    ((Fraction(1,10), Fraction(9,10), 1, 4, 4), (Fraction(2,100), Fraction(1,100), Fraction(9,1000), Fraction(4,100))),
    ((-3,-1,1,3), (Fraction(0), Fraction(0), Fraction(-15,1000), Fraction(15,1000))),
    ((0,0,0,0), (Fraction(0),)*4),
])
def test_independent_exact_mean_median_and_type7(changes, expected):
    # Construct terminating source strings without a floating-point oracle.
    q = [source_query(f'{600000+i}.SH', ['1000', str(1000 + int(Fraction(change)*10))]) for i, change in enumerate(changes)]
    r = run(q)
    assert tuple(ratio(r['summary'][key]) for key in ('mean','median','q1','q3')) == expected
    assert sum(r['sign_counts'].values()) == len(changes)
    assert r['counts']['selected'] == r['counts']['valid'] == len(changes)
    assert r['summary_reason'] is None


@pytest.mark.parametrize('valid', [0,1,3,4])
def test_k_limits_and_empty_proportions(valid):
    q = queries((1,0,-1,2))
    for item in q[valid:]: item['rows'].pop(); recount(item)
    r = run(q)
    assert r['counts'] == dict(selected=4, valid=valid, missing=4-valid)
    assert sum(r['sign_counts'].values()) == valid
    assert ratio(r['coverage']) == Fraction(valid,4)
    assert all(v is None for v in r['sign_proportions'].values()) == (valid == 0)
    assert all(v is None for v in r['summary'].values()) == (valid != 4)


def test_exact_near_zero_and_scientific_source_token():
    q = [source_query(f'{600000+i}.SH', ['1', close]) for i, close in enumerate(['1.000000000000000001','0.999999999999999999','1','1'])]
    q[0]['rows'][0]['tokens']['close'] = '1e0'
    r = run(q)
    assert r['sign_counts'] == dict(positive=1, zero=2, negative=1)
    assert ratio(r['summary']['mean']) == 0
    assert any(m['endpoints']['start']['close_token'] == '1e0' for m in r['members'])


def test_full_sources_input_order_identity_and_future_numeric_invariance():
    q = queries(); before = deepcopy(q); r = run(q)
    assert run(list(reversed(q))) == r and q == before
    later = [source_query(f'{600000+i}.SH', ['100', str(101 if i<4 else 106), '2'], [A,B,'2026-10-01']) for i in range(5)]
    rr = run(later)
    assert rr['summary'] == r['summary'] and rr['sign_counts'] == r['sign_counts']
    assert rr['analysis_id'] != r['analysis_id']
    q[0]['selection']['cutoff'] = B
    with pytest.raises(ValueError, match='full_query_required'): run(q)


def test_events_preserve_diagnostics_and_budget_without_rescuing_invalid_member():
    q = queries(); events = [event(q, 'corporate_action_unresolved')]
    r = run(q, events=events)
    assert r['diagnostic_only'] is True and r['counts']['valid'] == 5
    q[0]['rows'].pop(); recount(q[0])
    r = run(q, events=events)
    assert r['counts']['valid'] == 4 and r['summary']['mean'] is None
    with pytest.raises(ValueError, match='scope_conflict'): run(q, events=[event(q,'scope_conflict')])
    with pytest.raises(ValueError, match='auxiliary_input_limit'): run(q, events=['x'*1025])
    bad = event(q,'halt'); bad['snapshot_id'] = 'f'*64
    with pytest.raises(ValueError, match='descriptor_source_mismatch'): run(q, events=[bad])


def test_bounded_fraction_conversion_and_member_row_budget():
    with pytest.raises(ValueError, match='group_fraction_limit'): _group_exact(Fraction(10**5000))
    with pytest.raises(ValueError, match='member_limit'): run(queries((0,0,0)))
    with pytest.raises(ValueError, match='member_limit'): run(queries(tuple([0]*51)))
    q = queries(tuple(range(50))); assert run(q)['counts']['valid'] == 50
    q[0]['rows'] = q[0]['rows'] * 10001
    with pytest.raises(ValueError, match='research_row_limit'): run(q)


def test_synthetic_store_api_full_query_and_prefix_record_agree(tmp_path):
    root = tmp_path/'new-synthetic-store'; ids = []
    with EvidenceStore(root) as store:
        for i, change in enumerate((1,1,1,1,6)):
            ids.append(store.import_bytes(capture(f'{600000+i}.SH', ['100',str(100+change)]),FMT)['snapshot_id'])
        complete = [store.query(sid) for sid in ids]
        projected = [store._research_query(sid) for sid in ids]
        assert run(complete) == run(projected)
        expected = run(projected)
    async def scenario():
        async with client_for(root) as client:
            params = dict(snapshot_ids=','.join(ids), start_date=A, end_date=B)
            response = await client.get('/api/research/group-endpoints',params=params)
            assert response.status_code == 200, response.text
            assert response.json() == expected
            assert response.headers['cache-control'] == 'no-store'
            for member in response.json()['members']:
                for key in ('start','end'):
                    point = member['endpoints'][key]
                    raw = await client.get('/api/query/'+member['snapshot_id'], params={'cutoff':point['date']})
                    assert raw.status_code == 200, raw.text
                    query = raw.json()['query']
                    row = next(row for row in query['rows'] if row['ordinal'] == point['ordinal'])
                    assert row['values']['close'] == point['close_exact'] and row['tokens']['close'] == point['close_token']
                    assert query['query_id'] != member['query_id']
            for patch in ({'start_date':B}, {'end_date':'2026-02-30'}, {'snapshot_ids':','.join(ids[:3])}, {'snapshot_ids':','.join(ids+[ids[0]])}, {'unexpected':'x'}):
                bad = await client.get('/api/research/group-endpoints',params={**params,**patch})
                assert bad.status_code >= 400
    asyncio.run(scenario())


def test_report_constants_are_isolated_from_caller_mutation():
    q = queries(); baseline = run(q); changed = run(q)
    changed['scope']['price_currency']['value'] = 'USD'
    changed['limitations']['economic_return_qualified'] = True
    assert run(q) == baseline


@pytest.mark.parametrize('symbol', ['AAPL.NASDAQ','00700.HK','BRK.B.NYSE'])
def test_out_of_scope_display_identity_stays_unevaluated(symbol):
    q = queries(); q[0]['metadata']['source_code'] = symbol
    q[0]['metadata'].pop('source_venue',None)
    r = run(q); m = next(m for m in r['members'] if m['snapshot_id'] == q[0]['snapshot_id'])
    assert m['symbol'] == symbol and m['reasons'] == ['scope_conflict']
    assert m['evaluation'] == 'not_evaluated' and r['counts']['valid'] == 4


def test_twenty_example_cap_never_hides_later_blocking_anomaly():
    from datetime import date, timedelta
    dates = [(date(2026,9,1)+timedelta(days=i)).isoformat() for i in range(21)]+[A,B]
    q = queries(); q[0] = source_query('600000.SH',['100']*len(dates),dates)
    for row in q[0]['rows'][:21]: fail(row,'numeric.volume')
    fail(q[0]['rows'][-1],'future_unknown_check')
    r = run(q); m = next(m for m in r['members'] if m['snapshot_id']==q[0]['snapshot_id'])
    assert m['anomalies']['truncated'] and len(m['anomalies']['examples'])==20
    assert 'unclassified_source_failure' in m['reasons'] and m['source_change'] is None
    assert m['anomalies']['counts']['future_unknown_check']==1 and r['counts']['valid']==4


def test_group_api_budgets_before_loading_and_reverifies_damaged_raw(tmp_path,monkeypatch):
    root=tmp_path/'fresh';ids=[]
    with EvidenceStore(root) as store:
        for i in range(4):ids.append(store.import_bytes(capture(f'{600000+i}.SH',['100','101']),FMT)['snapshot_id'])
        q=store.query(ids[0]);path=store._raw_path(q['manifest']['raw_sha256']);original=path.read_bytes()
    params=dict(snapshot_ids=','.join(ids),start_date=A,end_date=B)
    async def scenario():
        async with client_for(root) as client:
            with monkeypatch.context() as patch:
                counts=[]
                def count(self,sid,cutoff=None):counts.append((sid,cutoff));return 20_001
                def no_read(*args,**kwargs):raise AssertionError('materialized before budget')
                patch.setattr(EvidenceStore,'query_row_count',count);patch.setattr(EvidenceStore,'_research_query',no_read)
                r=await client.get('/api/research/group-endpoints',params=params)
                assert r.status_code==400 and r.json()=={'error':'research_row_limit'}
                assert len(counts)==4 and all(cutoff is None for _,cutoff in counts)
            for damage in ('corrupt','missing'):
                if damage=='corrupt':path.write_bytes(b'bad')
                else:path.unlink()
                r=await client.get('/api/research/group-endpoints',params=params)
                assert r.status_code==409 and r.json()=={'error':'raw_object_'+damage}
                path.write_bytes(original)
                assert (await client.get('/api/research/group-endpoints',params=params)).status_code==200
    asyncio.run(scenario())


def test_result_limit_rejects_whole_report(monkeypatch):
    import anatrading.peer_relative_research as module
    monkeypatch.setattr(module,'GROUP_MAX_RESULT_BYTES',1)
    with pytest.raises(ValueError,match='group_result_limit'):run(queries())
