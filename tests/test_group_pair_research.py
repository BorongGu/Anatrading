"""051 independent synthetic inputs; no existing Store or private data."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import combinations
import pytest

from anatrading.group_pair_research import group_pair_report, serialize_report
from anatrading.peer_neighbor_research import peer_neighbor_report
from test_peer_neighbor_research import fixture
from test_peer_relative_research import source_query, recount, fail


def run(q, days):
    return group_pair_report(q, days[-1])


@pytest.mark.parametrize('defect', ['missing', 'extra', 'duplicate', 'unknown', 'price', 'token', 'global_identity', 'cutoff'])
def test_fail_closed_full_members_and_pairs(defect):
    q, days = fixture()
    if defect == 'missing': q[1]['rows'].pop(30)
    elif defect == 'extra':
        new = deepcopy(q[1]['rows'][30]); new['ordinal'] = 999
        new['label'] = new['tokens']['source_date'] = (date.fromisoformat(days[30])+timedelta(days=1)).isoformat()
        q[1]['rows'].append(new)
    elif defect == 'duplicate':
        new = deepcopy(q[1]['rows'][30]); new['ordinal'] = 999; q[1]['rows'].append(new)
    elif defect == 'unknown':
        new = q[1]['rows'].pop(30); new['label'] = None; new['tokens']['source_date'] = '?'; q[1]['unlocated'].append(new)
    elif defect == 'price': q[1]['rows'][30]['values']['close'] = '0'
    elif defect == 'token': q[1]['rows'][30]['tokens']['close'] = '999'
    elif defect == 'cutoff': q[1]['rows'].pop()
    else:
        new = deepcopy(q[1]['rows'][-1]); new['ordinal'] = 999
        new['label'] = new['tokens']['source_date'] = '2026-12-31'; new['tokens']['source_code'] = '600099.SH'; q[1]['rows'].append(new)
    recount(q[1]); r = run(q, days)
    assert not r['source_panel_complete'] and r['status'] == 'unavailable'
    assert len(r['members']) == 5 and len(r['pairs']) == 10
    assert all(p[w]['reason'] == 'source_panel_unavailable' for p in r['pairs'] for w in ('previous','current'))
    m = next(m for m in r['members'] if m['snapshot_id'] == q[1]['snapshot_id'])
    assert m['reasons'] or r['grid_reasons']
    assert m['anomalies'] is not None and m['endpoints'] is not None
    if defect in ('missing','extra','unknown','cutoff'): assert r['used_dates'] == []


@pytest.mark.parametrize('defect', ['counts','ordinal','checks','semantics'])
def test_structure_failure_survives_source_refusal(defect):
    q, days = fixture(); q[1]['manifest']['qualification'] = 'unsupported'
    if defect == 'counts': q[1]['counts']['batch_rows'] += 1
    elif defect == 'ordinal': q[1]['rows'][1]['ordinal'] = q[1]['rows'][0]['ordinal']
    elif defect == 'checks': q[1]['rows'][1]['checks'] = ['bad']
    else: q[1]['manifest']['contract']['source_semantics'] = {'fields':[]}
    with pytest.raises(ValueError): run(q, days)


def test_limits_and_refused_source(monkeypatch):
    import anatrading.group_pair_research as module
    q, days = fixture()
    for bad in ([],q[:1],q*11):
        with pytest.raises(ValueError, match='member_limit'): run(bad,days)
    with pytest.raises(ValueError, match='duplicate_member'): run([q[0],q[0]],days)
    with pytest.raises(ValueError, match='duplicate_member'): run([q[0],source_query('600000.SH',[1]*121,days)],days)
    with pytest.raises(ValueError, match='invalid_dates'): group_pair_report(q,'2026-02-30')
    with pytest.raises(TypeError): group_pair_report(q,days[-1],target=q[0]['snapshot_id'])
    with monkeypatch.context() as patch:
        patch.setattr(module,'MAX_RESULT_BYTES',1)
        with pytest.raises(ValueError, match='group_pair_result_limit'): run(q,days)
    q[1]['metadata']['requested_adjustment'] = 'qfq'; r=run(q,days)
    m=next(m for m in r['members'] if m['snapshot_id']==q[1]['snapshot_id'])
    assert m['date_array']==[] and m['endpoints'] is None and m['anomalies'] is None
    assert len(r['pairs'])==10 and r['used_dates']==[]


def world(vectors):
    days=[(date(2026,1,1)+timedelta(days=2*i)).isoformat() for i in range(121)]
    queries=[]
    for i,vector in enumerate(vectors):
        prices=[Decimal(100)]
        with localcontext() as ctx:
            ctx.prec=80
            for _ in range(2):
                for change in list(vector)+[0]*(60-len(vector)):
                    prices.append(prices[-1]*(1+Decimal(change)/10))
        queries.append(source_query(f'{600000+i}.SH',prices,days))
    return queries,days


def by_symbol(r):
    symbols={m['snapshot_id']:m['symbol'] for m in r['members']}
    return {frozenset((symbols[p['left_snapshot_id']],symbols[p['right_snapshot_id']])):p for p in r['pairs']}


def assert_oracle(q,r):
    lookup={item['snapshot_id']:item for item in q}
    for p in r['pairs']:
        for name,offset in (('previous',0),('current',60)):
            changes=[]
            for sid in (p['left_snapshot_id'],p['right_snapshot_id']):
                values=[Fraction(row['values']['close']) for row in lookup[sid]['rows'][offset:offset+61]]
                v=[b/a-1 for a,b in zip(values,values[1:])]
                mean=sum(v)/60; changes.append([x-mean for x in v])
            x,y=changes; cross=sum(a*b for a,b in zip(x,y)); xx=sum(a*a for a in x); yy=sum(b*b for b in y)
            c=p[name]['correlation']
            if not xx or not yy: assert c is None
            else:
                assert c['sign']==('positive' if cross>0 else 'negative' if cross<0 else 'zero')
                assert c['exact_boundary']==('zero' if not cross else ('positive_one' if cross>0 else 'negative_one') if cross*cross==xx*yy else 'none')
                with localcontext() as ctx:
                    ctx.prec=80
                    exact=Decimal(cross.numerator)/Decimal(cross.denominator)/(Decimal(xx.numerator)/Decimal(xx.denominator)*Decimal(yy.numerator)/Decimal(yy.denominator)).sqrt()
                    assert abs(Decimal(c['estimate'])-exact) < Decimal('1e-48')


def test_two_worlds_independent_oracle_and_all_target_049_baseline():
    u,v=(1,1,-1,-1),(1,-1,1,-1)
    a,days=world([u,u,v,v]); b,_=world([u,u,v,tuple(-x for x in v)])
    ra,rb=run(a,days),run(b,days)
    for q,r in ((a,ra),(b,rb)):
        assert_oracle(q,r)
        reports={item['snapshot_id']:peer_neighbor_report(q,item['snapshot_id'],days[-1]) for item in q}
        for p in r['pairs']:
            for target,other in ((p['left_snapshot_id'],p['right_snapshot_id']),(p['right_snapshot_id'],p['left_snapshot_id'])):
                candidate=next(c for c in reports[target]['candidates'] if c['snapshot_id']==other)
                for w in ('previous','current'): assert p[w]['correlation']==candidate[w]['correlation']
    for w in ('previous','current'):
        assert by_symbol(ra)[frozenset(('600002.SH','600003.SH'))][w]['correlation']['exact_boundary']=='positive_one'
        assert by_symbol(rb)[frozenset(('600002.SH','600003.SH'))][w]['correlation']['exact_boundary']=='negative_one'
        for symbol in ('600001.SH','600002.SH','600003.SH'):
            assert by_symbol(ra)[frozenset(('600000.SH',symbol))][w]['correlation']==by_symbol(rb)[frozenset(('600000.SH',symbol))][w]['correlation']
    for index,expected in ((0,'100'),(60,'98.01'),(120,'96.059601')):
        for r in (ra,rb): assert [m['endpoints'][index]['close_exact'] for m in r['members']]==[expected]*4
    assert [m['endpoints'][-1]['close_exact'] for m in ra['members']]==['96.059601']*4
    assert [m['endpoints'][-1]['close_exact'] for m in rb['members']]==['96.059601']*4


def test_six_member_structures_and_sign_flips():
    u,v,w=(1,1,-1,-1),(1,-1,1,-1),(1,-1,-1,1)
    results=[]
    for vectors in ([u]*3+[v]*3,[u]*4+[v,w],[u]*3+[tuple(-x for x in u)]*3):
        q,days=world(vectors); r=run(q,days); assert_oracle(q,r); results.append(r)
    for r in results[:2]:
        assert sum(p['current']['correlation']['sign']=='positive' for p in r['pairs'])==6
        assert sum(p['current']['correlation']['sign']=='zero' for p in r['pairs'])==9
    assert {k for k,p in by_symbol(results[0]).items() if p['current']['correlation']['sign']=='positive'} != {k for k,p in by_symbol(results[1]).items() if p['current']['correlation']['sign']=='positive'}
    assert sum(p['current']['correlation']['sign']=='negative' for p in results[2]['pairs'])==9


def test_constant_local_policy_nonzero_and_near_constant():
    q,days=fixture(3)
    q[0]=source_query('600000.SH',[1]*121,days)
    r=run(q,days); assert r['windows']['previous']['available']==1
    assert sum(m['constant']['previous'] is True for m in r['members'])==1
    # Exact constant nonzero in previous window: +100% repeated 60 times, then hold.
    q[0]=source_query('600000.SH',[2**i for i in range(61)]+[2**60]*60,days)
    r=run(q,days); assert r['windows']['previous']['available']==1 and r['windows']['current']['available']==1
    q[0]=source_query('600000.SH',['1']*60+['1.000000000000000001']+['1']*60,days)
    r=run(q,days); assert r['status']=='complete'; assert_oracle(q,r)
    q[1]=source_query('600001.SH',[1]*121,days); q[0]=source_query('600000.SH',[1]*121,days)
    r=run(q[:2],days); assert r['status']=='unavailable' and r['source_panel_complete']
    assert len(r['pairs'][0]['previous']['constant_members'])==2


def test_permutation_future_and_common_calendar_unknown():
    q,days=fixture(4); r=run(q,days)
    assert r==run(list(reversed(q)),days)
    for item in q:
        later=deepcopy(item['rows'][-1]);later['ordinal']=999;later['label']=later['tokens']['source_date']='2026-12-31';item['rows'].append(later);recount(item)
    future=run(q,days)
    assert future['pairs']==r['pairs'] and future['used_dates']==r['used_dates']
    assert future['limitations']['trading_calendar']=='unknown'  # every other calendar date is absent in these fixtures


def test_full_50_member_2450_cells_serialization_and_exact_budget(monkeypatch):
    import anatrading.group_pair_research as module
    for n in (2,50):
        q,days=fixture(n); r=run(q,days)
        assert len(r['pairs'])==n*(n-1)//2 and sum(len([p['previous'],p['current']]) for p in r['pairs'])==n*(n-1)
        data=serialize_report(r); assert len(data)<=2*1024*1024
        with monkeypatch.context() as patch:
            patch.setattr(module,'MAX_RESULT_BYTES',len(data)); assert serialize_report(r)==data
            patch.setattr(module,'MAX_RESULT_BYTES',len(data)-1)
            with pytest.raises(ValueError,match='group_pair_result_limit'): serialize_report(r)


def test_reused_kernel_guards_not_swallowed(monkeypatch):
    import anatrading.peer_neighbor_research as kernel
    q,days=fixture(3)
    with monkeypatch.context() as patch:
        patch.setattr(kernel,'MAX_INTEGER_BITS',1)
        with pytest.raises(ValueError,match='peer_neighbor_integer_limit'):run(q,days)
    with monkeypatch.context() as patch:
        def broken(*_): raise ValueError('peer_neighbor_display_failure')
        patch.setattr(kernel,'_display',broken)
        with pytest.raises(ValueError,match='peer_neighbor_display_failure'):run(q,days)


def test_all_unknown_dates_preserve_scoped_scan_failures():
    q,days=fixture(3)
    for point in q[1]['rows']:
        point['label']=None;point['tokens']['source_date']='?'
    q[1]['unlocated']=q[1]['rows'];q[1]['rows']=[]
    fail(q[1]['unlocated'][0],'source_date_range')
    fail(q[1]['unlocated'][1],'synthetic_future_check')
    recount(q[1]);r=run(q,days)
    m=next(m for m in r['members'] if m['snapshot_id']==q[1]['snapshot_id'])
    assert {'endpoint_integrity_unknown','local_source_conflict','unclassified_source_failure'} <= set(m['reasons'])
    assert m['date_array']==[] and m['endpoints']==[] and m['anomalies']['total']==121
    assert len(r['pairs'])==3 and r['status']=='unavailable'


def test_all_50_nonconstant_full_2450_correlations():
    q,days=fixture(3)
    queries=[source_query(f'{600000+i}.SH',[r['values']['close'] for r in q[i%3]['rows']],days) for i in range(50)]
    r=run(queries,days)
    assert r['status']=='complete' and r['windows']['previous']['available']==1225 and r['windows']['current']['available']==1225
    assert all(p[w]['correlation'] is not None for p in r['pairs'] for w in ('previous','current'))
    assert len(serialize_report(r)) <= 2*1024*1024


def test_nonboundary_and_constant_pairs_match_every_049_target():
    q,days=fixture(5)
    q[2]=source_query('600002.SH',range(100,221),days)
    r=run(q,days);assert_oracle(q,r)
    assert any(p['current']['correlation'] and p['current']['correlation']['exact_boundary']=='none' for p in r['pairs'])
    for target in q:
        old=peer_neighbor_report(q,target['snapshot_id'],days[-1])
        candidates={c['snapshot_id']:c for c in old['candidates']}
        for p in r['pairs']:
            if target['snapshot_id'] not in (p['left_snapshot_id'],p['right_snapshot_id']):continue
            other=p['right_snapshot_id'] if p['left_snapshot_id']==target['snapshot_id'] else p['left_snapshot_id']
            for w in ('previous','current'):assert p[w]['correlation']==candidates[other][w]['correlation']


def test_future_append_new_source_identities_preserve_fixed_cutoff_values():
    q,days=fixture(4);before=run(q,days)
    appended=[source_query(f'{600000+i}.SH',[r['values']['close'] for r in source['rows']]+['3'],days+['2026-12-31']) for i,source in enumerate(q)]
    assert {x['snapshot_id'] for x in q}.isdisjoint(x['snapshot_id'] for x in appended)
    after=run(appended,days)
    assert before['analysis_id']!=after['analysis_id'] and before['used_dates']==after['used_dates']
    old,new=by_symbol(before),by_symbol(after)
    for pair in old:
        for w in ('previous','current'):assert old[pair][w]['correlation']==new[pair][w]['correlation']
