"""Frozen path-retrieval failures and exact descriptive behavior."""
from copy import deepcopy
from decimal import Decimal, localcontext
import json

import pytest

from anatrading.historical_path_retrieval import historical_path_report
from test_pair_research import query


def report(prices, **kwargs):
    q = query(prices, **kwargs)
    return historical_path_report(q, q['rows'][-1]['label'])


@pytest.mark.parametrize('cutoff', ['', '2026-1-01', '2026-02-30', None])
def test_strict_cutoff_rejects(cutoff):
    with pytest.raises(ValueError, match='invalid_cutoff'):
        historical_path_report(query([1] * 42), cutoff)


def test_exact_endpoint_required_and_invalid_query_never_backfills():
    q = query([10] * 42)
    with pytest.raises(ValueError, match='path_cutoff_missing'):
        historical_path_report(q, '2026-02-12')
    q['rows'][-2]['values']['close'] = None
    with pytest.raises(ValueError, match='path_query_invalid'):
        historical_path_report(q, q['rows'][-1]['label'])
    with pytest.raises(ValueError, match='path_history_insufficient'):
        report([10] * 20)


def test_ordinal_window_and_wrong_cutoff_rejected():
    q = query([1] * 42)
    q['selection'] = dict(ordinal_start=1)
    with pytest.raises(ValueError, match='ordinal_window_not_supported'):
        historical_path_report(q, q['rows'][-1]['label'])
    q['selection'] = dict(cutoff='2026-01-21')
    with pytest.raises(ValueError, match='research_cutoff_mismatch'):
        historical_path_report(q, q['rows'][-1]['label'])


def test_quarantined_and_unknown_identity_reject_entire_source():
    q = query([10] * 42)
    q['metadata']['quarantined'] = True
    with pytest.raises(ValueError, match='known_negative_source'):
        historical_path_report(q, q['rows'][-1]['label'])
    q['metadata'] = dict(period='1d')
    with pytest.raises(ValueError, match='research_identity_unavailable'):
        historical_path_report(q, q['rows'][-1]['label'])


def test_query_overlap_never_enters_pool():
    for n, expected in [(21, 0), (41, 0), (42, 1), (63, 22)]:
        r = report([10] * n)
        assert r['counts']['path']['total'] == expected
        assert all(row[0] + 20 < r['query']['start_index'] for row in r['ledger'])
        assert r['query']['prices'] == ['10'] * 21
        assert len(r['query']['relative_path']) == 21


def test_duplicate_and_bad_groups_keep_their_slots_and_first_reason():
    q = query([10] * 65)
    q['rows'].append(deepcopy(q['rows'][10]))
    q['rows'][30]['values']['close'] = None
    r = historical_path_report(q, '2026-03-06')
    assert r['groups'][10] == '2026-01-11'
    assert len(r['groups']) == 65
    assert r['ledger'][0][1] == 'duplicate_date' and r['ledger'][0][7] == 10
    assert r['ledger'][11][1] == 'missing_ohlc' and r['ledger'][11][7] == 30
    assert r['counts']['path']['invalid'] == 24
    assert r['selections']['path'] == []


def test_hand_path_separates_same_endpoint_and_retains_raw_precision():
    # Padded five-point hand example: first 16 changes are flat.
    a = [100] * 17 + [108] * 4
    b = [50] * 17 + [51, 52, 53, 54]
    qpath = [100] * 17 + [102, 104, 106, 108]
    q = query(a + [None] + b + [None] + qpath)
    r = historical_path_report(q, q['rows'][-1]['label'])
    assert r['selections']['path'] == [22, 0]
    assert r['selections']['endpoint'] == [0, 22]
    ledger = {row[0]: row for row in r['ledger']}
    assert Decimal(ledger[0][2]) == Decimal('0.00028')
    assert Decimal(ledger[22][2]) == 0
    assert Decimal(ledger[0][3]) == Decimal(ledger[22][3]) == 0
    a_record = next(w for w in r['windows'] if w['start_index'] == 0)
    assert a_record['max_point_difference']['step'] == 17
    assert Decimal(a_record['max_point_difference']['value']) == Decimal('.06')
    assert Decimal(a_record['differences'][17]) == Decimal('-.06')


def test_exact_raw_strings_and_drawdown_witness():
    prices = ['10.000000000000000001'] * 42
    prices[3] = '20.000000000000000002'
    r = report(prices)
    w = r['windows'][0]
    assert w['prices'][0] == prices[0]
    assert w['max_drawdown'] == dict(value='5E-1', peak_step=3, trough_step=4)
    assert w['ordinals'] == list(range(1, 22))


def test_locatable_future_bad_label_does_not_poison_fixed_cutoff():
    q = query([10] * 70)
    cutoff = q['rows'][62]['label']
    baseline = historical_path_report(q, cutoff)
    q['unlocated'] = [dict(ordinal=71, label=None, tokens={'source_date': '20270401'}, values={})]
    q['counts'] = dict(batch_unlocated_rows=1)
    q['rows'][-1]['values']['close'] = None
    assert historical_path_report(q, cutoff) == baseline
    q['unlocated'][0]['tokens'] = {}
    with pytest.raises(ValueError, match='path_unreadable_date'):
        historical_path_report(q, cutoff)


def test_global_decimal_context_cannot_change_any_report():
    prices = ['0.000000000000000001', '99999999999999999999.999999999999999999'] * 32
    baseline = report(prices)
    with localcontext() as ctx:
        ctx.prec = 2
        ctx.rounding = 'ROUND_DOWN'
        assert report(prices) == baseline


def test_every_method_count_reconciles_and_no_selected_windows_overlap():
    r = report([10 + (i * 13 % 17) for i in range(160)])
    for method, selection in r['selections'].items():
        count = r['counts'][method]
        assert count['total'] == count['valid'] + count['invalid']
        assert count['valid'] == count['selected'] + count['overlap_excluded'] + count['remaining']
        assert all(abs(a - b) > 20 for i, a in enumerate(selection) for b in selection[i+1:])
    assert len(r['windows']) <= 9
    assert len({w['start_index'] for w in r['windows']}) == len(r['windows'])


def test_common_price_scale_changes_nothing_except_source_values():
    values = [10 + i % 13 for i in range(90)]
    a, b = report(values), report([v * 7 for v in values])
    assert a['ledger'] == b['ledger'] and a['selections'] == b['selections']
    assert a['query']['relative_path'] == b['query']['relative_path']


def test_input_limit_precedes_group_construction():
    with pytest.raises(ValueError, match='research_row_limit'):
        report([10] * 20_001)


@pytest.mark.parametrize('name', ['new_unknown_integrity_rule', 'structure', 'source_code',
                                  'source_adjustment', 'numeric.close', 'source_date_range', 'source_order'])
def test_failed_located_checks_stay_in_history_but_invalidate_containing_windows(name):
    q = query([10] * 65)
    q['rows'][0]['checks'] = [dict(name=name, outcome='fail')]
    r = historical_path_report(q, q['rows'][-1]['label'])
    assert r['ledger'][0][1] is not None and r['ledger'][0][7] == 0
    assert r['counts']['path']['invalid'] == 1
    assert r['selections']['path'][0] == 1
    q['rows'][-1]['checks'] = [dict(name=name, outcome='fail')]
    with pytest.raises(ValueError, match='path_query_invalid'):
        historical_path_report(q, q['rows'][-1]['label'])


def test_known_nonprice_failures_do_not_change_price_qualification():
    q = query([10] * 42)
    q['batch_checks'] = [dict(name='numeric.volume', outcome='fail')]
    q['rows'][0]['checks'] = [dict(name='nonnegative_amount', outcome='fail')]
    r = historical_path_report(q, q['rows'][-1]['label'])
    assert r['selections']['path'] == [0]
    assert r['nonprice_check_failures'] == {'numeric.volume': 1, 'nonnegative_amount': 1}


def test_phase_shift_can_lose_to_flat_reference_without_hiding_the_difference():
    shifted = [100, 100, 110] + [100] * 18
    flat = [100] * 21
    current = [100, 110] + [100] * 19
    r = report(shifted + [None] + flat + [None] + current)
    assert r['selections']['path'] == [22, 0]
    entries = {row[0]: row for row in r['ledger']}
    assert Decimal(entries[0][2]) == Decimal('.001')
    assert Decimal(entries[22][2]) == Decimal('.0005')


def test_amplitude_nearflat_and_wrong_anchor_are_not_standardized_away():
    current = [100 + i for i in range(21)]
    large = [100 + i * 10 for i in range(21)]
    nearflat = [str(Decimal(100) + Decimal(i) / 1_000_000) for i in range(21)]
    wrong_anchor = [200] + current[1:]
    for candidate in (large, nearflat, wrong_anchor):
        r = report(candidate + [None] + current)
        w = r['windows'][0]
        assert Decimal(w['distance']) > 0
        assert Decimal(w['max_point_difference']['value']) > 0
        assert w['prices'][0] == str(candidate[0])


def test_future_unknown_failed_check_is_removed_before_inspection():
    q = query([10] * 64)
    baseline = historical_path_report(q, q['rows'][62]['label'])
    q['rows'][-1]['checks'] = [dict(name='unknown_later_integrity', outcome='fail')]
    assert historical_path_report(q, q['rows'][62]['label']) == baseline


@pytest.mark.parametrize('extreme', [False, True])
def test_maximum_input_and_all_output_component_budgets(extreme):
    if extreme:
        units = [((i + 1) * 31415926535897932384626433832795028841) % (10**38 - 1) + 1 for i in range(20_000)]
        prices = [f'{value // 10**18}.{value % 10**18:018d}' for value in units]
    else:
        prices = [10 + i % 17 for i in range(20_000)]
    r = report(prices)
    encode = lambda value: json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()
    assert len(r['ledger']) == 19_959 and len(r['groups']) == 20_000
    assert max(len(encode(row)) + 1 for row in r['ledger']) <= 160
    assert max(len(encode(day)) + 1 for day in r['groups']) <= 13
    assert len(encode({k: v for k, v in r.items() if k not in ('groups', 'ledger')})) <= 256 * 1024
    assert len(encode(r)) <= 4 * 1024 * 1024
