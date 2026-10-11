"""Bounded, eager three-valued conditions on existing source-price facts.

No expression execution, Store access or independent price validation lives here.
The source-date gate is deliberately separate from both logic and economic trust.
"""
from fractions import Fraction
import json
import math
import re

from .numeric import decimal_text, decimal_value
from .research_series import source_rejection, strict_date
from .store import _identity, _json
from .universe_research import _universe_evaluation


METHOD_ID = 'selected-source-price-filter-v1'
RULE_BYTE_LIMIT = 2048
POLICIES = dict(rule_schema='bounded-price-filter-v1', window='daily-source-date-groups-v1',
                logic='strong-kleene-eager-v1', comparison='fraction-and-binary64-v1',
                source_gate='source-date-locatability-v1')
_FIELDS = {'momentum': ('gte', '-1', '10'), 'volatility': ('lte', '0', '1'),
           'max_drawdown': ('gte', '-1', '0')}
_THRESHOLD = re.compile(r'-?(0|[1-9][0-9]?)(\.[0-9]{1,18})?')
_METADATA = ('period', 'source', 'source_code', 'source_venue', 'source_symbol',
             'requested_symbol', 'requested_adjustment', 'capture_version', 'capture_mode',
             'header_cardinality', 'transport_evidence', 'provenance_hash_verification',
             'interpretation_status', 'source_claims_status')
_SEMANTICS = ('price_unit', 'adjustment', 'label_definition', 'closed', 'known_at', 'first_published_at')
_CONTRACT_FIELDS = ('source_contract_id', 'format_id', 'contract_version', 'versions',
                    'semantics_scope', 'semantics')
_LIMITATIONS = ['retrospective_source_version', 'adjustment_basis_unverified',
               'historical_availability_unverified', 'calendar_and_bar_closure_unverified',
               'descriptive_estimates_not_trading_returns', 'current_selected_membership',
               'source_identity_not_security_master_verified']
FILTER_ERRORS = frozenset({'invalid_filter_rule', 'filter_rule_limit', 'unsupported_filter_field',
                          'invalid_filter_operator', 'invalid_filter_threshold',
                          'duplicate_filter_field', 'duplicate_filter_group'})


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('invalid_filter_rule')
        result[key] = value
    return result


def _constant(value):
    raise ValueError('invalid_filter_rule')


def parse_rule(text):
    if not isinstance(text, str):
        raise ValueError('invalid_filter_rule')
    try:
        size = len(text.encode('utf-8'))
    except UnicodeError:
        raise ValueError('invalid_filter_rule') from None
    if size > RULE_BYTE_LIMIT:
        raise ValueError('filter_rule_limit')
    try:
        rule = json.loads(text, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, RecursionError):
        raise ValueError('invalid_filter_rule') from None
    return normalize_rule(rule)


def normalize_rule(rule):
    if type(rule) is not dict or set(rule) != {'any_of'} or type(rule['any_of']) is not list or not rule['any_of']:
        raise ValueError('invalid_filter_rule')
    if len(rule['any_of']) > 2:
        raise ValueError('filter_rule_limit')
    groups = []
    for group in rule['any_of']:
        if type(group) is not dict or set(group) != {'all_of'} or type(group['all_of']) is not list or not group['all_of']:
            raise ValueError('invalid_filter_rule')
        if len(group['all_of']) > 3:
            raise ValueError('filter_rule_limit')
        atoms, seen = [], set()
        for atom in group['all_of']:
            if type(atom) is not dict or set(atom) != {'field', 'op', 'threshold'}:
                raise ValueError('invalid_filter_rule')
            field, op, threshold = atom['field'], atom['op'], atom['threshold']
            if not isinstance(field, str) or field not in _FIELDS:
                raise ValueError('unsupported_filter_field')
            if op != _FIELDS[field][0]:
                raise ValueError('invalid_filter_operator')
            if field in seen:
                raise ValueError('duplicate_filter_field')
            seen.add(field)
            if not isinstance(threshold, str) or len(threshold) > 22 or _THRESHOLD.fullmatch(threshold) is None:
                raise ValueError('invalid_filter_threshold')
            try:
                number = decimal_value(threshold)
                if not decimal_value(_FIELDS[field][1]) <= number <= decimal_value(_FIELDS[field][2]):
                    raise ValueError()
            except ValueError:
                raise ValueError('invalid_filter_threshold') from None
            atoms.append(dict(field=field, op=op, threshold=decimal_text(number)))
        groups.append(dict(all_of=sorted(atoms, key=lambda a: (a['field'], a['op'], a['threshold']))))
    if len({_json(group) for group in groups}) != len(groups):
        raise ValueError('duplicate_filter_group')
    return dict(any_of=sorted(groups, key=_json))


def _combine(op, values):
    # Values are already materialized; explicit enum comparisons are essential.
    if op == 'all':
        return 'false' if 'false' in values else 'unknown' if 'unknown' in values else 'true'
    if op == 'any':
        return 'true' if 'true' in values else 'unknown' if 'unknown' in values else 'false'
    raise RuntimeError('filter_internal_operator')


def _compare(value, op, threshold):
    if op == 'gte':
        return 'true' if value >= threshold else 'false'
    if op == 'lte':
        return 'true' if value <= threshold else 'false'
    raise RuntimeError('filter_internal_operator')


def _present(mapping, name):
    return dict(present=name in mapping, value=mapping.get(name))


def _source(query, identity):
    metadata, manifest = query.get('metadata', {}), query.get('manifest', {})
    contract = manifest.get('contract', {})
    semantics = contract.get('source_semantics', {})
    fields = semantics.get('fields', {})
    result = dict(snapshot_id=query['snapshot_id'], query_id=query['query_id'], identity=identity,
                  raw_sha256=_present(manifest, 'raw_sha256'), source_contract_id=_present(manifest, 'source_contract_id'),
                  format_id=_present(contract, 'format_id'), contract_version=_present(contract, 'version'),
                  versions=_present(manifest, 'versions'), metadata={key: _present(metadata, key) for key in _METADATA},
                  semantics_scope=_present(semantics, 'scope'), semantics={
                      name: {key: _present(fields.get(name, {}), key)
                             for key in ('value', 'status', 'reason', 'applicability')}
                      for name in _SEMANTICS})
    return dict(result, id=_identity(result))


def _share_contracts(sources):
    """Share only this fixed, exactly equal projection within one response."""
    contracts = {}
    for source in sources:
        projection = {key: source.pop(key) for key in _CONTRACT_FIELDS}
        key = _identity(projection)
        contracts[key] = dict(projection, id=key)
        source['contract_ref'] = key
    return [contracts[key] for key in sorted(contracts)]


def _point(bar):
    if bar is None:
        return None
    return dict(date=bar['date'], ordinal=bar['ordinal'],
                close=None if bar['close'] is None else decimal_text(bar['close']))


def _facts(row, evidence):
    result = {}
    for field in _FIELDS:
        value, reason = row[field], row[field + '_reason']
        if (value is None) != (reason is not None) or value is not None and not math.isfinite(value):
            raise RuntimeError('filter_internal_fact')
        exact = evidence.get(field) if value is not None and field != 'volatility' else None
        if value is not None and field != 'volatility' and (exact is None or float(exact) != value):
            raise RuntimeError('filter_internal_exact_fact')
        result[field] = dict(value=value, reason=reason,
                             comparison_type='float64_estimate' if field == 'volatility' else 'source_fraction',
                             exact=None if exact is None else dict(numerator=str(exact.numerator), denominator=str(exact.denominator)))
        if field == 'volatility':
            result[field].update(estimate_text=None if value is None else repr(value),
                                 float_hex=None if value is None else value.hex())
    return result


def _reasons(query, row, evidence, gate):
    """Every normalized bad slot, not every possible defect within that slot."""
    grouped = {}
    def add(code, scope, point=None, field=None):
        key = (scope, code, field)
        item = grouped.setdefault(key, dict(code=code, scope=scope, field=field, count=0, examples=[]))
        item['count'] += 1
        if point is not None and len(item['examples']) < 8:
            item['examples'].append([point['date'], point['ordinal']])
    if gate == 'unknown':
        add('date_set_integrity_unknown', 'source_date')
    for bar in evidence['window']:
        if bar['reason'] is not None:
            add(bar['reason'], 'window_slot', bar)
    rejection = source_rejection(query)
    if rejection is not None:
        add(rejection, 'source')
    for field in _FIELDS:
        reason = row[field + '_reason']
        if reason == 'numerical_failure':
            add(reason, 'metric', field=field)
        elif reason is not None and not any(key[1] == reason for key in grouped):
            add(reason, 'window')
    result = []
    for index, (key, value) in enumerate(sorted(grouped.items(), key=lambda item: (item[0][0] != 'source_date', item[0][1], item[0][0], item[0][2] or '')), 1):
        # Non-slot reasons are a single state; examples refer only to source slots.
        value.update(omitted_count=value['count'] - len(value['examples']) if value['scope'] == 'window_slot' else 0,
                     id=f'r{index}')
        result.append(value)
    return result


def _member(query, row, evidence, canonical, atom_ids, source, cutoff, lookback):
    gate = 'pass' if row['coverage']['coverage_known'] else 'unknown'
    bars = evidence['window']
    window_key = dict(snapshot_id=query['snapshot_id'], query_id=query['query_id'], cutoff=cutoff,
                      lookback=lookback, method=POLICIES['window'],
                      start_date=bars[0]['date'] if bars else None, end_date=bars[-1]['date'] if bars else None)
    window_id = _identity(window_key)
    window = dict(window_key, id=window_id, unit='source_date_groups', expected_groups=lookback+1,
                  actual_groups=len(bars), n_prices=row['n_prices'], n_returns=row['n_returns'],
                  first=_point(bars[0]) if bars else None, last=_point(bars[-1]) if bars else None,
                  drawdown_witness=None if evidence['drawdown_witness'] is None else
                  {key: _point(bar) for key, bar in evidence['drawdown_witness'].items()})
    facts, reasons, atoms, groups = _facts(row, evidence), _reasons(query, row, evidence, gate), {}, []
    for index, group in enumerate(canonical['any_of'], 1):
        ids = []
        for atom in group['all_of']:
            aid, field = atom_ids[(atom['field'], atom['op'], atom['threshold'])], atom['field']
            ids.append(aid)
            if aid in atoms:
                continue
            reason = row[field + '_reason']
            usable = gate == 'pass' and reason is None
            value = (Fraction.from_float(row[field]) if field == 'volatility' else evidence[field]) if usable else None
            refs = [r['id'] for r in reasons if
                    r['scope'] == 'source_date' or (reason is not None and (
                        r['scope'] in ('window', 'window_slot', 'source') or r['field'] == field))]
            atoms[aid] = dict(id=aid, truth=_compare(value, atom['op'], Fraction(atom['threshold'])) if usable else 'unknown',
                              fact_ref=field, reason_refs=refs)
        truths = [atoms[aid]['truth'] for aid in ids]
        groups.append(dict(id=f'g{index}', atom_ids=ids, truth=_combine('all', truths),
                           false_atoms=[aid for aid in ids if atoms[aid]['truth'] == 'false'],
                           unknown_atoms=[aid for aid in ids if atoms[aid]['truth'] == 'unknown']))
    logical = _combine('any', [group['truth'] for group in groups])
    state = {'true': 'selected', 'false': 'excluded', 'unknown': 'undetermined'}[logical] if gate == 'pass' else 'undetermined'
    complete = all(atom['truth'] != 'unknown' for atom in atoms.values())
    return dict(identity=row['identity'], snapshot_id=row['snapshot_id'], source_ref=source['id'], window_ref=window_id,
                window=window, source_gate=gate, logical_truth=logical, selection_state=state,
                evidence_complete=complete, partial_evidence=not complete, facts=facts,
                atoms=sorted(atoms.values(), key=lambda a: a['id']), groups=groups,
                reasons=reasons, primary_reason=reasons[0]['code'] if reasons else None,
                proof_groups=[group['id'] for group in groups if group['truth'] == 'true'])


def _counts(members):
    result = dict(selected_members=len(members), selection=dict(selected=0, excluded=0, undetermined=0),
                  logical=dict(true=0, false=0, unknown=0), evidence=dict(complete=0, partial=0),
                  source_gate={'pass': 0, 'unknown': 0}, atoms={}, groups={})
    for member in members:
        result['selection'][member['selection_state']] += 1
        result['logical'][member['logical_truth']] += 1
        result['evidence']['complete' if member['evidence_complete'] else 'partial'] += 1
        result['source_gate'][member['source_gate']] += 1
        for kind in ('atoms', 'groups'):
            for item in member[kind]:
                result[kind].setdefault(item['id'], dict(true=0, false=0, unknown=0))[item['truth']] += 1
    return result


def filter_report(queries, cutoff, lookback, rule):
    """Read-only result over trusted full Store queries or synthetic fixtures."""
    canonical = normalize_rule(rule)  # Always validate before touching sources.
    strict_date(cutoff, 'invalid_label_cutoff')
    if not isinstance(queries, (list, tuple)) or not 2 <= len(queries) <= 50:
        raise ValueError('research_invalid_member_count')
    for query in queries:
        prior = (query.get('selection') or {}).get('cutoff')
        if prior is not None and strict_date(prior, 'invalid_cutoff') < cutoff:
            raise ValueError('research_cutoff_mismatch')
    queries = sorted(queries, key=lambda q: q['snapshot_id'])
    universe, evidence = _universe_evaluation(queries, cutoff, lookback, with_evidence=True)
    by_snapshot = {row['snapshot_id']: row for row in universe['members']}
    sources = [_source(query, by_snapshot[query['snapshot_id']]['identity']) for query in queries]
    contracts = _share_contracts(sources)
    unique_atoms = sorted({(atom['field'], atom['op'], atom['threshold'])
                           for group in canonical['any_of'] for atom in group['all_of']})
    atom_ids = {atom: f'a{index}' for index, atom in enumerate(unique_atoms, 1)}
    conditions = [dict(id=atom_ids[item], field=item[0], op=item[1], threshold=item[2]) for item in unique_atoms]
    members = [_member(query, by_snapshot[query['snapshot_id']], evidence[query['snapshot_id']], canonical,
                       atom_ids, source, cutoff, lookback) for query, source in zip(queries, sources)]
    inputs = [dict(snapshot_id=q['snapshot_id'], query_id=q['query_id']) for q in queries]
    rule_id = _identity(dict(canonical_rule=canonical, policy_versions=POLICIES))
    params = dict(cutoff=cutoff, lookback=lookback, canonical_rule=canonical, policy_versions=dict(POLICIES))
    base_identity = dict(method_id='selected-universe-research-v1', inputs=inputs,
                         parameters=dict(cutoff=cutoff, lookback=lookback, model=universe['parameters']))
    identity = dict(method_id=METHOD_ID, inputs=inputs, parameters=params, rule_id=rule_id,
                    source_metadata_id=_identity(dict(sources=sources, source_contracts=contracts)))
    return dict(identity, analysis_id=_identity(identity), base_analysis_id=_identity(base_identity),
                mode='retrospective', qualification='conditional_source_price_filter', limitations=list(_LIMITATIONS),
                result=dict(universe=universe, sources=sources, source_contracts=contracts, conditions=conditions,
                            reason_example_fields=['date', 'ordinal'],
                            members=members, counts=_counts(members)))
