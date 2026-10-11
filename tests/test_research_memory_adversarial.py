"""Independent lifetime, failure-boundary and frozen-output checks for B.

Synthetic inputs only. Golden hashes come from frozen commit 41190aa, not the
new shared preparation/evaluation helpers. No performance qualification here.
"""
import asyncio
from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
import hashlib
import json
import random
import weakref

import duckdb
import pytest
from starlette.responses import JSONResponse

import anatrading.research_api as api
import anatrading.stock_filters as filters
import anatrading.universe_research as universe
from anatrading.models import DecodeError, VALUE_FIELDS
from anatrading.numeric import NumericError
from anatrading.store import EvidenceStore, StoreError, _identity
from anatrading.tdx_acquisition import AcquireError
from anatrading.workbench import _RequestError, _STORE_CODES, _safe_store_call
from test_research_api import client_for, seed
from test_stock_filters import atom, rule

IDS = [f'{i:064x}' for i in range(1, 5)]
D = '2026-01-18'
SPEC = rule([atom(threshold='0.05'), atom('volatility', '0.2')],
            [atom('max_drawdown', '-0.1')])


def sources(trial=0):
    rng = random.Random(2601011 + trial)
    result = []
    for i, sid in enumerate(IDS):
        rows, unlocated = [], []
        for j in range(25):
            day = (date(2026, 1, 1) + timedelta(days=j)).isoformat()
            price = Decimal(f'{10 + rng.randrange(5)}.{rng.randrange(1000):018}')
            row = dict(ordinal=j + 1, label=day, tokens={}, checks=[],
                       values={key: price for key in ('open', 'high', 'low', 'close')})
            # Fixed source defects, including past/future/unknown unlocated dates.
            kind = (trial + i) % 8
            if kind == 1 and j == 17:
                continue
            if kind == 2 and j == 3:
                row['values']['high'] = None
            if kind == 3 and j == 16:
                row['label'] = '2026-01-16'
            if kind == 4 and j in (1, 15, 22):
                row['label'] = None
                row['tokens']['date'] = ['undated', '2026/01/16', '2099/01/01'][(1, 15, 22).index(j)]
            if kind == 5 and j == 16:
                row['tokens']['code'] = 'sh.000001'
                row['checks'] = [dict(name='source_code', outcome='fail')]
            if kind == 6 and j == 16:
                row['label'] = '2026-01-00'
                row['tokens']['source_date'] = '20260117'
            (unlocated if row['label'] is None else rows).append(row)
        rng.shuffle(rows)
        metadata = dict(period='1d', source_code=f'{600001 + i}.SH', source='synthetic',
                        quarantined=(trial + i) % 11 == 0,
                        requested_adjustment=None if i % 2 else 'none',
                        unknown_extra={'nested': [None, 'unknown', {'keep': True}]})
        if i % 2:
            metadata['transport_evidence'] = None
        manifest = dict(raw_sha256=str(i) * 64, source_contract_id='shared-claim',
                        versions=dict(test='frozen'), contract=dict(format_id='synthetic', version='1',
                        source_semantics=dict(scope=None, fields=dict(price_unit=dict(
                            value='CNY', status='known', reason='documented_meaning_only',
                            **({} if i == 0 else {'applicability': None if i == 1 else 'unverified'}))))))
        selection = dict(snapshot_id=sid, mode='retrospective', cutoff=D,
                         ordinal_start=None, ordinal_end=None, fields=list(VALUE_FIELDS), versions=manifest['versions'])
        result.append(dict(snapshot_id=sid, batch_id='b' + sid, query_id=_identity(selection),
                           selection=selection, manifest=manifest, metadata=metadata,
                           rows=rows, unlocated=unlocated,
                           counts=dict(selected_rows=len(rows), unlocated_rows=len(unlocated),
                                       batch_rows=len(rows) + len(unlocated), batch_unlocated_rows=len(unlocated)),
                           batch_checks=[dict(name='known_negative_sample', outcome='fail')]
                           if (trial + i) % 13 == 0 else [], read_projection='daily_ohlc_input_v1'))
    return result


class SyntheticStore:
    def __init__(self, queries=None):
        self.queries = queries if queries is not None else sources(7)
        self.events = []

    def query_row_count(self, sid, cutoff=None):
        self.events.append(('count', sid))
        q = next(q for q in self.queries if q['snapshot_id'] == sid)
        return len(q['rows']) + len(q['unlocated'])

    def _research_query(self, sid, cutoff=None):
        self.events.append(('read', sid))
        return deepcopy(next(q for q in self.queries if q['snapshot_id'] == sid))


def calculate(store, endpoint, n=5):
    if endpoint == 'universe':
        return api._calculate_universe(store, IDS, dict(cutoff=D, lookback=n), _RequestError, _safe_store_call)
    return api._calculate_filter(store, IDS, D, n, SPEC, _RequestError, _safe_store_call)


def error_result(operation):
    try:
        _safe_store_call(operation)
    except _RequestError as exc:
        return exc.code, exc.status
    raise AssertionError('a failed request returned a result')


@pytest.mark.parametrize('n,expected', [
    (2, '5ee73867b281b2c2a3e3db7fde247dc9e481c8dfcfffdd9a8c0c39b5cd1e11e6'),
    (5, '31f37767912cddf3eeb2b791ed89d730495faaac5e558a14d540a2faa92c1b34'),
    (252, 'e81ff6ad1d8fc62f08cb60cffb6c8a38d6671fd41c61030767bfd25269385c46'),
])
def test_prepared_complete_json_matches_independent_frozen_old_matrix(n, expected):
    bodies = []
    with localcontext() as context:
        context.prec = 2
        for trial in range(16):
            for endpoint in ('universe', 'universe-filter'):
                store = SyntheticStore(sources(trial))
                before = _identity(store.queries)
                response = calculate(store, endpoint, n)
                bodies.append(JSONResponse(response).body)
                assert _identity(store.queries) == before
                assert store.events == [('count', sid) for sid in IDS] + [('read', sid) for sid in IDS]
    assert hashlib.sha256(b'\n'.join(bodies)).hexdigest() == expected


class WeakDict(dict):
    pass


class WeakList(list):
    pass


def tracked_query(query, refs):
    """Instrument actual containers; header values deliberately remain retained."""
    query = WeakDict(query)
    refs.append(weakref.ref(query))
    for scope in ('rows', 'unlocated'):
        records = WeakList()
        for row in query[scope]:
            row = WeakDict(row)
            row['tokens'] = WeakDict(row['tokens'])
            row['checks'] = WeakList(row['checks'])
            row['values'] = WeakDict(row['values'])
            refs.extend(weakref.ref(obj) for obj in (row, row['tokens'], row['checks'], row['values']))
            records.append(row)
        query[scope] = records
        refs.append(weakref.ref(records))
    return query


def fail_with_chain(query, family):
    # Both the original exception argument and chained exception may hold rows.
    try:
        raise ValueError(query)
    except ValueError as cause:
        if family == 'acquire':
            raise AcquireError('invalid_response', raw=query['rows']) from cause
        if family == 'decode':
            raise DecodeError('invalid_text_structure') from cause
        if family == 'numeric':
            raise NumericError('invalid_decimal') from cause
        if family == 'value':
            raise ValueError('secret source text') from cause
        raise RuntimeError(query['rows']) from cause


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
@pytest.mark.parametrize('stage', ['selection', 'coverage'])
@pytest.mark.parametrize('family', ['acquire', 'decode', 'numeric', 'value', 'runtime'])
def test_chained_error_arguments_and_raw_never_keep_history_alive(monkeypatch, endpoint, stage, family):
    refs = []
    class Store(SyntheticStore):
        def _research_query(self, sid, cutoff=None):
            assert all(ref() is None for ref in refs), 'old rows/args/traceback/closure retained'
            return tracked_query(super()._research_query(sid, cutoff), refs)
    store = Store()
    name = '_at_cutoff' if stage == 'selection' else 'daily_coverage'
    def broken(query, *args):
        fail_with_chain(query, family)
    monkeypatch.setattr(universe, name, broken)
    response = error_result(lambda: calculate(store, endpoint))
    expected = ('internal_error', 500)
    if family != 'runtime':
        expected = ('invalid_research_input', 400) if endpoint == 'universe' else {
            'acquire': ('invalid_response', 400), 'decode': ('invalid_text_structure', 400),
            'numeric': ('invalid_decimal', 400), 'value': ('internal_error', 500)}[family]
    assert response == expected
    assert len([e for e in store.events if e[0] == 'read']) == len(IDS)
    assert all(ref() is None for ref in refs)


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_real_store_history_dies_before_each_following_read(monkeypatch, tmp_path, endpoint):
    ids = seed(tmp_path / 'store', 30)
    refs, events = [], Counter()
    original = EvidenceStore._research_query
    def read(self, sid, cutoff=None):
        assert all(ref() is None for ref in refs), 'real Store result survived next read'
        events['read'] += 1
        return tracked_query(original(self, sid, cutoff), refs)
    verify = EvidenceStore._verify_raw
    def checked(self, *args):
        events['raw'] += 1
        return verify(self, *args)
    monkeypatch.setattr(EvidenceStore, '_research_query', read)
    monkeypatch.setattr(EvidenceStore, '_verify_raw', checked)
    async def run():
        async with client_for(tmp_path / 'store') as client:
            events.clear()
            p = dict(snapshot_ids=','.join(ids), cutoff='2025-01-30', lookback='5')
            if endpoint == 'universe-filter': p['rule'] = json.dumps(SPEC)
            for _ in range(2):
                response = await client.get('/api/research/' + endpoint, params=p)
                assert response.status_code == 200, response.text
                assert all(ref() is None for ref in refs)
            assert events == {'read': 6, 'raw': 6}
    asyncio.run(run())


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
@pytest.mark.parametrize('site', ['read', 'selection', 'coverage'])
def test_all_owner_code_families_keep_exact_status(monkeypatch, endpoint, site):
    families = (StoreError, NumericError, DecodeError, AcquireError)
    for factory in families:
        for code in sorted(_STORE_CODES | {'unclassified secret'}):
            store = SyntheticStore()
            def broken(*args, _factory=factory, _code=code, **kwargs):
                raise _factory(_code)
            with monkeypatch.context() as local:
                if site == 'read': local.setattr(store, '_research_query', broken)
                else: local.setattr(universe, '_at_cutoff' if site == 'selection' else 'daily_coverage', broken)
                actual = error_result(lambda: calculate(store, endpoint))
            if site != 'read' and issubclass(factory, ValueError):
                if code in api._SAFE_ERRORS or endpoint == 'universe-filter' and code in filters.FILTER_ERRORS:
                    expected = (code, 400)
                elif endpoint == 'universe': expected = ('invalid_research_input', 400)
                else: expected = owner_expected(code)
            else: expected = owner_expected(code)
            assert actual == expected, (endpoint, site, factory.__name__, code, actual, expected)


def owner_expected(code):
    if code not in _STORE_CODES: code = 'internal_error'
    status = 404 if code == 'snapshot_not_found' else 400 if code.startswith('invalid_') or code == 'mode_not_supported' else 409
    if code in {'storage_io_error', 'database_error', 'internal_error'}: status = 500
    return code, status


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_identity_precedes_selection_and_period_precedes_identity(monkeypatch, endpoint):
    store = SyntheticStore()
    store.queries[2]['metadata'] = {'period': '1d'}
    def bad_selection(*args): raise ValueError('invalid_cutoff')
    monkeypatch.setattr(universe, '_at_cutoff', bad_selection)
    assert error_result(lambda: calculate(store, endpoint)) == ('research_identity_unavailable', 400)
    store.queries[3]['metadata']['period'] = '1m'
    assert error_result(lambda: calculate(store, endpoint)) == ('unsupported_period', 400)


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_cross_market_precedes_duplicate_symbol_and_snapshot(monkeypatch, endpoint):
    store = SyntheticStore()
    store.queries[1]['metadata']['source_code'] = store.queries[0]['metadata']['source_code']
    store.queries[2]['metadata']['source_code'] = 'ABC.NYSE'
    assert error_result(lambda: calculate(store, endpoint)) == ('research_market_mismatch', 400)
    store.queries[2]['metadata']['source_code'] = '600003.SH'
    assert error_result(lambda: calculate(store, endpoint)) == ('research_duplicate_symbol', 400)


def test_filter_all_source_projections_finish_before_first_member(monkeypatch):
    source_projection = filters._source
    events = []
    def source(query, identity):
        events.append(('source', query['snapshot_id']))
        if query['snapshot_id'] == IDS[-1]: raise ValueError('invalid_cutoff')
        return source_projection(query, identity)
    def member(*args):
        events.append(('member', None))
        raise ValueError('invalid_parameters')
    monkeypatch.setattr(filters, '_source', source)
    monkeypatch.setattr(filters, '_member', member)
    assert error_result(lambda: calculate(SyntheticStore(), 'universe-filter')) == ('invalid_cutoff', 400)
    assert events == [('source', sid) for sid in IDS]


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_envelope_valueerror_stays_at_original_route_boundary(monkeypatch, endpoint):
    def broken(*args): raise ValueError('private envelope detail')
    monkeypatch.setattr(api if endpoint == 'universe' else filters, '_identity', broken)
    expected = ('internal_error', 500)
    assert error_result(lambda: calculate(SyntheticStore(), endpoint)) == expected


@pytest.mark.parametrize('damage', ['same_length', 'truncate', 'missing'])
@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_same_open_owner_rechecks_raw_after_success_and_empty_prefix(tmp_path, endpoint, damage):
    root = tmp_path / 'store'
    ids = seed(root, 8)
    with EvidenceStore(root) as store:
        full = store.query(sorted(ids)[1])
        path = store._raw_path(full['manifest']['raw_sha256'])
        original = path.read_bytes()
    async def run():
        async with client_for(root) as client:
            for cutoff in ('2025-01-08', '2020-01-01'):
                params = dict(snapshot_ids=','.join(ids), cutoff=cutoff, lookback='2')
                if endpoint == 'universe-filter': params['rule'] = json.dumps(SPEC)
                baseline = await client.get('/api/research/' + endpoint, params=params)
                assert baseline.status_code == 200, baseline.text
                try:
                    if damage == 'missing': path.unlink()
                    elif damage == 'truncate': path.write_bytes(original[:-1])
                    else: path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                    response = await client.get('/api/research/' + endpoint, params=params)
                    expected = 'raw_object_missing' if damage == 'missing' else 'raw_object_corrupt'
                    assert response.status_code == 409 and response.json() == {'error': expected}
                finally:
                    path.write_bytes(original)
                restored = await client.get('/api/research/' + endpoint, params=params)
                assert restored.content == baseline.content
    asyncio.run(run())


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_only_small_windows_survive_complete_source_bar_preparation(monkeypatch, endpoint):
    groups = []
    original = universe.daily_bars
    def bars(query):
        result = [WeakDict(bar) for bar in original(query)]
        groups.append([weakref.ref(bar) for bar in result])
        return result
    monkeypatch.setattr(universe, 'daily_bars', bars)
    class Store(SyntheticStore):
        def _research_query(self, *args, **kwargs):
            for refs in groups:
                assert sum(ref() is not None for ref in refs) <= 6
            return super()._research_query(*args, **kwargs)
    guard = api._research_call if endpoint == 'universe' else api._filter_call
    prepared = api._load_universe(Store(sources(0)), IDS, D, 5, guard, _RequestError, _safe_store_call)
    expected = sum(len(item['prepared']['window']) for item in prepared)
    assert sum(sum(ref() is not None for ref in refs) for refs in groups) == expected <= 24
    assert all(set(item['prepared']) == {'coverage', 'window'} for item in prepared)
    assert all('rows' not in item['header'] and 'unlocated' not in item['header'] for item in prepared)
    del prepared
    assert all(ref() is None for group in groups for ref in group)


@pytest.mark.parametrize('endpoint', ['universe', 'universe-filter'])
def test_late_real_read_json_failure_beats_earlier_identity_error(monkeypatch, tmp_path, endpoint):
    root = tmp_path / 'store'
    ids = sorted(seed(root, 8))
    with EvidenceStore(root) as store:
        first, last = store._research_query(ids[0]), store._research_query(ids[1])
        metadata = dict(first['metadata'])
        metadata.pop('source_code', None)
        metadata.pop('source_symbol', None)
        metadata.pop('interpretation', None)
        store.db.execute('UPDATE batches SET metadata_json=? WHERE batch_id=?',
                         [json.dumps(metadata), first['batch_id']])
        store.db.execute('UPDATE observations SET tokens_json=? WHERE batch_id=? AND ordinal=1',
                         ['{secret invalid JSON', last['batch_id']])
    seen = []
    original = EvidenceStore._research_query
    def read(self, sid, cutoff=None):
        seen.append(sid)
        return original(self, sid, cutoff)
    monkeypatch.setattr(EvidenceStore, '_research_query', read)
    async def run():
        async with client_for(root) as client:
            params = dict(snapshot_ids=','.join(ids), cutoff='2025-01-08', lookback='2')
            if endpoint == 'universe-filter': params['rule'] = json.dumps(SPEC)
            response = await client.get('/api/research/' + endpoint, params=params)
            assert response.status_code == 500 and response.json() == {'error': 'internal_error'}
            assert 'secret' not in response.text
            assert seen == ids[:2]
    asyncio.run(run())


@pytest.mark.parametrize('kind', ['selection', 'normalize', 'coverage'])
def test_baseexception_interrupts_are_not_deferred_or_read_past(monkeypatch, kind):
    class StopPreparation(BaseException):
        pass
    store = SyntheticStore()
    name = {'selection': '_at_cutoff', 'normalize': 'daily_bars', 'coverage': 'daily_coverage'}[kind]
    def stop(*args):
        raise StopPreparation()
    monkeypatch.setattr(universe, name, stop)
    with pytest.raises(StopPreparation):
        calculate(store, 'universe')
    assert store.events == [('count', sid) for sid in IDS] + [('read', IDS[0])]
