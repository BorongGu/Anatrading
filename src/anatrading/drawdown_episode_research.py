"""Bounded observed source-price episodes on an all-member identical daily grid.

Window indices count source intervals. No calendar, economic-return or forecast
qualification is inferred. Source qualification helpers remain unchanged.
"""
from collections import Counter
from fractions import Fraction
import hashlib
import json
import re

from . import peer_relative_research as peer
from .pair_research import symbol_identity
from .research_series import strict_date

METHOD_ID = 'observed-drawdown-episodes-v1'
RULE_VERSION = 'all-member-grid-last-peak-first-valley-exact-v1'
MAX_RESULT_BYTES = 2 * 1024 * 1024
SUMMARY_KEYS = ('episode_count', 'recovered_count', 'open_count', 'deepest', 'longest_observed', 'current_open')
LIMITATIONS = dict(window_preceding_peak='unknown', trading_calendar='unknown',
    adjustment='request_declared_semantics_unverified', corporate_action_coverage='unknown',
    historical_availability='unverified', membership='current_members_retrospective',
    economic_return_qualified=False, recovery_prediction='not_provided',
    current_open_depth='deepest_so_far', interval_unit='source_interval')
ERRORS = peer.GROUP_ERRORS | {'invalid_lookback', 'drawdown_integer_limit',
    'drawdown_price_invalid', 'drawdown_ordinal_limit', 'drawdown_result_limit', 'research_market_mismatch'}


def serialize_report(report):
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')
    if len(encoded) > MAX_RESULT_BYTES:
        raise ValueError('drawdown_result_limit')
    return encoded


def _bounded(value):
    if abs(value).bit_length() > 256:
        raise ValueError('drawdown_integer_limit')
    return value


def _price_integer(value):
    if (type(value) is not str or len(value) > 39
            or re.fullmatch(r'(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?', value) is None):
        raise ValueError('drawdown_price_invalid')
    whole, _, fraction = value.partition('.')
    result = int(whole) * 10**18 + int(fraction.ljust(18, '0'))
    if not 1 <= result < 10**38:
        raise ValueError('drawdown_price_invalid')
    return result


def _display(numerator, denominator):
    quotient, remainder = divmod(_bounded(numerator * 10**6), denominator)
    if 2 * remainder > denominator or 2 * remainder == denominator and quotient % 2:
        quotient += 1
    return '小于0.0001%' if not quotient else f'{quotient // 10000}.{quotient % 10000:04d}%'


def _episode(points, prices, peak, valley, recovery):
    end = len(points)-1 if recovery is None else recovery
    fraction = Fraction(prices[peak]-prices[valley], prices[peak])
    return dict(peak=points[peak], valley=points[valley],
        recovery=None if recovery is None else points[recovery], observed_end=points[end],
        depth_fraction=dict(numerator=str(fraction.numerator), denominator=str(fraction.denominator)),
        depth_display=_display(fraction.numerator, fraction.denominator),
        status='open' if recovery is None else 'recovered',
        peak_to_valley_intervals=valley-peak,
        peak_to_recovery_intervals=None if recovery is None else recovery-peak,
        valley_to_recovery_intervals=None if recovery is None else recovery-valley,
        observed_intervals=end-peak, observed_is_lower_bound=recovery is None,
        underwater_observations=end-peak if recovery is None else recovery-peak-1)


def _deeper(left, right):
    a, b = left['depth_fraction'], right['depth_fraction']
    return _bounded(int(a['numerator'])*int(b['denominator'])) > _bounded(int(b['numerator'])*int(a['denominator']))


def summarize(points):
    """One bounded online scan; only the open episode and two leaders survive."""
    if not 3 <= len(points) <= 253:
        raise ValueError('invalid_lookback')
    prices = [_price_integer(p['close_exact']) for p in points]
    count = recovered = 0
    deepest = longest = current = None
    peak, valley = 0, None

    def select(episode):
        nonlocal deepest, longest
        # Scan order is increasing peak index, so strict comparison retains ties.
        if deepest is None or _deeper(episode, deepest):
            deepest = episode
        if longest is None or episode['observed_intervals'] > longest['observed_intervals']:
            longest = episode

    for index in range(1, len(points)):
        if valley is None:
            if prices[index] >= prices[peak]:
                peak = index
            else:
                valley = index
                count += 1
        elif prices[index] >= prices[peak]:
            select(_episode(points, prices, peak, valley, index))
            recovered += 1
            peak, valley = index, None
        elif prices[index] < prices[valley]:
            valley = index
    if valley is not None:
        current = _episode(points, prices, peak, valley, None)
        select(current)
    return dict(episode_count=count, recovered_count=recovered, open_count=int(current is not None),
                deepest=deepest, longest_observed=longest, current_open=current)


def _scan(query, identity):
    slots, issues, global_reasons = {}, [], set()
    for row in (*query['rows'], *query['unlocated']):
        day, located = peer._position(row)
        failed = peer._checks(row['checks'])
        codes = set(failed)
        if day is None:
            codes.add('endpoint_integrity_unknown')
            global_reasons.add('endpoint_integrity_unknown')
        else:
            slots.setdefault(day, []).append((row, located))
        if not located:
            codes.add('unlocated_label')
        if peer._row_conflict(row, failed, identity):
            codes.add('local_source_conflict')
        global_conflict = bool(failed & (peer._IDENTITY | peer._ADJUSTMENT | {'structure', 'known_negative_sample'}))
        global_conflict |= any(type(row['tokens'].get(k)) is str and row['tokens'][k] in peer._ADJUSTED
                               for k in ('adjustflag', 'source_adjustment'))
        for key in ('code', 'source_code'):
            if row['tokens'].get(key) is not None:
                try:
                    observed = symbol_identity({'metadata': {'source_code': row['tokens'][key], 'source_venue': identity['venue']}})
                    global_conflict |= observed['symbol'] != identity['symbol']
                except ValueError:
                    global_conflict = True
        if global_conflict:
            codes.add('global_source_conflict')
            global_reasons.add('global_source_conflict')
        if failed - peer._KNOWN_CHECKS:
            codes.add('unclassified_source_failure')
        if codes:
            issues.append((day, str(row['ordinal']), sorted(codes)))
    return slots, issues, global_reasons


def _window(member, query, identity, cutoff, lookback):
    slots, issues, reasons = _scan(query, identity)
    days = sorted(day for day in slots if day <= cutoff)[-(lookback+1):]
    cutoff_present = cutoff in slots
    if not cutoff_present:
        reasons.add('cutoff_missing')
    if len(days) != lookback+1:
        reasons.add('history_insufficient')
    # Merge newly assessed endpoint failures with decoder checks by source row.
    # A row remains one anomaly even when several independent checks fail.
    assessed = {ordinal: (day, set(codes)) for day, ordinal, codes in issues}
    endpoints = []
    for index, day in enumerate(days):
        endpoint, price = peer._endpoint(day, slots[day])
        reasons.update(endpoint['reasons'])
        if endpoint['reasons']:
            for row, _ in slots[day]:
                ordinal = str(row['ordinal'])
                assessed.setdefault(ordinal, (day, set()))[1].update(endpoint['reasons'])
        if price is not None:
            endpoints.append(dict(index=index, date=day, ordinal=str(endpoint['ordinal']), close_exact=endpoint['close_exact']))
    counts, examples = Counter(), []
    for ordinal, (day, codes) in sorted(assessed.items(), key=lambda item: int(item[0])):
        inside = day is not None and bool(days) and days[0] <= day <= cutoff
        if inside or day is None:
            reasons.update(codes & {'local_source_conflict', 'unclassified_source_failure', 'endpoint_integrity_unknown'})
        counts.update(codes)
        if len(examples) < 20:
            examples.append(dict(date=day, ordinal=ordinal, scope='unknown' if day is None else 'inside_interval' if inside else 'outside_interval', codes=sorted(codes)))
    qualified = not reasons
    member.update(window_qualified=qualified, date_array=days, window_length=len(days),
        cutoff_present=cutoff_present, endpoints=endpoints if qualified else None, reasons=sorted(reasons),
        anomalies=dict(total=len(assessed), counts=dict(sorted(counts.items())), examples=examples,
                       examples_truncated=len(assessed)>20))


def drawdown_episode_report(queries, cutoff, lookback):
    if type(queries) not in (list, tuple) or not 2 <= len(queries) <= peer.MAX_MEMBERS:
        raise ValueError('member_limit')
    if type(lookback) is not int or not 2 <= lookback <= 252:
        raise ValueError('invalid_lookback')
    cutoff = strict_date(cutoff, 'invalid_dates')
    if any(type(q) is not dict or type(q.get('rows')) not in (list, tuple)
           or type(q.get('unlocated')) not in (list, tuple) for q in queries):
        raise ValueError('invalid_query')
    sizes = [len(q['rows'])+len(q['unlocated']) for q in queries]
    if max(sizes) > peer.MAX_SOURCE_ROWS:
        raise ValueError('research_row_limit')
    if sum(sizes) > peer.MAX_TOTAL_ROWS:
        raise ValueError('universe_row_limit')
    for query in queries:
        peer._group_structure(query)
        if any(row['ordinal'] >= 10**20 for row in (*query['rows'], *query['unlocated'])):
            raise ValueError('drawdown_ordinal_limit')
    if len({q['snapshot_id'] for q in queries}) != len(queries):
        raise ValueError('duplicate_member')
    members, symbols, markets = [], set(), set()
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
        if identity is not None:
            if identity['symbol'] in symbols:
                raise ValueError('duplicate_member')
            symbols.add(identity['symbol'])
            markets.add(identity['market'])
        member = dict(snapshot_id=query['snapshot_id'], batch_id=query['batch_id'], query_id=query['query_id'],
            symbol=identity['symbol'] if identity else None, source_qualified=refusal is None,
            window_qualified=False, comparison_available=False, date_array=None, window_length=None,
            cutoff_present=None, endpoints=None, reasons=[refusal] if refusal else [], anomalies=None,
            **{key: None for key in SUMMARY_KEYS})
        if refusal is None:
            _window(member, query, identity, cutoff, lookback)
        members.append(member)
    if len(markets) > 1:
        raise ValueError('research_market_mismatch')
    complete = all(m['window_qualified'] for m in members)
    # No member is designated the target. Every full array must agree.
    grids = {tuple(m['date_array']) for m in members if m['window_qualified']}
    if len(grids) > 1:
        for member in members:
            if member['window_qualified']:
                member['reasons'].append('date_grid_mismatch')
    available = complete and len(grids) == 1
    for member in members:
        member['comparison_available'] = available
        if available:
            member.update(summarize(member['endpoints']))
    parameters = dict(cutoff=cutoff, lookback=lookback)
    identity_input = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, source_rule_version=peer.RULE_VERSION,
        parameters=parameters, sources=[{k: m[k] for k in ('snapshot_id', 'batch_id', 'query_id', 'date_array')} for m in members])
    report = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, source_rule_version=peer.RULE_VERSION,
        analysis_id=hashlib.sha256(peer._json(identity_input).encode('utf-8')).hexdigest(), parameters=parameters,
        comparison_available=available, dates=list(next(iter(grids))) if available else None,
        counts=dict(selected=len(members), source_qualified=sum(m['source_qualified'] for m in members),
                    window_qualified=sum(m['window_qualified'] for m in members), computable=len(members) if available else 0),
        members=members, limitations=dict(LIMITATIONS))
    serialize_report(report)
    return report
