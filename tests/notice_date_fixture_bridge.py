"""Fresh synthetic DTOs only; no Store instance, existing market data or network."""
from copy import deepcopy
from datetime import date, timedelta
import json
from anatrading.group_pair_research import group_pair_report
from test_peer_relative_research import source_query, recount, fail


def fixtures():
    result = {}
    days = [(date(2025, 12, 20) + timedelta(days=i)).isoformat() for i in range(133)]
    def fresh(symbols=('000001.SZ', '000002.SZ')):
        return [source_query(symbol, [100+i % 7 for i in range(len(days))], days) for symbol in symbols]
    def add(name, queries, cutoff=days[-1]):
        for query in queries: recount(query)
        result[name] = dict(expected=dict(ids=sorted(q['snapshot_id'] for q in queries), cutoff=cutoff), reply=group_pair_report(queries, cutoff))
    def at(q, day='2026-01-05'):
        return next(row for row in q['rows'] if row['label'] == day)
    add('complete', fresh())
    q = fresh()
    for member in q: member['rows'].remove(at(member))
    add('missing_all', q)
    q = fresh(); q[0]['rows'].remove(at(q[0])); add('missing_one', q)
    q = fresh(); at(q[0])['values']['close'] = '0'; add('price', q)
    q = fresh(); row = deepcopy(at(q[0])); row['ordinal'] = 999; q[0]['rows'].append(row); add('duplicate', q)
    q = fresh(); row = at(q[0]); q[0]['rows'].remove(row); row['label'] = None
    q[0]['unlocated'].append(row); add('unlocated_known', q)
    q = fresh()
    for row in q[0]['rows'][:25]: fail(row, 'numeric.close')
    row = at(q[0], '2026-02-24'); q[0]['rows'].remove(row); row['label'] = None; row['tokens']['source_date'] = '?'
    q[0]['unlocated'].append(row); add('unknown_after_twenty', q)
    q = fresh(); at(q[0])['tokens']['source_date'] = '2026-01-06'; add('label_mismatch', q)
    q = fresh(); fail(at(q[0]), 'source_date_range'); add('local_conflict', q)
    q = fresh(); fail(at(q[0]), 'future_unknown_check'); add('unclassified', q)
    q = fresh(); row = deepcopy(q[0]['rows'][-1]); row['ordinal'] = 999
    row['label'] = row['tokens']['source_date'] = '2026-12-31'; row['tokens']['source_code'] = '000099.SZ'
    q[0]['rows'].append(row); add('global_identity', q)
    q = fresh(); q[0]['metadata']['requested_adjustment'] = 'qfq'; add('refused', q)
    q = fresh(); q[0]['rows'].pop(); add('cutoff_missing', q)
    q = fresh()
    for member in q: member['rows'] = []
    add('empty', q)
    q = fresh(); q[0]['rows'] = [row for row in q[0]['rows'] if row['label'] >= '2026-02-01']; add('short', q)
    q = fresh(('600000.SH', '600001.SH', '000001.SZ'))
    for member in q[:2]: member['rows'].remove(at(member))
    add('mixed', q)
    q = fresh(); row = deepcopy(q[0]['rows'][-1]); row['ordinal'] = 999
    row['label'] = row['tokens']['source_date'] = '2026-12-31'
    for key in ('open','close','high','low'): row['values'][key] = row['tokens'][key] = '999'
    q[0]['rows'].append(row); add('future_price', q)
    add('reversed', list(reversed(fresh())))
    return result


if __name__ == '__main__':
    print(json.dumps(fixtures(), ensure_ascii=False, separators=(',', ':')))
