"""Complete signed pairs on two identical all-member source windows (051).

Only orchestration is new. The 049 exact kernel and source helpers are unchanged.
"""
from collections import Counter
from fractions import Fraction
import hashlib
from itertools import combinations

from . import peer_neighbor_research as kernel
from . import peer_relative_research as peer
from .pair_research import symbol_identity
from .research_series import strict_date

METHOD_ID = 'complete-group-pairs-simple-v1'
RULE_VERSION = 'all-member-grid-60x2-exact-pairs-v1'
MAX_RESULT_BYTES = 2 * 1024 * 1024
RULES = dict(intervals_per_window=60, source_endpoints=121, transform='source_simple_change',
    anchor='all_member_source_dates_exact_cutoff', panel='all_selected_complete',
    integer_bits=65536, display_precision=50, display_rounding='ROUND_HALF_EVEN',
    pairs='all_unique_snapshot_id_order', events='not_supported')
ERRORS = kernel.ERRORS - {'invalid_target', 'peer_neighbor_result_limit'} | {'group_pair_result_limit'}


def serialize_report(report):
    encoded = peer._json(report).encode('utf-8')
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError('group_pair_result_limit')
    return encoded


def _member_window(member, scanned, cutoff):
    slots, issues, global_reasons = scanned
    dates = sorted(day for day in slots if day <= cutoff)[-121:]
    reasons = set()
    if cutoff not in slots:
        reasons.add('cutoff_missing')
    if len(dates) < 121:
        reasons.add('history_insufficient')
    member['date_array'] = dates
    if dates:
        prices = kernel._window_member(member, scanned, dates)
        # Own candidate date groups are used, never another member's grid.
        member.pop('date_mismatch')
        member['reasons'] = sorted(set(member['reasons']) | reasons)
    else:
        prices = []
        for day, _, codes in issues:
            if day is None:
                reasons.update(set(codes) & {'local_source_conflict', 'unclassified_source_failure', 'endpoint_integrity_unknown'})
        counts = Counter(code for _, _, codes in issues for code in codes)
        member.update(evaluation='evaluated', endpoints=[], reasons=sorted(reasons | global_reasons),
            anomalies=dict(total=len(issues), counts=dict(sorted(counts.items())),
                examples=[dict(date=day, ordinal=ordinal,
                    scope='unknown' if day is None else 'window_unavailable', codes=codes)
                    for day, ordinal, codes in issues[:20]], truncated=len(issues)>20))
    member['panel_complete'] = not member['reasons']
    return prices


def group_pair_report(queries, cutoff):
    if type(queries) not in (list, tuple) or not 2 <= len(queries) <= peer.MAX_MEMBERS:
        raise ValueError('member_limit')
    if any(type(q) is not dict or type(q.get('rows')) not in (list, tuple)
           or type(q.get('unlocated')) not in (list, tuple) for q in queries):
        raise ValueError('invalid_query')
    sizes = [len(q['rows'])+len(q['unlocated']) for q in queries]
    if max(sizes) > peer.MAX_SOURCE_ROWS:
        raise ValueError('research_row_limit')
    if sum(sizes) > peer.MAX_TOTAL_ROWS:
        raise ValueError('universe_row_limit')
    cutoff = strict_date(cutoff, 'invalid_dates')
    for query in queries:
        peer._group_structure(query)
    if len({q['snapshot_id'] for q in queries}) != len(queries):
        raise ValueError('duplicate_member')
    members, prices, symbols = [], {}, set()
    for query in sorted(queries, key=lambda q: q['snapshot_id']):
        identity, refusal = None, None
        try:
            identity = peer._source(query)
        except ValueError as exc:
            if str(exc) not in peer._GROUP_SOURCE_REASONS:
                raise
            refusal = str(exc)
            if refusal != 'source_identity_conflict':
                try:
                    identity = symbol_identity(query)
                except ValueError:
                    pass
        symbol = identity['symbol'] if identity is not None else None
        if symbol is not None:
            if symbol in symbols:
                raise ValueError('duplicate_member')
            symbols.add(symbol)
        sid = query['snapshot_id']
        member = dict(symbol=symbol, snapshot_id=sid, batch_id=query['batch_id'], query_id=query['query_id'],
            source_qualified=refusal is None, evaluation='not_evaluated', panel_complete=False,
            date_array=[], endpoints=None, anomalies=None, reasons=[refusal] if refusal else [],
            constant=dict(previous=None, current=None))
        if refusal is None:
            prices[sid] = _member_window(member, kernel._scan(query, identity), cutoff)
        members.append(member)
    grid_reasons = []
    if any(len(m['date_array']) != 121 or m['date_array'][-1] != cutoff for m in members):
        grid_reasons.append('member_grid_unavailable')
    elif any(m['date_array'] != members[0]['date_array'] for m in members):
        grid_reasons.append('member_date_arrays_differ')
    dates = [] if grid_reasons else list(members[0]['date_array'])
    panel = bool(dates) and all(m['panel_complete'] for m in members)
    pairs = [dict(left_snapshot_id=a['snapshot_id'], right_snapshot_id=b['snapshot_id'])
             for a, b in combinations(members, 2)]
    windows = {}
    for name, offset in (('previous', 0), ('current', 60)):
        centered = {}
        if panel:
            for member in members:
                sid = member['snapshot_id']
                points = [kernel._price_integer(v) for v in prices[sid][offset:offset+61]]
                centered[sid] = kernel._center([Fraction(b-a, a) for a,b in zip(points, points[1:])])
                member['constant'][name] = centered[sid] is None
        available = 0
        for pair in pairs:
            left, right = pair['left_snapshot_id'], pair['right_snapshot_id']
            constants = [sid for sid in (left, right) if panel and centered[sid] is None]
            correlation = None
            reason = 'source_panel_unavailable' if not panel else 'constant_source_change' if constants else None
            if reason is None:
                correlation = kernel._display(kernel._correlation(centered[left], centered[right]))
                available += 1
            pair[name] = dict(correlation=correlation, reason=reason, constant_members=constants)
        windows[name] = dict(start=dates[offset] if dates else None, end=dates[offset+60] if dates else None,
            intervals=60, total=len(pairs), available=available, unavailable=len(pairs)-available)
    parameters = dict(cutoff=cutoff, rules=dict(RULES))
    refs = [{key:m[key] for key in ('symbol','snapshot_id','batch_id','query_id','date_array')} for m in members]
    identity = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, source_rule_version=peer.RULE_VERSION,
        parameters=parameters, sources=refs, used_dates=dates, scope=kernel.SCOPE, limitations=kernel.LIMITATIONS, events=[])
    total_available = sum(w['available'] for w in windows.values())
    report = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, source_rule_version=peer.RULE_VERSION,
        analysis_id=hashlib.sha256(peer._json(identity).encode()).hexdigest(), parameters=parameters,
        scope={k:dict(v) for k,v in kernel.SCOPE.items()}, limitations=dict(kernel.LIMITATIONS), events=[],
        used_dates=dates, grid_reasons=grid_reasons, members=members, pairs=pairs, windows=windows,
        counts=dict(selected=len(members), pairs=len(pairs), source_qualified=sum(m['source_qualified'] for m in members),
            panel_complete=sum(m['panel_complete'] for m in members)), source_panel_complete=panel,
        reasons=[] if panel else ['source_panel_unavailable'],
        status='complete' if total_available == 2*len(pairs) else 'partial' if total_available else 'unavailable')
    serialize_report(report)
    return report
