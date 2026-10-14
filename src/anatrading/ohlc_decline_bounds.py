"""Exact maximum source-price decline over supplied OHLC-compatible paths.

The witnesses are hypothetical extremizers, never reconstructed market paths.
The adapter consumes an already trusted full-prefix query; it authenticates no
arbitrary dictionaries and cannot bound a real interval with missing bars.
"""
from collections import Counter
from copy import deepcopy
from math import gcd
import json
import re

from .numeric import NumericError, decimal_text, decimal_value
from .pair_research import symbol_identity
from .research_series import (
    MAX_RESEARCH_ROWS, _source_conflict, daily_bars, daily_coverage,
    source_rejection, strict_date,
)

_FIELDS = ('open', 'high', 'low', 'close')
_PATH_IDS = dict(lower='olhc-extremizer-v1', upper='ohlc-extremizer-v1')
_RESULTS = ('lower', 'upper', 'close_only', 'identified', 'ambiguity_width')
_SCOPE = 'supplied_bars_compatible_paths'


class DeclineBoundsError(NumericError):
    """Controlled whole-window rejection, with the first bad input location."""
    def __init__(self, code, bar_index=None, field=None):
        self.bar_index, self.field = bar_index, field
        super().__init__(code)


def _rational(n, d):
    common = gcd(n, d)
    return dict(numerator=str(n // common), denominator=str(d // common))


def _validated(bars):
    if not isinstance(bars, (list, tuple)) or not 1 <= len(bars) <= 253:
        raise DeclineBoundsError('invalid_ohlc_window')
    parsed = []
    for i, bar in enumerate(bars):
        if not isinstance(bar, (list, tuple)) or len(bar) != 4:
            raise DeclineBoundsError('invalid_ohlc_bar', i)
        values = []
        for field, value in zip(_FIELDS, bar):
            try:
                number = decimal_value(value)
            except NumericError as error:
                raise DeclineBoundsError(error.code, i, field) from error
            if number <= 0:
                raise DeclineBoundsError('nonpositive_price', i, field)
            _, digits, exponent = number.as_tuple()
            coefficient = 0
            for digit in digits:
                coefficient = coefficient * 10 + digit
            values.append((coefficient * 10**(exponent + 18), decimal_text(number)))
        o, h, l, c = (v[0] for v in values)
        if not l <= o <= h or not l <= c <= h:
            raise DeclineBoundsError('invalid_ohlc', i)
        parsed.append(values)
    return parsed


def _scan(bars, order, path_id=None):
    best_n, best_d, peak_value = 0, 1, 0
    peak = witness = None
    for i, bar in enumerate(bars):
        for slot_index, field in enumerate(order):
            value, text = bar[_FIELDS.index(field)]
            point = dict(bar_index=i, price_exact=text)
            if path_id is not None:
                point.update(slot=field, path_position=4*i+slot_index)
            if peak_value > value:
                n = peak_value-value
                if n*best_d > best_n*peak_value:
                    best_n, best_d = n, peak_value
                    witness = dict(peak=peak, trough=point)
                    if path_id is not None:
                        witness.update(path_id=path_id, hypothetical=True)
            if value > peak_value:
                peak_value, peak = value, point
    return dict(value=_rational(best_n, best_d), witness=witness), (best_n, best_d)


def exact_bounds(bars):
    """Validate 1..253 ordered positive O,H,L,C bars before any calculation."""
    parsed = _validated(bars)
    lower, (ln, ld) = _scan(parsed, ('open','low','high','close'), _PATH_IDS['lower'])
    upper, (un, ud) = _scan(parsed, _FIELDS, _PATH_IDS['upper'])
    close, _ = _scan(parsed, ('close',))
    return dict(lower=lower, upper=upper, close_only=close,
                identified=ln*ud == un*ld, ambiguity_width=_rational(un*ld-ln*ud, ud*ld),
                path_ids=dict(_PATH_IDS), scope=_SCOPE)


def _json_size(value, error):
    try:
        return len(json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
    except (TypeError, ValueError, UnicodeError, RecursionError):
        raise ValueError(error) from None


def _request(query, start, end):
    strict_date(start, 'invalid_research_date')
    strict_date(end, 'invalid_research_date')
    if start > end:
        raise ValueError('invalid_research_date')
    invalid = 'invalid_decline_query'
    if not isinstance(query, dict) or any(not isinstance(query.get(k), dict) for k in ('selection','metadata','manifest')):
        raise ValueError(invalid)
    if any(not isinstance(query.get(k), (list,tuple)) for k in ('rows','unlocated')):
        raise ValueError(invalid)
    if len(query['rows']) + len(query['unlocated']) > MAX_RESEARCH_ROWS:
        raise ValueError('research_row_limit')
    selection = query['selection']
    if selection.get('mode') != 'retrospective' or selection.get('cutoff') != end:
        raise ValueError(invalid)
    if selection.get('ordinal_start') is not None or selection.get('ordinal_end') is not None:
        raise ValueError('ordinal_window_not_supported')
    if query['metadata'].get('period') != '1d':
        raise ValueError('unsupported_period')
    refs = [query.get(k) for k in ('snapshot_id','batch_id','query_id')]
    refs.append(query['manifest'].get('source_contract_id'))
    try:
        if any(not isinstance(v,str) or not v or len(v.encode('utf-8')) > 256 for v in refs):
            raise ValueError(invalid)
    except UnicodeError:
        raise ValueError(invalid) from None
    raw_hash = query['manifest'].get('raw_sha256')
    if not isinstance(raw_hash,str) or re.fullmatch('[0-9a-f]{64}', raw_hash) is None:
        raise ValueError(invalid)
    counts = query.get('counts', {})
    if not isinstance(counts,dict):
        raise ValueError(invalid)
    batch_unlocated = counts.get('batch_unlocated_rows', 0)
    if type(batch_unlocated) is not int or batch_unlocated < 0:
        raise ValueError(invalid)
    def checks_ok(checks):
        return isinstance(checks,(list,tuple)) and all(isinstance(c,dict)
            and isinstance(c.get('name'),str) and isinstance(c.get('outcome'),str) for c in checks)
    if not checks_ok(query.get('batch_checks', ())):
        raise ValueError(invalid)
    for row in (*query['rows'], *query['unlocated']):
        if not isinstance(row,dict) or any(not isinstance(row.get(k,{}),dict) for k in ('values','tokens')):
            raise ValueError(invalid)
        if not checks_ok(row.get('checks', ())):
            raise ValueError(invalid)
    identity = {k: query[k] for k in ('snapshot_id','batch_id','query_id')}
    identity.update({k: query['manifest'][k] for k in ('raw_sha256','source_contract_id')})
    identity.update(selection={k: selection.get(k) for k in ('mode','cutoff','ordinal_start','ordinal_end')},
                    symbol_identity=symbol_identity(query),
                    source_qualification=query['manifest'].get('qualification'))
    if _json_size(identity, invalid) > 16*1024:
        raise ValueError('ohlc_metadata_limit')
    return deepcopy(identity)


def decline_bounds_report(query, start_date, end_date):
    """One exact-date window from a trusted retrospective full daily prefix.

    Global source conflicts and unknown date coverage close the whole report;
    ordinary invalid dated groups close only windows containing those groups.
    Existing helpers classify their first reason, not concurrent predicates.
    """
    identity = _request(query, start_date, end_date)
    bars = daily_bars(query)
    coverage = daily_coverage(query, bars)
    window = [b for b in bars if start_date <= b['date'] <= end_date]
    if len(window) > 253:
        raise ValueError('ohlc_window_limit')
    days = {b['date'] for b in window}
    missing = list(dict.fromkeys(d for d in (start_date,end_date) if d not in days))
    conflicts = Counter()
    for row in (*query['rows'], *query['unlocated']):
        conflict = _source_conflict(row, query['metadata'])
        if conflict:
            conflicts[conflict] += 1
    rejected = source_rejection(query)
    reasons = ([rejected] if rejected else []) + list(conflicts)
    unknown = not coverage['coverage_known'] or coverage['unreadable_date_rows'] > 0
    if unknown:
        reasons.append('source_coverage_unknown')
    if missing:
        reasons.append('endpoint_not_present')
    members, invalid, seen_ordinals = [], [], set()
    for i, bar in enumerate(window):
        ordinal = bar['ordinal']
        ordinal_valid = type(ordinal) is int and 0 <= ordinal <= 2**63-1
        reason = bar['reason']
        if reason is None and (not ordinal_valid or ordinal in seen_ordinals):
            reason = 'invalid_source_ordinal'
        if ordinal_valid:
            seen_ordinals.add(ordinal)
        member = dict(index=i, date=bar['date'], ordinal=str(ordinal) if ordinal_valid else None,
                      **{k: decimal_text(bar[k]) if bar[k] is not None else None for k in _FIELDS},
                      source_reason=reason)
        members.append(member)
        if reason is not None:
            invalid.append(dict(index=i,date=bar['date'],ordinal=member['ordinal'],reason=reason))
    if invalid:
        reasons.append('invalid_window')
        reasons.extend(m['reason'] for m in invalid)
    reasons = list(dict.fromkeys(reasons))
    reason = rejected or next(iter(conflicts), None) or ('source_coverage_unknown' if unknown else
             'endpoint_not_present' if missing else 'invalid_window' if invalid else None)
    result = dict.fromkeys(_RESULTS) if reason else exact_bounds([tuple(m[k] for k in _FIELDS) for m in members])
    if not reason:
        for key in ('lower','upper','close_only'):
            witness = result[key]['witness']
            if witness:
                for endpoint in ('peak','trough'):
                    point = witness[endpoint]
                    member = members[point['bar_index']]
                    point.update(date=member['date'],ordinal=member['ordinal'])
    report = dict(method_id='source-ohlc-compatible-max-decline-v1',
        adapter_id='daily-bars-positive-selected-window-strict-coverage-v1',
        numeric_policy_id='scaled18-rational-earliest-extremizer-v1',
        identity=identity, window=dict(requested_start=start_date,requested_end=end_date,
            resolved_start=start_date if start_date in days else None,
            resolved_end=end_date if end_date in days else None,bar_count=len(window),first_open_initialization=True),
        coverage=coverage, source_qualification=deepcopy(identity['source_qualification']),
        calendar_completeness='unverified', members=members,
        price_evidence='normalized_source_values',raw_token_status='not_embedded',
        status='unavailable' if reason else 'computed',reason=reason,reasons=reasons,
        invalid_members=invalid,missing_endpoints=missing,source_rejected=bool(rejected),
        source_conflict_counts=dict(conflicts),source_conflict_policy='first_rejection_per_source_row',
        suppressed_source_predicates='not_evaluated_after_first_rejection',
        limitations=['hypothetical_extremizers','window_pre_history_excluded','calendar_and_bar_finality_unverified',
            'adjustment_and_corporate_actions_unverified','historical_availability_unverified',
            'source_values_not_economic_wealth','upper_not_full_real_interval_bound_if_observations_missing',
            'no_prediction_or_execution_claim'], **result)
    report.update(scope=_SCOPE, path_ids=dict(_PATH_IDS))
    if _json_size(report, 'invalid_decline_query') > 256*1024:
        raise ValueError('ohlc_result_limit')
    return report
