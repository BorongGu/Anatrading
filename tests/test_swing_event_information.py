"""Test-first frozen legacy behavior and exact, bounded lagged-ER connection."""
from contextlib import nullcontext
from copy import deepcopy
from datetime import date, timedelta
from decimal import localcontext
from fractions import Fraction
import hashlib
import importlib
import json
from pathlib import Path

import pytest

from anatrading.event_study import event_report
from anatrading.research_series import daily_bars
from anatrading.signal_research import signal_report

FIXTURE = Path(__file__).parent / 'fixtures' / 'swing_event_information_legacy.json'
FIELDS = ['open', 'high', 'low', 'close', 'volume', 'amount']
VERSIONS = {'schema': '1', 'decode': '1', 'normalization': 'disabled-1', 'quality': '1',
            'numeric': 'decimal38.18-bigint-v1'}


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def query_for(prices, *, start='2025-12-01'):
    first = date.fromisoformat(start)
    rows = [dict(ordinal=i+1, label=(first+timedelta(days=i)).isoformat(), tokens={}, checks=[],
                 values=dict.fromkeys(('open','high','low','close'), str(p))) for i,p in enumerate(prices)]
    cutoff = max('2026-02-01', rows[-1]['label'] if rows else '2026-02-01')
    selection = dict(snapshot_id='a'*64, mode='retrospective', cutoff=cutoff,
                     ordinal_start=None, ordinal_end=None, fields=FIELDS, versions=VERSIONS)
    return dict(snapshot_id='a'*64, batch_id='b'*64,
                query_id=hashlib.sha256(canonical(selection).encode()).hexdigest(),
                selection=selection, metadata=dict(period='1d', source_code='sh.600001', source_adjustflag='3'),
                manifest=dict(raw_sha256='c'*64, source_contract_id='d'*64, versions=VERSIONS),
                rows=rows, unlocated=[], batch_checks=[], counts=dict(batch_unlocated_rows=0))


def report(query, **changes):
    dates = dict(report_start='2025-12-01', test_start='2026-01-01', cutoff=query['selection']['cutoff'])
    dates.update(changes)
    return importlib.import_module('anatrading.swing_event_information').swing_event_report(query, **dates)


def fraction(value):
    return None if value is None else Fraction(int(value['numerator']), int(value['denominator']))


def check_period(period, *, admitted):
    old = period['old_counts']; q = period['selection_qualification']
    assert old['raw_events'] == old['overlap_excluded'] + old['selected_events']
    assert old['selected_events'] == sum(old[k] for k in ('valid','immature','invalid','purged'))
    assert old['valid'] == q['comparable'] + q['source_unavailable_valid'] + q['internal_failure_valid']
    assert old['selected_events'] == sum(q[k] for k in (
        'condition_computed','condition_source_unavailable','condition_internal_failure'))
    assert sum(sum(v.values()) for v in period['label_evaluation_counts'].values()) == old['raw_events']
    assert sum(sum(v.values()) for v in period['qualification_counts'].values()) == old['raw_events']
    if not admitted:
        assert all(period[k] is None for k in ('condition_counts','groups','costs','delta','distinct_signal_dates'))
        return
    c=period['condition_counts']; groups=period['groups']
    assert q['condition_computed'] == c['D_true']+c['D_false']
    assert c['D_true'] == c['E_true']+c['E_false']
    assert groups['a1']['count'] == groups['e_true']['count']+groups['e_false']['count']
    for g in groups.values():
        assert g['count'] == sum(g[k] for k in ('positive_count','zero_count','negative_count'))
    a,b=groups['e_true'],groups['e_false']
    expected=(Fraction(a['zero_count']+a['negative_count'],a['count'])-
              Fraction(b['zero_count']+b['negative_count'],b['count'])) if a['count'] and b['count'] else None
    assert fraction(period['delta']) == expected
    assert period['costs']['missed_positive_count'] == b['positive_count']
    expected_miss=Fraction(b['positive_count'],groups['a1']['positive_count']) if groups['a1']['positive_count'] else None
    assert fraction(period['costs']['missed_positive_fraction']) == expected_miss


@pytest.mark.parametrize('index', range(14))
def test_frozen_complete_legacy_outputs(index):
    case=json.loads(FIXTURE.read_text())['cases'][index]
    context=localcontext() if case.get('context_precision') else nullcontext()
    with context as ctx:
        if ctx is not None: ctx.prec=case['context_precision']
        q=case['query']; d=case['dates']
        assert event_report(daily_bars(q),20,5,d['test_start'],d['cutoff']) == case['legacy_event']
        assert signal_report(q,20,5,d['test_start']) == case['legacy_signal']


@pytest.mark.parametrize('index', range(14))
def test_frozen_cases_old_projection_and_conservation(index):
    module=importlib.import_module('anatrading.swing_event_information')
    case=json.loads(FIXTURE.read_text())['cases'][index]
    q=case['query']; before=deepcopy(q)
    context=localcontext() if case.get('context_precision') else nullcontext()
    with context as ctx:
        if ctx is not None: ctx.prec=case['context_precision']
        result=module.swing_event_report(q,**case['dates'])
    assert q==before
    assert result['legacy']=={k:case['legacy_event'][k] for k in ('counts','partitions')}
    assert len(result['events'])==len(case['legacy_event']['rows'])
    for actual,old in zip(result['events'],case['legacy_event']['rows']):
        assert {k:actual[k] for k in old}==old
    for period in result['periods'].values():
        check_period(period,admitted=result['calculation_status']=='computed')
    assert result['parameters']['lookback']==20 and result['parameters']['horizon']==5
    assert result['parameters']['efficiency_lookback']==10 and result['parameters']['lag']==1
    assert result['historical_availability']=='unverified'
    canonical(result)


def test_covered_close_still_preserves_old_valid_and_null_conditions():
    q=query_for(range(100,190)); q['unlocated']=[dict(ordinal=999,label=None,tokens={},values={})]
    q['counts']['batch_unlocated_rows']=1
    result=report(q)
    assert result['calculation_status']=='source_unavailable'
    p=result['periods']['primary']; assert p['old_counts']['valid']>0
    assert p['selection_qualification']['comparable']==0
    assert p['selection_qualification']['source_unavailable_valid']==p['old_counts']['valid']
    assert p['selection_qualification']['condition_computed']==0
    check_period(p,admitted=False)
    assert all(e['background'] is None and e['label_sign'] is None for e in result['events'])


@pytest.mark.parametrize('count', [0,20,21,25,26,80])
def test_no_event_warm_history_maturity_and_zero_path(count):
    result=report(query_for([10]*count))
    assert result['calculation_status']=='computed' and result['events']==[]
    for p in result['periods'].values():
        check_period(p,admitted=True)
        assert p['delta'] is None
        assert p['costs']['retention'] is None


def test_lagged_background_independent_of_valid_current_and_future_prices():
    q=query_for(range(100,190)); first=report(q)
    target=first['events'][10]; i=target['index']
    changed=deepcopy(q)
    changed['rows'][i]['values']=dict.fromkeys(('open','high','low','close'),'999')
    after=report(changed)
    event=next(e for e in after['events'] if e['index']==i)
    assert event['background']==target['background']
    future=deepcopy(q)
    for row in future['rows'][i+1:]: row['values']=dict.fromkeys(('open','high','low','close'),'2')
    later=report(future)
    assert [(e['index'],e['selected'],e['background']) for e in later['events'] if e['index']<=i] == [
        (e['index'],e['selected'],e['background']) for e in first['events'] if e['index']<=i]


def test_b_only_selection_not_reset_at_report_start_or_test_start():
    q=query_for(range(100,200)); r=report(q)
    expected=list(range(20,100,6))
    assert [e['index'] for e in r['events'] if e['selected']]==expected
    changed=report(q,report_start='2025-12-30',test_start='2026-01-04')
    assert [e['index'] for e in changed['events'] if e['selected']]==expected
    for key,p in r['periods'].items():
        assert p['old_counts']['raw_events']==sum(p['start']<=e['date']<=p['end'] for e in r['events'])


def test_numeric_sign_extremes_are_not_extra_filtered_events():
    maximum='99999999999999999999.999999999999999999'
    q=query_for(['1e-18']*20+[maximum]+['1e-18']*5)
    r=report(q); e=r['events'][0]
    assert e['price_change']==-1 and e['end_close']=='0.000000000000000001'
    assert e['label_sign']=='negative' and e['comparison_status']=='comparable'
    tiny=query_for(['9']*20+['10']+['10.000000000000000001']*5)
    e=report(tiny)['events'][0]
    assert e['price_change']>0 and e['label_sign']=='positive'


def test_source_scale_and_low_decimal_context_do_not_change_conditions():
    q=query_for([p+20*(i//11) for i,p in enumerate([100,109,100,109,100,109,100,109,100,109,110]*7)])
    baseline=report(q)
    assert baseline['events']
    with localcontext() as context:
        context.prec=2
        assert report(q)==baseline
    scaled=deepcopy(q)
    for row in scaled['rows']:
        row['values']={k:str(int(v)*7) for k,v in row['values'].items()}
    r=report(scaled)
    assert [(e['index'],e['selected'],e['background']['er'],e['background']['efficient']) for e in r['events']] == [
        (e['index'],e['selected'],e['background']['er'],e['background']['efficient']) for e in baseline['events']]


def test_calls_once_and_budget_before_formulas(monkeypatch):
    m=importlib.import_module('anatrading.swing_event_information'); counts={}
    for name in ('daily_bars','daily_coverage','event_report'):
        original=getattr(m,name)
        def call(*a,_name=name,_original=original,**k):
            counts[_name]=counts.get(_name,0)+1; return _original(*a,**k)
        monkeypatch.setattr(m,name,call)
    report(query_for(range(100,180)))
    assert counts==dict(daily_bars=1,daily_coverage=1,event_report=1)
    counts.clear(); q=query_for([10]);q['rows']=q['rows']*20001
    with pytest.raises(ValueError,match='^research_row_limit$'): report(q)
    assert counts=={}


@pytest.mark.parametrize('change,code', [
    ({'report_start':'20260101'},'invalid_swing_dates'),
    ({'report_start':'2026-01-01','test_start':'2026-01-01'},'invalid_swing_dates'),
    ({'report_start':'2020-01-01'},'invalid_swing_dates'),
    ({'cutoff':'2026-02-02'},'research_cutoff_mismatch'),
])
def test_date_validation(change,code):
    with pytest.raises(ValueError,match=f'^{code}$'): report(query_for(range(80)),**change)


@pytest.mark.parametrize('which', ['ordinal_start','ordinal_end'])
def test_no_ordinal_cropping(which):
    q=query_for(range(100,180));q['selection'][which]=1
    with pytest.raises(ValueError,match='^ordinal_window_not_supported$'):report(q)


def test_old_failure_and_whole_security_invariant_failure(monkeypatch):
    m=importlib.import_module('anatrading.swing_event_information'); original=m.event_report
    q=query_for(range(100,190))
    def legacy_failure(*a,**k):raise ArithmeticError('injected')
    monkeypatch.setattr(m,'event_report',legacy_failure)
    r=report(q)
    assert r['calculation_status']=='legacy_event_failure'
    assert r['legacy'] is r['events'] is r['periods'] is None
    def corrupt(*a,**k):
        old=original(*a,**k)
        event=next(x for x in old['rows'] if x['label_status']=='valid')
        event['price_change']=-event['price_change']
        return old
    monkeypatch.setattr(m,'event_report',corrupt)
    r=report(q)
    assert r['calculation_status']=='connection_invariant_failure'
    assert r['legacy'] is not None and r['events']
    assert all(e['background'] is None and e['label_sign'] is None and e['comparison_status']=='internal_failure' for e in r['events'])
    for p in r['periods'].values():check_period(p,admitted=False)


def test_actual_decoder_store_public_projection_and_old_outputs(tmp_path):
    from anatrading.store import EvidenceStore
    from test_formats import bao_payload
    rows=[]
    for i in range(100):
        label=(date(2025,12,1)+timedelta(days=i)).isoformat(); p=str(100+i)
        rows.append([label,'sh.600001',p,p,p,p,'100','1000','3'])
    with EvidenceStore(tmp_path/'store') as store:
        sid=store.import_bytes(bao_payload(rows,code='sh.600001'),'baostock-decoded-v0.9.4')['snapshot_id']
        cutoff=rows[-1][0];q=store.query(sid,cutoff=cutoff);projection=store._research_query(sid,cutoff=cutoff)
        before=canonical(q); old=signal_report(q,20,5,'2026-01-01')
        assert report(q)==report(projection)
        assert canonical(store.query(sid,cutoff=cutoff))==before
        assert signal_report(q,20,5,'2026-01-01')==old


@pytest.mark.parametrize('index', range(14))
def test_frozen_independent_exact_oracle(index):
    m=importlib.import_module('anatrading.swing_event_information')
    case=json.loads(FIXTURE.read_text())['cases'][index]
    r=m.swing_event_report(case['query'],**case['dates']); oracle=case['oracle']
    assert len(r['events'])==len(oracle['events'])
    for actual,expected in zip(r['events'],oracle['events']):
        for name in ('date','ordinal','index','selected','label_status','label_reason','evaluation_status','label_end','start_close','end_close','prior_high'):
            assert actual[name]==expected[name], (case['name'],name)
        assert actual['price_change']==expected['price_change_estimate']
        # The independent arithmetic oracle retains endpoint signs even when
        # source qualification closes the new public comparison.
        assert actual['label_sign']==(expected['label_sign'] if r['calculation_status']=='computed' else None)
        b, ref=actual['background'],expected['background']
        if ref is None:
            assert b is None
        else:
            for side in ('start','end'):
                for field in ('date','index','ordinal'):
                    assert b[f'{side}_{field}']==ref[side][field]
            for field, key in [('net','N'),('path','L'),('er','ER')]:
                assert fraction(b[field])==fraction(ref[key])
            assert b['direction_up']==ref['D'] and b['efficient']==ref['E']
            assert b['reason']==ref['reason']
    p=r['periods']['primary']; ref=oracle['primary']
    assert fraction(p['delta'])==fraction(ref['delta'])
    if ref['groups'] is None:
        assert p['groups'] is None
    else:
        for a,b in [('a0','A0'),('a1','A1'),('e_true','E_true'),('e_false','E_false')]:
            for field,key in [('count','count'),('positive_count','positive'),('zero_count','zero'),('negative_count','negative')]:
                assert p['groups'][a][field]==ref['groups'][b][key]
        assert fraction(p['costs']['retention'])==fraction(ref['retention'])
        assert p['costs']['missed_positive_count']==ref['missed_positive_count']
        assert fraction(p['costs']['missed_positive_fraction'])==fraction(ref['missed_positive_fraction'])


@pytest.mark.parametrize('index', range(14))
def test_frozen_oracle_distribution_estimates_with_predeclared_tolerance(index):
    case=json.loads(FIXTURE.read_text())['cases'][index]
    r=importlib.import_module('anatrading.swing_event_information').swing_event_report(case['query'],**case['dates'])
    expected=case['oracle']['primary']['groups']
    if expected is None:
        assert r['periods']['primary']['groups'] is None
        return
    ordinary=case['name'] not in ('tiny_legal_return','negative_rounds_minus_one')
    for actual_name,oracle_name in [('a0','A0'),('a1','A1'),('e_true','E_true'),('e_false','E_false')]:
        actual=r['periods']['primary']['groups'][actual_name]
        reference=expected[oracle_name]['statistics_exact']
        tolerance=fraction(reference['float_summary_absolute_tolerance'])
        for field in ('mean','median','q05','q25','q75','q95'):
            exact=fraction(reference[field])
            if exact is None:
                assert actual[field] is None
            elif ordinary:
                # Frozen plan §5: normal synthetic domain only. Never relax
                # this bound for a boolean, sign, count, fraction or extreme.
                assert abs(Fraction(actual[field])-exact)<=tolerance
            else:
                assert actual[field]==float(exact)


def test_analysis_identity_has_only_frozen_math_and_source_reference_keys():
    q=query_for(range(100,190)); r=report(q)
    bound={key:r[key] for key in ('method_id','protocol_version','inputs','source','parameters')}
    assert r['analysis_id']==hashlib.sha256(canonical(bound).encode()).hexdigest()
    changed=deepcopy(q);changed['counts']['batch_unlocated_rows']=1
    closed=report(changed)
    assert closed['analysis_id']==r['analysis_id']
    assert closed['calculation_status']=='source_unavailable'
    # This is a trusted-query boundary, not a second hash authentication layer.
    changed=deepcopy(q);changed['query_id']='referenced-not-recomputed'
    assert report(changed)['inputs'][0]['query_id']=='referenced-not-recomputed'


def test_append_beyond_frozen_cutoff_preserves_whole_report():
    q=query_for(range(100,180)); before=report(q)
    changed=deepcopy(q);future=date.fromisoformat(q['selection']['cutoff'])+timedelta(days=1)
    changed['rows'].append(dict(ordinal=81,label=future.isoformat(),tokens={},checks=[],
                               values=dict.fromkeys(('open','high','low','close'),'500')))
    after=report(changed)
    assert after['events']==before['events'] and after['periods']==before['periods']
    assert after['coverage']['source_rows']==before['coverage']['source_rows']+1
    assert after['coverage']['date_groups']==before['coverage']['date_groups']


@pytest.mark.parametrize('mutation,code', [
    (lambda q:q.pop('rows'),'invalid_swing_query'),
    (lambda q:q['manifest'].pop('raw_sha256'),'invalid_swing_query'),
    (lambda q:q['selection'].update(mode='as_known'),'invalid_swing_query'),
    (lambda q:q['metadata'].update(period='1m'),'unsupported_period'),
    (lambda q:q['metadata'].pop('source_code'),'research_identity_unavailable'),
])
def test_minimal_request_boundary(mutation,code):
    q=query_for(range(100,150));mutation(q)
    with pytest.raises(ValueError,match=f'^{code}$'):report(q)
