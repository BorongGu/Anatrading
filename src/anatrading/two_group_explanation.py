"""Bounded all-member, leave-target-out source log explanations (043).

Only complete trusted Store queries enter here. No acquisition, price replacement,
calendar certification, prediction, or generalized numerical framework.
"""
from collections import Counter
from decimal import Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
import hashlib
import math

from . import peer_relative_research as peer
from .research_series import strict_date

METHOD_ID = 'two-group-frozen-source-v1'
RULE_VERSION = 'decimal80-qr2-reference-v1'
MAX_RESULT_BYTES = 2 * 1024 * 1024
RULES = dict(training_intervals=60, decimal_precision=80, rounding='ROUND_HALF_EVEN',
             sd_min=1e-12, rank_min=1e-10, rank_gray=1e-12,
             tolerance_absolute=1e-10, tolerance_relative=1e-8,
             exclusion='each_target_from_own_group_train_and_current', unit='source_log_change')
ERRORS = {'invalid_groups', 'invalid_dates', 'member_limit', 'duplicate_member',
          'explanation_result_limit', 'invalid_events', 'universe_row_limit',
          'invalid_query', 'research_row_limit'}
LIMITATIONS = dict(trading_calendar='unknown', historical_availability='unverified',
                   membership='current_members_retrospective', source_semantics='unverified',
                   adjustment='request_declared_semantics_unverified', corporate_action_coverage='unknown',
                   economic_return_qualified=False, predictive_advantage='not_evaluated',
                   residuals='mutually_dependent_not_noise_or_probability', risk_standardized=False)
SCOPE = {key: dict(value=value, evidence_status='assumed') for key, value in
         dict(asset_type='stock', share_class='A_share', price_currency='CNY',
              daily_label_basis='CN_exchange_date').items()}


def _float(value):
    result = float(value)
    if not math.isfinite(result) or value != 0 and result == 0:
        raise ValueError('numerical_unstable')
    return result


def _log(left, right):
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        result = Decimal(0) if left == right else (right / left).ln()
        _float(result)
        return result


def _dot(left, right):
    return math.fsum(a * b for a, b in zip(left, right))


def _fit(target, factors):
    """60 training + one current value; each factor excludes this target."""
    with localcontext() as context:
        context.prec = 80
        context.rounding = ROUND_HALF_EVEN
        n = Decimal(60)
        mean_y = sum(target[:60], Decimal(0)) / n
        means = [sum(f[:60], Decimal(0)) / n for f in factors]
        centered = [[value - mean for value in f[:60]] for f, mean in zip(factors, means)]
        scales = [(sum((v*v for v in col), Decimal(0)) / n).sqrt() for col in centered]
        if any(sd <= Decimal('1e-12') for sd in scales):
            raise ValueError('factor_scale_too_small')
        z = [[_float(v/sd) for v in col] for col, sd in zip(centered, scales)]
        current = [_float((f[60]-mean)/sd) for f, mean, sd in zip(factors, means, scales)]
        y = [_float(v-mean_y) for v in target[:60]]
        r11 = math.sqrt(_dot(z[0], z[0]))
        q1 = [v/r11 for v in z[0]]
        r12 = _dot(q1, z[1])
        work = [v-r12*q for v, q in zip(z[1], q1)]
        correction = _dot(q1, work)
        r12 += correction
        work = [v-correction*q for v, q in zip(work, q1)]
        r22 = math.sqrt(_dot(work, work))
        scale = max(abs(r11), abs(r12), abs(r22))
        a, b, d = r11/scale, r12/scale, r22/scale
        # Largest singular value of triangular 2x2: no subtractive eigenvalue gap.
        smax = (math.hypot(a+d, b) + math.hypot(a-d, b))/2
        rank = abs(a*d)/(smax*smax)
        if not math.isfinite(rank) or rank <= 1e-10 or abs(rank-1e-10) <= 1e-12:
            raise ValueError('factor_rank_unavailable')
        q2 = [v/r22 for v in work]
        gamma_b = _dot(q2, y)/r22
        gamma_a = (_dot(q1, y)-r12*gamma_b)/r11
        baseline = _float(mean_y)
        contributions = [gamma_a*current[0], gamma_b*current[1]]
        prediction = math.fsum([baseline, *contributions])
        raw = _float(target[60])
        residual = math.fsum([raw, -prediction])
        # Independent high precision centered normal equations, only two columns.
        u, v = centered
        yc = [value-mean_y for value in target[:60]]
        aa = sum((x*x for x in u), Decimal(0))
        ab = sum((x*y for x, y in zip(u, v)), Decimal(0))
        bb = sum((x*x for x in v), Decimal(0))
        ay = sum((x*y for x, y in zip(u, yc)), Decimal(0))
        by = sum((x*y for x, y in zip(v, yc)), Decimal(0))
        determinant = aa*bb-ab*ab
        if determinant <= 0:
            raise ValueError('numerical_unstable')
        beta_a, beta_b = (ay*bb-by*ab)/determinant, (by*aa-ay*ab)/determinant
        reference = mean_y + beta_a*(factors[0][60]-means[0]) + beta_b*(factors[1][60]-means[1])
        ref_pred, ref_res = _float(reference), _float(target[60]-reference)
        tolerance = 1e-10 + 1e-8*max(abs(raw), abs(ref_pred), abs(ref_res))
        values = [baseline, *contributions, prediction, residual, gamma_a, gamma_b, *current, tolerance]
        if not all(math.isfinite(value) for value in values) or max(abs(prediction-ref_pred), abs(residual-ref_res)) > tolerance:
            raise ValueError('numerical_unstable')
        return dict(baseline=baseline, contributions=contributions, explained=prediction, residual=residual,
                    gamma=[gamma_a, gamma_b], factor_mean=[_float(v) for v in means],
                    factor_sd=[_float(v) for v in scales], current_factor=[_float(f[60]) for f in factors],
                    current_z=current, rank_ratio=rank, tolerance=tolerance,
                    within_resolution=abs(residual) <= tolerance)


def _groups(queries, groups):
    ids = [query['snapshot_id'] for query in queries]
    if type(groups) is not dict or set(groups) != {'A', 'B'}:
        raise ValueError('invalid_groups')
    if any(type(g) is not list or len(g) < 2 or any(type(i) is not str for i in g) for g in groups.values()):
        raise ValueError('invalid_groups')
    combined = groups['A'] + groups['B']
    if len(set(combined)) != len(combined) or set(combined) != set(ids):
        raise ValueError('invalid_groups')
    return {key: sorted(value) for key, value in groups.items()}


def two_group_report(queries, groups, current_start, current_end, *, events=None):
    if type(queries) not in (list, tuple) or not 4 <= len(queries) <= peer.MAX_MEMBERS:
        raise ValueError('member_limit')
    if any(type(q) is not dict or type(q.get('rows')) not in (list, tuple) or
           type(q.get('unlocated')) not in (list, tuple) for q in queries):
        raise ValueError('invalid_query')
    sizes = [len(q['rows'])+len(q['unlocated']) for q in queries]
    if max(sizes) > peer.MAX_SOURCE_ROWS:
        raise ValueError('research_row_limit')
    if sum(sizes) > peer.MAX_TOTAL_ROWS:
        raise ValueError('universe_row_limit')
    b, c = strict_date(current_start, 'invalid_dates'), strict_date(current_end, 'invalid_dates')
    if b >= c:
        raise ValueError('invalid_dates')
    groups = _groups(queries, groups)
    sources, days, global_reasons = [], set(), set()
    identities = set()
    for query in queries:
        source_error = None
        try:
            identity = peer._source(query)  # 030 remains unchanged.
        except ValueError as error:
            source_error = str(error)
            global_reasons.add(source_error)
            # Trust only enough identity to retain the selected row; no source
            # arithmetic or row scan is allowed after failed qualification.
            identity = dict(symbol=query.get('metadata', {}).get('source_code', query['snapshot_id']))
        if identity['symbol'] in identities:
            raise ValueError('duplicate_member')
        identities.add(identity['symbol'])
        slots, issues = {}, []
        for rows in (() if source_error else (query['rows'], query['unlocated'])):
            for row in rows:
                day, located = peer._position(row)
                failed = peer._checks(row['checks'])
                codes = set(failed)
                if day is None:
                    global_reasons.add('endpoint_integrity_unknown')
                    codes.add('endpoint_integrity_unknown')
                else:
                    days.add(day)
                    slots.setdefault(day, []).append((row, located))
                if not located:
                    codes.add('unlocated_label')
                if peer._row_conflict(row, failed, identity):
                    codes.add('local_source_conflict')
                if (failed & (peer._IDENTITY | peer._ADJUSTMENT | {'structure', 'known_negative_sample'})
                        or any(row['tokens'].get(key) in peer._ADJUSTED for key in
                               ('adjustflag', 'source_adjustment') if type(row['tokens'].get(key)) is str)):
                    codes.add('global_source_conflict')
                    global_reasons.add('global_source_conflict')
                if failed - peer._KNOWN_CHECKS:
                    codes.add('unclassified_source_failure')
                if codes:
                    issues.append((day, row['ordinal'], sorted(codes)))
        sources.append((query, identity, slots, issues, source_error))
    ordered = sorted(days)
    training = [day for day in ordered if day <= b][-61:]
    if len(training) != 61 or not training or training[-1] != b:
        global_reasons.add('training_window_incomplete')
    if b not in days or c not in days or any(b < day < c for day in days):
        global_reasons.add('current_interval_not_adjacent')
    used = training + [c]
    first = training[0] if training else b
    # Reuse the descriptor's bounded explicit event validator over the whole used span.
    identity_map = {identity['symbol']: dict(symbol=identity['symbol'], snapshot_id=q['snapshot_id'], query_id=q['query_id'])
                    for q, identity, _, _, _ in sources}
    descriptor = dict(schema_version=1, group_name='Explicit A/B', group_axis='explicit_sample', selection_date=c,
                      membership='current_members_retrospective', selection_basis='user_explicit_groups', scope=SCOPE,
                      evidence_refs=[dict(source_id='explicit-request', version='1', declared_by='user_declaration')],
                      members=list(identity_map.values()), events=events if events is not None else [])
    descriptor = peer._descriptor(descriptor, identity_map, next(iter(identity_map)), first, c)
    members, matrix = [], {}
    source_complete = 0
    for query, identity, slots, issues, source_error in sources:
        reasons, endpoints, closes = ({source_error} if source_error else set()), [], []
        examples, counts, issue_count = [], Counter(), 0
        for day, ordinal, codes in issues:
            scope = 'unknown' if day is None else 'inside_interval' if first <= day <= c else 'outside_interval'
            if 'global_source_conflict' in codes:
                reasons.add('global_source_conflict')
            if scope != 'outside_interval':
                reasons.update(set(codes) & {'local_source_conflict', 'unclassified_source_failure', 'endpoint_integrity_unknown'})
            counts.update(codes)
            issue_count += 1
            if len(examples) < 20:
                examples.append(dict(date=day, ordinal=ordinal, scope=scope, codes=codes))
        for day in used:
            endpoint, close = peer._endpoint(day, slots.get(day, []))
            endpoints.append(endpoint)
            closes.append(close)
            reasons.update(endpoint['reasons'])
        for event in descriptor['events']:
            if event['symbol'] != identity['symbol']:
                continue
            if event['kind'] == 'corporate_action_unresolved':
                reasons.add('corporate_action_unresolved')
            elif event['kind'] == 'halt' and any(event['start_date'] <= day <= event['end_date'] for day in used):
                reasons.add('halted_endpoint_source_value')
        start, left = peer._endpoint(b, slots.get(b, []))
        end, right = peer._endpoint(c, slots.get(c, []))
        current_conflict = any((day is None or day in (b, c)) and
                               set(codes) & {'local_source_conflict', 'unclassified_source_failure', 'endpoint_integrity_unknown'}
                               for day, _, codes in issues)
        raw = (_float(_log(left, right)) if left is not None and right is not None
               and not current_conflict and not source_error and 'global_source_conflict' not in reasons else None)
        complete = not reasons and len(training) == 61 and training[-1] == b
        if complete:
            source_complete += 1
            matrix[query['snapshot_id']] = [_log(l, r) for l, r in zip(closes, closes[1:])]
        global_reasons.update(reasons)
        members.append(dict(symbol=identity['symbol'], snapshot_id=query['snapshot_id'], query_id=query['query_id'],
                            group='A' if query['snapshot_id'] in groups['A'] else 'B',
                            endpoints=dict(start=start, end=end), training_endpoints=endpoints,
                            raw_change=raw, source_complete=complete, model=None, reasons=sorted(reasons),
                            anomalies=dict(total=issue_count, counts=dict(counts), examples=examples, truncated=issue_count>20)))
    if not global_reasons and source_complete == len(members):
        symbol_by_id = {m['snapshot_id']: m['symbol'] for m in members}
        with localcontext() as context:
            context.prec = 80
            context.rounding = ROUND_HALF_EVEN
            for member in members:
                sid = member['snapshot_id']
                factors = []
                for key in ('A', 'B'):
                    peers = sorted((i for i in groups[key] if i != sid), key=lambda i: symbol_by_id[i])
                    factors.append([sum((matrix[i][t] for i in peers), Decimal(0))/len(peers) for t in range(61)])
                try:
                    member['model'] = _fit(matrix[sid], factors)
                except (ArithmeticError, DecimalException, ValueError) as error:
                    code = str(error)
                    member['reasons'] = [code if code in {'factor_scale_too_small', 'factor_rank_unavailable'} else 'numerical_unstable']
    else:
        for member in members:
            member['reasons'] = sorted(set(member['reasons']) | {'source_panel_unavailable'})
    parameters = dict(groups=groups, current_start=b, current_end=c, rules=RULES)
    identity_input = dict(method_id=METHOD_ID, rule_version=RULE_VERSION,
                          parameters={key: value for key, value in parameters.items() if key != 'rules'},
                          numerical_protocol={key: str(value) for key, value in RULES.items()},
                          sources=sorted(identity_map.values(), key=lambda m: m['symbol']), scope=SCOPE, events=descriptor['events'])
    available = sum(m['model'] is not None for m in members)
    report = dict(method_id=METHOD_ID, rule_version=RULE_VERSION,
                  analysis_id=hashlib.sha256(peer._json(identity_input).encode()).hexdigest(),
                  parameters=parameters, scope=SCOPE, events=descriptor['events'], training_dates=training,
                  members=members, counts=dict(selected=len(members), source_complete=source_complete, model_available=available),
                  status='unavailable' if available == 0 else 'complete' if available == len(members) else 'partial',
                  reasons=sorted(global_reasons), limitations=LIMITATIONS)
    if len(peer._json(report).encode('utf-8')) > MAX_RESULT_BYTES:
        raise ValueError('explanation_result_limit')
    return report
