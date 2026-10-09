"""Endpoint observation cannot redefine the earlier screening cohort."""
from fractions import Fraction
import struct

import pytest

from anatrading import daily_followup
from anatrading.daily_screen import screen_report
from anatrading.tdx_acquisition import AcquireError
from test_daily_coverage import POOL, committed, run
from test_daily_screen import raw_record, PARAMS


def observed(value):
    return dict(group='matched', observation=dict(status='computed', reason=None, change=daily_followup.signed_fraction(value)))


def test_signed_fraction_and_zero_rounding_are_exact():
    assert daily_followup.signed_fraction(Fraction(-1,5)) == dict(numerator='-1',denominator='5',percent_display='-20.0000')
    assert daily_followup.signed_fraction(Fraction(-1,2000000))['percent_display']=='0.0000'
    assert daily_followup.signed_fraction(Fraction(-3,2000000))['percent_display']=='-0.0002'


def test_type7_hand_quantiles_and_missing_denominator():
    rows=[observed(Fraction(-1,5)),observed(Fraction(3,10)),dict(group='matched',observation=dict(status='not_evaluated',reason='end_date_missing',change=None))]
    result=daily_followup.group_summary(rows,'matched')
    assert (result['selected'],result['observed'],result['missing'])==(3,2,1)
    expected={'q1':Fraction(-3,40),'median':Fraction(1,20),'q3':Fraction(7,40)}
    for field,value in expected.items(): assert result['quantiles'][field]==daily_followup.signed_fraction(value)
    assert result['sign_counts']==dict(positive=1,zero=0,negative=1)
    assert result['sign_proportions']['positive']==daily_followup.signed_fraction(Fraction(1,2))
    assert result['coverage']==daily_followup.signed_fraction(Fraction(2,3))
    assert result['missing_reasons']=={'end_date_missing':1}


def test_empty_single_and_exact_sign_not_display_sign():
    empty=daily_followup.group_summary([],'matched')
    assert empty['quantiles']==dict(q1=None,median=None,q3=None) and empty['coverage'] is None
    value=Fraction(1,1000000000)
    result=daily_followup.group_summary([observed(value)],'matched')
    assert result['sign_counts']==dict(positive=1,zero=0,negative=0)
    assert all(item==daily_followup.signed_fraction(value) for item in result['quantiles'].values())
    assert result['quantiles']['median']['percent_display']=='0.0000'


def test_exact_endpoint_preserves_original_ordinals_and_never_fills():
    raw=raw_record(4,80)+raw_record(1,100)+raw_record(3,100)
    result=daily_followup.source_change(raw,'2026-09-03','2026-09-04')
    assert result['status']=='computed'
    assert result['start']['ordinals']==[3] and result['end']['ordinals']==[1]
    assert result['change']==daily_followup.signed_fraction(Fraction(-1,5))
    assert daily_followup.source_change(raw,'2026-09-03','2026-09-05')['reason']=='end_date_missing'
    assert daily_followup.source_change(raw+raw_record(4,90),'2026-09-03','2026-09-04')['reason']=='duplicate_end_date'


def test_zero_base_invalid_close_and_irrelevant_fields():
    assert daily_followup.source_change(raw_record(3,0)+raw_record(4,100),'2026-09-03','2026-09-04')['reason']=='zero_start_close'
    result=daily_followup.source_change(raw_record(3,100,opening=999,amount=float('nan'))+raw_record(4,0,0),'2026-09-03','2026-09-04')
    assert result['change']==daily_followup.signed_fraction(Fraction(-1))
    bad=struct.pack('<IIIIIfII',20260904,100,101,99,1000,1000,100,0)
    assert daily_followup.source_change(raw_record(3,100)+bad,'2026-09-03','2026-09-04')['reason']=='close_outside_range'


@pytest.mark.parametrize('start,end',[('2026-09-03','2026-09-03'),('2026-09-03','2026-09-02'),('bad','2026-09-04'),('2026-09-03','20260904')])
def test_invalid_interval(start,end):
    with pytest.raises(AcquireError,match='invalid_daily_followup'):
        daily_followup.validate_interval(start,end)


def test_later_endpoint_missing_does_not_remove_or_reclassify_members(tmp_path):
    first,snapshot=committed(tmp_path,POOL[0],[20260901,20260902,20260903,20260904])
    run(tmp_path,'a'*32,[first,dict(symbol=POOL[1],status='missing')],state='failed')
    before=screen_report(tmp_path,[snapshot],['a'*32],**PARAMS,minimum_efficiency='0')
    for end in ['2026-09-04','2026-09-05']:
        result=screen_report(tmp_path,[snapshot],['a'*32],**PARAMS,minimum_efficiency='0',evaluation_date=end)
        assert result['counts']==before['counts']
        assert result['rows'][0]['status']==before['rows'][0]['status']=='matched'
        assert result['rows'][0]['analysis']==before['rows'][0]['analysis']
        assert result['source_screen_id']==before['screen_id']
        assert result['groups']['matched']['selected']==1
        assert result['groups']['matched']['observed']==int(end=='2026-09-04')
        assert result['groups']['other_eligible']['selected']==0


def test_followup_rejects_a_different_original_screen_identity(tmp_path):
    item,snapshot=committed(tmp_path,POOL[0],[20260901,20260902,20260903,20260904])
    run(tmp_path,'a'*32,[item])
    before=screen_report(tmp_path,[snapshot],['a'*32],**PARAMS)
    result=screen_report(tmp_path,[snapshot],['a'*32],**PARAMS,evaluation_date='2026-09-04',expected_screen_id=before['screen_id'])
    assert result['source_screen_id']==before['screen_id']
    with pytest.raises(AcquireError,match='followup_screen_mismatch'):
        screen_report(tmp_path,[snapshot],['a'*32],**PARAMS,evaluation_date='2026-09-04',expected_screen_id='0'*64)


def test_counterpart_group_excludes_screen_unevaluable_members(tmp_path):
    first,snapshot=committed(tmp_path,POOL[0],[20260901,20260902,20260903,20260904])
    second,other=committed(tmp_path,POOL[1],[20260903,20260904])
    run(tmp_path,'a'*32,[first,second])
    report=screen_report(tmp_path,[snapshot,other],['a'*32],**PARAMS,minimum_volume='2',evaluation_date='2026-09-04')
    assert report['groups']['other_eligible']['selected']==1
    assert report['groups']['matched']['selected']==0
    assert report['rows'][1]['group'] is None and report['rows'][1]['status']=='not_evaluated'


def test_http_followup_has_separate_method_and_parameters(tmp_path):
    import asyncio
    from test_workbench import running
    root=tmp_path/'root'; run(root,'a'*32,[dict(symbol=POOL[0],status='missing')])
    async def scenario():
        async with running(root) as (_,client,auth):
            params=dict(run_ids='a'*32,**PARAMS,evaluation_date='2026-09-04')
            response=await client.get('/api/daily-followup',params=params)
            assert response.status_code==200
            report=response.json()['followup']
            assert report['method_id']=='current-pool-daily-followup-v1'
            assert report['parameters']['evaluation_date']=='2026-09-04'
            frozen=(await client.get('/api/daily-screen',params={name:value for name,value in params.items() if name!='evaluation_date'})).json()['screen']
            verified=await client.get('/api/daily-followup',params={**params,'screen_id':frozen['screen_id']})
            assert verified.status_code==200 and verified.json()['followup']['source_screen_id']==frozen['screen_id']
            mismatch=await client.get('/api/daily-followup',params={**params,'screen_id':'0'*64})
            assert mismatch.status_code==409 and mismatch.json()['error']=='followup_screen_mismatch'
            bad=await client.get('/api/daily-followup',params={**params,'evaluation_date':'2026-09-03'})
            assert bad.status_code==400 and bad.json()['error']=='invalid_daily_followup'
            assert (await client.get('/api/daily-screen',params=params)).status_code==400
    asyncio.run(scenario())
