"""Synthetic 050 reports and independent Fraction expectations; no Store/network.

Expected group paths use Fraction per member and all strict p<v pairs, not the
candidate common-denominator scan. The full-bound case has an analytic witness.
"""
from copy import deepcopy
from datetime import date, timedelta
from fractions import Fraction
import json
from anatrading.drawdown_episode_research import drawdown_episode_report, summarize
from test_peer_relative_research import source_query, recount


def pair(x):
    return dict(numerator=str(x.numerator), denominator=str(x.denominator))


def reference(report, large=False):
    if not report['comparison_available']:
        return None
    prices = [[Fraction(p['close_exact']) for p in m['endpoints']] for m in report['members']]
    n, length = len(prices), len(prices[0])
    curve = [sum(row[t]/row[0] for row in prices)/n for t in range(length)]
    if large:
        # All rows: q_i, U-1, 1, then q_i. 1 is unique low, U-1 a common high.
        p, v, depth = 1, 2, 1-curve[2]/curve[1]
    else:
        candidates = [(1-curve[v]/curve[p], v, p) for v in range(1,length) for p in range(v) if curve[v]<curve[p]]
        depth, v, p = max(candidates, key=lambda x:(x[0],-x[1],x[2])) if candidates else (Fraction(0),None,None)
    contributions = None if p is None else [pair((row[p]-row[v])/row[0]/n/curve[p]) for row in prices]
    return dict(curve=list(map(pair,curve)),peak=p,trough=v,depth=pair(depth),contributions=contributions)


def fixtures():
    output={}
    def make(values):
        days=[(date(2026,1,1)+timedelta(days=i)).isoformat() for i in range(len(values[0]))]
        return [source_query(f'{600000+i}.SH',row,days) for i,row in enumerate(values)],days
    def add(name,values=None,queries=None,days=None,large=False):
        if queries is None: queries,days=make(values)
        for q in queries: recount(q)
        r=drawdown_episode_report(queries,days[-1],len(days)-1)
        output[name]=dict(reply=r,expected=dict(ids=sorted(q['snapshot_id'] for q in queries),cutoff=days[-1],lookback=len(days)-1),oracle=reference(r,large))
        return queries,days
    cases={
      'T1':[[100,80,100],[100,120,100]],'T2':[[100,120,90],[100,90,100]],
      'T3':[[100,100,90,100,90]]*2,'no_drawdown':[[100,101,102]]*2,
      'T4':[[100,200,100],[100,100,100]],'T5':[[100,50,50],[100,100,100]],
      'T7_scaled':[[200,240,180],[300,270,300]],
      'near_peak':[['1','1.000000000000000001','0.5']]*2,
      'near_depth':[['1','0.999999999999999999','1','0.999999999999999998']]*2,
      'tiny_offset':[['1','1','0.9'],['1','1','1.000000000000000001']],
      'domain':[['0.000000000000000001','99999999999999999999.999999999999999999','0.000000000000000001']]*2,
    }
    for name,values in cases.items(): add(name,values)
    for end in (3,4): add(f'T3_prefix_{end}',[row[:end] for row in cases['T3']])
    add('T2_four_members',[cases['T2'][0]]*2+[cases['T2'][1]]*2)
    q,days=make(cases['T2']);add('T7_permuted',queries=list(reversed(q)),days=days)
    q,days=make(cases['T2'])
    for i,m in enumerate(q):
        row=deepcopy(m['rows'][-1]);row['ordinal']=999;row['label']=row['tokens']['source_date']='2026-12-31'
        for key in ('open','high','low','close'):row['values'][key]=row['tokens'][key]=str(1 if i==0 else 1000)
        m['rows'].append(row)
    add('T7_future',queries=q,days=days)
    for kind in ('missing','duplicate','zero','unknown','future_global','refused','mismatch'):
        values=[[100,120,90,100],[100,90,100,100]] if kind=='mismatch' else cases['T2']
        q,days=make(values)
        if kind=='missing':q[0]['rows'].pop(1)
        if kind=='duplicate':row=deepcopy(q[0]['rows'][1]);row['ordinal']=999;q[0]['rows'].append(row)
        if kind=='zero':q[0]['rows'][1]['values']['close']='0'
        if kind=='unknown':
            row=deepcopy(q[0]['rows'][1]);row['ordinal']=999;row['label']=None;row['tokens']['source_date']='?';q[0]['unlocated'].append(row)
        if kind=='future_global':
            row=deepcopy(q[0]['rows'][-1]);row['ordinal']=999;row['label']=row['tokens']['source_date']='2026-12-31';row['tokens']['source_code']='600099.SH';q[0]['rows'].append(row)
        if kind=='refused':q[0]['metadata']['requested_adjustment']='qfq'
        if kind=='mismatch':
            # Keep equal length and equal endpoints but distinct interior source dates.
            q[0]['rows'][1]['label']=q[0]['rows'][1]['tokens']['source_date']='2026-01-02'
            q[1]['rows'].pop(1);q[0]['rows'].pop(2);days=[days[0],days[1],days[-1]]
        add('failure_'+kind,queries=q,days=days)
    base=output['T2']
    for kind in ('price','ordinal'):
        f=deepcopy(base)
        if kind=='price':f['reply']['members'][0]['endpoints'][1]['close_exact']='130'
        else:f['reply']['members'][0]['endpoints'][1]['ordinal']='999'
        for m in f['reply']['members']:m.update(summarize(m['endpoints']))
        f['oracle']=reference(f['reply']);output['same_id_'+kind]=f
    # Failed original source evidence preserves dates/query identity, so analysis_id is unchanged.
    q,days=make(cases['T2']);q[0]['rows'][1]['values']['close']='0';add('same_id_qualification',queries=q,days=days)
    def decimal(a):
        text=f'{a//10**18}.{a%10**18:018d}'.rstrip('0').rstrip('.')
        return text
    upper=10**38-1
    add('full_bound',[[decimal(upper-2*i),decimal(upper),decimal(1)]+[decimal(upper-2*i)]*250 for i in range(50)],large=True)
    return output


if __name__=='__main__': print(json.dumps(fixtures(),separators=(',',':')))
