"""Research route identity, validation and bounded source reads."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal

import httpx
import pytest

from anatrading.store import EvidenceStore
from anatrading.workbench import create_app
from test_formats import bao_payload

ORIGIN = "http://127.0.0.1:8765"


def seed(root, count=80):
    ids = []
    with EvidenceStore(root) as store:
        for index, code in enumerate(("sh.600001", "sz.000001", "sh.600002")):
            rows = []
            for i in range(count):
                day = (date(2025, 1, 1) + timedelta(days=i)).isoformat()
                close = Decimal(10 + index * 2) + Decimal(i) / 10 + Decimal((i * (index + 1)) % 7) / 100
                rows.append([day, code, str(close), str(close + Decimal('.04')), str(close - Decimal('.04')),
                             str(close), "100", "1000", "3"])
            ids.append(store.import_bytes(bao_payload(rows, code=code), "baostock-decoded-v0.9.4")["snapshot_id"])
    return ids


@asynccontextmanager
async def client_for(root):
    app = create_app(root)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            yield client


def test_research_routes_identity_and_cutoff(tmp_path):
    ids = seed(tmp_path / 'store')
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            params = dict(cutoff='2025-03-20', lookback=20, horizon=5)
            reply = await client.get('/api/research/single/' + ids[0], params=params)
            assert reply.status_code == 200, reply.text
            report = reply.json()
            assert report['mode'] == 'retrospective' and report['method_id'] == 'daily-causal-research-v1'
            assert report['inputs'][0]['snapshot_id'] == ids[0]
            assert len(report['analysis_id']) == 64 and reply.headers['cache-control'] == 'no-store'
            assert (await client.get('/api/research/single/' + ids[0], params=params)).json() == report
            changed = (await client.get('/api/research/single/' + ids[0], params={**params,'lookback':10})).json()
            assert changed['analysis_id'] != report['analysis_id']
            pair = await client.get('/api/research/pair', params=dict(left=ids[0],right=ids[1],cutoff=params['cutoff']))
            assert pair.status_code == 200, pair.text
            assert [i['snapshot_id'] for i in pair.json()['inputs']] == ids[:2]
            group_params = dict(snapshot_ids=','.join(ids),cutoff=params['cutoff'])
            group = await client.get('/api/research/universe',params=group_params)
            assert group.status_code == 200, group.text
            reverse = await client.get('/api/research/universe',params={**group_params,'snapshot_ids':','.join(reversed(ids))})
            assert reverse.json() == group.json()
    asyncio.run(scenario())


@pytest.mark.parametrize('suffix',[
    '?unknown=1','?lookback=2&lookback=3','?lookback=NaN','?lookback=true','?lookback=253',
    '?horizon=2','?cutoff=2025-2-1','?cutoff=2025-02-30','?test_start=2026-01-01&cutoff=2025-01-01',
])
def test_research_validation(tmp_path,suffix):
    ids=seed(tmp_path/'store',25)
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            response=await client.get('/api/research/single/'+ids[0]+suffix)
            assert response.status_code==400
            assert set(response.json())=={'error'}
    asyncio.run(scenario())


def test_duplicate_and_missing_members(tmp_path):
    ids=seed(tmp_path/'store',25)
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            for path,params in [
                ('pair',dict(left=ids[0],right=ids[0],cutoff='2025-01-25')),
                ('pair',dict(left=ids[0],right=ids[1])),
                ('universe',dict(snapshot_ids=ids[0],cutoff='2025-01-25')),
                ('universe',dict(snapshot_ids=','.join([ids[0]]*2),cutoff='2025-01-25')),
                ('universe',dict(snapshot_ids=','.join([ids[0]]*51),cutoff='2025-01-25')),
            ]:
                response=await client.get('/api/research/'+path,params=params)
                assert response.status_code==400
    asyncio.run(scenario())


def test_preflight_rejects_without_materializing(monkeypatch,tmp_path):
    ids=seed(tmp_path/'store',25)
    monkeypatch.setattr(EvidenceStore,'query_row_count',lambda self,snapshot_id,cutoff=None:20_001)
    def forbidden(*args,**kwargs):
        raise AssertionError('over-budget request materialized rows')
    monkeypatch.setattr(EvidenceStore,'query',forbidden)
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            response=await client.get('/api/research/single/'+ids[0])
            assert response.status_code==400 and response.json()=={'error':'research_row_limit'}
    asyncio.run(scenario())
