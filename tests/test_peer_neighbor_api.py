"""Only freshly generated captures and tmp_path Stores are used here."""
import asyncio
import json

from anatrading.store import EvidenceStore
from anatrading.peer_neighbor_research import peer_neighbor_report
from test_peer_neighbor_research import fixture
from test_peer_relative_research import capture, FMT
from test_research_api import client_for


def seed(root):
    q, dates = fixture(); ids = []
    with EvidenceStore(root) as store:
        for i, source in enumerate(q):
            ids.append(store.import_bytes(capture(f'{600000+i}.SH',
                [r['values']['close'] for r in source['rows']], dates), FMT)['snapshot_id'])
        full = [store.query(sid) for sid in ids]
        projected = [store._research_query(sid) for sid in ids]
        expected = peer_neighbor_report(full, ids[0], dates[-1])
        assert peer_neighbor_report(projected, ids[0], dates[-1]) == expected
    return ids, dates, expected


def test_synthetic_store_api_dto_and_every_boundary_prefix(tmp_path):
    root = tmp_path/'fresh-source-panel'; ids, dates, expected = seed(root)
    async def scenario():
        async with client_for(root) as client:
            params = dict(snapshot_ids=','.join(ids), target_snapshot_id=ids[0], cutoff=dates[-1])
            response = await client.get('/api/research/peer-neighbors', params=params)
            assert response.status_code == 200, response.text
            assert response.json() == expected and response.headers['cache-control'] == 'no-store'
            for member in expected['members']:
                for index in (0,30,60,120):
                    ep = member['endpoints'][index]
                    raw = await client.get('/api/query/'+member['snapshot_id'], params={'cutoff':ep['date']})
                    assert raw.status_code == 200, raw.text
                    query = raw.json()['query']; point = next(r for r in query['rows'] if r['ordinal'] == ep['ordinal'])
                    assert point['values']['close'] == ep['close_exact'] and point['tokens']['close'] == ep['close_token']
                    assert query['query_id'] != member['query_id']
            for patch in ({'target_snapshot_id':'f'*64}, {'cutoff':'2026-02-30'}, {'snapshot_ids':ids[0]},
                          {'snapshot_ids':','.join(ids+[ids[0]])}, {'events':'[]'}, {'lookback':'60'}):
                bad = await client.get('/api/research/peer-neighbors', params={**params,**patch})
                assert bad.status_code == 400
            bad = await client.get('/api/research/peer-neighbors', params=[*params.items(),('cutoff',dates[-1])])
            assert bad.status_code == 400
    asyncio.run(scenario())


def test_budget_before_reads_corrupt_missing_recovery(tmp_path, monkeypatch):
    root = tmp_path/'fresh-recovery'; ids, dates, _ = seed(root)
    with EvidenceStore(root) as store:
        query = store.query(ids[0]); raw = store._raw_path(query['manifest']['raw_sha256']); original = raw.read_bytes()
    params = dict(snapshot_ids=','.join(ids), target_snapshot_id=ids[0], cutoff=dates[-1])
    async def scenario():
        async with client_for(root) as client:
            with monkeypatch.context() as patch:
                calls = []
                def count(self,sid,cutoff=None): calls.append((sid,cutoff)); return 20001
                def forbidden(*args,**kwargs): raise AssertionError('loaded before full budget')
                patch.setattr(EvidenceStore,'query_row_count',count); patch.setattr(EvidenceStore,'_research_query',forbidden)
                r = await client.get('/api/research/peer-neighbors',params=params)
                assert r.json() == {'error':'research_row_limit'} and len(calls) == 5
                assert all(cutoff is None for _,cutoff in calls)
            for damage in ('corrupt','missing'):
                if damage == 'corrupt': raw.write_bytes(b'broken-synthetic')
                else: raw.unlink()
                r = await client.get('/api/research/peer-neighbors',params=params)
                assert r.status_code == 409 and r.json() == {'error':'raw_object_'+damage}
                raw.write_bytes(original)
                assert (await client.get('/api/research/peer-neighbors',params=params)).status_code == 200
    asyncio.run(scenario())
