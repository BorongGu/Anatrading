"""Independent 034 adversarial review; synthetic observations only.

The oracle below does not call product normalization, state, loss or window
helpers. Binary64 boundary tests independently compare the saved residuals.
No result establishes market calibration, historical availability or alpha.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import math

import pytest

import anatrading.forecast_diagnostics as diagnostic
import anatrading.signal_research as signal
from anatrading.research_series import daily_bars


NAMES = ('kalman', 'last_close', 'lagged_ema')


def day(i):
    return (date(2022, 1, 1) + timedelta(days=i)).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def query(prices, *, cutoff=None):
    end = day(len(prices) - 1) if cutoff is None else cutoff
    versions = {'synthetic_review': '034-v1'}
    selection = dict(snapshot_id='1' * 64, mode='retrospective', cutoff=end,
        ordinal_start=None, ordinal_end=None, fields=['open', 'high', 'low', 'close', 'volume', 'amount'],
        versions=versions)
    return dict(snapshot_id='1' * 64, batch_id='2' * 64, query_id=digest(selection),
        selection=selection, manifest=dict(raw_sha256='3' * 64, source_contract_id='4' * 64,
        versions=versions), metadata=dict(period='1d', source_code='600001.SH'),
        rows=[dict(ordinal=i+1, label=day(i), tokens={}, checks=[],
            values=dict.fromkeys(('open', 'high', 'low', 'close'), str(price)))
            for i, price in enumerate(prices)], unlocated=[],
        counts=dict(batch_unlocated_rows=0), batch_checks=[])


def result(q):
    return diagnostic.forecast_diagnostic_report(q, cutoff=q['selection']['cutoff'])


def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b)))
        for j in range(len(b[0]))] for i in range(len(a))]


def add(a, b):
    return [[x+y for x, y in zip(ar, br)] for ar, br in zip(a, b)]


def tr(a):
    return [list(column) for column in zip(*a)]


def reference(q):
    """Independent grouped-source + generic matrix oracle for this fixture set.

    It has deliberately separate storage and summation from product code. Only
    finite ordinary vectors are numerically compared; counts and membership
    are exact. Unknown source qualification is tested separately.
    """
    groups = defaultdict(list)
    for row in q['rows']:
        if row['label'] <= q['selection']['cutoff']:
            groups[row['label']].append(row)
    F, Q, R = [[1., 1.], [0., 1.]], [[1e-6, 0.], [0., 1e-8]], 1e-4
    alpha = 1 - 2 ** (-1 / 10)
    counts = dict(total_groups=0, forecast_origin_warmup=0, common_errors=0,
        source_or_state_unavailable=0, pre_window_insufficient=0, pre_window_complete=0)
    chain, segment, history, previous, x, P, ema = 0, 0, [], None, None, None, None
    snapshots = {}
    for stamp, rows in sorted(groups.items()):
        counts['total_groups'] += 1
        if len(rows) != 1 or Decimal(rows[0]['values']['close']) <= 0:
            chain, history, previous = 0, [], None
            counts['source_or_state_unavailable'] += 1
            snapshots[stamp] = dict(status='unavailable', counts=dict(counts), evidence=[])
            continue
        row = rows[0]
        y = math.log(float(row['values']['close']))
        if chain == 0:
            x, P, ema = [[y], [0.]], [[R, 0.], [0., R]], y
            segment += 1
            prior = None
        else:
            pred = mm(F, x)
            predP = add(mm(mm(F, P), tr(F)), Q)
            prior = [pred[0][0], previous, ema]
            innovation = y - pred[0][0]
            gain = [predP[0][0] / (predP[0][0]+R), predP[1][0] / (predP[0][0]+R)]
            x = [[pred[i][0] + gain[i]*innovation] for i in range(2)]
            A = [[1-gain[0], 0.], [-gain[1], 1.]]
            krk = [[a*b*R for b in gain] for a in gain]
            P = add(mm(mm(A, predP), tr(A)), krk)
            ema = (1-alpha)*ema + alpha*y
        chain += 1
        previous = y
        before = list(history)
        if chain <= 21:
            counts['forecast_origin_warmup'] += 1
            status, errors = 'warming_up', None
        else:
            errors = [y-v for v in prior]
            status = 'computed' if len(before) == 60 else 'history_insufficient'
            counts['common_errors'] += 1
            counts['pre_window_complete' if len(before) == 60 else 'pre_window_insufficient'] += 1
            history.append(dict(date=stamp, ordinal=row['ordinal'], errors=errors))
            history = history[-60:]
        snapshots[stamp] = dict(status=status, counts=dict(counts), evidence=before,
            predictions=prior, errors=errors, segment=segment, observations=chain)
    return snapshots


@pytest.mark.parametrize('broken', [None, 0, 20, 21, 60, 80, 81, 115])
@pytest.mark.parametrize('kind', ['zero', 'duplicate'])
def test_independent_matrix_window_and_counts_across_reset_edges(broken, kind):
    prices = [f'{100 + ((i*17) % 31)/100 + i/1000:.6f}' for i in range(200)]
    q = query(prices)
    if broken is not None:
        if kind == 'zero':
            q['rows'][broken]['values'] = dict.fromkeys(('open','high','low','close'), '0')
        else:
            dupe = deepcopy(q['rows'][broken]); dupe['ordinal'] = 1000
            q['rows'].append(dupe)
    q['rows'].reverse()  # Source ordinal/order is not the observation-step clock.
    before = deepcopy(q)
    ref = reference(q)[day(199)]
    actual = result(q)['result']
    assert q == before
    assert actual['cohort_counts'] == ref['counts']
    assert actual['calculation_status'] == ref['status']
    assert actual['current']['segment_id'] == ref['segment']
    assert actual['current']['segment_observations'] == ref['observations']
    assert [(e['observation_date'], e['observation_ordinal']) for e in actual['evidence']] == [
        (e['date'], e['ordinal']) for e in ref['evidence']]
    for k, model in enumerate(actual['models']):
        assert model['prediction_log'] == pytest.approx(ref['predictions'][k], abs=2e-11, rel=2e-10)
        assert model['error_log'] == pytest.approx(ref['errors'][k], abs=2e-11, rel=2e-10)
        magnitudes = [abs(e['errors'][k]) for e in ref['evidence']]
        if len(magnitudes) < 60:
            assert model['mae_pre'] is model['rmse_pre'] is model['abs_error_quantile'] is None
        else:
            assert model['abs_error_quantile'] == pytest.approx(sorted(magnitudes)[53], abs=2e-11)
            assert model['mae_pre'] == pytest.approx(math.fsum(magnitudes)/60, abs=2e-11)
            assert model['rmse_pre'] == pytest.approx(math.sqrt(math.fsum(e*e for e in magnitudes)/60), abs=2e-11)
            e, quantile = model['error_log'], model['abs_error_quantile']
            assert model['position'] == ('below' if e < -quantile else 'above' if e > quantile else 'inside')


@pytest.mark.parametrize('n', [20, 21, 22, 81, 82, 83])
def test_zero_paths_exact_origin_window_boundaries(n):
    actual = result(query(['1'] * n))['result']
    counts = actual['cohort_counts']
    assert counts['forecast_origin_warmup'] == min(n, 21)
    assert counts['common_errors'] == max(0, n-21)
    assert counts['pre_window_insufficient'] == min(60, max(0, n-21))
    assert counts['pre_window_complete'] == max(0, n-81)
    if n >= 82:
        assert len(actual['evidence']) == 60
        assert actual['evidence'][-1]['observation_ordinal'] == n-1
        for m in actual['models']:
            assert m['error_log'] == m['abs_error_quantile'] == m['mae_pre'] == m['rmse_pre'] == 0
            assert m['position'] == 'inside'


@pytest.mark.parametrize('invalid', [False, True])
def test_capture_precedes_even_reading_current_close_and_exception_is_external(monkeypatch, invalid):
    bars = daily_bars(query(['10', '11']))
    events = []
    class Watched(dict):
        def __getitem__(self, key):
            if key == 'close': events.append('current-close-read')
            return super().__getitem__(key)
    bars[1] = Watched(bars[1])
    if invalid:
        bars[1]['reason'] = 'invalid_price'
    capture = signal._capture_prior
    def traced(*args):
        events.append('capture')
        return capture(*args)
    monkeypatch.setattr(signal, '_capture_prior', traced)
    iterator = signal._causal_rows(bars, capture_prior=True)
    next(iterator)
    row, prior = next(iterator)
    assert events[0] == 'capture'
    assert prior.mR == math.log(10)
    assert row['reason'] == ('invalid_price' if invalid else None)
    def broken(*args):
        raise ArithmeticError('independent_capture_failure')
    monkeypatch.setattr(signal, '_capture_prior', broken)
    iterator = signal._causal_rows(bars, capture_prior=True)
    next(iterator)
    with pytest.raises(ArithmeticError, match='independent_capture_failure'):
        next(iterator)
    assert signal._causal_series(bars)[1]['reason'] == ('invalid_price' if invalid else None)


def test_only_one_summary_and_bounded_collector_without_legacy_report(monkeypatch):
    q = query([f'{10 + i/1000:.3f}' for i in range(500)])
    actual_freeze = diagnostic._DiagnosticCollector.freeze
    actual_observe = diagnostic._DiagnosticCollector.observe
    freezes, sizes = [], []
    def freeze(self):
        freezes.append([e['observation_ordinal'] for e in self.ring])
        return actual_freeze(self)
    def observe(self, *args):
        actual_observe(self, *args)
        sizes.append(len(self.ring))
        assert self.ring.maxlen == 60
        assert not hasattr(self, '__dict__')
    def forbidden(*args, **kwargs):
        pytest.fail('The new path duplicated the legacy series/event report')
    monkeypatch.setattr(diagnostic._DiagnosticCollector, 'freeze', freeze)
    monkeypatch.setattr(diagnostic._DiagnosticCollector, 'observe', observe)
    monkeypatch.setattr(signal, '_causal_series', forbidden)
    monkeypatch.setattr(signal, 'signal_report', forbidden)
    monkeypatch.setattr(signal, 'event_report', forbidden)
    actual = result(q)
    assert len(freezes) == 1 and freezes[0] == list(range(440, 500))
    assert len(sizes) == 500 and max(sizes) == 60
    assert len(json.dumps(actual, allow_nan=False).encode()) < 32768


@pytest.mark.parametrize('collision', [2, 21, 22, 81, 82, 100])
def test_late_precision_collision_closes_suffix_until_actual_old_reset(collision):
    prices = [str(10+i) for i in range(190)]
    prices[collision-2:collision] = ['100', '100.000000000000000001']
    blocked = result(query(prices))['result']
    assert blocked['calculation_status'] == 'unavailable'
    assert blocked['diagnostic_block']['ordinal'] == collision
    assert blocked['cohort_counts']['source_or_state_unavailable'] == 191-collision
    prices[105] = '0'
    restored = result(query(prices))['result']
    assert restored['calculation_status'] == 'computed'
    assert restored['diagnostic_block'] is None
    assert restored['current']['segment_observations'] == 84
    assert all(e['segment_id'] == 2 and e['observation_ordinal'] > 106 for e in restored['evidence'])


def witnesses(kalman, rw=None, ema=None):
    rw, ema = kalman if rw is None else rw, kalman if ema is None else ema
    return [dict(origin_date=day(i), origin_ordinal=i+1, observation_date=day(i+1),
        observation_ordinal=i+2, segment_id=1, origin_observations=i+21,
        kalman_error_log=k, last_close_error_log=r, lagged_ema_error_log=e)
        for i, (k,r,e) in enumerate(zip(kalman,rw,ema))]


@pytest.mark.parametrize('bad,expected', [(1e200, 'numerical_failure'),
    (math.sqrt(math.ulp(0.)), 'numerical_underflow'), (math.ulp(0.), 'numerical_underflow')])
def test_one_models_loss_failure_preserves_common_window_and_other_models(bad, expected):
    summary = diagnostic._window_summary(witnesses([bad]+[0.]*59, [.1]*60, [.2]*60))
    k, r, e = summary['models']
    assert k['rmse_pre'] is None and k['field_reasons']['rmse_pre'] == expected
    assert r['rmse_pre'] == pytest.approx(.1) and e['rmse_pre'] == pytest.approx(.2)
    comparisons = diagnostic._comparisons(summary['models'])
    assert comparisons['rmse_pre']['K_minus_R'] is None
    assert comparisons['rmse_pre']['K_minus_E'] is None
    assert len(summary['evidence']) == 60 and k['abs_error_quantile'] == 0
    if bad != math.ulp(0.):
        assert k['mae_pre'] is not None and comparisons['mae_pre']['K_minus_R'] is not None
    json.dumps(summary, allow_nan=False)


@pytest.mark.parametrize('errors', [[math.nan]*60, [math.inf]*60, [-math.inf]*60, [0.]*59, [0.]*61])
def test_invalid_internal_loss_inputs_raise_without_silent_unavailability(errors):
    with pytest.raises(RuntimeError, match='forecast_internal_invariant'):
        diagnostic._losses(errors)


def test_finite_mean_overflow_and_subtraction_fail_only_the_named_dependency():
    summary = diagnostic._window_summary(witnesses([1e308]*60, [0.]*60, [.01]*60))
    assert summary['models'][0]['field_reasons'] == {'mae_pre':'numerical_failure','rmse_pre':'numerical_failure'}
    assert summary['models'][0]['abs_error_quantile'] == 1e308
    assert summary['models'][1]['mae_pre'] == summary['models'][1]['rmse_pre'] == 0
    model = dict(model_id='kalman', abs_error_quantile=1e308, mae_pre=None, rmse_pre=None,
        field_reasons={'mae_pre':'numerical_failure','rmse_pre':'numerical_failure'})
    displayed = diagnostic._model_result(model, -1e308, -.5e308)
    assert displayed['lower_log'] is None and displayed['upper_log'] == 0
    assert displayed['position'] == 'inside'
    assert displayed['field_reasons']['lower_log'] == 'price_range_numerical_failure'


def test_residual_domain_scoring_differs_from_rounded_endpoint_scoring():
    # This is an independent specification example, not a product IS helper.
    m, error, q = 1., 2.**-52, .75*2.**-52
    assert m+error == m+q
    residual_score = 2*q + 20*max(abs(error)-q, 0.)
    endpoint_score = 2*q + 20*max((m+error)-(m+q), 0.)
    assert residual_score > endpoint_score
    assert diagnostic._position(error,q) == 'above'
    assert 2*1 + 20*max(abs(1.5)-1,0) == 12


@pytest.mark.parametrize('scope', ['unknown_calendar', 'declared_only', 'claimed_known_at'])
def test_semantics_remain_conditional_without_global_source_certification(scope):
    q = query([str(100+i) for i in range(90)])
    if scope == 'declared_only':
        del q['metadata']['source_code']
        q['metadata']['interpretation'] = {'instrument':'600001', 'venue':'SH'}
    elif scope == 'claimed_known_at':
        q['metadata'].update(known_at='2021-01-01', closed=True, adjustment='verified')
    actual = result(q)
    assert actual['result']['calculation_status'] == 'computed'
    assert actual['historical_availability'] == 'unverified'
    assert actual['source_qualification'] == 'conditional_frozen_source_observations'
    assert 'adjustment_basis_unverified' in actual['limitations']
    assert 'display_endpoints_rounded_position_uses_residual_domain' in actual['limitations']
    assert actual['source']['identity']['qualification'] == ('declared' if scope == 'declared_only' else 'source_claim')


def test_real_store_fixed_cutoff_is_unchanged_by_reliable_future_values(tmp_path):
    from anatrading.store import EvidenceStore
    from test_formats import bao_payload
    records = [[day(i), 'sh.600001', *([str(100+i)]*4), 'bad', 'bad', '3'] for i in range(110)]
    changed = deepcopy(records)
    for row in changed[90:]: row[2:6] = ['999']*4
    unknown = deepcopy(changed)
    unknown[-1][0] = 'not-a-date'
    with EvidenceStore(tmp_path/'store') as store:
        ids = [store.import_bytes(bao_payload(rows,code='sh.600001'),'baostock-decoded-v0.9.4')['snapshot_id']
            for rows in (records,changed,unknown)]
        qs = [store.query(sid,cutoff=day(89)) for sid in ids]
        a,b,c = [result(q) for q in qs]
        assert a['result'] == b['result']
        assert a['analysis_id'] != b['analysis_id']
        assert a['source'] != b['source']
        for sid,q,report in zip(ids,qs,(a,b,c)):
            assert result(store._research_query(sid,cutoff=day(89))) == report
            assert store.query(sid,cutoff=day(89)) == q
        assert c['result']['calculation_status'] == 'unavailable'
        assert c['result']['reasons'] == ['date_set_integrity_unknown']
        assert c['result']['cohort_counts'] is None
