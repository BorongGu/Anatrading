"""Only disposable synthetic Store and in-process ASGI qualification."""
import asyncio
import json
import pytest
from anatrading.store import EvidenceStore
from anatrading.close_dispersion import selected_dispersion_report
from test_research_api import seed, client_for


def test_selected_api_identity_and_empty(tmp_path):
    root=tmp_path/'store'; sid=seed(root,25)[0]
    async def scenario():
        async with client_for(root) as client:
            path='/api/research/close-dispersion/'+sid
            response=await client.get(path)
            assert response.status_code==200, response.text
            latest=response.json(); assert len(response.content)<=65536
            assert response.headers['cache-control']=='no-store'
            assert latest['selection']['resolved_date']=='2025-01-25'
            explicit=(await client.get(path,params={'date':'2025-01-25'})).json()
            assert latest['selected']==explicit['selected']
            assert latest['analysis_id']!=explicit['analysis_id']
            assert (await client.get(path)).json()==latest
            empty=(await client.get(path,params={'cutoff':'2024-01-01'})).json()
            assert empty['reason']=='no_date_groups' and empty['identity']['query_id']!=latest['identity']['query_id']
            missing=(await client.get(path,params={'date':'2026-01-01'})).json()
            assert missing['reason']=='date_not_present' and missing['selected'] is None
    asyncio.run(scenario())
    with EvidenceStore(root,read_only=True) as store:
        q=store._research_query(sid)
        assert selected_dispersion_report(q)['selected']['date']=='2025-01-25'


@pytest.mark.parametrize('suffix',['?date=20250230','?date=2025-02-30','?date=2025-01-01T00:00:00',
    '?date=2025-01-02&cutoff=2025-01-01','?date=2025-01-01&date=2025-01-02','?wat=1'])
def test_invalid_before_any_store_read(monkeypatch,tmp_path,suffix):
    root=tmp_path/'store';sid=seed(root,20)[0]
    def forbidden(*a,**k): pytest.fail('invalid input reached Store')
    monkeypatch.setattr(EvidenceStore,'query_row_count',forbidden)
    monkeypatch.setattr(EvidenceStore,'_research_query',forbidden)
    async def scenario():
        async with client_for(root) as client:
            assert (await client.get('/api/research/close-dispersion/'+sid+suffix)).status_code==400
    asyncio.run(scenario())


def test_budget_preflight(monkeypatch,tmp_path):
    root=tmp_path/'store'; sid=seed(root,20)[0]
    monkeypatch.setattr(EvidenceStore,'query_row_count',lambda *a,**k:20001)
    monkeypatch.setattr(EvidenceStore,'_research_query',lambda *a,**k:pytest.fail('loaded over budget'))
    async def scenario():
        async with client_for(root) as client:
            r=await client.get('/api/research/close-dispersion/'+sid)
            assert r.json()=={'error':'research_row_limit'}
    asyncio.run(scenario())


@pytest.mark.parametrize('cutoff',[None,'2024-01-01'])
def test_raw_verified_even_empty(tmp_path,cutoff):
    root=tmp_path/'store';sid=seed(root,20)[0]
    with EvidenceStore(root) as store:
        sha=store._research_query(sid)['manifest']['raw_sha256']
    raw=root/'raw'/sha[:2]/sha
    assert raw.is_file()
    raw.write_bytes(b'tampered synthetic')
    async def scenario():
        async with client_for(root) as client:
            r=await client.get('/api/research/close-dispersion/'+sid,params={} if cutoff is None else {'cutoff':cutoff})
            assert r.json()=={'error':'raw_object_corrupt'}
    asyncio.run(scenario())


def test_huge_qualification_rejects_whole_response(monkeypatch,tmp_path):
    root=tmp_path/'store';sid=seed(root,20)[0]
    original=EvidenceStore._research_query
    def bloated(self,*a,**k):
        q=original(self,*a,**k); q['manifest']['qualification']='中'*22000; return q
    monkeypatch.setattr(EvidenceStore,'_research_query',bloated)
    async def scenario():
        async with client_for(root) as client:
            r=await client.get('/api/research/close-dispersion/'+sid)
            assert r.status_code==400 and r.json()=={'error':'dispersion_result_limit'}
    asyncio.run(scenario())
