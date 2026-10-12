"""Frozen synthetic controls; never opens private samples or an existing Store."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import json

import pytest

from anatrading.peer_neighbor_research import (
    peer_neighbor_report, _center, _correlation, _compare, _display, _price_integer,
)
from test_peer_relative_research import source_query, recount, fail


def fixture(members=5):
    dates = [(date(2026, 1, 1) + timedelta(days=2*t)).isoformat() for t in range(121)]
    a = [1] + [2, 1, 2, 1]*30
    b = [1] + [2, 1, 2, 1]*15 + [2, 4, 2, 1]*15
    c = [1] + [2, 4, 2, 1]*15 + [2, 1, 2, 1]*15
    prices = [a, b, c, b, [1]*121]
    queries = [source_query(f'{600000+i}.SH', prices[i % 5], dates) for i in range(members)]
    return queries, dates


def run(q, dates):
    return peer_neighbor_report(q, q[0]['snapshot_id'], dates[-1])


def row(r, q):
    return next(m for m in r['members'] if m['snapshot_id'] == q['snapshot_id'])


def candidate(r, q):
    return next(m for m in r['candidates'] if m['snapshot_id'] == q['snapshot_id'])


@pytest.mark.parametrize('defect', ['missing', 'extra', 'duplicate', 'known_bad_label', 'unknown_date', 'price', 'token', 'global_future'])
def test_source_failure_closes_both_windows_and_keeps_original_members(defect):
    q, days = fixture()
    if defect == 'missing': q[1]['rows'].pop(30)
    elif defect == 'extra':
        new = deepcopy(q[1]['rows'][30]); new['ordinal'] = 999
        new['label'] = new['tokens']['source_date'] = (date.fromisoformat(days[30]) + timedelta(days=1)).isoformat()
        q[1]['rows'].append(new)
    elif defect == 'duplicate':
        new = deepcopy(q[1]['rows'][30]); new['ordinal'] = 999; q[1]['rows'].append(new)
    elif defect in ('known_bad_label', 'unknown_date'):
        new = q[1]['rows'].pop(30); new['label'] = None
        if defect == 'unknown_date': new['tokens']['source_date'] = '?'
        q[1]['unlocated'].append(new)
    elif defect == 'price': q[1]['rows'][30]['values']['close'] = '0'
    elif defect == 'token': q[1]['rows'][30]['tokens']['close'] = '999'
    else:
        new = deepcopy(q[1]['rows'][-1]); new['ordinal'] = 999
        new['label'] = new['tokens']['source_date'] = '2026-12-31'
        fail(new, 'source_adjustment'); q[1]['rows'].append(new)
    recount(q[1]); r = run(q, days)
    assert r['status'] == 'unavailable' and r['counts']['selected'] == 5
    assert len(r['members']) == 5 and len(r['candidates']) == 4
    assert all(c['previous']['correlation'] is None and c['current']['correlation'] is None for c in r['candidates'])
    assert r['reasons'] == ['source_panel_unavailable']
    assert row(r, q[1])['reasons']


@pytest.mark.parametrize('defect', ['counts', 'ordinal', 'checks', 'semantics'])
def test_source_refusal_never_hides_structural_damage(defect):
    q, days = fixture(); q[1]['manifest']['qualification'] = 'unsupported'
    if defect == 'counts': q[1]['counts']['batch_rows'] += 1
    elif defect == 'ordinal': q[1]['rows'][1]['ordinal'] = q[1]['rows'][0]['ordinal']
    elif defect == 'checks': q[1]['rows'][1]['checks'] = [] + ['bad']
    else: q[1]['manifest']['contract']['source_semantics'] = {'fields': []}
    with pytest.raises(ValueError): run(q, days)


def test_target_anchor_exact_cutoff_no_fill_and_known_bad_group_included():
    q, days = fixture(); cutoff = (date.fromisoformat(days[-1]) + timedelta(days=1)).isoformat()
    r = peer_neighbor_report(q, q[0]['snapshot_id'], cutoff)
    assert r['used_dates'] == [] and r['windows']['current']['start'] is None
    assert r['anchor']['reasons'] == ['cutoff_missing']
    assert all(m['endpoints'] is None for m in r['members'])
    q[0]['rows'].pop(0); recount(q[0]); r = run(q, days)
    assert r['used_dates'] == [] and 'anchor_history_insufficient' in r['anchor']['reasons']
    q, days = fixture(); bad = q[0]['rows'].pop(30); bad['label'] = None; q[0]['unlocated'].append(bad); recount(q[0])
    r = run(q, days)
    assert r['used_dates'] == days and 'unlocated_endpoint' in row(r, q[0])['reasons']
    assert r['status'] == 'unavailable'


def test_source_refused_row_is_not_evaluated():
    q, days = fixture(); q[1]['metadata']['requested_adjustment'] = 'qfq'
    r = run(q, days); m = row(r, q[1])
    assert m['endpoints'] is None and m['anomalies'] is None
    assert m['source_qualified'] is False and m['evaluation'] == 'not_evaluated'
    assert m['reasons'] == ['source_adjustment_conflict']


def test_two_windows_switch_first_and_keep_exact_ties_and_constant():
    q, days = fixture(); before = deepcopy(q); r = run(q, days)
    assert q == before and r == peer_neighbor_report(list(reversed(q)), q[0]['snapshot_id'], days[-1])
    assert r['counts'] == dict(selected=5, candidates=4, source_qualified=5, panel_complete=5)
    assert r['used_dates'] == days and r['windows']['previous']['end'] == days[60]
    b, c, clone, constant = [candidate(r, x) for x in q[1:]]
    assert b['previous']['rank'] == clone['previous']['rank'] == 1
    assert b['previous']['tie_size'] == 2 and c['previous']['rank'] == 3
    assert c['current']['rank'] == 1 and b['current']['rank'] == 2
    assert b['previous']['correlation']['exact_boundary'] == 'positive_one'
    assert b['current']['correlation']['sign'] == 'zero'
    assert b['difference']['direction'] == 'decreased' and c['difference']['direction'] == 'increased'
    assert constant['current']['reason'] == 'constant_source_change'
    assert r['windows']['current']['available'] == 3 and r['status'] == 'partial'


def test_target_constant_only_disables_its_own_window():
    q, days = fixture(); prices = [1]*61 + [2,1,2,1]*15
    q[0] = source_query('600000.SH', prices, days); r = run(q, days)
    assert r['windows']['previous']['available'] == 0
    assert r['windows']['current']['available'] == 3
    assert all(c['previous']['reason'] == 'target_constant_source_change' for c in r['candidates'])


def test_exact_kernel_sign_order_true_ties_not_just_equal_series():
    a = _center(list(map(Fraction, [-1,0,1])))
    values = [_correlation(a, _center(list(map(Fraction, v)))) for v in
              ([-1,0,1], [1,3,5], [-1,1,0], [1,-2,1], [1,-1,0], [1,0,-1])]
    assert _compare(values[0], values[1]) == 0
    assert all(_compare(values[i], values[i+1]) > 0 for i in range(1,5))
    assert [_display(v)['sign'] for v in values] == ['positive','positive','positive','zero','negative','negative']
    assert _center([Fraction(2)]*60) is None


def test_display_equal_is_not_tie_or_exact_extreme_and_tiny_difference_survives():
    a = _center(list(map(Fraction, [-1,0,1])))
    values = [_correlation(a, _center([Fraction(-1), e, Fraction(1)])) for e in
              (Fraction(1,100), Fraction(1,200), Fraction(2,10**30), Fraction(1,10**30))]
    assert _compare(values[0], values[1]) < 0 and _compare(values[2], values[3]) < 0
    assert all(_display(v)['display'] == '1.0000' for v in values)
    assert all(_display(v)['exact_boundary'] == 'none' for v in values)
    assert _display(values[2])['estimate'] == _display(values[3])['estimate']
    with localcontext() as ctx:
        ctx.prec = 5
        assert _price_integer(Decimal('10000000000000000000.000000000000000001')) == 10**37+1


def test_fixed_prefix_numeric_invariance_and_no_event_input():
    q, days = fixture(); r = run(q, days)
    for item in q:
        later = deepcopy(item['rows'][-1]); later['ordinal'] = 999
        later['label'] = later['tokens']['source_date'] = '2026-12-31'
        later['values']['close'] = later['tokens']['close'] = '-1'
        fail(later, 'ohlc_bounds'); item['rows'].append(later); recount(item)
    later = run(q, days)
    assert later['candidates'] == r['candidates']
    with pytest.raises(TypeError): peer_neighbor_report(q, q[0]['snapshot_id'], days[-1], events=[])


def test_outside_source_token_identity_conflict_revokes_panel():
    q, days = fixture()
    extra = deepcopy(q[1]['rows'][-1]); extra['ordinal'] = 999
    extra['label'] = extra['tokens']['source_date'] = '2026-12-31'
    extra['tokens']['source_code'] = '600099.SH'
    q[1]['rows'].append(extra); recount(q[1])
    r = run(q, days)
    assert not r['source_panel_complete']
    assert 'global_source_conflict' in row(r, q[1])['reasons']


def test_failed_anchor_preserves_already_scanned_global_anomalies():
    q, days = fixture()
    extra = deepcopy(q[0]['rows'][-1]); extra['ordinal'] = 999; extra['label'] = None
    extra['tokens']['source_date'] = '?'; fail(extra, 'source_adjustment')
    q[0]['unlocated'].append(extra); recount(q[0]); r = run(q, days)
    target = row(r, q[0])
    assert r['used_dates'] == [] and target['endpoints'] is None
    assert 'global_source_conflict' in target['reasons']
    assert target['anomalies']['total'] == 1 and target['anomalies']['examples'][0]['scope'] == 'unknown'
    assert all(m['anomalies'] is not None for m in r['members'])


def test_member_limits_output_limit_integer_limit_and_duplicate_identity(monkeypatch):
    import anatrading.peer_neighbor_research as module
    for count in (2,50):
        q, days = fixture(count); r = run(q, days)
        assert len(r['members']) == count and len(r['candidates']) == count-1
    q, days = fixture()
    with pytest.raises(ValueError,match='invalid_target'): peer_neighbor_report(q,'f'*64,days[-1])
    with pytest.raises(ValueError,match='duplicate_member'): run([q[0],q[0]],days)
    other=source_query('600000.SH',[1]*121,days)
    with pytest.raises(ValueError,match='duplicate_member'): run([q[0],other],days)
    with monkeypatch.context() as patch:
        patch.setattr(module,'MAX_RESULT_BYTES',1)
        with pytest.raises(ValueError,match='peer_neighbor_result_limit'):run(q,days)
    with monkeypatch.context() as patch:
        patch.setattr(module,'MAX_INTEGER_BITS',16)
        with pytest.raises(ValueError,match='peer_neighbor_integer_limit'):_center([Fraction(1,65521),Fraction(1,65519)])


def test_shared_boundary_changes_both_windows_and_zero_quantity_does_not_infer_halt():
    q,days=fixture(4);before=run(q,days)
    for key in ('open','high','low','close'):q[0]['rows'][60]['values'][key]=q[0]['rows'][60]['tokens'][key]='3'
    r=run(q,days)
    assert r['source_panel_complete']
    assert candidate(r,q[1])['previous']['correlation'] != candidate(before,q[1])['previous']['correlation']
    assert candidate(r,q[1])['current']['correlation'] != candidate(before,q[1])['current']['correlation']
    for source in q:
        for point in source['rows']:
            point['tokens']['volume']='0';fail(point,'zero_volume_amount')
    zero=run(q,days)
    assert zero['source_panel_complete'] and zero['candidates']==r['candidates']
