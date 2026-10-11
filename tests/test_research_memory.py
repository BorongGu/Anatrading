"""Full-prefix preparation keeps source history request-local and errors ordered."""
import asyncio
from decimal import localcontext
import json
import weakref

import duckdb
import pytest

import anatrading.research_api as api
import anatrading.universe_research as universe
from anatrading.numeric import NumericError
from anatrading.stock_filters import filter_report
from anatrading.store import EvidenceStore, StoreError, _identity
from anatrading.workbench import _RequestError
from test_pair_research import query
from test_research_api import client_for, seed
from test_stock_filters import atom, golden_queries, rule

IDS = [f'{i:064x}' for i in range(1, 4)]
D = '2026-01-06'
SPEC = rule([atom(), atom('volatility', '0.1'), atom('max_drawdown', '-0.1')],
            [atom(threshold='0.2'), atom('volatility', '0.2'), atom('max_drawdown', '-0.2')])


class TrackedRow(dict):
    pass


def source(sid):
    index = IDS.index(sid)
    result = query([1, 2, 3, 4, 5, 6], f'{600001 + index}.SH', snapshot=sid)
    result['selection'] = dict(cutoff=D, ordinal_start=None, ordinal_end=None)
    result['batch_id'] = 'batch-' + sid
    result['rows'] = [TrackedRow(row) for row in result['rows']]
    return result


def request(tmp_path, endpoint, ids=IDS):
    async def run():
        async with client_for(tmp_path / 'store') as client:
            params = dict(snapshot_ids=','.join(reversed(ids)), cutoff=D, lookback='2')
            if endpoint == 'universe-filter':
                params['rule'] = json.dumps(SPEC)
            return await client.get('/api/research/' + endpoint, params=params)
    return asyncio.run(run())


def mock_reads(monkeypatch, read):
    monkeypatch.setattr(EvidenceStore, 'query_row_count', lambda *args, **kwargs: 6)
    monkeypatch.setattr(EvidenceStore, '_research_query', read)


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
@pytest.mark.parametrize('failure_stage', [None, 'selection', 'normalization'])
def test_previous_source_rows_die_before_next_read_even_with_deferred_failure(monkeypatch, tmp_path, endpoint, failure_stage):
    refs, read_ids = [], []
    def read(store, sid, cutoff=None):
        assert all(ref() is None for ref in refs), 'previous full source is still retained'
        read_ids.append(sid)
        result = source(sid)
        refs.extend(weakref.ref(row) for row in result['rows'])
        return result
    mock_reads(monkeypatch, read)
    if failure_stage is not None:
        name = '_at_cutoff' if failure_stage == 'selection' else 'daily_bars'
        original = getattr(universe, name)
        def broken(q, *args):
            if q['snapshot_id'] == IDS[0]:
                # The raised exception's frame refers to q; retaining it leaks rows.
                raise ValueError('invalid_cutoff')
            return original(q, *args)
        monkeypatch.setattr(universe, name, broken)
    response = request(tmp_path, endpoint)
    assert response.status_code == (200 if failure_stage is None else 400), response.text
    if failure_stage:
        assert response.json() == dict(error='invalid_cutoff')
    assert read_ids == IDS
    assert all(ref() is None for ref in refs)


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
@pytest.mark.parametrize('kind', ['period', 'identity', 'selection', 'normalization'])
def test_later_raw_failure_precedes_every_earlier_research_failure(monkeypatch, tmp_path, endpoint, kind):
    seen = []
    def read(store, sid, cutoff=None):
        seen.append(sid)
        if sid == IDS[1]:
            raise StoreError('raw_object_corrupt')
        q = source(sid)
        if kind == 'period':
            q['metadata']['period'] = '1m'
        elif kind == 'identity':
            q['metadata'] = dict(period='1d')
        return q
    mock_reads(monkeypatch, read)
    if kind in ('selection', 'normalization'):
        name = '_at_cutoff' if kind == 'selection' else 'daily_bars'
        def broken(*args):
            raise ValueError('invalid_cutoff')
        monkeypatch.setattr(universe, name, broken)
    response = request(tmp_path, endpoint)
    assert response.status_code == 409 and response.json() == dict(error='raw_object_corrupt')
    assert seen == IDS[:2], 'never read past the first source read error'


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_all_counts_finish_before_budget_rejection(monkeypatch, tmp_path, endpoint):
    seen = []
    def count(store, sid, cutoff=None):
        seen.append(sid)
        if sid == IDS[1]:
            raise StoreError('snapshot_not_found')
        return 20_001
    def forbidden(*args, **kwargs):
        raise AssertionError('budget failure read a source')
    monkeypatch.setattr(EvidenceStore, 'query_row_count', count)
    monkeypatch.setattr(EvidenceStore, '_research_query', forbidden)
    response = request(tmp_path, endpoint)
    assert response.status_code == 404 and response.json() == dict(error='snapshot_not_found')
    assert seen == IDS[:2]


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_all_identity_errors_precede_cross_member_checks(monkeypatch, tmp_path, endpoint):
    def read(store, sid, cutoff=None):
        q = source(sid)
        if sid == IDS[1]:
            q['metadata']['source_code'] = 'AAPL.NASDAQ'
        elif sid == IDS[2]:
            q['metadata'] = dict(period='1d')
        return q
    mock_reads(monkeypatch, read)
    response = request(tmp_path, endpoint)
    assert response.status_code == 400 and response.json() == dict(error='research_identity_unavailable')


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_every_selection_error_precedes_earlier_normalization_error(monkeypatch, tmp_path, endpoint):
    mock_reads(monkeypatch, lambda store, sid, cutoff=None: source(sid))
    original_selection, original_bars = universe._at_cutoff, universe.daily_bars
    def selected(q, cutoff):
        if q['snapshot_id'] == IDS[1]:
            raise ValueError('invalid_cutoff')
        return original_selection(q, cutoff)
    def bars(q):
        if q['snapshot_id'] == IDS[0]:
            raise ValueError('research_row_limit')
        return original_bars(q)
    monkeypatch.setattr(universe, '_at_cutoff', selected)
    monkeypatch.setattr(universe, 'daily_bars', bars)
    response = request(tmp_path, endpoint)
    assert response.status_code == 400 and response.json() == dict(error='invalid_cutoff')


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_first_member_metric_error_precedes_later_normalization_error(monkeypatch, tmp_path, endpoint):
    mock_reads(monkeypatch, lambda store, sid, cutoff=None: source(sid))
    original_bars = universe.daily_bars
    def bars(q):
        if q['snapshot_id'] == IDS[1]:
            raise ValueError('research_row_limit')
        return original_bars(q)
    def metric(prices):
        raise ValueError('invalid_parameters')
    monkeypatch.setattr(universe, 'daily_bars', bars)
    monkeypatch.setattr(universe, '_volatility', metric)
    response = request(tmp_path, endpoint)
    assert response.status_code == 400 and response.json() == dict(error='invalid_parameters')


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
@pytest.mark.parametrize('factory,universe_error,filter_error,status', [
    (lambda: ValueError('secret'), 'invalid_research_input', 'internal_error', None),
    (lambda: ValueError('invalid_cutoff'), 'invalid_cutoff', 'invalid_cutoff', 400),
    (lambda: NumericError('invalid_decimal'), 'invalid_research_input', 'invalid_decimal', 400),
    (lambda: StoreError('raw_object_corrupt'), 'raw_object_corrupt', 'raw_object_corrupt', 409),
    (lambda: OSError('secret'), 'storage_io_error', 'storage_io_error', 500),
    (lambda: duckdb.Error('secret'), 'database_error', 'database_error', 500),
    (lambda: TypeError('secret'), 'internal_error', 'internal_error', 500),
    (lambda: AssertionError('secret'), 'internal_error', 'internal_error', 500),
])
def test_preparation_reuses_exact_existing_http_error_mapping(monkeypatch, tmp_path, endpoint, factory, universe_error, filter_error, status):
    refs, seen = [], []
    def read(store, sid, cutoff=None):
        assert all(ref() is None for ref in refs)
        seen.append(sid)
        q = source(sid)
        refs.extend(weakref.ref(row) for row in q['rows'])
        return q
    mock_reads(monkeypatch, read)
    def bars(q):
        raise factory()
    monkeypatch.setattr(universe, 'daily_bars', bars)
    response = request(tmp_path, endpoint)
    expected = universe_error if endpoint == 'universe' else filter_error
    expected_status = status if status is not None else 400 if endpoint == 'universe' else 500
    assert response.status_code == expected_status and response.json() == dict(error=expected), response.text
    assert 'secret' not in response.text and response.headers['cache-control'] == 'no-store'
    assert seen == IDS
    assert all(ref() is None for ref in refs)


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_read_valueerror_remains_owner_500_not_calculation_400(monkeypatch, tmp_path, endpoint):
    def read(*args, **kwargs):
        raise ValueError('invalid_cutoff')
    mock_reads(monkeypatch, read)
    response = request(tmp_path, endpoint)
    assert response.status_code == 500 and response.json() == dict(error='internal_error')


def test_pure_wrapper_still_normalizes_and_calculates_one_member_at_a_time(monkeypatch):
    events = []
    original_bars = universe.daily_bars
    def bars(q):
        events.append(('bars', q['snapshot_id']))
        if q['snapshot_id'] == IDS[1]:
            raise AssertionError('later member reached early')
        return original_bars(q)
    def metric(prices):
        events.append(('metric', IDS[0]))
        raise ValueError('first_metric')
    monkeypatch.setattr(universe, 'daily_bars', bars)
    monkeypatch.setattr(universe, '_volatility', metric)
    with pytest.raises(ValueError, match='first_metric'):
        universe.universe_report([source(sid) for sid in IDS], D, 2)
    assert events == [('bars', IDS[0]), ('metric', IDS[0])]


@pytest.mark.parametrize('n', [2, 20, 252])
def test_http_prepared_bytes_match_complete_public_query_oracle(tmp_path, n):
    ids = seed(tmp_path / 'store', 25)
    cutoff = '2025-01-25'
    with EvidenceStore(tmp_path / 'store') as store:
        queries = [store.query(sid, cutoff=cutoff) for sid in sorted(ids)]
        with localcontext() as context:
            context.prec = 2
            reference = {
                'universe': api._calculate('universe', queries, dict(cutoff=cutoff, lookback=n), _RequestError),
                'universe-filter': filter_report(queries, cutoff, n, SPEC),
            }
    from starlette.responses import JSONResponse
    async def run():
        async with client_for(tmp_path / 'store') as client:
            for endpoint in reference:
                params = dict(snapshot_ids=','.join(reversed(ids)), cutoff=cutoff, lookback=str(n))
                if endpoint == 'universe-filter':
                    params['rule'] = json.dumps(SPEC)
                response = await client.get('/api/research/' + endpoint, params=params)
                assert response.status_code == 200, response.text
                assert response.content == JSONResponse(reference[endpoint]).body
    asyncio.run(run())


@pytest.mark.parametrize('n,expected', [
    (2, '09297f64ecf517077072a0535acea65bc22f942712f4c072e266ee9255bce253'),
    (5, '36f5b7dd84c5c14d3fb7d21fd818863a89133d711b5c4452e91da37dc2bc4fc2'),
    (252, 'f2aa2b9f1a65138493ce766ad72f61cdff910387cd97b22ed46baf2b0384b697'),
])
def test_filter_envelope_frozen_before_memory_refactor(n, expected):
    assert _identity(filter_report(golden_queries(), D, n, SPEC)) == expected


def test_shared_evaluator_never_silently_truncates_prepared_members():
    queries = [source(sid) for sid in IDS]
    identities = universe._universe_identities(queries, D, 2)
    preparations = [universe._prepare_window(q, D, 2) for q in queries[:-1]]
    with pytest.raises(ValueError):
        universe._evaluate_members(queries, identities, preparations, D, 2)


@pytest.mark.parametrize('guard', [api._research_call, api._filter_call])
def test_preparation_does_not_capture_baseexception_interrupts(guard):
    from anatrading.workbench import _safe_store_call
    class Cancelled(BaseException):
        pass
    def interrupted():
        raise Cancelled()
    with pytest.raises(Cancelled):
        api._capture_preparation(interrupted, guard, _RequestError, _safe_store_call)
