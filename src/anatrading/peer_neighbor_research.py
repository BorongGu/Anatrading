"""One explicit target, two complete source windows, exact signed simple-change ranks.

No all-pairs matrix, source acquisition, event input or change to older contracts.
"""
from collections import Counter
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from fractions import Fraction
from functools import cmp_to_key
import hashlib
from math import lcm

from . import peer_relative_research as peer
from .pair_research import symbol_identity
from .research_series import strict_date

METHOD_ID = 'explicit-peer-neighbors-simple-v1'
RULE_VERSION = 'target-grid-60x2-exact-correlation-v1'
MAX_INTEGER_BITS = 65536
MAX_RESULT_BYTES = 2 * 1024 * 1024
RULES = dict(intervals_per_window=60, source_endpoints=121, transform='source_simple_change',
             anchor='target_source_dates_exact_cutoff', panel='all_selected_complete',
             integer_bits=65536, display_precision=50, display_rounding='ROUND_HALF_EVEN',
             ranking='signed_descending_exact_competition', events='not_supported')
SCOPE = {key: dict(value=value, evidence_status='assumed') for key, value in
         dict(asset_type='stock', share_class='A_share', price_currency='CNY',
              daily_label_basis='CN_exchange_date').items()}
LIMITATIONS = dict(economic_return_qualified=False, total_return_qualified=False,
    historical_availability='unverified', closure='unknown', trading_calendar='unknown',
    corporate_action_coverage='unknown', halt_event_coverage='unknown',
    adjustment='request_declared_semantics_unverified', source_integrity='trusted_store_boundary',
    membership='current_members_retrospective', source_semantics='unverified',
    statistical_or_trading_advantage='not_evaluated', user_efficiency='not_evaluated',
    windows='nonoverlapping_changes_shared_price_boundary', log_correlation_equivalent=False)
ERRORS = peer.GROUP_ERRORS | {'invalid_target', 'peer_neighbor_integer_limit',
    'peer_neighbor_display_failure', 'peer_neighbor_arithmetic_failure', 'peer_neighbor_result_limit'}


def _bounded(value):
    if abs(value).bit_length() > MAX_INTEGER_BITS:
        raise ValueError('peer_neighbor_integer_limit')
    return value


def _price_integer(value):
    # Decimal arithmetic under the ambient context would round 38-digit prices.
    exact = Fraction(value) * 10**18
    if exact.denominator != 1 or not 1 <= exact.numerator < 10**38:
        raise ValueError('peer_neighbor_arithmetic_failure')
    return exact.numerator


def _center(values):
    """Private rational kernel; the report always supplies exactly 60 changes."""
    if not 2 <= len(values) <= 60:
        raise ValueError('peer_neighbor_arithmetic_failure')
    denominator = 1
    for value in values:
        _bounded(value.numerator); _bounded(value.denominator)
        denominator = _bounded(lcm(denominator, value.denominator))
    scaled = [_bounded(v.numerator * (denominator // v.denominator)) for v in values]
    total = _bounded(sum(scaled))
    vector = [_bounded(len(values)*v-total) for v in scaled]
    norm = _bounded(sum(_bounded(v*v) for v in vector))
    return (vector, norm) if norm else None


def _correlation(left, right):
    if left is None or right is None or len(left[0]) != len(right[0]):
        raise ValueError('peer_neighbor_arithmetic_failure')
    cross = _bounded(sum(_bounded(a*b) for a, b in zip(left[0], right[0])))
    denominator = _bounded(left[1]*right[1])
    if denominator <= 0 or _bounded(cross*cross) > denominator:
        raise ValueError('peer_neighbor_arithmetic_failure')
    return cross, left[1], right[1]


def _sign(value):
    return (value > 0) - (value < 0)


def _compare(left, right):
    """Exact ascending comparison, including negative magnitude reversal."""
    ls, rs = _sign(left[0]), _sign(right[0])
    if ls != rs:
        return _sign(ls-rs)
    if not ls:
        return 0
    a = _bounded(_bounded(left[0]*left[0]) * _bounded(right[1]*right[2]))
    b = _bounded(_bounded(right[0]*right[0]) * _bounded(left[1]*left[2]))
    return ls * _sign(a-b)


def _formatted(value, bound):
    if not value.is_finite() or abs(value) > bound or value and value.adjusted() < -10000:
        raise ValueError('peer_neighbor_display_failure')
    estimate = format(value.normalize(), 'E') if value else '0'
    rounded = value.quantize(Decimal('0.0001'))
    display = format(abs(rounded) if not rounded else rounded, '.4f')
    if len(estimate) > 80:
        raise ValueError('peer_neighbor_display_failure')
    return dict(estimate=estimate, display=display)


def _display(value):
    cross, xx, yy = value
    sign = _sign(cross)
    square, denominator = _bounded(cross*cross), _bounded(xx*yy)
    if denominator <= 0 or square > denominator:
        raise ValueError('peer_neighbor_arithmetic_failure')
    boundary = 'zero' if not sign else ('positive_one' if sign > 0 else 'negative_one') if square == denominator else 'none'
    try:
        with localcontext() as ctx:
            ctx.prec = 50; ctx.rounding = ROUND_HALF_EVEN
            ctx.Emin = -999999; ctx.Emax = 999999
            result = Decimal(sign) if boundary != 'none' else Decimal(sign)*(Decimal(square)/Decimal(denominator)).sqrt()
            if sign and not result:
                raise ValueError('peer_neighbor_display_failure')
            return dict(**_formatted(result, 1), sign={-1:'negative', 0:'zero', 1:'positive'}[sign], exact_boundary=boundary)
    except DecimalException:
        raise ValueError('peer_neighbor_display_failure') from None


def _difference(current, previous):
    try:
        with localcontext() as ctx:
            ctx.prec = 50; ctx.rounding = ROUND_HALF_EVEN
            ctx.Emin = -999999; ctx.Emax = 999999
            delta = Decimal(_display(current)['estimate']) - Decimal(_display(previous)['estimate'])
            direction = {-1:'decreased', 0:'equal', 1:'increased'}[_compare(current, previous)]
            return dict(**_formatted(delta, 2), direction=direction)
    except DecimalException:
        raise ValueError('peer_neighbor_display_failure') from None


def _scan(query, identity):
    slots, issues, global_reasons = {}, [], set()
    for rows in (query['rows'], query['unlocated']):
        for row in rows:
            day, located = peer._position(row)
            failed = peer._checks(row['checks'])
            codes = set(failed)
            if day is None:
                codes.add('endpoint_integrity_unknown'); global_reasons.add('endpoint_integrity_unknown')
            else:
                slots.setdefault(day, []).append((row, located))
            if not located:
                codes.add('unlocated_label')
            if peer._row_conflict(row, failed, identity):
                codes.add('local_source_conflict')
            if (failed & (peer._IDENTITY | peer._ADJUSTMENT | {'structure', 'known_negative_sample'})
                    or any(row['tokens'].get(k) in peer._ADJUSTED for k in ('adjustflag', 'source_adjustment')
                           if type(row['tokens'].get(k)) is str)):
                codes.add('global_source_conflict'); global_reasons.add('global_source_conflict')
            # A token identity contradiction anywhere revokes this source;
            # source_date_range alone remains a located, interval-scoped issue.
            for key in ('code', 'source_code'):
                if row['tokens'].get(key) is not None:
                    try:
                        observed = symbol_identity({'metadata': {'source_code': row['tokens'][key],
                                                                 'source_venue': identity['venue']}})
                        conflict = observed['symbol'] != identity['symbol']
                    except ValueError:
                        conflict = True
                    if conflict:
                        codes.add('global_source_conflict'); global_reasons.add('global_source_conflict')
            if failed - peer._KNOWN_CHECKS:
                codes.add('unclassified_source_failure')
            if codes:
                issues.append((day, row['ordinal'], sorted(codes)))
    return slots, issues, global_reasons


def _window_member(member, scanned, dates):
    slots, issues, global_reasons = scanned
    reasons = set(global_reasons)
    first, last = dates[0], dates[-1]
    counts, examples = Counter(), []
    for day, ordinal, codes in issues:
        scope = 'unknown' if day is None else 'inside_interval' if first <= day <= last else 'outside_interval'
        if scope != 'outside_interval':
            reasons.update(set(codes) & {'local_source_conflict', 'unclassified_source_failure', 'endpoint_integrity_unknown'})
        counts.update(codes)
        if len(examples) < 20:
            examples.append(dict(date=day, ordinal=ordinal, scope=scope, codes=codes))
    present = {day for day in slots if first <= day <= last}
    missing, extra = sorted(set(dates)-present), sorted(present-set(dates))
    if extra:
        reasons.add('extra_source_dates')
    endpoints, prices = [], []
    for day in dates:
        endpoint, price = peer._endpoint(day, slots.get(day, []))
        endpoints.append(endpoint); prices.append(price); reasons.update(endpoint['reasons'])
    member.update(evaluation='evaluated', endpoints=endpoints, reasons=sorted(reasons), panel_complete=not reasons,
        date_mismatch=dict(missing_count=len(missing), extra_count=len(extra), missing_examples=missing[:20],
                           extra_examples=extra[:20], truncated=len(missing)>20 or len(extra)>20),
        anomalies=dict(total=len(issues), counts=dict(sorted(counts.items())), examples=examples, truncated=len(issues)>20))
    return prices


def _empty_cell(reason):
    return dict(correlation=None, rank=None, tie_size=None, reason=reason)


def peer_neighbor_report(queries, target_snapshot_id, cutoff):
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
    ids = [q['snapshot_id'] for q in queries]
    if len(set(ids)) != len(ids):
        raise ValueError('duplicate_member')
    if type(target_snapshot_id) is not str or target_snapshot_id not in ids:
        raise ValueError('invalid_target')
    members, scans, symbols = [], {}, set()
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
        members.append(dict(symbol=symbol, snapshot_id=sid, batch_id=query['batch_id'], query_id=query['query_id'],
            role='target' if sid == target_snapshot_id else 'candidate', source_qualified=refusal is None,
            evaluation='not_evaluated', panel_complete=False, endpoints=None, date_mismatch=None,
            anomalies=None, reasons=[refusal] if refusal else []))
        if refusal is None:
            scans[sid] = _scan(query, identity)
    anchor_reasons, ordered, dates = [], [], []
    if target_snapshot_id not in scans:
        anchor_reasons.append('anchor_source_unavailable')
    else:
        slots, _, global_reasons = scans[target_snapshot_id]
        ordered = sorted(day for day in slots if day <= cutoff)
        if 'endpoint_integrity_unknown' in global_reasons:
            anchor_reasons.append('endpoint_integrity_unknown')
        if cutoff not in slots:
            anchor_reasons.append('cutoff_missing')
        if len(ordered) < 121:
            anchor_reasons.append('anchor_history_insufficient')
        if not anchor_reasons:
            dates = ordered[-121:]
    anchor = dict(reasons=sorted(anchor_reasons), located_dates=len(ordered),
                  last_date=ordered[-1] if ordered else None, examples=ordered[-20:], truncated=len(ordered)>20)
    prices = {}
    for member in members:
        if not member['source_qualified']:
            continue
        if dates:
            prices[member['snapshot_id']] = _window_member(member, scans[member['snapshot_id']], dates)
        else:
            # The full scan ran even when no anchor window could be formed.
            # Preserve its global evidence; only endpoint evaluation is pending.
            _, issues, global_reasons = scans[member['snapshot_id']]
            counts = Counter(code for _, _, codes in issues for code in codes)
            member['reasons'] = sorted({'anchor_window_unavailable', *global_reasons})
            member['anomalies'] = dict(total=len(issues), counts=dict(sorted(counts.items())),
                examples=[dict(date=day, ordinal=ordinal, scope='unknown' if day is None else 'window_unavailable',
                               codes=codes) for day, ordinal, codes in issues[:20]], truncated=len(issues)>20)
    panel = bool(dates) and all(m['panel_complete'] for m in members)
    candidate_ids = sorted(sid for sid in ids if sid != target_snapshot_id)
    candidates = {sid: dict(snapshot_id=sid, previous=_empty_cell('source_panel_unavailable'),
                            current=_empty_cell('source_panel_unavailable'), difference=None) for sid in candidate_ids}
    windows, exact = {}, {}
    for name, offset in (('previous', 0), ('current', 60)):
        window = dict(start=dates[offset] if dates else None, end=dates[offset+60] if dates else None,
                      intervals=60, available=0, target_reason=None if panel else 'source_panel_unavailable',
                      order=list(candidate_ids))
        if panel:
            centered = {}
            for sid in ids:
                points = [_price_integer(v) for v in prices[sid][offset:offset+61]]
                centered[sid] = _center([Fraction(b-a, a) for a,b in zip(points, points[1:])])
            target = centered[target_snapshot_id]
            if target is None:
                window['target_reason'] = 'target_constant_source_change'
            values = {}
            for sid in candidate_ids:
                if target is None:
                    candidates[sid][name] = _empty_cell('target_constant_source_change')
                elif centered[sid] is None:
                    candidates[sid][name] = _empty_cell('constant_source_change')
                else:
                    values[sid] = _correlation(target, centered[sid])
            ordered_ids = sorted(values, key=cmp_to_key(lambda a,b: -_compare(values[a], values[b]) or (a>b)-(a<b)))
            position = 0
            while position < len(ordered_ids):
                end = position+1
                while end < len(ordered_ids) and _compare(values[ordered_ids[position]], values[ordered_ids[end]]) == 0:
                    end += 1
                for sid in ordered_ids[position:end]:
                    candidates[sid][name] = dict(correlation=_display(values[sid]), rank=position+1,
                                                tie_size=end-position, reason=None)
                position = end
            window['available'] = len(values)
            window['order'] = ordered_ids + sorted(set(candidate_ids)-set(values))
            exact[name] = values
        windows[name] = window
    if panel:
        for sid in candidate_ids:
            if sid in exact['previous'] and sid in exact['current']:
                candidates[sid]['difference'] = _difference(exact['current'][sid], exact['previous'][sid])
    parameters = dict(target_snapshot_id=target_snapshot_id, cutoff=cutoff, rules=dict(RULES))
    refs = [{key:m[key] for key in ('symbol','snapshot_id','batch_id','query_id')} for m in members]
    identity = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, source_rule_version=peer.RULE_VERSION,
                    parameters=parameters, sources=refs, used_dates=dates, scope=SCOPE, events=[])
    n = len(members); available = sum(w['available'] for w in windows.values())
    report = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, source_rule_version=peer.RULE_VERSION,
        analysis_id=hashlib.sha256(peer._json(identity).encode()).hexdigest(), parameters=parameters,
        scope={k:dict(v) for k,v in SCOPE.items()}, events=[], used_dates=dates, anchor=anchor,
        members=members, candidates=[candidates[sid] for sid in candidate_ids], windows=windows,
        counts=dict(selected=n, candidates=n-1, source_qualified=sum(m['source_qualified'] for m in members),
                    panel_complete=sum(m['panel_complete'] for m in members)),
        source_panel_complete=panel, reasons=[] if panel else ['source_panel_unavailable'],
        status='complete' if available == 2*(n-1) else 'partial' if available else 'unavailable',
        limitations=dict(LIMITATIONS))
    if len(peer._json(report).encode('utf-8')) > MAX_RESULT_BYTES:
        raise ValueError('peer_neighbor_result_limit')
    return report
