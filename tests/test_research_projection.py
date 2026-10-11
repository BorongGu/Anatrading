"""Private research reads preserve full-source identity and exact results.

Constructed input only; this is neither real-market nor predictive validation.
The oracle deliberately uses the unchanged public query, never the new reader.
"""
import asyncio
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path

import pyarrow.parquet as pq
import pytest

import anatrading.store as store_module
from anatrading.numeric import decimal_text
from anatrading.pair_research import pair_report
from anatrading.research_api import _load
from anatrading.research_series import daily_bars, daily_coverage
from anatrading.signal_research import signal_report
from anatrading.store import EvidenceStore, StoreError, _json
from anatrading.universe_research import universe_report
from test_formats import bao_payload
from test_research_api import client_for, seed
from test_store import record, text_bytes


PRICES = ('open', 'high', 'low', 'close')
TOP_FIELDS = ('snapshot_id', 'batch_id', 'selection', 'query_id', 'manifest',
              'metadata', 'counts', 'batch_checks')


def projected_reference(full):
    result = {key: deepcopy(full[key]) for key in TOP_FIELDS}
    result['read_projection'] = 'daily_ohlc_input_v1'
    for scope in ('rows', 'unlocated'):
        result[scope] = []
        for row in full[scope]:
            item = {key: deepcopy(row[key]) for key in ('ordinal', 'label', 'tokens', 'checks')}
            item['values'] = {key: None if row['values'][key] is None else Decimal(row['values'][key])
                              for key in PRICES}
            result[scope].append(item)
    return result


def records(code='sh.600001', count=36):
    return [[(date(2025, 1, 1) + timedelta(days=i)).isoformat(), code,
             *([str(10 + i)] * 4), '100', '1000', '3'] for i in range(count)]


def import_rows(store, rows, code='sh.600001', adjustment='3'):
    imported = store.import_bytes(bao_payload(rows, code=code, adjustment=adjustment),
                                  'baostock-decoded-v0.9.4')
    assert imported['status'] == 'committed', imported
    return imported['snapshot_id']


@pytest.fixture
def mixed_source(tmp_path):
    rows = records()
    rows[1][2:6] = ['0.000000000000000001'] * 4
    rows[2][2:6] = ['99999999999999999999.999999999999999999'] * 4
    rows[3][2:6] = ['1.000000000000000001'] * 4
    rows[4][2:6] = ['1.000000000000000002'] * 4
    rows[5][2], rows[6][5], rows[7][3] = '', '0', '-1'
    rows[8][2], rows[9][5] = 'NaN', 'Infinity'
    rows[10][6:8] = ['9223372036854775807', '99999999999999999999.999999999999999999']
    rows[11][6:8] = ['bad', 'NaN']
    rows[12][0] = rows[13][0]  # Duplicate located date.
    rows[14][0] = '2025/01/15'  # An unlocated, recoverably dated source slot.
    rows[15][0] = 'not-a-date'
    rows[16][0] = '2030/01/01'  # Survives SQL cutoff, never enters earlier bars.
    rows.reverse()  # Source ordinals must not be renumbered by label sorting.
    with EvidenceStore(tmp_path / 'store') as store:
        yield store, import_rows(store, rows)


@pytest.mark.parametrize('cutoff', [None, '2020-01-01', '2025-01-04', '2025-01-15', '2025-02-05', '2031-01-01'])
def test_projection_matches_public_query_exactly_on_required_fields(mixed_source, cutoff):
    store, sid = mixed_source
    full = store.query(sid, cutoff=cutoff)
    with localcontext() as context:
        context.prec = 2
        compact = store._research_query(sid, cutoff=cutoff)
        assert compact == projected_reference(full)
        assert daily_bars(compact) == daily_bars(full)
        assert daily_coverage(compact) == daily_coverage(full)
        for horizon in (1, 5, 10, 20):
            assert signal_report(compact, 2, horizon, '2025-01-20') == signal_report(full, 2, horizon, '2025-01-20')
    for scope in ('rows', 'unlocated'):
        for actual, expected in zip(compact[scope], full[scope]):
            for key in PRICES:
                value = actual['values'][key]
                assert value is None or type(value) is Decimal
                assert (None if value is None else decimal_text(value)) == expected['values'][key]
    assert compact['counts']['batch_unlocated_rows'] == 3
    assert compact['counts']['unlocated_rows'] == 3
    assert store.query(sid, cutoff=cutoff) == full


def test_projection_does_not_construct_full_query_extras(mixed_source, monkeypatch):
    store, sid = mixed_source
    expected = projected_reference(store.query(sid))
    statements = []
    connection = store.db

    class TrackedConnection:
        def execute(self, statement, parameters=None):
            statements.append(statement)
            return connection.execute(statement, parameters)

        def close(self):
            connection.close()

    def forbidden(*args, **kwargs):
        raise AssertionError('private read constructed full-query extras')

    store.db = TrackedConnection()
    monkeypatch.setattr(store, 'query', forbidden)
    monkeypatch.setattr(store, '_quality', forbidden)
    monkeypatch.setattr(store_module, 'exact_sum', forbidden)
    monkeypatch.setattr(store_module, 'decimal_text', forbidden)
    assert store._research_query(sid) == expected
    observation_sql = [sql for sql in statements if 'FROM observations' in sql and 'count(*)' not in sql]
    assert len(observation_sql) == 1
    sql = observation_sql[0]
    assert 'SELECT *' not in sql
    for included in ('ordinal', 'label', 'tokens_json', 'checks_json', 'source_open', 'source_close'):
        assert included in sql
    for omitted in ('source_volume', 'source_amount', 'locator', 'source_label', 'volume_shares', 'amount_cny'):
        assert omitted not in sql
    assert 'ORDER BY label NULLS LAST,ordinal' in sql


@pytest.mark.parametrize('bad', ['code', 'adjustment', 'unsupported_adjustment', 'negative', 'unrelated'])
def test_source_qualification_and_all_reports_match(tmp_path, monkeypatch, bad):
    rows = records()
    adjustment = '3'
    if bad == 'code':
        rows[20][1] = 'sz.000001'
    elif bad == 'adjustment':
        rows[20][8] = '2'
    elif bad == 'unsupported_adjustment':
        adjustment = '1'
        for row in rows:
            row[8] = '1'
    elif bad == 'unrelated':
        rows[20][6:8] = ['bad', 'bad']
    if bad == 'negative':
        import anatrading.formats as formats
        monkeypatch.setattr(formats, '_NEGATIVE_DAY', hashlib.sha256(bao_payload(rows, code='sh.600001')).hexdigest())
    with EvidenceStore(tmp_path / 'store') as store:
        ids = [import_rows(store, rows, adjustment=adjustment),
               import_rows(store, records('sz.000001'), code='sz.000001')]
        full = [store.query(sid, cutoff='2025-02-05') for sid in ids]
        compact = [store._research_query(sid, cutoff='2025-02-05') for sid in ids]
    before = deepcopy(compact)
    assert signal_report(compact[0], 5, 5, '2025-01-25') == signal_report(full[0], 5, 5, '2025-01-25')
    assert pair_report(*compact, lookback=5) == pair_report(*full, lookback=5)
    assert universe_report(compact, '2025-02-05', 5) == universe_report(full, '2025-02-05', 5)
    assert compact == before
    expected = {'code': 'source_identity_conflict', 'adjustment': 'source_adjustment_conflict',
                'unsupported_adjustment': 'source_adjustment_check_failed', 'negative': 'known_negative_source',
                'unrelated': None}[bad]
    assert daily_bars(compact[0])[20]['reason'] == expected
    if bad == 'negative':
        compact[0]['metadata']['quarantined'] = False
        assert all(bar['reason'] == 'known_negative_source' for bar in daily_bars(compact[0]))
        compact[0]['metadata']['quarantined'] = True
        compact[0]['batch_checks'] = []
        assert all(bar['reason'] == 'known_negative_source' for bar in daily_bars(compact[0]))


def test_http_bytes_and_all_identities_equal_full_query_path(tmp_path, monkeypatch):
    root = tmp_path / 'store'
    ids = seed(root, 300)
    cutoff = '2025-10-27'
    routes = []
    for window in (20, 252):
        for horizon in (1, 5, 10, 20):
            routes.append(('/api/research/single/' + ids[0],
                           dict(cutoff=cutoff, lookback=window, horizon=horizon, test_start='2025-07-01')))
        for left, right in (ids[:2], list(reversed(ids[:2]))):
            routes.append(('/api/research/pair', dict(left=left, right=right, cutoff=cutoff, lookback=window)))
        for members in (ids, list(reversed(ids))):
            routes.append(('/api/research/universe', dict(snapshot_ids=','.join(members), cutoff=cutoff, lookback=window)))

    async def collect():
        async with client_for(root) as client:
            output = []
            for route, params in routes:
                response = await client.get(route, params=params)
                assert response.status_code == 200, response.text
                assert response.headers['cache-control'] == 'no-store'
                assert 'read_projection' not in response.text
                json.dumps(response.json(), allow_nan=False)
                output.append(response.content)
            return output

    with monkeypatch.context() as patch:
        patch.setattr(EvidenceStore, '_research_query', EvidenceStore.query)
        old = asyncio.run(collect())
    assert asyncio.run(collect()) == old


@pytest.mark.parametrize('damage', ['same_length', 'truncate', 'missing'])
def test_every_read_verifies_raw_even_empty_cutoff(tmp_path, monkeypatch, damage):
    with EvidenceStore(tmp_path / 'store') as store:
        sid = import_rows(store, records())
        full = store.query(sid)
        path = store._raw_path(full['manifest']['raw_sha256'])
        original = path.read_bytes()
        verify = store._verify_raw
        verified = []

        def track(*args):
            verified.append(args)
            return verify(*args)

        monkeypatch.setattr(store, '_verify_raw', track)
        first = store._research_query(sid)
        assert store._research_query(sid) == first
        assert len(verified) == 2
        if damage == 'same_length':
            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
        elif damage == 'truncate':
            path.write_bytes(original[:-1])
        else:
            path.unlink()
        for cutoff in (None, '2020-01-01'):
            with pytest.raises(StoreError, match='raw_object_(corrupt|missing)'):
                store._research_query(sid, cutoff=cutoff)
        assert len(verified) == 4
        path.write_bytes(original)
        assert store._research_query(sid) == first


@pytest.mark.parametrize('scope,column,payload', [
    ('observations', 'checks_json', 'bad json'),
    ('observations', 'checks_json', '[{"name":"source_code"}]'),
    ('observations', 'checks_json', '[{"outcome":"fail"}]'),
    ('observations', 'checks_json', '[{"name":"source_code","outcome":"bogus"}]'),
    ('observations', 'checks_json', '[{"name":1,"outcome":"pass"}]'),
    ('observations', 'checks_json', '{}'),
    ('observations', 'checks_json', '[null]'),
    ('observations', 'tokens_json', '[]'),
    ('batches', 'checks_json', '[{"name":"known_negative_sample"}]'),
    ('batches', 'checks_json', '{}'),
])
def test_malformed_persisted_checks_fail_closed(tmp_path, scope, column, payload):
    root = tmp_path / 'store'
    with EvidenceStore(root) as store:
        sid = import_rows(store, records())
        # Deliberately corrupt synthetic storage, not a decoder-valid source.
        store.db.execute(f'UPDATE {scope} SET {column}=?', [payload])
        with pytest.raises(ValueError):
            store._research_query(sid)

    async def scenario():
        async with client_for(root) as client:
            response = await client.get('/api/research/single/' + sid)
            assert response.status_code == 500
            assert response.json() == {'error': 'internal_error'}
    asyncio.run(scenario())


def test_minute_rejection_does_not_mask_raw_integrity(tmp_path):
    root = tmp_path / 'store'
    with EvidenceStore(root) as store:
        sid = store.import_bytes(text_bytes([record()]), 'tdx-public-text-v1')['snapshot_id']
        full = store.query(sid)
        assert store._research_query(sid) == projected_reference(full)
        path = store._raw_path(full['manifest']['raw_sha256'])
        original = path.read_bytes()

    async def scenario():
        async with client_for(root) as client:
            response = await client.get('/api/research/single/' + sid)
            assert response.status_code == 400 and response.json() == {'error': 'unsupported_period'}
            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            response = await client.get('/api/research/single/' + sid)
            assert response.status_code == 409 and response.json() == {'error': 'raw_object_corrupt'}
    asyncio.run(scenario())


def test_all_budget_counts_precede_compact_materialization():
    events = []

    class Store:
        def query_row_count(self, sid, cutoff=None):
            events.append(('count', sid))
            return 20_000

        def _research_query(self, sid, cutoff=None):
            events.append(('read', sid))
            return {'metadata': {'period': '1d'}}

    ids = ['a', 'b', 'c']
    assert len(_load(Store(), ids, '2025-01-01', ValueError)) == 3
    assert events == [('count', sid) for sid in ids] + [('read', sid) for sid in ids]


@pytest.mark.parametrize('counts', [[20_001], [20_000] * 10 + [1]])
def test_exact_over_budget_never_materializes(counts):
    calls = []

    class Store:
        def query_row_count(self, sid, cutoff=None):
            calls.append(sid)
            return counts[sid]

        def _research_query(self, *args, **kwargs):
            raise AssertionError('over-budget source materialized')

        query = _research_query

    with pytest.raises(ValueError, match='research_row_limit'):
        _load(Store(), list(range(len(counts))), None, ValueError)
    assert calls == list(range(len(counts)))


def test_public_query_and_exports_are_unchanged_after_private_read(mixed_source):
    store, sid = mixed_source
    selection = dict(cutoff='2025-01-20', ordinal_start=2, ordinal_end=30)
    full = store.query(sid, **selection)
    before_json = store.export_json(sid, **selection)
    before_parquet = store.export_parquet(sid, **selection)
    json_bytes = Path(before_json['path']).read_bytes()
    parquet_bytes = Path(before_parquet['path']).read_bytes()
    table = pq.read_table(before_parquet['path'])
    store._research_query(sid, cutoff=selection['cutoff'])
    assert store.query(sid, **selection) == full
    assert store.export_json(sid, **selection) == before_json
    assert store.export_parquet(sid, **selection) == before_parquet
    assert Path(before_json['path']).read_bytes() == json_bytes == _json(full).encode('utf-8')
    assert Path(before_parquet['path']).read_bytes() == parquet_bytes
    after = pq.read_table(before_parquet['path'])
    assert after.equals(table, check_metadata=True)
    assert json.loads(after.schema.metadata[b'anatrading_query'])['query_id'] == full['query_id']


@pytest.mark.parametrize('sid,cutoff,error', [
    ('invalid', None, 'invalid_snapshot_id'),
    ('0' * 64, None, 'snapshot_not_found'),
    (None, None, 'invalid_snapshot_id'),
])
def test_private_read_input_validation(tmp_path, sid, cutoff, error):
    with EvidenceStore(tmp_path / 'store') as store:
        with pytest.raises(StoreError, match=error):
            store._research_query(sid, cutoff=cutoff)


@pytest.mark.parametrize('cutoff', [True, 3, '2025-02-30', '20250101', '2025-01-01T00:00'])
def test_private_read_invalid_cutoff(tmp_path, cutoff):
    with EvidenceStore(tmp_path / 'store') as store:
        sid = import_rows(store, records())
        with pytest.raises(StoreError, match='invalid_label_cutoff'):
            store._research_query(sid, cutoff=cutoff)
