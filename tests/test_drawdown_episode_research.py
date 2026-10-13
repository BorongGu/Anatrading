"""Frozen prefix-run oracle and synthetic source controls. No historical Store."""
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
from itertools import product
import json
import pytest
from test_peer_relative_research import source_query, recount, fail
from anatrading.drawdown_episode_research import drawdown_episode_report, summarize, serialize_report


def oracle(values):
    """Independent O(m²) partition of strictly underwater prefix observations."""
    values = list(map(Fraction, values))
    underwater = [i for i, v in enumerate(values) if v < max(values[:i+1])]
    runs = []
    for i in underwater:
        if not runs or i != runs[-1][-1]+1: runs.append([])
        runs[-1].append(i)
    episodes = []
    for run in runs:
        p = run[0]-1; r = run[-1]+1 if run[-1]+1 < len(values) else None
        v = min(run, key=lambda i: values[i]); e = r if r is not None else len(values)-1
        episodes.append((p,v,r,e,(values[p]-values[v])/values[p]))
    return episodes


def points(values):
    return [dict(index=i,date=(date(2026,1,1)+timedelta(days=2*i)).isoformat(),
                 ordinal=str(10**18+i*97),close_exact=str(v)) for i,v in enumerate(values)]


def check(values):
    ep = points(values); expected = oracle(values); actual = summarize(ep)
    assert actual['episode_count'] == len(expected)
    assert actual['recovered_count'] == sum(x[2] is not None for x in expected)
    assert actual['open_count'] == sum(x[2] is None for x in expected)
    reps = dict(deepest=max(expected,key=lambda x:(x[4],-x[0])) if expected else None,
                longest_observed=max(expected,key=lambda x:(x[3]-x[0],-x[0])) if expected else None,
                current_open=next((x for x in expected if x[2] is None),None))
    for key, want in reps.items():
        got=actual[key]
        if want is None: assert got is None; continue
        p,v,r,e,d=want
        assert got['peak']==ep[p] and got['valley']==ep[v] and got['observed_end']==ep[e]
        assert got['recovery']==(ep[r] if r is not None else None)
        assert got['depth_fraction']==dict(numerator=str(d.numerator),denominator=str(d.denominator))
        assert got['peak_to_valley_intervals']==v-p
        assert got['peak_to_recovery_intervals']==(r-p if r is not None else None)
        assert got['valley_to_recovery_intervals']==(r-v if r is not None else None)
        assert got['observed_intervals']==e-p and got['observed_is_lower_bound']==(r is None)
        assert got['underwater_observations']==(r-p-1 if r is not None else len(ep)-1-p)
    return actual


@pytest.mark.parametrize('values', [[100,80]+[100]*19,[100]+[80]*19+[100],
 [100,80,100,99,99,99,99,100],[100,80,100,99,99,99,99],
 [100,100,80,80,100,100,90,100],[100,80,101],[100,80,100,80,100],
 ['1','0.999999999999999999','1','0.999999999999999998','1'],
 ['1','0.8','0.999999999999999999'],[1,1,1],[1,2,3],[3,2,1],
 ['99999999999999999999.999999999999999999','0.000000000000000001','99999999999999999999.999999999999999999']])
def test_fixed_and_all_legal_prefixes(values):
    for end in range(3,len(values)+1): check(values[:end])


def test_exhaustive_partition_oracle():
    for size in range(3,8):
        for values in product((1,2,3),repeat=size): check(values)


def fixtures(values=(100,80,100),n=2):
    dates=[(date(2026,1,1)+timedelta(days=i*(1 if len(values)>183 else 2))).isoformat() for i in range(len(values))]
    return [source_query(f'{600000+i}.SH',values,dates) for i in range(n)],dates


def run(q,days,lookback=None):
    return drawdown_episode_report(q,days[-1],len(days)-1 if lookback is None else lookback)


def test_full_report_stable_and_original_ordinals():
    q,d=fixtures(); before=deepcopy(q); r=run(q,d)
    assert r==run(q[::-1],d) and q==before
    assert r['comparison_available'] and r['dates']==d
    assert r['counts']==dict(selected=2,source_qualified=2,window_qualified=2,computable=2)
    assert all(m['episode_count']==1 for m in r['members'])


@pytest.mark.parametrize('defect',['grid','cutoff','history','duplicate','unlocated','unknown','price','unsupported','future_conflict'])
def test_all_members_retained_and_no_partial_summaries(defect):
    q,d=fixtures((100,90,80,100),3); bad=q[1]
    if defect=='grid': bad['rows'][1]['label']=bad['rows'][1]['tokens']['source_date']='2026-01-02'
    elif defect=='cutoff': bad['rows'].pop()
    elif defect=='history': bad['rows'].pop(0)
    elif defect=='duplicate':
        row=deepcopy(bad['rows'][1]);row['ordinal']=99;bad['rows'].append(row)
    elif defect in ('unlocated','unknown'):
        row=bad['rows'].pop(1);row['label']=None;bad['unlocated'].append(row)
        if defect=='unknown': row['tokens']['source_date']='?'
    elif defect=='price': bad['rows'][1]['values']['close']='0'
    elif defect=='unsupported': bad['metadata']['period']='1m'
    else:
        row=deepcopy(bad['rows'][-1]);row['ordinal']=99;row['label']=row['tokens']['source_date']='2026-12-31';fail(row,'source_adjustment');bad['rows'].append(row)
    recount(bad);r=run(q,d)
    assert not r['comparison_available'] and r['dates'] is None and len(r['members'])==3
    assert r['counts']['computable']==0
    for member in r['members']:
        assert all(member[key] is None for key in ('episode_count','recovered_count','open_count','deepest','longest_observed','current_open'))
    if defect=='grid': assert all(m['reasons']==['date_grid_mismatch'] for m in r['members'])


def test_full_serialization_limit_not_truncation():
    q,d=fixtures();r=run(q,d)
    r['padding']='汉'*800000
    with pytest.raises(ValueError,match='drawdown_result_limit'):serialize_report(r)


def test_frozen_closed_forms_and_rounding():
    a=check([100,80]+[100]*19);b=check([100]+[80]*19+[100])
    assert a['deepest']['depth_fraction']==b['deepest']['depth_fraction']=={'numerator':'1','denominator':'5'}
    assert (a['longest_observed']['observed_intervals'],b['longest_observed']['observed_intervals'])==(2,20)
    assert check([100]+[80]*19)['current_open']['underwater_observations']==19
    near=check(['1','0.999999999999999999','1','0.999999999999999998','1'])
    assert near['deepest']['peak']['index']==2 and near['deepest']['depth_display']=='小于0.0001%'
    from anatrading.drawdown_episode_research import _display,_bounded,_price_integer
    assert _display(1,2000000)=='小于0.0001%' # Half-even at zero.
    assert _display(3,2000000)=='0.0002%' # Half-even at odd one.
    assert _display(5,2000000)=='0.0002%' # Half-even at even two.
    assert _bounded(2**256-1)==2**256-1
    with pytest.raises(ValueError,match='integer_limit'):_bounded(2**256)
    for value in ['1e2','01','1.0','0','-1','NaN','Infinity','1'+'0'*20,'0.'+'0'*18+'1']:
        with pytest.raises(ValueError,match='price_invalid'):_price_integer(value)


def test_fixed_cutoff_future_prices_do_not_change_any_member_analysis():
    q,d=fixtures((100,80,100,99,100,98))
    for last in range(2,len(d)):
        for lookback in range(2,last+1):
            a=drawdown_episode_report(q,d[last],lookback)
            future=deepcopy(q)
            for source in future:
                for row in source['rows'][last+1:]:
                    for key in ('open','high','low','close'):row['values'][key]=row['tokens'][key]='900'
                row=deepcopy(source['rows'][-1]);row['ordinal']=1000;row['label']=row['tokens']['source_date']='2026-12-31';source['rows'].append(row);recount(source)
            b=drawdown_episode_report(future,d[last],lookback)
            assert a['members']==b['members'] and a['dates']==b['dates']


def test_fifty_maximum_windows_and_failed_rows_serialize_with_exact_bytes():
    maximum='99999999999999999999.999999999999999999'
    values=[maximum if i%2==0 else '0.000000000000000001' for i in range(253)]
    q,d=fixtures(values,50);report=run(q,d)
    assert report['counts']['computable']==50 and len(report['members'])==50
    encoded=serialize_report(report)
    assert len(encoded)<=2*1024*1024
    for source in q:
        for row in source['rows'][:25]:fail(row,'source_date_range');fail(row,'numeric.close')
    failed=run(q,d);assert len(failed['members'])==50
    assert failed['counts']['computable']==0 and len(serialize_report(failed))<=2*1024*1024
    assert all(m['anomalies']['total']==25 and len(m['anomalies']['examples'])==20 and m['anomalies']['examples_truncated'] for m in failed['members'])
    print('max-success-bytes',len(encoded),'failed-50-bytes',len(serialize_report(failed)))


def test_mixed_failures_and_source_early_stop_remain_distinct():
    q,d=fixtures((100,80,100,99),4)
    q[0]['rows'].pop();recount(q[0]);q[1]['rows'].pop(0);recount(q[1])
    q[2]['rows'][1]['values']['close']='0';q[3]['metadata']['period']='1m'
    r=run(q,d);byid={m['snapshot_id']:m for m in r['members']}
    assert r['counts']==dict(selected=4,source_qualified=3,window_qualified=0,computable=0)
    assert set(byid[q[0]['snapshot_id']]['reasons'])=={'cutoff_missing','history_insufficient'}
    assert 'history_insufficient' in byid[q[1]['snapshot_id']]['reasons']
    assert 'invalid_price' in byid[q[2]['snapshot_id']]['reasons']
    early=byid[q[3]['snapshot_id']];assert early['anomalies'] is None and early['date_array'] is None


@pytest.mark.parametrize('defect',['count','ordinal','checks','container'])
def test_structural_failure_precedes_retained_source_refusal(defect):
    q,d=fixtures();q[0]['manifest']['qualification']='unsupported'
    if defect=='count':q[0]['counts']['batch_rows']+=1
    elif defect=='ordinal':q[0]['rows'][0]['ordinal']=q[0]['rows'][1]['ordinal']
    elif defect=='checks':q[0]['rows'][0]['checks']=['bad']
    else:q[0]['rows']={}
    with pytest.raises(ValueError):run(q,d)


def test_identity_ordinal_and_input_bounds():
    q,d=fixtures()
    with pytest.raises(ValueError,match='duplicate_member'):run([q[0],q[0]],d)
    duplicate=deepcopy(q[0]);duplicate['snapshot_id']='f'*64;duplicate['selection']['snapshot_id']='f'*64
    with pytest.raises(ValueError,match='duplicate_member'):run([q[0],duplicate],d)
    q[0]['rows'][0]['ordinal']=10**20
    with pytest.raises(ValueError,match='ordinal_limit'):run(q,d)
    for value in [True,1,253,2.0,'2']:
        with pytest.raises(ValueError,match='invalid_lookback'):drawdown_episode_report(q,d[-1],value)


def test_exact_source_and_total_budget_before_structure(monkeypatch):
    from anatrading import drawdown_episode_research as module
    # New lightweight synthetic query-list stubs; no Store or raw-object reads.
    class Stop(Exception):pass
    def admitted(q):raise Stop
    monkeypatch.setattr(module.peer,'_group_structure',admitted)
    for sizes in ([20000,3],[20000]*10):
        queries=[{'rows':[None]*n,'unlocated':[]} for n in sizes]
        with pytest.raises(Stop):module.drawdown_episode_report(queries,'2026-01-01',2)
    for sizes,error in [([20001,3],'research_row_limit'),([20000]*10+[1],'universe_row_limit')]:
        queries=[{'rows':[None]*n,'unlocated':[]} for n in sizes]
        with pytest.raises(ValueError,match=error):module.drawdown_episode_report(queries,'2026-01-01',2)


def test_endpoint_discovered_defects_are_full_anomaly_counts():
    q,d=fixtures((100,0,100),3)
    r=run(q,d)
    for m in r['members']:
        assert 'invalid_price' in m['reasons']
        assert m['anomalies']['total']==1
        assert m['anomalies']['counts']['invalid_price']==1
        assert m['anomalies']['examples'][0]['codes']==['invalid_price']


def test_top_level_oversized_complete_report_is_rejected_without_reducing_members():
    maximum='99999999999999999999.999999999999999999'
    values=[maximum if i%2==0 else '0.000000000000000001' for i in range(253)]
    q,d=fixtures(values,50)
    # All windows remain complete. The already assessed, reliably future source
    # failures add bounded diagnostic evidence and are never silently truncated.
    for source in q:
        for j in range(20):
            row=deepcopy(source['rows'][-1]);row['ordinal']=1000+j
            row['label']=row['tokens']['source_date']='2026-12-31'
            for k in range(12):fail(row,'synthetic_future_'+str(k)+'_'+'x'*50)
            source['rows'].append(row)
        recount(source)
    before=deepcopy(q)
    with pytest.raises(ValueError,match='drawdown_result_limit'):run(q,d)
    assert q==before and len(q)==50


def test_resolved_cross_market_rejects_whole_request():
    q,d=fixtures()
    q[1]['metadata'].update(source_code='0700.HK',source_venue='HK',requested_symbol='0700.HK',source_symbol='hk0700')
    with pytest.raises(ValueError,match='research_market_mismatch'):run(q,d)


def test_distinct_selector_ties_never_use_other_selector_as_secondary_key():
    # Equal depth, later episode longer: deepest keeps earlier peak.
    r=check([100,80,100,80,80,100])
    assert r['deepest']['peak']['index']==0 and r['longest_observed']['peak']['index']==2
    # Equal span, later episode deeper: longest keeps earlier peak.
    r=check([100,90,100,80,100])
    assert r['deepest']['peak']['index']==2 and r['longest_observed']['peak']['index']==0
