"""One budgeted verified source read, readonly route, and safe path replies."""
import asyncio
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal

import pytest

from anatrading.store import EvidenceStore
from test_research_api import client_for
from test_formats import bao_payload


def seed(root, count=80):
    """Keep the payload's source-date claim consistent with the synthetic rows."""
    rows = []
    for i in range(count):
        day = (date(2025, 1, 1) + timedelta(days=i)).isoformat()
        close = Decimal(10) + Decimal(i) / 10 + Decimal(i % 7) / 100
        rows.append([day, 'sh.600001', str(close), str(close), str(close), str(close), '100', '1000', '3'])
    parts = bao_payload(rows, code='sh.600001').split(b'\x01')
    parts[-4], parts[-3] = rows[0][0].encode(), rows[-1][0].encode()
    with EvidenceStore(root) as store:
        return [store.import_bytes(b'\x01'.join(parts), 'baostock-decoded-v0.9.4')['snapshot_id']]


def path(sid):
    return '/api/research/path-match/' + sid


def test_path_identity_prefix_and_legacy_single_stays_unchanged(tmp_path):
    root = tmp_path / 'store'
    ids = seed(root, 100)
    cutoff = '2025-04-10'
    with EvidenceStore(root) as store:
        source = store.query(ids[0], cutoff=cutoff)
    async def scenario():
        async with client_for(root) as client:
            old = await client.get('/api/research/single/' + ids[0], params=dict(cutoff=cutoff))
            response = await client.get(path(ids[0]), params=dict(cutoff=cutoff))
            assert response.status_code == 200, response.text
            reply = response.json()
            assert reply['method_id'] == 'historical-source-path-retrieval-v1'
            assert reply['mode'] == 'retrospective'
            assert reply['inputs'] == [dict(snapshot_id=ids[0], query_id=source['query_id'])]
            assert reply['parameters']['cutoff'] == cutoff
            assert reply['parameters']['model']['steps'] == 20
            assert reply['result']['query']['start_date'] == '2025-03-21'
            assert len(reply['result']['groups']) == 100
            assert response.headers['cache-control'] == 'no-store'
            assert (await client.get(path(ids[0]), params=dict(cutoff=cutoff))).content == response.content
            earlier = await client.get(path(ids[0]), params=dict(cutoff='2025-04-09'))
            assert earlier.json()['analysis_id'] != reply['analysis_id']
            assert (await client.get('/api/research/single/' + ids[0], params=dict(cutoff=cutoff))).content == old.content
    asyncio.run(scenario())
    with EvidenceStore(root) as store:
        assert store.query(ids[0], cutoff=cutoff) == source


def test_invalid_parameters_fail_before_any_source_read(monkeypatch, tmp_path):
    ids = seed(tmp_path / 'store', 42)
    def forbidden(*args, **kwargs):
        raise AssertionError('invalid path request touched source')
    monkeypatch.setattr(EvidenceStore, 'query_row_count', forbidden)
    monkeypatch.setattr(EvidenceStore, '_research_query', forbidden)
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            for suffix in ['', '?cutoff=2025-2-11', '?cutoff=2025-02-30',
                           '?cutoff=2025-02-11&cutoff=2025-02-11',
                           '?cutoff=2025-02-11&lookback=20', '?cutoff=2025-02-11&ordinal_start=1']:
                response = await client.get(path(ids[0]) + suffix)
                assert response.status_code == 400 and set(response.json()) == {'error'}
            response = await client.get(path('not-a-source') + '?cutoff=2025-02-11')
            assert response.json() == dict(error='invalid_snapshot_id')
    asyncio.run(scenario())


def test_budget_before_load_then_only_one_prefix_and_raw_check(monkeypatch, tmp_path):
    ids = seed(tmp_path / 'store', 64)
    calls = Counter()
    originals = {name: getattr(EvidenceStore, name) for name in ('query_row_count', '_research_query', '_verify_raw')}
    for name, original in originals.items():
        def counted(self, *args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(self, *args, **kwargs)
        monkeypatch.setattr(EvidenceStore, name, counted)
    def forbidden(*args, **kwargs):
        raise AssertionError('unnecessary public query or write')
    for name in ('query', 'import_bytes', 'redecode', 'reclassify'):
        if hasattr(EvidenceStore, name):
            monkeypatch.setattr(EvidenceStore, name, forbidden)
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            calls.clear()
            response = await client.get(path(ids[0]), params=dict(cutoff='2025-03-05'))
            assert response.status_code == 200, response.text
            assert calls == dict(query_row_count=1, _research_query=1, _verify_raw=1)
            monkeypatch.setattr(EvidenceStore, 'query_row_count', lambda *args, **kwargs: 20_001)
            monkeypatch.setattr(EvidenceStore, '_research_query', forbidden)
            response = await client.get(path(ids[0]), params=dict(cutoff='2025-03-05'))
            assert response.json() == dict(error='research_row_limit')
    asyncio.run(scenario())


def test_safe_calculation_failures_and_bounded_output_identity(monkeypatch, tmp_path):
    import anatrading.historical_path_retrieval as module
    ids = seed(tmp_path / 'store', 64)
    original = module.historical_path_report
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            for failure, status, code in [(ValueError('path_query_invalid'), 400, 'path_query_invalid'),
                                          (ValueError('private path /user/secret'), 400, 'invalid_research_input'),
                                          (RuntimeError('private path'), 500, 'internal_error')]:
                def fail(*args, **kwargs):
                    raise failure
                monkeypatch.setattr(module, 'historical_path_report', fail)
                response = await client.get(path(ids[0]), params=dict(cutoff='2025-03-05'))
                assert response.status_code == status and response.json() == dict(error=code)
            monkeypatch.setattr(module, 'historical_path_report', original)
            monkeypatch.setattr(module, 'MAX_RESULT_BYTES', 100)
            response = await client.get(path(ids[0]), params=dict(cutoff='2025-03-05'))
            assert response.status_code == 400
            assert response.json() == dict(error='path_result_limit', snapshot_id=ids[0], cutoff='2025-03-05',
                                           method_id=module.METHOD_ID)
    asyncio.run(scenario())


def test_actual_raw_change_is_rejected_after_success(tmp_path):
    root = tmp_path / 'store'
    ids = seed(root, 42)
    with EvidenceStore(root) as store:
        q = store._research_query(ids[0], cutoff='2025-02-11')
        raw = store._raw_path(q['manifest']['raw_sha256'])
    async def scenario():
        async with client_for(root) as client:
            assert (await client.get(path(ids[0]), params=dict(cutoff='2025-02-11'))).status_code == 200
            raw.write_bytes(raw.read_bytes() + b' ')
            response = await client.get(path(ids[0]), params=dict(cutoff='2025-02-11'))
            assert response.status_code == 409 and response.json() == dict(error='raw_object_corrupt')
    asyncio.run(scenario())
