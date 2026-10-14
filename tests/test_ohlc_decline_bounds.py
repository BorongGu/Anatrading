"""Frozen exact acceptance: independent all-pairs hypothetical path oracle."""
from copy import deepcopy
from decimal import Context, localcontext
from fractions import Fraction
from itertools import product
import json

import pytest

from anatrading.ohlc_decline_bounds import exact_bounds, decline_bounds_report
from test_research_series import source_query, source_row

FIELDS = ('open', 'high', 'low', 'close')
MAX = '99999999999999999999.999999999999999999'


def query(n=3):
    return source_query(['100'] * n, batch_id='batch',
        manifest=dict(raw_sha256='a'*64, source_contract_id='synthetic', qualification={'kind': 'synthetic'}),
        selection=dict(mode='retrospective', cutoff=source_row(max(n-1, 0))['label']),
        metadata=dict(period='1d', source_code='600000', source_venue='SH'))


def report(q, start=None, end=None):
    return decline_bounds_report(q, start or '2026-01-01', end or q['selection']['cutoff'])


def fraction(v):
    return Fraction(int(v['numerator']), int(v['denominator']))


def oracle(bars, order):
    path = [(i, slot, Fraction(str(bar[FIELDS.index(slot)]))) for i, bar in enumerate(bars) for slot in order]
    candidates = [(max(Fraction(0), (p-v)/p), j, k) for j, (_, _, v) in enumerate(path)
                  for k, (_, _, p) in enumerate(path[:j])]
    depth = max((x[0] for x in candidates), default=Fraction(0))
    if not depth:
        return depth, None
    _, j, k = min((x for x in candidates if x[0] == depth), key=lambda x: (x[1], x[2]))
    return depth, (path, k, j)


@pytest.mark.parametrize('bars,code,index,field', [
    ([], 'invalid_ohlc_window', None, None), ([None]*254, 'invalid_ohlc_window', None, None),
    (iter([]), 'invalid_ohlc_window', None, None), ([[1]], 'invalid_ohlc_bar', 0, None),
    ([[True,1,1,1]], 'numeric_type', 0, 'open'), ([[1.,1,1,1]], 'numeric_type', 0, 'open'),
    ([[None,1,1,1]], 'numeric_type', 0, 'open'), ([['NaN',1,1,1]], 'nonfinite', 0, 'open'),
    ([['Infinity',1,1,1]], 'nonfinite', 0, 'open'), ([['1e20',1,1,1]], 'decimal_range', 0, 'open'),
    ([['1e-19',1,1,1]], 'decimal_scale', 0, 'open'), ([[0,1,1,1]], 'nonpositive_price', 0, 'open'),
    ([[-1,1,1,1]], 'nonpositive_price', 0, 'open'), ([[2,1,1,1]], 'invalid_ohlc', 0, None),
])
def test_invalid_first(bars, code, index, field):
    with pytest.raises(ValueError) as error:
        exact_bounds(bars)
    assert str(error.value) == code
    assert error.value.bar_index == index and error.value.field == field


@pytest.mark.parametrize('bars,expected', [
    ([(100,100,100,100),(100,120,80,100)], (Fraction(1,5), Fraction(1,3), 0)),
    ([(100,100,100,100),(120,120,80,80)], (Fraction(1,3), Fraction(1,3), Fraction(1,5))),
    ([(100,120,100,120),(120,120,80,100)], (Fraction(1,3), Fraction(1,3), Fraction(1,6))),
    ([(100,100,100,100)], (0,0,0)), ([(100,120,80,100)], (Fraction(1,5),Fraction(1,3),0)),
    ([(1,1,1,1),(2,2,2,2)], (0,0,0)),
    ([(MAX,MAX,'99999999999999999999.999999999999999998',MAX)], (Fraction(1,10**38-1),)*2+(0,)),
])
def test_fixed(bars, expected):
    r = exact_bounds(bars)
    assert tuple(fraction(r[k]['value']) for k in ('lower','upper','close_only')) == expected
    assert fraction(r['ambiguity_width']) == expected[1]-expected[0]
    assert r['identified'] == (expected[0] == expected[1])
    assert json.loads(json.dumps(r)) == r


def assert_oracle(bars):
    r = exact_bounds(bars)
    for key, order in [('lower', ('open','low','high','close')), ('upper', FIELDS)]:
        value, endpoints = oracle(bars, order)
        assert fraction(r[key]['value']) == value
        w = r[key]['witness']
        if endpoints is None:
            assert w is None
        else:
            path, k, j = endpoints
            assert w['hypothetical'] is True
            for name, pos in [('peak',k),('trough',j)]:
                i, slot, price = path[pos]
                assert w[name]['bar_index'] == i and w[name]['slot'] == slot
                assert w[name]['path_position'] == pos and Fraction(w[name]['price_exact']) == price
    assert fraction(r['close_only']['value']) <= fraction(r['lower']['value']) <= fraction(r['upper']['value']) < 1


def test_all_ohlc_equalities_pairs_and_witnesses():
    bars = [v for v in product((1,2,3), repeat=4) if v[2] <= v[0] <= v[1] and v[2] <= v[3] <= v[1]]
    for b in bars:
        assert_oracle([b])
    for pair in product(bars, repeat=2):
        assert_oracle(pair)


def test_original_finite_domain():
    paths = [p for n in range(2,6) for p in product((1,2,3), repeat=n)]
    assert len(paths) == 360
    groups = {}
    count = 0
    def add(ps):
        nonlocal count
        bars = tuple((p[0],max(p),min(p),p[-1]) for p in ps)
        p = sum(ps, ())
        d = max([Fraction(0)] + [Fraction(a-b,a) for j,b in enumerate(p) for a in p[:j]])
        lo, hi = groups.get(bars, (d,d))
        groups[bars] = min(lo,d), max(hi,d)
        count += 1
    for p in paths: add((p,))
    for a,b in product(paths, repeat=2): add((a,b))
    assert count == 129960 and len(groups) == 420
    for bars, (lo, hi) in groups.items():
        r = exact_bounds(bars)
        assert (fraction(r['lower']['value']),fraction(r['upper']['value'])) == (lo,hi)
        assert_oracle(bars)


def test_context_prefix_scaling_and_large_window():
    bars = [(10,12,8,11),(11,20,5,10),(10,20,5,20)]
    for n in range(1,4): assert_oracle(bars[:n])
    r = exact_bounds(bars)
    context = Context(prec=1, Emin=-1, Emax=1)
    for signal in context.traps: context.traps[signal] = True
    with localcontext(context): assert exact_bounds(bars) == r
    scaled = exact_bounds([tuple(v*3 for v in b) for b in bars])
    for k in ('lower','upper','close_only'): assert scaled[k]['value'] == r[k]['value']
    assert exact_bounds([(1,1,1,1)]*253)['identified']
    assert exact_bounds([('1e-18',MAX,'1e-18',MAX)])['upper']['value']['numerator'] == str(10**38-2)


def test_adapter_computed_identity_and_immutability():
    q = query(); before = deepcopy(q)
    r = report(q)
    assert r['status'] == 'computed' and r['calendar_completeness'] == 'unverified'
    assert r['members'][0]['ordinal'] == '1'
    assert q == before
    r['identity']['source_qualification']['kind'] = 'changed'
    assert q == before


@pytest.mark.parametrize('kind,reason', [('duplicate','invalid_window'),('ordinal','invalid_window'),
    ('price','invalid_window'),('unlocated','source_coverage_unknown'),('batch','source_coverage_unknown'),
    ('quarantine','known_negative_source'),('code','source_identity_conflict')])
def test_adapter_rejections(kind, reason):
    q = query()
    if kind == 'duplicate': q['rows'].append(deepcopy(q['rows'][1]))
    if kind == 'ordinal': q['rows'][1]['ordinal'] = True
    if kind == 'price': q['rows'][1]['values']['low'] = 'bad'
    if kind == 'unlocated': q['unlocated'] = [source_row(9, label=None)]
    if kind == 'batch': q['counts'] = {'batch_unlocated_rows': 1}
    if kind == 'quarantine': q['metadata']['quarantined'] = True
    if kind == 'code': q['rows'][-1]['tokens']['code'] = 'wrong'
    r = report(q)
    assert r['reason'] == reason
    assert all(r[k] is None for k in ('lower','upper','close_only','identified','ambiguity_width'))


def test_conflicts_hidden_outside_window_first_reason_per_row():
    q = query(4); q['metadata']['source_adjustflag'] = '1'
    row = q['rows'][0]
    row['tokens'] = dict(code='wrong', adjustflag='2')
    row['checks'] = [dict(name='source_adjustment',outcome='fail')]*2
    q['rows'].append(deepcopy(row))
    q['rows'][1]['tokens']['adjustflag'] = '2'
    q['rows'][2]['checks'] = [dict(name='source_adjustment',outcome='fail')]*2
    before = deepcopy(q)
    r = report(q, start=q['rows'][3]['label'])
    assert r['source_conflict_counts'] == dict(source_identity_conflict=2,source_adjustment_conflict=1,source_adjustment_check_failed=1)
    assert q == before and r['status'] == 'unavailable'
    r = report(q)
    assert r['members'][0]['ordinal'] is None
    assert set(r['members'][0]) == {'index','date','ordinal',*FIELDS,'source_reason'}


def test_endpoints_outside_bad_future_and_volume():
    q = query(4); start=q['rows'][1]['label']
    q['rows'][0]['values']['low'] = 'bad'
    for row in q['rows']: row['values'].update(volume='bad',amount=None)
    r = report(q,start=start)
    assert r['status'] == 'computed' and r['coverage']['invalid_groups'] == 1
    q['rows'].append(source_row(100, '999'))
    assert report(q,start=start)['lower'] == r['lower']
    q['rows'][-1]['tokens']['code'] = 'wrong'
    assert report(q,start=start)['status'] == 'unavailable'
    q = query(); q['rows'].pop(0)
    assert report(q)['missing_endpoints'] == ['2026-01-01']


@pytest.mark.parametrize('change', ['shape','rows','values','tokens','checks','hash','id','mode','period','cutoff','ordinal'])
def test_bad_query_structure(change):
    q=query()
    if change=='shape': q['metadata']=[]
    if change=='rows': q['rows'][0]=None
    if change in ('values','tokens','checks'): q['rows'][0][change]=[None] if change=='checks' else []
    if change=='hash': q['manifest']['raw_sha256']='A'*64
    if change=='id': q['snapshot_id']='x'*257
    if change=='mode': q['selection']['mode']='other'
    if change=='period': q['metadata']['period']='1m'
    if change=='cutoff': q['selection']['cutoff']='20260103'
    if change=='ordinal': q['selection']['ordinal_start']=1
    with pytest.raises(ValueError): report(q, end='2026-01-03')


def test_limits():
    with pytest.raises(ValueError, match='ohlc_window_limit'): report(query(254))
    q=query(); q['manifest']['qualification']='x'*16384
    with pytest.raises(ValueError,match='ohlc_metadata_limit'): report(q)
    q=query(); q['rows'] *= 6667
    with pytest.raises(ValueError,match='research_row_limit'): report(q)


def test_all_prefixes_close_witness_and_monotone_bounds():
    bars = [(10,12,8,11),(11,20,5,10),(10,20,5,20),(20,20,4,4),(4,20,4,10)]
    previous = (0,0)
    for n in range(1,len(bars)+1):
        r=exact_bounds(bars[:n]); assert_oracle(bars[:n])
        expected, endpoints=oracle(bars[:n], ('close',))
        assert fraction(r['close_only']['value']) == expected
        if endpoints:
            path,k,j=endpoints
            assert r['close_only']['witness']['peak']['bar_index'] == path[k][0]
            assert r['close_only']['witness']['trough']['bar_index'] == path[j][0]
        current=tuple(fraction(r[k]['value']) for k in ('lower','upper'))
        assert all(a<=b for a,b in zip(previous,current)); previous=current
    flat=lambda prices: [tuple([p]*4) for p in prices]
    assert fraction(exact_bounds(flat([100,80]))['lower']['value']) == Fraction(1,5)
    assert fraction(exact_bounds(flat([200,180]))['lower']['value']) == Fraction(1,10)
    assert fraction(exact_bounds(flat([100,1,100]))['upper']['value']) == Fraction(99,100)
    assert fraction(exact_bounds(flat([100,100]))['upper']['value']) == 0
    assert fraction(exact_bounds(flat([80,100]))['lower']['value']) == 0


@pytest.mark.parametrize('ordinal', [None, -1, 2**63, '1', 1.0, False])
def test_bad_ordinals(ordinal):
    q=query(); q['rows'][0]['ordinal']=ordinal
    r=report(q)
    assert r['reason']=='invalid_window' and r['members'][0]['ordinal'] is None


def test_duplicate_ordinals_and_empty():
    q=query(); q['rows'][1]['ordinal']=q['rows'][0]['ordinal']
    assert report(q)['reason']=='invalid_window'
    r=report(query(0))
    assert r['reason']=='endpoint_not_present' and r['members']==[]


@pytest.mark.parametrize('start,end', [('20260101','2026-01-03'),('2026-01-01','2026-01-03T00:00:00'),
    ('2026-01-04','2026-01-03'),(None,'2026-01-03')])
def test_strict_requested_dates(start,end):
    with pytest.raises(ValueError,match='invalid_research_date'): decline_bounds_report(query(),start,end)


def test_exact_large_source_boundary_and_no_calendar_inference():
    q=query(20000); start=q['rows'][-253]['label']
    r=report(q,start=start)
    assert r['status']=='computed' and len(r['members'])==253
    assert r['coverage']['source_rows']==20000
    q['rows'].append(source_row(20001))
    with pytest.raises(ValueError,match='research_row_limit'): report(q,start=start)
    q=query(3); q['rows'].pop(1)
    assert report(q)['status']=='computed' and report(q)['calendar_completeness']=='unverified'


@pytest.mark.parametrize('key', ['snapshot_id','batch_id','query_id','raw_sha256','source_contract_id','qualification'])
def test_all_source_identity_changes(key):
    q=query(); old=report(q)
    if key in ('snapshot_id','batch_id','query_id'): q[key]='changed'
    else: q['manifest'][key]='b'*64 if key=='raw_sha256' else {'kind':'changed'} if key=='qualification' else 'changed'
    assert report(q)['identity']!=old['identity']
    assert report(q)['lower']==old['lower']


def test_identity_claim_conflict_and_batch_rejection():
    q=query(); q['metadata']['interpretation']={'instrument':'600001.SH'}
    with pytest.raises(ValueError,match='research_identity_conflict'): report(q)
    q=query(); q['batch_checks']=[dict(name='known_negative_sample',outcome='fail')]
    r=report(q)
    assert r['source_rejected'] and r['source_conflict_counts']=={}
