"""Only one admitted full-prefix read feeds universe and filter results."""
import asyncio
from collections import Counter
from datetime import date, timedelta
import json
import struct

import pytest

from anatrading.store import EvidenceStore, StoreError
from test_research_api import client_for, seed
from test_stock_filters import atom, rule
from test_formats import bao_payload


def parameters(ids, spec=None):
    return dict(snapshot_ids=','.join(ids), cutoff='2025-01-25', lookback='20',
                rule=json.dumps(spec or rule([atom()]), separators=(',',':')))


def test_api_identity_byte_stability_source_metadata_and_base_equality(tmp_path):
    ids=seed(tmp_path/'store',25)
    async def request():
        async with client_for(tmp_path/'store') as client:
            p=parameters(ids)
            response=await client.get('/api/research/universe-filter',params=p)
            assert response.status_code==200,response.text
            report=response.json()
            assert response.headers['cache-control']=='no-store'
            old=await client.get('/api/research/universe',params={k:v for k,v in p.items() if k!='rule'})
            assert report['result']['universe']==old.json()['result']
            assert report['base_analysis_id']==old.json()['analysis_id']
            assert report['inputs']==old.json()['inputs']
            for source in report['result']['sources']:
                contract=next(c for c in report['result']['source_contracts'] if c['id']==source['contract_ref'])
                assert contract['semantics']['price_unit']['applicability']==dict(present=True,value='unverified')
            p['snapshot_ids']=','.join(reversed(ids))
            assert (await client.get('/api/research/universe-filter',params=p)).content==response.content
            changed=await client.get('/api/research/universe-filter',params=parameters(ids,rule([atom(threshold='0.1')])))
            assert changed.json()['analysis_id']!=report['analysis_id']
            return response.content
    assert asyncio.run(request())==asyncio.run(request())


def test_invalid_rules_rejected_before_any_store_call(monkeypatch,tmp_path):
    ids=seed(tmp_path/'store',25)
    def forbidden(*args,**kwargs):
        raise AssertionError('invalid rule touched sources')
    monkeypatch.setattr(EvidenceStore,'query_row_count',forbidden)
    monkeypatch.setattr(EvidenceStore,'_research_query',forbidden)
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            for spec,code in [({},'invalid_filter_rule'),(rule([atom(op='gte')]*4),'filter_rule_limit'),
                              (rule([atom('known_at')]),'unsupported_filter_field'),
                              (rule([atom(threshold='NaN')]),'invalid_filter_threshold')]:
                response=await client.get('/api/research/universe-filter',params=parameters(ids,spec) if spec else
                                          {**parameters(ids),'rule':'{}'})
                assert response.status_code==400 and response.json()==dict(error=code)
            for text,code in [(' '*2049,'filter_rule_limit'),('{"any_of":[],"any_of":[]}','invalid_filter_rule')]:
                response=await client.get('/api/research/universe-filter',params={**parameters(ids),'rule':text})
                assert response.json()==dict(error=code)
    asyncio.run(scenario())


@pytest.mark.parametrize('size,members',[(20_001,3),(20_000,11)])
def test_row_budget_rejected_before_loading_or_normalizing(size,members,monkeypatch,tmp_path):
    ids=seed(tmp_path/'store',25)
    if members!=len(ids):ids=[f'{i:064x}' for i in range(members)]
    import anatrading.universe_research as module
    monkeypatch.setattr(EvidenceStore,'query_row_count',lambda *args,**kwargs:size)
    def forbidden(*args,**kwargs):
        raise AssertionError('over budget materialized/normalized sources')
    monkeypatch.setattr(EvidenceStore,'_research_query',forbidden)
    monkeypatch.setattr(module,'daily_bars',forbidden)
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            response=await client.get('/api/research/universe-filter',params=parameters(ids))
            assert response.status_code==400 and response.json()==dict(error='research_row_limit')
    asyncio.run(scenario())


def test_six_atoms_do_not_multiply_reads_verifications_or_normalizations(monkeypatch,tmp_path):
    ids=seed(tmp_path/'store',25)
    import anatrading.universe_research as module
    calls=Counter()
    for name in ('query_row_count','_research_query','_verify_raw'):
        original=getattr(EvidenceStore,name)
        def tracked(self,*args,_name=name,_original=original,**kwargs):
            calls[_name]+=1
            return _original(self,*args,**kwargs)
        monkeypatch.setattr(EvidenceStore,name,tracked)
    original_bars=module.daily_bars
    def bars(q):
        calls['daily_bars']+=1
        return original_bars(q)
    monkeypatch.setattr(module,'daily_bars',bars)
    def forbidden(*args,**kwargs):
        raise AssertionError('filter built a redundant full query')
    monkeypatch.setattr(EvidenceStore,'query',forbidden)
    spec=rule([atom(),atom('volatility','0.1'),atom('max_drawdown','-0.1')],
              [atom(threshold='0.2'),atom('volatility','0.2'),atom('max_drawdown','-0.2')])
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            calls.clear()  # Store startup integrity checks are outside this request.
            response=await client.get('/api/research/universe-filter',params=parameters(ids,spec))
            assert response.status_code==200,response.text
            assert calls==dict(query_row_count=3,_research_query=3,_verify_raw=3,daily_bars=3)
    asyncio.run(scenario())


def test_read_failure_and_unclassified_program_error_never_return_partial_success(monkeypatch,tmp_path):
    ids=seed(tmp_path/'store',25)
    original=EvidenceStore._research_query
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            for exc,expected in [(StoreError('raw_object_corrupt'),409),(RuntimeError('broken calculation'),500)]:
                def broken(self,snapshot_id,cutoff=None):
                    if snapshot_id==sorted(ids)[1]:raise exc
                    return original(self,snapshot_id,cutoff)
                monkeypatch.setattr(EvidenceStore,'_research_query',broken)
                response=await client.get('/api/research/universe-filter',params=parameters(ids))
                assert response.status_code==expected,response.text
                assert set(response.json())=={'error'}
    asyncio.run(scenario())


def test_route_rejects_unknown_duplicate_and_truncating_parameters(tmp_path):
    ids=seed(tmp_path/'store',25)
    async def scenario():
        async with client_for(tmp_path/'store') as client:
            p=parameters(ids)
            for extra in [('rule',p['rule']),('ordinal_start','2'),('known_at','2025-01-25')]:
                response=await client.get('/api/research/universe-filter',params=[*p.items(),extra])
                assert response.status_code==400 and response.json()==dict(error='invalid_request')
            for changes,code in [({'snapshot_ids':ids[0]+','+ids[0]},'duplicate_snapshot'),
                                 ({'lookback':'true'},'invalid_lookback'),
                                 ({'cutoff':'2025-1-25'},'invalid_research_date')]:
                response=await client.get('/api/research/universe-filter',params={**p,**changes})
                assert response.status_code==400 and response.json()==dict(error=code)
    asyncio.run(scenario())


@pytest.mark.parametrize('extreme',[False,True])
def test_fifty_mixed_actual_store_contracts_and_heavy_failure_evidence_are_bounded(tmp_path,extreme):
    """Supported decoders generate the metadata; no invented contract schema."""
    from anatrading.stock_filters import filter_report
    from anatrading.research_api import _load, _calculate
    from anatrading.store import _json, _identity
    from anatrading.public_market import build_request
    from test_public_market_formats import tx_capture, tx_row
    from test_public_market_legacy import legacy_capture
    ids=[];last=(date(2025,1,1)+timedelta(days=399)).isoformat()
    with EvidenceStore(tmp_path/'store') as store:
        for i in range(50):
            code=f'sh.{600000+i}';adjustment=str(i%3+1);rows=[];raw=[];tx=[]
            for j in range(400):
                day=(date(2025,1,1)+timedelta(days=j));label=day.isoformat()
                number=int(day.strftime('%Y%m%d'));kind=0 if extreme else j%10
                if kind==6:
                    previous=day-timedelta(days=1);label=previous.isoformat();number=int(previous.strftime('%Y%m%d'))
                if kind==7:label='unlocated';number=20250230
                values=['10','11','9','10']
                if extreme:
                    values=['99999999999999999998.123456789012345678',
                            '99999999999999999999.999999999999999999',
                            '99999999999999999997.987654321098765432',
                            f'99999999999999999998.{j:018}']
                if kind==1:values[1]=''
                if kind==2:values[3]='0'
                if kind==3:values[1:3]=['9','11']
                row_code='sh.999999' if kind==4 else code
                flag=str(int(adjustment)%3+1) if kind==8 else adjustment
                rows.append([label,row_code,*values,'100','1000',flag])
                tx.append(tx_row(day=day.isoformat() if label=='unlocated' else label,
                                 **{'1':values[0],'2':values[3],'3':values[1],'4':values[2]}))
                raw.append(struct.pack('<IIIIIfII',number,1000,900 if kind==3 else 1100,
                                       900,0 if kind==2 else 1000,1000.0,100,0))
            if i%5==3:
                imported=store.import_bytes(b''.join(raw),'tdx-public-day-v1',
                                            interpretation=dict(instrument=f'{600000+i}.SH',venue='SH'))
            elif i%5==4:
                request=build_request('tencent',f'{600000+i}.SH','1d',start='2025-10-11',end=last,count=640)
                captured=tx_capture(tx,request=request,symbol=f'sh{600000+i}')
                imported=store.import_bytes(legacy_capture(captured),'tencent-daily-capture-v1')
            else:
                imported=store.import_bytes(bao_payload(rows,code=code,adjustment=adjustment),'baostock-decoded-v0.9.4')
            assert imported['status']=='committed'
            ids.append(imported['snapshot_id'])
        queries=_load(store,sorted(ids),last,ValueError)
        spec=rule([atom(),atom('volatility','0.1'),atom('max_drawdown','-0.1')],
                  [atom(threshold='0.2'),atom('volatility','0.2'),atom('max_drawdown','-0.2')])
        report=filter_report(queries,last,252,spec)
        old=_calculate('universe',queries,dict(cutoff=last,lookback=252),ValueError)
        new_size,old_size=len(_json(report).encode()),len(_json(old).encode())
        assert new_size<=512*1024,(new_size,old_size)
        assert new_size-old_size<=256*1024,(new_size,old_size)
        contracts={c['id']:c for c in report['result']['source_contracts']}
        assert len(contracts)>=5
        assert report['source_metadata_id']==_identity(dict(sources=report['result']['sources'],source_contracts=report['result']['source_contracts']))
        for source in report['result']['sources']:
            contract=contracts[source['contract_ref']]
            payload={k:v for k,v in contract.items() if k!='id'}
            assert _identity(payload)==contract['id']
            expanded={**{k:v for k,v in source.items() if k not in {'id','contract_ref'}},**payload}
            assert _identity(expanded)==source['id']
        legacy=[source for source in report['result']['sources'] if source['metadata']['capture_mode']['value']=='legacy_reconstruction']
        assert len(legacy)==10 and all(source['metadata']['transport_evidence']['value']=='not_established' for source in legacy)
        for member in report['result']['members']:
            assert len(member['atoms'])==6
            if not extreme:
                assert any(r['omitted_count']>0 and len(r['examples'])==8 for r in member['reasons'])
            reason_ids={r['id'] for r in member['reasons']}
            assert all(set(a['reason_refs'])<=reason_ids for a in member['atoms'])
            conditions={c['id']:c for c in report['result']['conditions']}
            assert all(conditions[a['id']]['field']==a['fact_ref'] for a in member['atoms'])
