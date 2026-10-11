"""Pre-edit golden, independent 60-digit matrix oracle, and strict causal contracts.

The seven numerical paths and tolerances are frozen in the reviewed plan. The
reference uses neither product filter, prior-capture, window, nor loss helpers.
Synthetic dates are source slots, not an asserted exchange trading calendar.
"""
from contextlib import nullcontext
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from functools import lru_cache
import hashlib
import importlib
import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest

import anatrading.signal_research as signal


MODELS = ('kalman', 'last_close', 'lagged_ema')
FIELDS = ['open', 'high', 'low', 'close', 'volume', 'amount']
VERSIONS = {'schema': '1', 'decode': '1', 'normalization': 'disabled-1',
            'quality': '1', 'numeric': 'decimal38.18-bigint-v1'}
LEGACY_NAMES = ('Z', 'T', 'J', 'T_zero', 'T_duplicate', 'T_unlocated',
                'T_code_conflict', 'T_adjustflag_conflict', 'T_quarantined',
                'T_low_context', 'T_update_failure', 'T_price_scale_failure')
LEGACY_SHA256 = 'bd68f0583a5441930bdfa47dafe23bf6b9a0fb8fc332227f77fda802fa007eb4'


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':'))


def identity(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def day(i):
    return (date(2020, 1, 1) + timedelta(days=i)).isoformat()


@lru_cache(maxsize=7)
def fixed_prices(kind):
    """Exact reviewed formulas, then HALF_EVEN to eight source decimal places."""
    assert kind in 'ZCTAJPV'
    with localcontext() as context:
        context.prec = 60
        result, g = [], Decimal(0)
        for i in range(160):
            if kind == 'Z':
                result.append('1')
                continue
            if kind == 'C':
                g = Decimal(0)
            if kind == 'T':
                g = Decimal('.001') * i
            if kind == 'A':
                g = Decimal('.002') * (i % 2)
            if kind == 'J':
                g = Decimal('.0005') * i + (Decimal('.08') if i >= 80 else 0)
            if kind == 'P':
                g = Decimal('.0005') * i + (Decimal('.08') if i == 80 else 0)
            if kind == 'V' and i:
                g += (Decimal('.001') if i < 80 else Decimal('.004')) * (
                    -2, -1, 1, 2, 0, 1, -1, 0)[(i - 1) % 8]
            result.append(format((100 * g.exp()).quantize(
                Decimal('.00000001'), rounding=ROUND_HALF_EVEN), '.8f'))
        return tuple(result)


def source_query(prices, *, cutoff=None):
    """Explicit synthetic trusted-Store shape with independently hashed selection."""
    if cutoff is None:
        cutoff = day(len(prices) - 1)
    selection = dict(snapshot_id='a' * 64, mode='retrospective', cutoff=cutoff,
                     ordinal_start=None, ordinal_end=None, fields=FIELDS.copy(),
                     versions=deepcopy(VERSIONS))
    rows = [dict(ordinal=i + 1, label=day(i), tokens={}, checks=[],
                 values=dict.fromkeys(('open', 'high', 'low', 'close'), value))
            for i, value in enumerate(prices)]
    return dict(snapshot_id='a' * 64, batch_id='c' * 64, query_id=identity(selection),
                selection=selection,
                manifest=dict(raw_sha256='d' * 64, source_contract_id='e' * 64,
                              versions=deepcopy(VERSIONS)),
                metadata=dict(period='1d', source_code='sh.600001', source_adjustflag='3'),
                rows=rows, unlocated=[], counts=dict(selected_rows=len(rows),
                unlocated_rows=0, batch_rows=len(rows), batch_unlocated_rows=0), batch_checks=[])


def reidentify(query):
    query['query_id'] = identity(query['selection'])
    return query


def report(query, cutoff=None):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    return module.forecast_diagnostic_report(
        query, cutoff=query['selection']['cutoff'] if cutoff is None else cutoff)


def mm(a, b):
    return [[sum((a[i][k] * b[k][j] for k in range(len(b))), Decimal(0))
             for j in range(len(b[0]))] for i in range(len(a))]


def ma(a, b):
    return [[x + y for x, y in zip(ar, br)] for ar, br in zip(a, b)]


def mt(a):
    return list(map(list, zip(*a)))


@lru_cache(maxsize=7)
def independent_oracle(prices):
    """60-digit source ln, generic matrices/Joseph update, independent EMA/EWMA.

    This returns observations and their strictly pre-observation error windows.
    Product implementation helpers are never called by the oracle.
    """
    with localcontext() as context:
        context.prec = 60
        zero, one = Decimal(0), Decimal(1)
        F, H = [[one, one], [zero, one]], [[one, zero]]
        Q, R = [[Decimal('.000001'), zero], [zero, Decimal('.00000001')]], [[Decimal('.0001')]]
        alpha = one - (-Decimal(2).ln() / 10).exp()
        decay = (-Decimal(2).ln() / 20).exp()
        output, errors, previous = [], [], None
        x = covariance = ema = variance_post = None
        for i, raw in enumerate(prices):
            y = Decimal(raw).ln()
            if i == 0:
                x = [[y], [zero]]
                covariance = [[R[0][0], zero], [zero, R[0][0]]]
                ema = y
                prior = current_errors = None
            else:
                x_pre = mm(F, x)
                covariance_pre = ma(mm(mm(F, covariance), mt(F)), Q)
                S = ma(mm(mm(H, covariance_pre), mt(H)), R)[0][0]
                prior = dict(kalman=x_pre[0][0], last_close=previous, lagged_ema=ema,
                             S=S, v_pre=variance_post)
                innovation = y - mm(H, x_pre)[0][0]
                gain = [[row[0] / S] for row in mm(covariance_pre, mt(H))]
                x = ma(x_pre, [[gain[0][0] * innovation], [gain[1][0] * innovation]])
                IKH = [[one - gain[0][0], zero], [-gain[1][0], one]]
                covariance = ma(mm(mm(IKH, covariance_pre), mt(IKH)),
                                mm(mm(gain, R), mt(gain)))
                ema = (one - alpha) * ema + alpha * y
                change = y - previous
                variance_post = (change * change if variance_post is None else
                                 decay * variance_post + (one - decay) * change * change)
                current_errors = ({model: y - prior[model] for model in MODELS}
                                  if i >= 21 else None)
            summary = {}
            if len(errors) == 60:
                for model in MODELS:
                    magnitudes = [abs(item[model]) for item in errors]
                    summary[model] = dict(q=sorted(magnitudes)[53],
                        mae=sum(magnitudes, zero) / 60,
                        rmse=(sum((v * v for v in magnitudes), zero) / 60).sqrt())
            output.append(dict(index=i, y=y, prior=prior, errors=current_errors,
                               pre_count=len(errors), summary=summary,
                               level=x[0][0], slope=x[1][0], covariance=deepcopy(covariance),
                               ema=ema, variance_post=variance_post))
            if current_errors is not None:
                errors.append(current_errors)
                if len(errors) > 60:
                    errors.pop(0)
            previous = y
        return tuple(output)


def close_to_reference(actual, reference):
    """This tolerance applies only to the seven reviewed ordinary vectors."""
    assert math.isfinite(actual)
    expected = float(reference)
    assert abs(actual - expected) <= max(2e-11, 2e-10 * abs(expected))


def legacy_query(name):
    query = source_query(fixed_prices(name if name in ('Z', 'T', 'J') else 'T'))
    if name == 'T_zero':
        query['rows'][40]['values'] = dict.fromkeys(('open', 'high', 'low', 'close'), '0')
    if name == 'T_duplicate':
        row = deepcopy(query['rows'][40])
        row['ordinal'] = 161
        query['rows'].append(row)
        query['counts']['selected_rows'] += 1
        query['counts']['batch_rows'] += 1
    if name == 'T_unlocated':
        row = query['rows'].pop(40)
        row['label'] = None
        query['unlocated'].append(row)
        query['counts'].update(selected_rows=159, unlocated_rows=1, batch_unlocated_rows=1)
    if name == 'T_code_conflict':
        query['rows'][40]['tokens']['code'] = 'sz.000001'
    if name == 'T_adjustflag_conflict':
        query['rows'][40]['tokens']['adjustflag'] = '2'
    if name == 'T_quarantined':
        query['metadata']['quarantined'] = True
    return query


def legacy_injection(name):
    if name == 'T_update_failure':
        original, calls = signal._update, 0
        def update(*args):
            nonlocal calls
            calls += 1
            if calls == 40:
                raise ArithmeticError('numerical_failure')
            return original(*args)
        return patch.object(signal, '_update', update)
    if name == 'T_price_scale_failure':
        original, calls = signal._price_scale, 0
        def price(*args):
            nonlocal calls
            calls += 1
            if calls == 60:
                return None, 'price_scale_out_of_range'
            return original(*args)
        return patch.object(signal, '_price_scale', price)
    return nullcontext()


@lru_cache(maxsize=1)
def golden():
    raw = (Path(__file__).parent / 'fixtures' / 'forecast_diagnostics_legacy.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == LEGACY_SHA256, 'Pre-edit golden must never be refreshed'
    return json.loads(raw)


@pytest.mark.parametrize('name', LEGACY_NAMES)
def test_pre_edit_complete_legacy_golden(name):
    with localcontext() as context, legacy_injection(name):
        if name == 'T_low_context':
            context.prec = 3
        actual = signal.signal_report(legacy_query(name), lookback=20, horizon=5, test_start=None)
    assert canonical(actual) == canonical(golden()[name])


@pytest.mark.parametrize('kind', tuple('ZCTAJPV'))
def test_independent_reference_self_check_against_existing_public_states(kind):
    prices = fixed_prices(kind)
    reference = independent_oracle(prices)
    actual = signal.signal_report(source_query(prices))['series']
    assert len(reference) == len(actual) == 160
    for got, expected in zip(actual, reference):
        for field, ref_field in (('kalman_level', 'level'), ('kalman_slope', 'slope'), ('ema_log', 'ema')):
            close_to_reference(got[field], expected[ref_field])
        for field, row, column in (('variance_level', 0, 0), ('covariance_level_slope', 0, 1), ('variance_slope', 1, 1)):
            close_to_reference(got[field], expected['covariance'][row][column])
        if expected['prior']:
            close_to_reference(got['innovation_variance'], expected['prior']['S'])
    assert reference[20]['errors'] is None
    assert reference[21]['errors'] is not None
    assert reference[80]['pre_count'] == 59 and reference[81]['pre_count'] == 60


@pytest.mark.parametrize('kind', tuple('ZCTAJPV'))
def test_seven_frozen_vectors_against_independent_decimal_matrix_oracle(kind):
    prices = fixed_prices(kind)
    reference = independent_oracle(prices)
    for n in (22, 81, 82, 100, 160):
        query = source_query(prices[:n])
        before = deepcopy(query)
        result = report(query)['result']
        expected = reference[n - 1]
        assert query == before
        assert result['calculation_status'] == ('computed' if n >= 82 else 'history_insufficient')
        assert result['window']['actual_count'] == expected['pre_count']
        assert [m['model_id'] for m in result['models']] == list(MODELS)
        for model in result['models']:
            key = model['model_id']
            close_to_reference(model['prediction_log'], expected['prior'][key])
            close_to_reference(model['error_log'], expected['errors'][key])
            if n >= 82:
                for field, ref_field in (('abs_error_quantile', 'q'), ('mae_pre', 'mae'), ('rmse_pre', 'rmse')):
                    close_to_reference(model[field], expected['summary'][key][ref_field])
                error, q = model['error_log'], model['abs_error_quantile']
                assert model['position'] == ('below' if error < -q else 'above' if error > q else 'inside')
            else:
                assert all(model[field] is None for field in ('abs_error_quantile', 'mae_pre', 'rmse_pre', 'position'))
        close_to_reference(result['prior_scales']['model_innovation_variance_pre'], expected['prior']['S'])
        close_to_reference(result['prior_scales']['rw_ewma_variance_pre'], expected['prior']['v_pre'])
        assert [e['observation_ordinal'] for e in result['evidence']] == list(range(max(22, n - 60), n))
        assert all(e['origin_ordinal'] + 1 == e['observation_ordinal'] for e in result['evidence'])
        assert all(e['origin_observations'] + 1 == e['observation_ordinal'] for e in result['evidence'])
        json.dumps(result, allow_nan=False)


@pytest.mark.parametrize('kind', ('Z', 'T', 'J'))
@pytest.mark.parametrize('n,status,count', [(20, 'warming_up', 0), (21, 'warming_up', 0),
    (22, 'history_insufficient', 0), (81, 'history_insufficient', 59), (82, 'computed', 60)])
def test_forecast_origin_boundaries(kind, n, status, count):
    result = report(source_query(fixed_prices(kind)[:n]))['result']
    assert result['calculation_status'] == status
    if status == 'warming_up':
        assert result['reasons'] == ['forecast_origin_warmup']
        for model in result['models']:
            assert all(model[field] is None for field in ('prediction_log', 'error_log', 'abs_error_quantile', 'mae_pre', 'rmse_pre', 'position'))
    else:
        assert result['window']['actual_count'] == count
        assert len(result['evidence']) == count


def test_price_one_is_strict_zero_scale_and_inside():
    result = report(source_query(fixed_prices('Z')))['result']
    assert result['calculation_status'] == 'computed'
    for model in result['models']:
        assert all(model[field] == 0.0 for field in ('prediction_log', 'error_log', 'abs_error_quantile', 'mae_pre', 'rmse_pre', 'lower_log', 'upper_log'))
        assert model['position'] == 'inside' and model['field_reasons'] == {}
    assert result['prior_scales']['rw_ewma_variance_pre'] == 0.0


@pytest.mark.parametrize('cutoff', [None, True, False, 20200101, '', '2020-1-01', '20200101',
                                    '2020-01-01T00:00:00', '2020-02-30', '2020-W01-1'])
def test_invalid_cutoff_is_stable(cutoff):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    with pytest.raises(ValueError, match='^invalid_cutoff$'):
        module.forecast_diagnostic_report(source_query(['1']), cutoff=cutoff)


@pytest.mark.parametrize('value', [None, '2019-12-31', '2020-01-02', 'missing'])
def test_query_cutoff_must_match_explicit_day(value):
    query = source_query(['1'])
    if value == 'missing':
        del query['selection']['cutoff']
    else:
        query['selection']['cutoff'] = value
    reidentify(query)
    with pytest.raises(ValueError, match='^research_cutoff_mismatch$'):
        report(query, '2020-01-01')


@pytest.mark.parametrize('key', ['snapshot_id', 'batch_id', 'query_id', 'selection', 'manifest',
                                'metadata', 'rows', 'unlocated', 'counts', 'batch_checks'])
def test_required_query_fields_fail_before_model(key):
    query = source_query(['1'])
    del query[key]
    module = importlib.import_module('anatrading.forecast_diagnostics')
    with pytest.raises(ValueError, match='^invalid_forecast_query$'):
        module.forecast_diagnostic_report(query, cutoff='2020-01-01')


@pytest.mark.parametrize('key,value', [('rows', iter(())), ('unlocated', {}), ('selection', []),
    ('manifest', None), ('metadata', []), ('counts', []), ('batch_checks', {})])
def test_container_contract(key, value):
    query = source_query(['1'])
    query[key] = value
    module = importlib.import_module('anatrading.forecast_diagnostics')
    with pytest.raises(ValueError, match='^invalid_forecast_query$'):
        module.forecast_diagnostic_report(query, cutoff='2020-01-01')


@pytest.mark.parametrize('path', [('snapshot_id',), ('batch_id',), ('query_id',),
                                 ('manifest', 'raw_sha256'), ('manifest', 'source_contract_id')])
@pytest.mark.parametrize('bad', ['A' * 64, 'f' * 63, True])
def test_source_id_format_is_not_guessed(path, bad):
    query = source_query(['1'])
    owner = query if len(path) == 1 else query[path[0]]
    owner[path[-1]] = bad
    with pytest.raises(ValueError, match='^invalid_forecast_query$'):
        report(query)


@pytest.mark.parametrize('key,value,code', [('mode', 'live', 'invalid_forecast_selection'),
    ('fields', ['close'], 'invalid_forecast_selection'), ('versions', {}, 'invalid_forecast_selection'),
    ('ordinal_start', 1, 'ordinal_window_not_supported'), ('ordinal_end', 1, 'ordinal_window_not_supported')])
def test_invalid_selection(key, value, code):
    query = source_query(['1'])
    query['selection'][key] = value
    reidentify(query)
    with pytest.raises(ValueError, match=f'^{code}$'):
        report(query)


@pytest.mark.parametrize('mutation', ['query_identity', 'snapshot_selection', 'unknown_projection'])
def test_direct_identity_links_and_projection(mutation):
    query = source_query(['1'])
    if mutation == 'query_identity':
        query['query_id'] = 'f' * 64
    elif mutation == 'snapshot_selection':
        query['selection']['snapshot_id'] = 'f' * 64
        reidentify(query)
    else:
        query['read_projection'] = 'arbitrary_projection'
    with pytest.raises(ValueError, match='^invalid_forecast_query$'):
        report(query)


@pytest.mark.parametrize('count', [True, -1, None, 1.0])
def test_batch_unlocated_count_must_be_nonnegative_true_integer(count):
    query = source_query(['1'])
    query['counts']['batch_unlocated_rows'] = count
    with pytest.raises(ValueError, match='^invalid_forecast_query$'):
        report(query)


@pytest.mark.parametrize('period', [None, '1m', '1D'])
def test_daily_period_only(period):
    query = source_query(['1'])
    query['metadata']['period'] = period
    with pytest.raises(ValueError, match='^unsupported_period$'):
        report(query)


@pytest.mark.parametrize('mutation,code', [('missing', 'research_identity_unavailable'),
    ('conflict', 'research_identity_conflict'), ('unknown', 'research_market_unknown')])
def test_symbol_identity_failures_are_preserved(mutation, code):
    query = source_query(['1'])
    if mutation == 'missing':
        del query['metadata']['source_code']
    elif mutation == 'conflict':
        query['metadata']['interpretation'] = dict(instrument='000001.SZ')
    else:
        query['metadata']['source_code'] = '600001'
    with pytest.raises(ValueError, match=f'^{code}$'):
        report(query)


def test_row_limit_is_checked_before_normalization_or_state(monkeypatch):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    query = source_query(['1'])
    query['rows'] *= 20000
    query['unlocated'] = [deepcopy(query['rows'][0])]
    def forbidden(*args, **kwargs):
        pytest.fail('Oversize input entered normalization or state recurrence')
    monkeypatch.setattr(module, 'daily_bars', forbidden)
    monkeypatch.setattr(signal, '_causal_rows', forbidden)
    with pytest.raises(ValueError, match='^research_row_limit$'):
        report(query)


@pytest.mark.parametrize('case,reason', [('quarantine', 'known_negative_source'),
    ('negative_check', 'known_negative_source'), ('unlocated', 'date_set_integrity_unknown'),
    ('batch_unlocated', 'date_set_integrity_unknown'), ('missing', 'cutoff_missing'),
    ('empty', 'cutoff_missing')])
def test_global_unavailable_skips_model(case, reason, monkeypatch):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    query = source_query(fixed_prices('T')[:82])
    if case == 'quarantine': query['metadata']['quarantined'] = True
    if case == 'negative_check': query['batch_checks'] = [dict(name='known_negative_sample', outcome='fail')]
    if case == 'unlocated': query['unlocated'] = [dict(ordinal=83, label=None, tokens={}, values={}, checks=[])]
    if case == 'batch_unlocated': query['counts']['batch_unlocated_rows'] = 1
    if case == 'missing': query['rows'].pop()
    if case == 'empty': query['rows'] = []
    def forbidden(*args, **kwargs):
        pytest.fail('Globally unavailable source entered model recurrence')
    monkeypatch.setattr(signal, '_causal_rows', forbidden)
    if hasattr(module, '_causal_rows'):
        monkeypatch.setattr(module, '_causal_rows', forbidden)
    result = report(query)['result']
    assert result['calculation_status'] == 'unavailable' and reason in result['reasons']
    assert all(result[field] is None for field in ('current', 'models', 'comparisons', 'window', 'prior_scales', 'cohort_counts'))
    assert result['evidence'] == []


def error_evidence(errors):
    return [dict(origin_date=day(i + 20), origin_ordinal=i + 21,
                 observation_date=day(i + 21), observation_ordinal=i + 22,
                 segment_id=1, origin_observations=i + 21,
                 kalman_error_log=e, last_close_error_log=e, lagged_ema_error_log=e)
            for i, e in enumerate(errors)]


def test_fixed_window_nearest_rank_excludes_current_and_does_not_mutate_input():
    module = importlib.import_module('anatrading.forecast_diagnostics')
    evidence = error_evidence([.01] * 54 + [.10] * 6)
    before = deepcopy(evidence)
    summary = module._window_summary(evidence)
    assert evidence == before
    assert summary['window'] == dict(expected_count=60, actual_count=60,
        start_date=day(21), end_date=day(80), origin_start_date=day(20),
        origin_end_date=day(79), window_unit='source_observation_intervals')
    assert summary['evidence'] == evidence
    for model in summary['models']:
        assert model['abs_error_quantile'] == .01
        assert model['mae_pre'] == math.fsum([.01] * 54 + [.10] * 6) / 60
        assert model['rmse_pre'] == math.sqrt(math.fsum([.01**2] * 54 + [.10**2] * 6) / 60)
    # The wrong append-before-freeze algorithm changes the authoritative rank.
    wrong = module._window_summary(evidence[1:] + error_evidence([.02]))
    assert all(m['abs_error_quantile'] == .02 for m in wrong['models'])


@pytest.mark.parametrize('errors,mae_reason,rmse_reason', [
    ([0.] * 60, None, None),
    ([math.ulp(0.)] + [0.] * 59, 'numerical_underflow', 'numerical_underflow'),
    ([math.sqrt(math.ulp(0.))] + [0.] * 59, None, 'numerical_underflow'),
    ([1e200] + [0.] * 59, None, 'numerical_failure'),
])
def test_loss_failures_have_minimum_field_scope(errors, mae_reason, rmse_reason):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    before = errors.copy()
    mae, rmse, reasons = module._losses(errors)
    assert errors == before
    if mae_reason:
        assert mae is None and reasons['mae_pre'] == mae_reason
    else:
        assert mae == math.fsum(abs(e) for e in errors) / 60
        assert 'mae_pre' not in reasons
    if rmse_reason:
        assert rmse is None and reasons['rmse_pre'] == rmse_reason
    else:
        assert rmse == math.sqrt(math.fsum(e * e for e in errors) / 60)
        assert 'rmse_pre' not in reasons
    summary = module._window_summary(error_evidence(errors))
    assert all(m['abs_error_quantile'] == 0. for m in summary['models'])


def test_bad_square_slot_is_not_dropped_until_it_leaves_fixed_window():
    module = importlib.import_module('anatrading.forecast_diagnostics')
    evidence = error_evidence([0.] * 59 + [1e200])
    for i in range(60):
        summary = module._window_summary(evidence)
        assert summary['window']['actual_count'] == 60
        assert len(summary['evidence']) == 60
        assert all(m['rmse_pre'] is None for m in summary['models'])
        evidence = evidence[1:] + error_evidence([.01])
    assert all(m['rmse_pre'] is not None for m in module._window_summary(evidence)['models'])


def test_normal_82_source_slot_count_conservation():
    result = report(source_query(fixed_prices('T')[:82]))['result']
    assert result['cohort_counts'] == dict(total_groups=82, forecast_origin_warmup=21,
        common_errors=61, source_or_state_unavailable=0,
        pre_window_insufficient=60, pre_window_complete=1)
    assert result['window']['start_date'] == day(21)
    assert result['window']['end_date'] == day(80)
    assert result['current']['requested_date'] == day(81)
    assert result['current']['source_prefix_start'] == day(0)
    assert result['current']['state_segment_start'] == day(0)


@pytest.mark.parametrize('case,reason', [('zero', 'invalid_price'), ('duplicate', 'duplicate_date'),
    ('code', 'source_identity_conflict'), ('adjustflag', 'source_adjustment_conflict')])
def test_bad_current_keeps_requested_source_slot_and_closes_models(case, reason):
    query = source_query(fixed_prices('T')[:82])
    if case == 'zero': query['rows'][-1]['values'] = dict.fromkeys(('open', 'high', 'low', 'close'), '0')
    if case == 'duplicate':
        row = deepcopy(query['rows'][-1]); row['ordinal'] = 83; query['rows'].append(row)
    if case == 'code': query['rows'][-1]['tokens']['code'] = 'sz.000001'
    if case == 'adjustflag': query['rows'][-1]['tokens']['adjustflag'] = '2'
    result = report(query)['result']
    assert result['calculation_status'] == 'unavailable' and reason in result['reasons']
    assert result['current']['date'] == result['current']['requested_date'] == day(81)
    assert result['current']['ordinal'] == (None if case == 'duplicate' else 82)
    assert all(result[field] is None for field in ('models', 'window', 'comparisons', 'prior_scales'))
    assert result['evidence'] == []
    assert result['cohort_counts']['source_or_state_unavailable'] == 1


@pytest.mark.parametrize('bad', ['zero', 'duplicate'])
def test_existing_reset_clears_ring_and_rewarms_without_cross_segment_fill(bad):
    query = source_query(fixed_prices('T'))
    if bad == 'zero': query['rows'][100]['values'] = dict.fromkeys(('open', 'high', 'low', 'close'), '0')
    else:
        row = deepcopy(query['rows'][100]); row['ordinal'] = 161; query['rows'].append(row)
    result = report(query)['result']
    assert result['calculation_status'] == 'history_insufficient'
    assert result['current']['segment_id'] == 2 and result['current']['segment_observations'] == 59
    assert result['current']['source_prefix_start'] == day(0)
    assert result['current']['state_segment_start'] == day(101)
    assert result['window']['actual_count'] == 37
    assert all(e['segment_id'] == 2 and e['origin_ordinal'] >= 122 for e in result['evidence'])


def test_precision_collision_blocks_existing_segment_from_second_slot():
    prices = list(fixed_prices('T'))
    prices[1] = '100.000000000000000001'
    assert Decimal(prices[0]) != Decimal(prices[1]) and float(prices[0]) == float(prices[1])
    result = report(source_query(prices))['result']
    assert result['calculation_status'] == 'unavailable'
    assert 'precision_loss_state_dependency' in result['reasons']
    assert result['diagnostic_block'] == dict(date=day(1), ordinal=2, reason='precision_loss_state_dependency')
    assert all(result[field] is None for field in ('models', 'window', 'comparisons', 'prior_scales'))
    assert result['evidence'] == []
    assert result['cohort_counts'] == dict(total_groups=160, forecast_origin_warmup=1,
        common_errors=0, source_or_state_unavailable=159, pre_window_insufficient=0, pre_window_complete=0)
    # Only a real legacy reset ends the blocked state dependency.
    prices[30] = '0'
    recovered = report(source_query(prices))['result']
    assert recovered['calculation_status'] == 'computed'
    assert recovered['current']['segment_id'] == 2
    assert recovered['diagnostic_block'] is None
    assert recovered['window']['actual_count'] == 60
    assert all(e['segment_id'] == 2 for e in recovered['evidence'])


def test_low_global_decimal_context_cannot_change_source_or_diagnostic():
    query = source_query(fixed_prices('T'))
    ordinary = report(query)
    with localcontext() as context:
        context.prec = 3
        assert report(query) == ordinary


def test_current_valid_change_preserves_prior_and_strict_pre_window():
    from anatrading.research_series import daily_bars
    query = source_query(fixed_prices('T')[:100])
    changed = deepcopy(query)
    changed['rows'][-1]['values'] = dict.fromkeys(('open', 'high', 'low', 'close'), '250')
    old_stream = list(signal._causal_rows(daily_bars(query), capture_prior=True))
    new_stream = list(signal._causal_rows(daily_bars(changed), capture_prior=True))
    assert old_stream[:-1] == new_stream[:-1]
    assert old_stream[-1][1] == new_stream[-1][1]
    old, new = report(query)['result'], report(changed)['result']
    for field in ('window', 'evidence', 'prior_scales', 'comparisons'):
        assert old[field] == new[field]
    for a, b in zip(old['models'], new['models']):
        for field in ('prediction_log', 'abs_error_quantile', 'mae_pre', 'rmse_pre', 'lower_log', 'upper_log'):
            assert a[field] == b[field]
        assert a['error_log'] != b['error_log']


def test_current_unused_valid_high_low_do_not_change_diagnostic():
    query = source_query(fixed_prices('T')[:100])
    changed = deepcopy(query)
    changed['rows'][-1]['values'].update(high='1000', low='1')
    assert report(query) == report(changed)


@pytest.mark.parametrize('replacement', ['0', '100.000000000000000001'])
def test_private_prior_is_captured_before_current_invalid_or_precision_change(replacement):
    from anatrading.research_series import daily_bars
    prices = list(fixed_prices('T')[:100])
    prices[-2] = '100'
    query, changed = source_query(prices), source_query(prices)
    changed['rows'][-1]['values'] = dict.fromkeys(('open', 'high', 'low', 'close'), replacement)
    original = list(signal._causal_rows(daily_bars(query), capture_prior=True))
    revised = list(signal._causal_rows(daily_bars(changed), capture_prior=True))
    assert original[-1][1] == revised[-1][1]
    assert revised[-1][1].origin_date == day(98)
    assert revised[-1][1].origin_observations == 99
    assert report(changed)['result']['calculation_status'] == 'unavailable'


def test_capture_is_previous_saved_state_and_default_path_allocates_no_prior(monkeypatch):
    from anatrading.research_series import daily_bars
    query = source_query(fixed_prices('J'))
    old = signal.signal_report(query)['series']
    captured = list(signal._causal_rows(daily_bars(query), capture_prior=True))
    assert captured[0][1] is None
    for i, (_, prior) in enumerate(captured[1:], 1):
        previous = old[i - 1]
        assert prior.origin_date == previous['date'] and prior.origin_ordinal == previous['ordinal']
        assert prior.origin_observations == previous['segment_observations']
        assert prior.mK == previous['kalman_level'] + previous['kalman_slope']
        assert prior.mR == math.log(float(query['rows'][i - 1]['values']['close']))
        assert prior.mE == previous['ema_log']
        assert prior.S == ((previous['variance_level'] + 2 * previous['covariance_level_slope']
                           + previous['variance_slope'] + 1e-6) + 1e-4)
        assert prior.v_pre == previous['ewma_variance_post']
    def forbidden(*args, **kwargs):
        pytest.fail('Default legacy path allocated a diagnostic prior')
    monkeypatch.setattr(signal, '_capture_prior', forbidden)
    assert all(prior is None for _, prior in signal._causal_rows(daily_bars(query)))
    assert signal.signal_report(query)['series'] == old


@pytest.mark.parametrize('kind', ('Z', 'T', 'J'))
def test_private_series_all_prefixes_and_future_revision_are_exact(kind):
    from anatrading.research_series import daily_bars
    prices = fixed_prices(kind)
    full = list(signal._causal_rows(daily_bars(source_query(prices)), capture_prior=True))
    for n in range(1, 161):
        prefix = list(signal._causal_rows(daily_bars(source_query(prices[:n])), capture_prior=True))
        assert prefix == full[:n]
    revised = list(prices)
    revised[100:] = ['999'] * 60
    newer = list(signal._causal_rows(daily_bars(source_query(revised)), capture_prior=True))
    assert newer[:100] == full[:100]


@pytest.mark.parametrize('exception', [RuntimeError, ArithmeticError])
def test_diagnostic_collector_exceptions_propagate_and_old_path_is_unchanged(monkeypatch, exception):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    query = source_query(fixed_prices('T'))
    before = signal.signal_report(query)
    def fail(*args, **kwargs):
        raise exception('deliberate_collector_failure')
    monkeypatch.setattr(module, '_window_summary', fail)
    with pytest.raises(exception, match='deliberate_collector_failure'):
        report(query)
    assert signal.signal_report(query) == before


def test_source_projections_and_nonidentity_presentation_fields_are_identical():
    public = source_query(fixed_prices('T'))
    internal = deepcopy(public)
    internal['read_projection'] = 'daily_ohlc_input_v1'
    public.update(quality={'display_only': True}, unlocated_quality=[], totals={})
    assert report(public) == report(internal)


def test_method_identity_and_qualification_never_upgrade_declared_source():
    query = source_query(fixed_prices('T'))
    query['metadata']['known_at'] = '2010-01-01T00:00:00Z'
    actual = report(query)
    assert set(actual) == {'method_id', 'analysis_id', 'inputs', 'parameters', 'mode', 'units',
        'source', 'source_qualification', 'historical_availability', 'limitations', 'result'}
    assert actual['method_id'] == 'daily-one-step-source-diagnostic-v1'
    assert actual['mode'] == 'retrospective'
    assert actual['source_qualification'] == 'conditional_frozen_source_observations'
    assert actual['historical_availability'] == 'unverified'
    assert actual['source']['identity']['qualification'] == 'source_claim'
    assert actual['parameters']['window'] == 60 and actual['parameters']['order_rank'] == 54
    assert actual['parameters']['absolute_error_quantile'] == .9
    assert actual['parameters']['quantile_method'] == 'nearest-rank-no-interpolation'
    assert actual['parameters']['forecast_origin_min_observations'] == 21
    assert actual['analysis_id'] == identity({key: actual[key] for key in ('method_id', 'inputs', 'parameters', 'source')})
    required = {'retrospective_source_version', 'calendar_and_corporate_actions_unverified',
        'adjustment_basis_unverified', 'historical_availability_unverified', 'bar_closure_unverified',
        'source_identity_not_security_master_verified', 'fixed_engineering_parameters_not_calibrated',
        'empirical_quantile_without_coverage_guarantee', 'no_prediction_alpha_or_trading_return_claim',
        'one_step_observation_target_not_latent_trend'}
    assert required <= set(actual['limitations'])
    assert len(canonical(actual).encode()) <= 32 * 1024
    changed = deepcopy(query)
    changed['snapshot_id'] = changed['selection']['snapshot_id'] = 'f' * 64
    reidentify(changed)
    assert report(changed)['analysis_id'] != actual['analysis_id']


def test_diagnostic_calls_leave_old_complete_report_unchanged():
    for name in ('Z', 'T', 'J', 'T_zero', 'T_duplicate', 'T_unlocated',
                 'T_code_conflict', 'T_adjustflag_conflict', 'T_quarantined'):
        query = legacy_query(name)
        before = signal.signal_report(query, lookback=20, horizon=5, test_start=None)
        report(query)
        after = signal.signal_report(query, lookback=20, horizon=5, test_start=None)
        assert canonical(before) == canonical(after) == canonical(golden()[name])


def test_original_price_scale_overflow_and_underflow_remain_explicit():
    assert signal._price_scale(1000) == (None, 'price_scale_out_of_range')
    assert signal._price_scale(-1000) == (None, 'price_scale_out_of_range')


def install_prior_stream(monkeypatch, module, transform):
    """Defensive binary64 injection; this is not a normal-price numerical oracle."""
    original = signal._causal_rows
    def stream(bars, *, capture_prior=False):
        for row, prior in original(bars, capture_prior=capture_prior):
            if prior is not None:
                prior = transform(row, prior)
            yield row, prior
    monkeypatch.setattr(signal, '_causal_rows', stream)
    if hasattr(module, '_causal_rows'):
        monkeypatch.setattr(module, '_causal_rows', stream)


@pytest.mark.parametrize('error,position', [(.01, 'inside'), (-.01, 'inside'),
    (math.nextafter(.01, math.inf), 'above'), (math.nextafter(-.01, -math.inf), 'below'),
    (math.nextafter(.01, 0.), 'inside'), (math.nextafter(-.01, 0.), 'inside')])
def test_strict_binary64_equal_and_nextafter_positions(error, position, monkeypatch):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    def transform(row, prior):
        e = error if row['ordinal'] == 82 else .01
        return prior._replace(mK=-e, mR=-e, mE=-e)
    install_prior_stream(monkeypatch, module, transform)
    result = report(source_query(fixed_prices('Z')[:82]))['result']
    assert result['calculation_status'] == 'computed'
    for model in result['models']:
        assert model['abs_error_quantile'] == .01
        assert model['error_log'] == error
        assert model['position'] == position


def test_rounded_display_endpoint_cannot_reclassify_residual_outside(monkeypatch):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    q = math.nextafter(2. ** -53, math.inf)
    prices = list(fixed_prices('Z')[:82])
    prices[-1] = '2.718281828459046000'
    y = math.log(float(prices[-1]))
    assert y == math.nextafter(1., math.inf)
    assert y == 1. + q and y - 1. > q
    def transform(row, prior):
        prediction = 1. if row['ordinal'] == 82 else -q
        return prior._replace(mK=prediction, mR=prediction, mE=prediction)
    install_prior_stream(monkeypatch, module, transform)
    result = report(source_query(prices))['result']
    for model in result['models']:
        assert model['abs_error_quantile'] == q
        assert model['upper_log'] == y
        assert model['error_log'] == y - 1.
        assert model['position'] == 'above'


def test_distinct_float_values_with_equal_logs_also_block_existing_segment():
    prices = list(fixed_prices('T'))
    prices[1] = '100.000000000000014211'
    assert float(prices[0]) != float(prices[1])
    assert math.log(float(prices[0])) == math.log(float(prices[1]))
    result = report(source_query(prices))['result']
    assert result['calculation_status'] == 'unavailable'
    assert result['diagnostic_block'] == dict(date=day(1), ordinal=2, reason='precision_loss_state_dependency')
    assert result['cohort_counts']['source_or_state_unavailable'] == 159


def test_zero_scale_does_not_gain_probability_or_price_target_outputs():
    result = report(source_query(fixed_prices('Z')))
    encoded = canonical(result)
    for unsupported in ('prediction_probability', 'trading_return', 'price_target',
                        'win_rate', 'model_winner', 'coverage_probability', 'error_ratio'):
        assert f'"{unsupported}":' not in encoded


def test_comparison_values_are_exact_differences_of_the_same_reported_losses():
    result = report(source_query(fixed_prices('P')))['result']
    models = {m['model_id']: m for m in result['models']}
    for field in ('mae_pre', 'rmse_pre'):
        comparison = result['comparisons'][field]
        assert comparison['K_minus_R'] == models['kalman'][field] - models['last_close'][field]
        assert comparison['K_minus_E'] == models['kalman'][field] - models['lagged_ema'][field]
        assert comparison['field_reasons'] == {}


@pytest.mark.parametrize('field', ['rows', 'unlocated'])
def test_supported_tuple_containers_preserve_readonly_inputs(field):
    query = source_query(fixed_prices('T'))
    expected = report(query)
    query[field] = tuple(query[field])
    before = deepcopy(query)
    assert report(query) == expected
    assert query == before


def test_strict_position_helper_and_display_rounding_have_separate_authority():
    module = importlib.import_module('anatrading.forecast_diagnostics')
    q = math.nextafter(2. ** -53, math.inf)
    error = 2. ** -52
    previous = dict(model_id='kalman', abs_error_quantile=q, mae_pre=0., rmse_pre=0., field_reasons={})
    actual = module._model_result(previous, 1., error)
    assert actual['upper_log'] == 1. + error
    assert actual['position'] == 'above'
    for e, expected in ((q, 'inside'), (-q, 'inside'),
                        (math.nextafter(q, math.inf), 'above'),
                        (math.nextafter(-q, -math.inf), 'below')):
        assert module._position(e, q) == expected


def test_nonfinite_display_endpoint_only_closes_that_endpoint():
    module = importlib.import_module('anatrading.forecast_diagnostics')
    previous = dict(model_id='kalman', abs_error_quantile=1e308,
                    mae_pre=1e308, rmse_pre=None, field_reasons={'rmse_pre': 'numerical_failure'})
    before = deepcopy(previous)
    actual = module._model_result(previous, 1e308, 1.)
    assert previous == before
    assert actual['lower_log'] == 0. and actual['upper_log'] is None
    assert actual['position'] == 'inside'
    assert actual['abs_error_quantile'] == actual['mae_pre'] == 1e308
    assert actual['field_reasons']['upper_log'] == 'price_range_numerical_failure'
    assert actual['field_reasons']['rmse_pre'] == 'numerical_failure'


@pytest.mark.parametrize('invalid_current', [False, True])
def test_cutoff_freeze_precedes_capture_update_current_and_ring_append(monkeypatch, invalid_current):
    from collections import deque
    module = importlib.import_module('anatrading.forecast_diagnostics')
    events, current_ordinal = [], None
    old_init = module._DiagnosticCollector.__init__
    old_freeze = module._DiagnosticCollector.freeze
    old_observe = module._DiagnosticCollector.observe
    old_capture = signal._capture_prior
    old_update = signal._update
    class TracedRing(deque):
        def append(self, value):
            events.append(('append', value['observation_ordinal']))
            super().append(value)
        def clear(self):
            events.append(('clear', current_ordinal))
            super().clear()
    def init(self, *args, **kwargs):
        old_init(self, *args, **kwargs)
        self.ring = TracedRing(self.ring, maxlen=60)
    def freeze(self, *args, **kwargs):
        events.append(('freeze', len(self.ring)))
        return old_freeze(self, *args, **kwargs)
    def capture(*args, **kwargs):
        prior = old_capture(*args, **kwargs)
        events.append(('capture', prior.origin_ordinal + 1))
        return prior
    updates = 1
    def update(*args, **kwargs):
        nonlocal updates
        updates += 1
        events.append(('update', updates))
        return old_update(*args, **kwargs)
    def observe(self, bar, row, prior):
        nonlocal current_ordinal
        current_ordinal = row['ordinal']
        events.append(('observe', current_ordinal))
        return old_observe(self, bar, row, prior)
    monkeypatch.setattr(module._DiagnosticCollector, '__init__', init)
    monkeypatch.setattr(module._DiagnosticCollector, 'freeze', freeze)
    monkeypatch.setattr(module._DiagnosticCollector, 'observe', observe)
    monkeypatch.setattr(signal, '_capture_prior', capture)
    monkeypatch.setattr(signal, '_update', update)
    query = source_query(fixed_prices('T')[:82])
    if invalid_current:
        query['rows'][-1]['values'] = dict.fromkeys(('open', 'high', 'low', 'close'), '0')
    result = report(query)['result']
    freeze_at = events.index(('freeze', 60))
    capture_at = events.index(('capture', 82))
    observe_at = events.index(('observe', 82))
    assert freeze_at < capture_at < observe_at
    if invalid_current:
        assert ('update', 82) not in events and ('append', 82) not in events
        assert observe_at < events.index(('clear', 82))
        assert result['calculation_status'] == 'unavailable'
    else:
        assert capture_at < events.index(('update', 82)) < observe_at
        assert observe_at < events.index(('append', 82))
        assert [e['observation_ordinal'] for e in result['evidence']] == list(range(22, 82))


@pytest.mark.parametrize('name', LEGACY_NAMES)
def test_legacy_api_envelope_and_analysis_identity_are_frozen(name):
    from anatrading.research_api import _calculate
    query = legacy_query(name)
    parameters = dict(cutoff=day(159), lookback=20, horizon=5, test_start=None)
    frozen_result = golden()[name]
    expected_identity = dict(method_id='daily-causal-research-v1',
        inputs=[dict(snapshot_id=query['snapshot_id'], query_id=query['query_id'])],
        parameters={**parameters, 'model': frozen_result['parameters']})
    expected = dict(**expected_identity, analysis_id=identity(expected_identity), mode='retrospective',
        limitations=['retrospective_source_version', 'adjustment_basis_unverified',
                     'historical_availability_unverified', 'calendar_and_bar_closure_unverified',
                     'descriptive_estimates_not_trading_returns'], result=frozen_result)
    with localcontext() as context, legacy_injection(name):
        if name == 'T_low_context': context.prec = 3
        actual = _calculate('single', [query], parameters, ValueError)
    assert canonical(actual) == canonical(expected)


@pytest.mark.parametrize('invalid_query', [None, [], True, 'query'])
def test_top_level_query_must_be_mapping(invalid_query):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    with pytest.raises(ValueError, match='^invalid_forecast_query$'):
        module.forecast_diagnostic_report(invalid_query, cutoff='2020-01-01')


@pytest.mark.parametrize('kind', tuple('ZCTAJPV'))
def test_binary64_current_and_evidence_errors_exactly_match_old_innovation_and_return(kind):
    prices = fixed_prices(kind)
    old = signal.signal_report(source_query(prices))['series']
    checked = set()
    for n in (82, 100, 160):
        result = report(source_query(prices[:n]))['result']
        assert result['models'][0]['error_log'] == old[n - 1]['innovation']
        assert result['models'][1]['error_log'] == old[n - 1]['log_return']
        checked.add(n)
        for evidence in result['evidence']:
            ordinal = evidence['observation_ordinal']
            assert evidence['kalman_error_log'] == old[ordinal - 1]['innovation']
            assert evidence['last_close_error_log'] == old[ordinal - 1]['log_return']
            checked.add(ordinal)
    assert checked == set(range(22, 161))


@pytest.mark.parametrize('case', ['ordinary', 'bad_price', 'duplicate', 'unlocated',
                                  'code_conflict', 'adjustflag_conflict', 'precision'])
def test_decoded_store_public_and_internal_reads_match_without_changing_query_export_or_old_report(tmp_path, case):
    from anatrading.store import EvidenceStore
    from test_formats import bao_payload
    prices = fixed_prices('T')
    records = [[day(i), 'sh.600001', price, price, price, price, '100', '1000', '3']
               for i, price in enumerate(prices)]
    if case == 'bad_price': records[40][2:6] = ['0'] * 4
    if case == 'duplicate': records[40][0] = records[41][0]
    if case == 'unlocated': records[40][0] = 'not-a-date'
    if case == 'code_conflict': records[40][1] = 'sz.000001'
    if case == 'adjustflag_conflict': records[40][8] = '2'
    if case == 'precision': records[1][2:6] = ['100.000000000000000001'] * 4
    with EvidenceStore(tmp_path / 'store') as store:
        imported = store.import_bytes(bao_payload(records, code='sh.600001'), 'baostock-decoded-v0.9.4')
        assert imported['status'] == 'committed'
        sid = imported['snapshot_id']
        public = store.query(sid, cutoff=day(159))
        internal = store._research_query(sid, cutoff=day(159))
        before_public, before_internal = deepcopy(public), deepcopy(internal)
        before_old = signal.signal_report(public)
        first_export = store.export_json(sid, cutoff=day(159))
        expected_bytes = Path(first_export['path']).read_bytes()
        public_report, internal_report = report(public), report(internal)
        assert public_report == internal_report
        assert public['query_id'] == internal['query_id']
        assert public == before_public and internal == before_internal
        assert store.query(sid, cutoff=day(159)) == before_public
        assert store._research_query(sid, cutoff=day(159)) == before_internal
        assert signal.signal_report(public) == signal.signal_report(internal) == before_old
        second_export = store.export_json(sid, cutoff=day(159))
        assert second_export == first_export
        assert Path(second_export['path']).read_bytes() == expected_bytes


def test_single_normalization_coverage_and_state_pass(monkeypatch):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    counts = dict(bars=0, coverage=0, state=0)
    original_bars, original_coverage, original_state = module.daily_bars, module.daily_coverage, signal._causal_rows
    normalized = None
    def bars(query):
        nonlocal normalized
        counts['bars'] += 1
        normalized = original_bars(query)
        return normalized
    def coverage(query, supplied=None):
        counts['coverage'] += 1
        assert supplied is normalized
        return original_coverage(query, supplied)
    def state(supplied, **kwargs):
        counts['state'] += 1
        assert supplied is normalized
        return original_state(supplied, **kwargs)
    monkeypatch.setattr(module, 'daily_bars', bars)
    monkeypatch.setattr(module, 'daily_coverage', coverage)
    monkeypatch.setattr(signal, '_causal_rows', state)
    assert report(source_query(fixed_prices('T')))['result']['calculation_status'] == 'computed'
    assert counts == dict(bars=1, coverage=1, state=1)


def test_covariance_scale_stays_path_independent_while_empirical_errors_differ():
    results = [report(source_query(fixed_prices(kind)))['result'] for kind in 'ZCTAJPV']
    assert len({r['prior_scales']['model_innovation_variance_pre'] for r in results}) == 1
    assert len({r['models'][0]['abs_error_quantile'] for r in results}) > 1


def test_one_model_rmse_failure_preserves_other_model_losses_and_mae_pairs():
    module = importlib.import_module('anatrading.forecast_diagnostics')
    evidence = error_evidence([0.] * 60)
    evidence[0]['kalman_error_log'] = 1e200
    for item in evidence:
        item['last_close_error_log'] = 1.
        item['lagged_ema_error_log'] = 2.
    summary = module._window_summary(evidence)
    models = summary['models']
    assert models[0]['rmse_pre'] is None
    assert models[0]['mae_pre'] == 1e200 / 60
    assert models[0]['abs_error_quantile'] == 0.
    assert models[1]['mae_pre'] == models[1]['rmse_pre'] == 1.
    assert models[2]['mae_pre'] == models[2]['rmse_pre'] == 2.
    comparisons = module._comparisons(models)
    assert comparisons['rmse_pre'] == dict(K_minus_R=None, K_minus_E=None,
        field_reasons=dict(K_minus_R='numerical_failure', K_minus_E='numerical_failure'))
    assert comparisons['mae_pre'] == dict(K_minus_R=models[0]['mae_pre'] - 1.,
        K_minus_E=models[0]['mae_pre'] - 2., field_reasons={})


def test_loss_sum_overflow_does_not_close_finite_quantile():
    module = importlib.import_module('anatrading.forecast_diagnostics')
    summary = module._window_summary(error_evidence([1e308] * 60))
    for model in summary['models']:
        assert model['abs_error_quantile'] == 1e308
        assert model['mae_pre'] is None and model['rmse_pre'] is None
        assert model['field_reasons'] == dict(mae_pre='numerical_failure', rmse_pre='numerical_failure')
    json.dumps(summary, allow_nan=False)


@pytest.mark.parametrize('bad', [math.inf, math.nan])
def test_nonfinite_internal_error_is_an_explicit_invariant_failure(bad):
    module = importlib.import_module('anatrading.forecast_diagnostics')
    evidence = error_evidence([0.] * 59 + [bad])
    with pytest.raises(RuntimeError, match='forecast_internal_invariant'):
        module._window_summary(evidence)
