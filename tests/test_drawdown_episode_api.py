"""Fresh synthetic Store lifecycle only; ASGI transport never binds a socket."""
import asyncio
import json
from pathlib import Path
import os
import pytest
from anatrading.store import EvidenceStore
from anatrading.drawdown_episode_research import drawdown_episode_report
from test_peer_relative_research import capture, FMT
from test_drawdown_episode_research import points
from test_research_api import client_for


def seed(root):
    values=[100,80,100,99,99,99,99,100,98]
    days=[p['date'] for p in points(values)];ids=[]
    with EvidenceStore(root) as store:
        for i in range(3):ids.append(store.import_bytes(capture(f'{600000+i}.SH',values,days),FMT)['snapshot_id'])
        full=[store.query(sid) for sid in ids]
        projected=[store._research_query(sid) for sid in ids]
        expected=drawdown_episode_report(full,days[-1],8)
        assert expected==drawdown_episode_report(projected,days[-1],8)
    return ids,days,expected


def test_new_store_api_roundtrip_and_fixture_export(tmp_path):
    root=tmp_path/'fresh-drawdown-api';ids,days,expected=seed(root)
    async def scenario():
        async with client_for(root) as client:
            params=dict(snapshot_ids=','.join(ids),cutoff=days[-1],lookback='8')
            response=await client.get('/api/research/drawdown-episodes',params=params)
            assert response.status_code==200,response.text
            assert response.json()==expected and response.headers['cache-control']=='no-store'
            fixtures={'complete':dict(expected=dict(ids=sorted(ids),cutoff=days[-1],lookback=8),reply=response.json())}
            for name,cutoff,lookback in [('open',days[-3],6),('missing','2026-02-01',8),('flat',days[0],2)]:
                r=await client.get('/api/research/drawdown-episodes',params={**params,'cutoff':cutoff,'lookback':str(lookback)})
                assert r.status_code==200,r.text
                fixtures[name]=dict(expected=dict(ids=sorted(ids),cutoff=cutoff,lookback=lookback),reply=r.json())
            # Each added frontend case comes through a new synthetic Store and the actual API.
            for name,values in [('tiny',['1','0.999999999999999999','1','0.999999999999999998','1']),
                                ('no_drawdown',[100,100,101]),('tie',[100,80,100,80,100]),('zero_price',[100,0,100]),('duplicate_invalid',[100,'NaN',80,100])]:
                case_root=tmp_path/('fresh-'+name);case_days=[p['date'] for p in points(values)];case_ids=[]
                if name=='duplicate_invalid':case_days=['2026-01-01','2026-01-02','2026-01-02','2026-01-03']
                case_lookback=len(set(case_days))-1
                with EvidenceStore(case_root) as store:
                    for i in range(2):case_ids.append(store.import_bytes(capture(f'{600010+i}.SH',values,case_days),FMT)['snapshot_id'])
                async with client_for(case_root) as case_client:
                    r=await case_client.get('/api/research/drawdown-episodes',params=dict(snapshot_ids=','.join(case_ids),cutoff=case_days[-1],lookback=str(case_lookback)))
                    assert r.status_code==200,r.text
                    fixtures[name]=dict(expected=dict(ids=sorted(case_ids),cutoff=case_days[-1],lookback=case_lookback),reply=r.json())
            if os.environ.get('DRAWDOWN_FIXTURE_EXPORT'):
                Path(os.environ['DRAWDOWN_FIXTURE_EXPORT']).write_text(json.dumps(fixtures,ensure_ascii=False,separators=(',',':')))
            for member in expected['members']:
                for ep in member['endpoints']:
                    raw=await client.get('/api/query/'+member['snapshot_id'],params={'cutoff':ep['date']})
                    assert raw.status_code==200
                    row=next(r for r in raw.json()['query']['rows'] if str(r['ordinal'])==ep['ordinal'])
                    assert row['values']['close']==ep['close_exact']
            for patch in ({'cutoff':'2026-02-30'},{'snapshot_ids':ids[0]},{'lookback':'253'},
                          {'lookback':'2.0'},{'events':'[]'},{'snapshot_ids':','.join(ids+[ids[0]])}):
                assert (await client.get('/api/research/drawdown-episodes',params={**params,**patch})).status_code==400
            assert (await client.get('/api/research/drawdown-episodes',params=[*params.items(),('cutoff',days[-1])])).status_code==400
    asyncio.run(scenario())


def test_budget_all_counts_before_load_and_new_raw_recovery(tmp_path,monkeypatch):
    root=tmp_path/'fresh-drawdown-recovery';ids,days,_=seed(root)
    with EvidenceStore(root) as store:
        q=store.query(ids[0]);raw=store._raw_path(q['manifest']['raw_sha256']);original=raw.read_bytes()
    async def scenario():
        async with client_for(root) as client:
            params=dict(snapshot_ids=','.join(ids),cutoff=days[-1],lookback='8')
            with monkeypatch.context() as patch:
                calls=[]
                def count(self,sid,cutoff=None):calls.append((sid,cutoff));return 20001
                def forbidden(*a,**k):raise AssertionError('source loaded before all budgets')
                patch.setattr(EvidenceStore,'query_row_count',count);patch.setattr(EvidenceStore,'_research_query',forbidden)
                response=await client.get('/api/research/drawdown-episodes',params=params)
                assert response.json()=={'error':'research_row_limit'} and len(calls)==len(ids)
                assert all(cutoff is None for _,cutoff in calls)
            for damage in ('corrupt','missing'):
                if damage=='corrupt':raw.write_bytes(b'new synthetic damage')
                else:raw.unlink()
                r=await client.get('/api/research/drawdown-episodes',params=params)
                assert r.status_code==409 and r.json()=={'error':'raw_object_'+damage}
                raw.write_bytes(original)
                assert (await client.get('/api/research/drawdown-episodes',params=params)).status_code==200
    asyncio.run(scenario())


def test_http_budget_exact_limits_count_every_source_before_rejection():
    from anatrading.research_api import _research_budget
    class BudgetError(Exception):pass
    class Counts:
        def __init__(self,counts):self.counts=counts;self.calls=[]
        def query_row_count(self,sid,cutoff=None):self.calls.append((sid,cutoff));return self.counts[sid]
    for counts,accepted in [([20000,3],True),([20000]*10,True),([20001,3],False),([20000]*10+[1],False)]:
        store=Counts(counts)
        if accepted:_research_budget(store,list(range(len(counts))),None,BudgetError)
        else:
            with pytest.raises(BudgetError,match='research_row_limit'):_research_budget(store,list(range(len(counts))),None,BudgetError)
        assert store.calls==[(i,None) for i in range(len(counts))]


def test_http_preserves_unsupported_period_row_instead_of_loader_refusal(tmp_path,monkeypatch):
    root=tmp_path/'fresh-period-refusal';ids,days,_=seed(root)
    original=EvidenceStore._research_query
    def read(self,sid,*,cutoff=None):
        assert cutoff is None
        query=original(self,sid,cutoff=cutoff)
        if sid==ids[0]:query['metadata']['period']='1m'
        return query
    monkeypatch.setattr(EvidenceStore,'_research_query',read)
    async def scenario():
        async with client_for(root) as client:
            response=await client.get('/api/research/drawdown-episodes',params=dict(snapshot_ids=','.join(ids),cutoff=days[-1],lookback='8'))
            assert response.status_code==200,response.text
            report=response.json();assert not report['comparison_available'] and len(report['members'])==3
            member=next(m for m in report['members'] if m['snapshot_id']==ids[0])
            assert member['reasons']==['unsupported_period'] and member['anomalies'] is None
    asyncio.run(scenario())
