"""Independent rule, exact-value, three-valued and source-contract checks."""
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
from itertools import product
import json
import math

import pytest

from anatrading.research_api import _calculate
from anatrading.store import _identity
from anatrading.universe_research import universe_report
from anatrading.stock_filters import filter_report, normalize_rule, parse_rule, _combine, _compare
from test_pair_research import query


def atom(field='momentum', threshold='0', op=None):
    return dict(field=field, op=op or ('lte' if field == 'volatility' else 'gte'), threshold=threshold)


def rule(*groups):
    return dict(any_of=[dict(all_of=list(group)) for group in groups])


def calculate(queries=None, spec=None, cutoff='2026-01-03', lookback=2):
    queries = queries or [query([100, 120, 90]), query([10]*3, '000001.SZ')]
    return filter_report(queries, cutoff, lookback, spec or rule([atom()]))


def member(report, symbol='600001.SH'):
    return next(row for row in report['result']['members'] if row['identity']['symbol'] == symbol)


def golden_queries():
    qs = [query([10,20,15,12,18,15]), query([4]*6, '000001.SZ'),
          query([3]*5, '600002.SH'), query([10]*6, '600003.SH')]
    qs[-1]['rows'][2]['values']['close'] = '0'
    return qs


@pytest.mark.parametrize('n,pure_hash,api_hash', [
    (2,'9737466e6a3e3a64300ad530ccffd59465b769fa574f8178d514270f89fc1cee',
     '4e90d1b8288d0c815881a58cf2608e93f64e2c3e67d9bb31ccc2f7453ea62fce'),
    (5,'ec28de4f822915a0017880b1273207dce55c8b29017ecfadf083e5213760a6a5',
     'ad5e32eb48492b6e864d9d56541a3a7fd04f81d6fe2ac412f0c634f624cb4d81'),
])
def test_old_universe_and_envelope_frozen_before_refactor(n, pure_hash, api_hash):
    qs, params = golden_queries(), dict(cutoff='2026-01-06', lookback=n)
    assert _identity(universe_report(qs, **params)) == pure_hash
    assert _identity(_calculate('universe', qs, params, ValueError)) == api_hash


@pytest.mark.parametrize('bad', [None, [], {}, {'any_of': []}, {'any_of': [{}]},
    {'any_of': [{'all_of': []}]}, {'any_of': [{'all_of': [dict(any_of=[])]}]},
    {'any_of': [{'all_of': [atom()]}], 'version': 1}])
def test_invalid_rule_shapes(bad):
    with pytest.raises(ValueError, match='invalid_filter_rule'):
        normalize_rule(bad)


@pytest.mark.parametrize('bad', [None, True, 0, .1, '', ' 0', '+0', '01', '.1', '1.',
    'NaN', 'Infinity', '-Infinity', '1e-2', '10%', '0.1234567890123456789', '9'*100])
def test_invalid_threshold_types_and_grammar(bad):
    with pytest.raises(ValueError, match='invalid_filter_threshold'):
        normalize_rule(rule([atom(threshold=bad)]))


@pytest.mark.parametrize('field,value', [('momentum','-1.01'), ('momentum','10.01'),
    ('volatility','-0.1'), ('volatility','1.01'), ('max_drawdown','-1.01'), ('max_drawdown','0.01')])
def test_threshold_domains(field, value):
    with pytest.raises(ValueError, match='invalid_filter_threshold'):
        normalize_rule(rule([atom(field, value)]))


@pytest.mark.parametrize('spec,code', [
    (rule([atom('rank')]), 'unsupported_filter_field'),
    (rule([atom(op='eq')]), 'invalid_filter_operator'),
    (rule([atom(), atom(threshold='1')]), 'duplicate_filter_field'),
    (rule([atom()], [atom(threshold='0.00')]), 'duplicate_filter_group'),
    (rule([atom()], [atom(threshold='1')], [atom(threshold='2')]), 'filter_rule_limit'),
    (rule([atom()]*4), 'filter_rule_limit'),
])
def test_unknown_duplicate_and_budget_rules(spec, code):
    with pytest.raises(ValueError, match=code):
        normalize_rule(spec)


@pytest.mark.parametrize('text', ['{"any_of":[],"any_of":[]}',
    '{"any_of":[{"all_of":[{"field":"momentum","op":"gte","threshold":NaN}]}]}',
    '['*900+']'*900, '\ud800'])
def test_json_errors_are_bounded_and_never_execute(text):
    with pytest.raises(ValueError, match='invalid_filter_rule'):
        parse_rule(text)
    with pytest.raises(ValueError, match='filter_rule_limit'):
        parse_rule(' '*2049)


def test_all_three_value_assignments_use_independent_boolean_completions():
    for n in range(1, 7):
        for values in product(('true','false','unknown'), repeat=n):
            options = [(True, False) if v == 'unknown' else (v == 'true',) for v in values]
            for op, reference in [('all', all), ('any', any)]:
                possible = {reference(v) for v in product(*options)}
                expected = 'true' if possible == {True} else 'false' if possible == {False} else 'unknown'
                assert _combine(op, values) == expected


@pytest.mark.parametrize('value,truth', [(math.nextafter(.5, 0),'true'), (.5,'true'),
                                      (math.nextafter(.5, 1),'false')])
def test_binary_estimate_comparison_has_no_hidden_epsilon(value, truth):
    assert _compare(Fraction.from_float(value), 'lte', Fraction('0.5')) == truth


@pytest.mark.parametrize('field,prices,threshold,expected', [
    ('momentum',['10000000000000000000']*2+['10499999999999999999'],'0.05','false'),
    ('momentum',['10000000000000000000']*2+['10500000000000000001'],'0.05','true'),
    ('max_drawdown',['10000000000000000000']*2+['8999999999999999999'],'-0.1','false'),
    ('max_drawdown',['10000000000000000000']*2+['9000000000000000001'],'-0.1','true'),
])
def test_identical_float_displays_do_not_erase_exact_source_thresholds(field, prices, threshold, expected):
    with localcontext() as ctx:
        ctx.prec = 2
        row = member(calculate([query(prices), query([1]*3,'000001.SZ')], rule([atom(field,threshold)])))
    assert row['atoms'][0]['truth'] == expected
    fact = row['facts'][field]
    assert fact['value'] == float(threshold)
    exact = Fraction(int(fact['exact']['numerator']), int(fact['exact']['denominator']))
    assert (exact >= Fraction(threshold)) == (expected == 'true')


def test_hand_calculation_and_recovered_path_drawdown():
    qs = [query([10,20,15,12,18,15]), query([1]*6,'000001.SZ')]
    out = calculate(qs, rule([atom('momentum','0.5'), atom('max_drawdown','-0.3')]), '2026-01-06', 5)
    row = member(out)
    assert row['facts']['max_drawdown']['exact'] == dict(numerator='-2', denominator='5')
    assert row['selection_state'] == 'excluded'
    assert row['window']['drawdown_witness']['peak']['date'] == '2026-01-02'
    assert row['window']['drawdown_witness']['trough']['date'] == '2026-01-04'
    hand = member(calculate(spec=rule([atom('momentum','-0.1'), atom('max_drawdown','-0.25')])) )
    assert hand['selection_state'] == 'selected'
    assert hand['facts']['volatility']['value'] == pytest.approx(abs(math.log(1.2)-math.log(.75))/math.sqrt(2))


def test_valid_or_branch_and_false_and_preserve_unknowns(monkeypatch):
    import anatrading.universe_research as module
    monkeypatch.setattr(module, '_volatility', lambda prices:(None,'numerical_failure'))
    spec=rule([atom('momentum','0.05'),atom('volatility','0.02')],
              [atom('momentum','0.10'),atom('max_drawdown','-0.08')])
    qs=[query([100,100,112]),query([100,100,108],'000001.SZ'),query([100,100,90],'600002.SH')]
    out=calculate(qs,spec)
    states={r['identity']['symbol']:r for r in out['result']['members']}
    assert [states[s]['selection_state'] for s in ['600001.SH','000001.SZ','600002.SH']] == ['selected','undetermined','excluded']
    assert all(r['partial_evidence'] and not r['evidence_complete'] and r['source_gate']=='pass' for r in states.values())
    assert all(any(a['truth']=='unknown' and a['reason_refs'] for a in r['atoms']) for r in states.values())
    assert out['result']['counts']['selection'] == dict(selected=1,excluded=1,undetermined=1)
    only_m=calculate(qs,rule([atom()]))
    assert all(r['evidence_complete'] for r in only_m['result']['members'])


def test_source_date_gate_preserves_old_numeric_diagnostics():
    qs=[query([1]*3),query([2]*3,'000001.SZ')]
    qs[0]['unlocated']=[dict(ordinal=99,label=None,tokens={},values={})]
    old=universe_report(qs,'2026-01-03',2)
    out=calculate(qs)
    row=member(out)
    assert out['result']['universe']==old
    assert row['facts']['momentum']['value']==0
    assert row['source_gate']=='unknown' and row['selection_state']=='undetermined'
    assert row['atoms'][0]['truth']=='unknown' and row['primary_reason']=='date_set_integrity_unknown'


def test_bad_slots_keep_each_primary_without_revalidating_secondary_errors():
    a=query([1]*6)
    a['rows'].append(deepcopy(a['rows'][1]))
    a['rows'][2]['values']['close']='0'
    a['rows'][3]['tokens']=dict(code='other',adjustflag='2')
    a['rows'][3]['values']['high']=None
    a['metadata']['source_adjustflag']='3'
    out=calculate([a,query([2]*6,'000001.SZ')],cutoff='2026-01-06',lookback=5)
    row=member(out)
    assert row['source_gate']=='pass' and row['selection_state']=='undetermined'
    codes={r['code'] for r in row['reasons']}
    assert {'duplicate_date','invalid_price','source_identity_conflict'} <= codes
    assert 'source_adjustment_conflict' not in codes and 'missing_ohlc' not in codes
    duplicate=next(r for r in row['reasons'] if r['code']=='duplicate_date')
    assert duplicate['count']==1 and duplicate['examples'][0][1] is None


def test_reason_examples_are_bounded_without_discarding_slot_counts():
    a=query([1]*20)
    for row in a['rows']:
        row['values']['close']='0'
    r=member(calculate([a,query([2]*20,'000001.SZ')],cutoff='2026-01-20',lookback=19))
    item=next(r for r in r['reasons'] if r['code']=='invalid_price')
    assert item['count']==20 and len(item['examples'])==8 and item['omitted_count']==12


def test_summary_keeps_applicability_presence_and_original_qualification():
    base=[query([1]*3),query([2]*3,'000001.SZ')]
    field=dict(value='CNY',status='known',reason='documented_meaning_only')
    ids=[]
    for applicability in ['absent',None,'unverified']:
        qs=deepcopy(base)
        f=dict(field)
        if applicability!='absent': f['applicability']=applicability
        qs[0]['manifest']=dict(source_contract_id='contract',contract=dict(source_semantics=dict(fields=dict(price_unit=f))))
        out=calculate(qs)
        source=next(s for s in out['result']['sources'] if s['snapshot_id']==qs[0]['snapshot_id'])
        contract=next(c for c in out['result']['source_contracts'] if c['id']==source['contract_ref'])
        summary=contract['semantics']['price_unit']
        assert summary['status']==dict(present=True,value='known')
        assert summary['applicability']==dict(present=applicability!='absent',value=None if applicability=='absent' else applicability)
        assert member(out)['identity']['qualification']=='source_claim'
        ids.append(out['analysis_id'])
    assert len(set(ids))==3


def test_order_canonicalization_ids_and_base_envelope_match():
    qs=[query([1,2,3]),query([3,2,1],'000001.SZ')]
    spec=rule([atom('momentum','0.00'),atom('volatility','0.3')], [atom('max_drawdown','-0.1')])
    old=deepcopy((qs,spec))
    out=calculate(qs,spec)
    shuffled=deepcopy(spec)
    shuffled['any_of'].reverse()
    shuffled['any_of'][1]['all_of'].reverse()
    shuffled['any_of'][1]['all_of'][1]['threshold']='-0'
    assert calculate(list(reversed(qs)),shuffled)==out
    assert (qs,spec)==old
    base=_calculate('universe',sorted(qs,key=lambda q:q['snapshot_id']),dict(cutoff='2026-01-03',lookback=2),ValueError)
    assert out['base_analysis_id']==base['analysis_id']
    assert out['result']['universe']==base['result']
    assert calculate(qs,rule([atom(threshold='0.1')]))['analysis_id']!=out['analysis_id']


def test_future_prefix_and_missing_cutoff_are_not_backfilled():
    qs=[query([1,2,3,999]),query([2]*3,'000001.SZ')]
    out=calculate(qs)
    qs[0]['rows'][-1]['values']['close']='0'
    assert calculate(qs)==out
    qs[0]['rows']=qs[0]['rows'][:2]
    missing=member(calculate(qs))
    assert missing['source_gate']=='pass' and missing['selection_state']=='undetermined'
    assert missing['facts']['momentum']['reason']=='cutoff_missing'
    qs[0]['selection']=dict(cutoff='2026-01-02')
    with pytest.raises(ValueError,match='research_cutoff_mismatch'):
        calculate(qs)


def test_count_conservation_with_independent_member_enumeration():
    out=calculate(golden_queries(),rule([atom('momentum','0.1')],[atom('max_drawdown','-0.2')]),'2026-01-06',5)
    rows=out['result']['members'];counts=out['result']['counts'];n=len(rows)
    for group in ['selection','logical','evidence','source_gate']:
        assert sum(counts[group].values())==n
    for group in ['atoms','groups']:
        for key,values in counts[group].items():
            assert sum(values.values())==n
            for truth in ['true','false','unknown']:
                assert values[truth]==sum(next(a for a in r[group] if a['id']==key)['truth']==truth for r in rows)
    assert len({r['snapshot_id'] for r in rows})==n


def test_normalization_runs_once_per_source_and_not_per_atom(monkeypatch):
    import anatrading.universe_research as module
    original=module.daily_bars;calls=[]
    def tracked(q):
        calls.append(q['snapshot_id']);return original(q)
    monkeypatch.setattr(module,'daily_bars',tracked)
    spec=rule([atom(),atom('volatility','0.1'),atom('max_drawdown','-0.2')],
              [atom(threshold='0.1'),atom('volatility','0.2'),atom('max_drawdown','-0.3')])
    calculate(spec=spec)
    assert len(calls)==len(set(calls))==2
