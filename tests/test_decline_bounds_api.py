"""069 preflight and bounded transport; only disposable synthetic sources."""
import asyncio
import json
import pytest
from anatrading.store import EvidenceStore
from test_research_api import seed, client_for

@pytest.mark.parametrize('suffix', ['', '?start=2025-01-01', '?end=2025-01-01', '?start=2025-01-02&end=2025-01-01', '?start=2025-02-30&end=2025-03-01', '?start=2025-01-01&end=2025-01-01&start=2025-01-01', '?start=2025-01-01&end=2025-01-01&cutoff=2025-01-01'])
def test_preflight_before_store(tmp_path, monkeypatch, suffix):
    root=tmp_path/'store'; sid=seed(root,2)[0]
    def forbidden(*a,**k): pytest.fail('invalid request reached Store')
    monkeypatch.setattr(EvidenceStore,'query_row_count',forbidden)
    monkeypatch.setattr(EvidenceStore,'_research_query',forbidden)
    async def run():
        async with client_for(root) as client:
            assert (await client.get('/api/research/ohlc-decline-bounds/'+sid+suffix)).status_code==400
    asyncio.run(run())

def test_final_byte_and_structure_limits():
    from anatrading.research_api import _decline_bytes
    error=ValueError
    # Quotes occupy two bytes: exact final bytes, then one byte over.
    assert len(_decline_bytes('x'*262142,error))==262144
    with pytest.raises(ValueError,match='ohlc_result_limit'): _decline_bytes('x'*262143,error)
    assert len(_decline_bytes('中'*87380+'xx',error))==262144
    value=0
    for _ in range(64): value=[value]
    _decline_bytes(value,error)
    with pytest.raises(ValueError,match='ohlc_result_limit'): _decline_bytes([value],error)
    _decline_bytes([0]*65535,error)
    with pytest.raises(ValueError,match='ohlc_result_limit'): _decline_bytes([0]*65536,error)

def test_exact_core_full_prefix_and_content_identity(tmp_path):
    from anatrading.ohlc_decline_bounds import decline_bounds_report
    from anatrading.store import _identity
    root=tmp_path/'store';sid=seed(root,25)[0]
    with EvidenceStore(root,read_only=True) as store:
        expected=decline_bounds_report(store._research_query(sid,cutoff='2025-01-25'),'2025-01-20','2025-01-25')
    async def run():
        async with client_for(root) as client:
            path='/api/research/ohlc-decline-bounds/'+sid
            response=await client.get(path,params={'start':'2025-01-20','end':'2025-01-25'})
            assert response.status_code==200,response.text
            assert response.headers['cache-control']=='no-store'
            r=response.json(); analysis=r.pop('analysis_id');assert _identity(r)==analysis
            assert r.pop('view_method_id')=='selected-source-ohlc-decline-bounds-v1'
            assert r==expected
            assert r['coverage']['date_groups']==25 and len(r['members'])==6
            assert (await client.get(path,params={'start':'2025-01-20','end':'2025-01-25'})).json()['analysis_id']==analysis
            single=(await client.get(path,params={'start':'2025-01-25','end':'2025-01-25'})).json()
            assert single['status']=='computed' and single['window']['bar_count']==1
            assert single['analysis_id']!=analysis
            absent=(await client.get(path,params={'start':'2024-01-01','end':'2024-01-01'})).json()
            assert absent['missing_endpoints']==['2024-01-01'] and absent['lower'] is None
    asyncio.run(run())

@pytest.mark.parametrize('end',['2024-01-01','2025-01-02'])
@pytest.mark.parametrize('damage',['missing','tampered'])
def test_raw_verified_even_empty(tmp_path,end,damage):
    import hashlib
    root=tmp_path/'store';sid=seed(root,2)[0]
    with EvidenceStore(root) as store: sha=store._research_query(sid)['manifest']['raw_sha256']
    raw=root/'raw'/sha[:2]/sha; original=raw.read_bytes()
    if damage=='missing': raw.unlink()
    else: raw.write_bytes(b'tampered synthetic')
    async def run():
        async with client_for(root) as client:
            r=await client.get('/api/research/ohlc-decline-bounds/'+sid,params={'start':end,'end':end})
            assert r.status_code!=200 and r.json()['error'].startswith('raw_object_')
    asyncio.run(run());raw.write_bytes(original);assert hashlib.sha256(raw.read_bytes()).hexdigest()==sha

def test_budget_before_query(tmp_path,monkeypatch):
    root=tmp_path/'store';sid=seed(root,2)[0]
    monkeypatch.setattr(EvidenceStore,'query_row_count',lambda *a,**k:20001)
    monkeypatch.setattr(EvidenceStore,'_research_query',lambda *a,**k:pytest.fail('overbudget read'))
    async def run():
        async with client_for(root) as client:
            r=await client.get('/api/research/ohlc-decline-bounds/'+sid,params={'start':'2025-01-01','end':'2025-01-02'})
            assert r.json()=={'error':'research_row_limit'}
    asyncio.run(run())

def test_complete_content_changes_identity():
    from copy import deepcopy
    from anatrading.research_api import _calculate_decline
    from test_ohlc_decline_bounds import query
    class Store:
        def __init__(self):self.q=query(2)
        def query_row_count(self,*a,**k):return 2
        def _research_query(self,*a,**k):return deepcopy(self.q)
    s=Store()
    get=lambda:json.loads(_calculate_decline(s,s.q['snapshot_id'],'2026-01-01','2026-01-02',ValueError))
    a=get();assert get()==a
    s.q['manifest']['qualification']={'changed':True};b=get();assert a['analysis_id']!=b['analysis_id']
    s.q['rows'][1]['values']['low']='80';c=get();assert b['analysis_id']!=c['analysis_id']
    s.q['rows'][1]['ordinal']=s.q['rows'][0]['ordinal'];d=get()
    assert d['coverage']['invalid_groups']==0 and len(d['invalid_members'])==1
    assert c['analysis_id']!=d['analysis_id']
