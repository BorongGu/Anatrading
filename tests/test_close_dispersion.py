"""Independent exact oracles for the fixed, current-inclusive source window."""
from copy import deepcopy
from decimal import Context, Decimal, ROUND_DOWN, localcontext
from fractions import Fraction
import json

import pytest

from anatrading.close_dispersion import _interval, dispersion_report, exact_window
from test_research_series import source_query, source_row

MAX = '99999999999999999999.999999999999999999'
ADJ = '99999999999999999999.999999999999999998'
CASES = [
    ['1', '1.000000000000000001'] * 10,
    ['10000000000000000000', '10000000000000000001'] * 10,
    ['0.000000000000000001', '0.000000000000000002'] * 10,
    ['99', '101'] + ['100'] * 18, ['100'] * 20,
    ['0'] * 20, ['0', '1'] * 10, ['0', '1e-18'] * 10,
    ['1e-18', MAX] * 10, ['0'] * 19 + ['1'],
    [MAX] * 20, [ADJ, MAX] * 10, ['1'] * 19 + ['100'],
    list(map(str, range(140, 160))), ['100'] * 19 + ['120'],
    ['0'] * 19 + ['1e-18'], ['0', MAX] * 10,
]


def query(prices):
    return source_query(prices, batch_id='batch', selection=dict(mode='retrospective', cutoff=None),
                        manifest=dict(raw_sha256='raw', source_contract_id='contract', qualification='synthetic'),
                        metadata=dict(period='1d', source_code='600000', source_venue='SH'))


def bisect_sqrt(n):
    lo, hi = 0, 1 << ((n.bit_length() + 1) // 2)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if mid * mid <= n:
            lo = mid
        else:
            hi = mid - 1
    return lo


@pytest.mark.parametrize('prices', CASES)
def test_centered_fraction_pairwise_and_independent_root(prices):
    result = exact_window(prices)
    values = list(map(Fraction, prices))
    mean = sum(values) / 20
    variance = sum((v - mean) ** 2 for v in values) / 20
    units = [int(v * 10**18) for v in values]
    d = sum((a - b)**2 for i, a in enumerate(units) for b in units[i+1:])
    assert result['sum_u'] == str(sum(units))
    assert result['sum_squares_u'] == str(sum(v*v for v in units))
    assert result['dispersion_numerator'] == str(d)
    assert Fraction(result['mean_exact']) == mean
    assert Fraction(result['variance_exact']) == variance
    n = variance * 10**72
    assert n.denominator == 1
    a = bisect_sqrt(n.numerator)
    b = a if a*a == n else a + 1
    assert a*a <= n < (a+1)**2
    expected = {'sigma': (Fraction(a, 10**36), Fraction(b, 10**36)),
                'envelope_lower': (mean-2*Fraction(b, 10**36), mean-2*Fraction(a, 10**36)),
                'envelope_upper': (mean+2*Fraction(a, 10**36), mean+2*Fraction(b, 10**36))}
    for name, (lower, upper) in expected.items():
        interval = result[name]
        assert (Fraction(interval['lower']), Fraction(interval['upper'])) == (lower, upper)
        assert interval['exact'] is (lower == upper)
    assert json.loads(json.dumps(result)) == result
    assert all(type(value) is not float for value in result.values())


@pytest.mark.parametrize('prices', CASES)
def test_hostile_decimal_context_independence(prices):
    expected = exact_window(prices)
    context = Context(prec=2, rounding=ROUND_DOWN, Emin=-2, Emax=2)
    for signal in context.traps:
        context.traps[signal] = True
    with localcontext(context):
        assert exact_window(prices) == expected


@pytest.mark.parametrize('value', [True, 1.0, None, 'NaN', 'Infinity', '1e20', '1e-19', '-1'])
def test_rejected_source_values(value):
    with pytest.raises(ValueError):
        exact_window([value] + ['1'] * 19)


@pytest.mark.parametrize('values', [[], [None]*19, [None]*21, iter(['1']*20), '1'*20])
def test_length_before_parsing(values):
    with pytest.raises(ValueError, match='^invalid_window_length$'):
        exact_window(values)


@pytest.mark.parametrize('low,high,display,reason', [
    (5*10**31, 5*10**31, '0.0000', None),
    (15*10**31, 15*10**31, '0.0002', None),
    (-5*10**31, -5*10**31, '0.0000', None),
    (-15*10**31, -15*10**31, '-0.0002', None),
    (5*10**31-1, 5*10**31+1, None, 'ambiguous_display_rounding'),
    (-5*10**31-1, -5*10**31+1, None, 'ambiguous_display_rounding'),
    (-1, 1, '0.0000', None),
])
def test_display_rounding_boundaries(low, high, display, reason):
    result = _interval(low, high)
    assert result['display'] == display and result['display_reason'] == reason
    assert Fraction(result['lower']) == Fraction(low, 10**36)


def test_invalid_current_window_and_recovery_without_compression():
    q = query(['10'] * 60)
    q['rows'][25]['values']['open'] = '0'
    before = deepcopy(q)
    rows = dispersion_report(q)['series']
    assert all(r['reason'] == 'history_insufficient' for r in rows[:19])
    assert rows[24]['status'] == 'computed'
    assert all(r['reason'] == 'invalid_window' for r in rows[25:45])
    assert rows[45]['status'] == 'computed'
    for i, row in enumerate(rows):
        assert row['position'] == i
        assert row['window_start_position'] == max(0, i-19)
        assert row['window_end_position'] == i and row['window_count'] == min(i+1, 20)
    assert rows[25]['invalid_members'] == [dict(position=25, date=q['rows'][25]['label'], ordinal=26, reason='invalid_price')]
    assert rows[25]['mean_exact'] is None and rows[25]['sigma'] is None
    assert q == before


def test_duplicates_dated_errors_unreadable_and_empty_coverage():
    q = query(['10']*30)
    q['rows'].append(source_row(2, '9', ordinal=40))
    row = q['rows'].pop(5)
    row.update(label=None, tokens=dict(source_date='20260106'))
    q['unlocated'] = [row, source_row(90, label=None)]
    report = dispersion_report(q)
    assert report['qualification'] == 'source_coverage_unknown'
    assert report['series'][2]['source_reason'] == 'duplicate_date'
    assert report['series'][2]['ordinal'] is None
    assert report['series'][5]['source_reason'] == 'unlocated_label'
    assert len(report['series']) == 30
    assert report['coverage']['unreadable_date_rows'] == 1
    assert len(report['series'][19]['invalid_members']) == 2
    assert dispersion_report(query([]))['series'] == []


@pytest.mark.parametrize('field', ['open', 'high', 'low', 'close'])
def test_adapter_strict_positive_separate_from_core_zero(field):
    q = query(['1']*20)
    q['rows'][10]['values'][field] = '0'
    assert dispersion_report(q)['series'][-1]['reason'] == 'invalid_window'
    assert exact_window(['0']*20)['variance_exact'] == '0'


@pytest.mark.parametrize('kind,reason', [('code', 'source_identity_conflict'), ('adjust', 'source_adjustment_conflict'), ('quarantine', 'known_negative_source')])
def test_source_checks_retained(kind, reason):
    q = query(['10']*20)
    if kind == 'code':
        q['rows'][4]['tokens']['code'] = '600001'
    elif kind == 'adjust':
        q['metadata']['source_adjustflag'] = '1'
        q['rows'][4]['tokens']['adjustflag'] = '2'
    else:
        q['metadata']['quarantined'] = True
    result = dispersion_report(q)
    assert result['series'][4]['source_reason'] == reason
    if kind == 'quarantine':
        assert result['qualification'] == 'source_rejected'


def test_volume_amount_do_not_block_and_negative_lower_is_valid():
    q = query(['1']*19+['100'])
    for row in q['rows']:
        row['values'].update(volume='invalid', amount=None)
    result = dispersion_report(q)['series'][-1]
    assert result['status'] == 'computed'
    assert Fraction(result['envelope_lower']['upper']) < 0


def test_all_prefixes_future_revision_and_physical_order():
    q = query([str(100+i%7) for i in range(55)])
    q['rows'][25]['values']['close'] = None
    full = dispersion_report(q)
    for count in range(56):
        prefix = deepcopy(q)
        prefix['rows'] = prefix['rows'][:count]
        assert dispersion_report(prefix)['series'] == full['series'][:count]
    revised = deepcopy(q)
    revised['rows'][50] = source_row(50, '1000')
    assert dispersion_report(revised)['series'][:50] == full['series'][:50]
    q['rows'].reverse()
    assert dispersion_report(q) == full


@pytest.mark.parametrize('key', ['snapshot_id', 'batch_id', 'query_id'])
def test_missing_query_identity(key):
    q = query(['1']*20)
    q.pop(key)
    with pytest.raises(ValueError, match='invalid_dispersion_query'):
        dispersion_report(q)


def test_identity_refs_cutoff_and_conflicts():
    q = query(['1']*25)
    report = dispersion_report(q)
    for key in ['snapshot_id', 'batch_id', 'query_id']:
        changed = deepcopy(q)
        changed[key] = 'changed'
        assert dispersion_report(changed)['identity'] != report['identity']
    q['selection']['cutoff'] = q['rows'][19]['label']
    assert len(dispersion_report(q)['series']) == 20
    q['metadata']['interpretation'] = dict(instrument='600001.SH')
    with pytest.raises(ValueError, match='research_identity_conflict'):
        dispersion_report(q)


@pytest.mark.parametrize('change,error', [
    ('period', 'unsupported_period'), ('ordinal', 'ordinal_window_not_supported'),
    ('cutoff', 'invalid_cutoff'), ('mode', 'invalid_dispersion_query'),
    ('limit', 'research_row_limit'), ('manifest', 'invalid_dispersion_query'),
])
def test_request_boundaries(change, error):
    q = query(['1']*20)
    if change == 'period': q['metadata']['period'] = '1m'
    if change == 'ordinal': q['selection']['ordinal_start'] = 0
    if change == 'cutoff': q['selection']['cutoff'] = '20260101'
    if change == 'mode': q['selection']['mode'] = 'window'
    if change == 'limit': q['unlocated'] = [source_row(0)]*19981
    if change == 'manifest': q['manifest'].pop('raw_sha256')
    with pytest.raises(ValueError, match=error):
        dispersion_report(q)
