"""Test-only fresh synthetic DTO bridge. No database or network access."""
from copy import deepcopy
import json
from test_group_pair_research import world, run
from test_peer_neighbor_research import fixture
from test_peer_relative_research import recount, fail


def fixtures():
    result={}
    def add(name,q,days):
        result[name]=dict(expected=dict(ids=sorted(x['snapshot_id'] for x in q),cutoff=days[-1]),reply=run(q,days))
    q,days=world([(1,1,-1,-1)]*2+[(1,-1,1,-1)]*2); add('complete',q,days)
    q,days=fixture();add('partial',q,days)
    q[1]['metadata']['requested_adjustment']='qfq';add('refused',q,days)
    q,days=fixture();q[1]['rows'].pop(30);recount(q[1]);add('missing',q,days)
    q,days=fixture();q[1]['rows'][30]['tokens']['close']='999';add('price',q,days)
    q,days=fixture();q[1]['rows']=[];recount(q[1]);add('empty',q,days)
    q,days=fixture();q[1]['rows'].pop();recount(q[1]);add('cutoff',q,days)
    q,days=fixture();new=deepcopy(q[1]['rows'][30]);new['ordinal']=999;q[1]['rows'].append(new);recount(q[1]);add('duplicate',q,days)
    q,days=fixture();new=q[1]['rows'].pop(30);new['label']=None;new['tokens']['source_date']='?';q[1]['unlocated'].append(new);recount(q[1]);add('unknown',q,days)
    q,days=fixture(3)
    for point in q[1]['rows']:
        point['label']=None;point['tokens']['source_date']='?'
    q[1]['unlocated']=q[1]['rows'];q[1]['rows']=[]
    fail(q[1]['unlocated'][0],'source_date_range');fail(q[1]['unlocated'][1],'synthetic_future_check')
    recount(q[1]);add('all_unknown',q,days)
    q,days=fixture(50);add('maximum',q,days)
    return result

if __name__=='__main__':
    print(json.dumps(fixtures(),ensure_ascii=False,separators=(',',':')))
