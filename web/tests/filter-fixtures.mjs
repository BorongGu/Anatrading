// All identities, source contracts and prices below are synthetic UI contracts.
import { buildFilterRequest, FILTER_POLICIES } from '../src/filter-model.ts';

export const goldenDraftGroups = [
  [{ field: 'volatility', threshold: '0.0200' }, { field: 'momentum', threshold: '-0.00' }],
  [{ field: 'max_drawdown', threshold: '10.00' }, { field: 'momentum', threshold: '0.00' }],
];
const absent = () => ({ present: false, value: null });
const present = value => ({ present: true, value });
const identity = i => ({ symbol: i ? '000001.SZ' : '600001.SH', code: i ? '000001' : '600001', venue: i ? 'SZ' : 'SH', market: 'CN_A', qualification: 'source_claim' });
const coverage = count => ({ source_rows: count, date_groups: count, valid_groups: count, invalid_groups: 0,
  duplicate_groups: 0, unlocated_rows: 0, unreadable_date_rows: 0, batch_unlocated_rows: 0, coverage_known: true });
const fields = ['momentum', 'volatility', 'max_drawdown'];
export function recountFilter(reply) {
  const rows = reply.result.members, baselines = reply.result.universe.members;
  const count = (values, categories) => Object.fromEntries(categories.map(category => [category, values.filter(v => v === category).length]));
  reply.result.counts = {
    selected_members: rows.length,
    selection: count(rows.map(row => row.selection_state), ['selected', 'excluded', 'undetermined']),
    logical: count(rows.map(row => row.logical_truth), ['true', 'false', 'unknown']),
    evidence: count(rows.map(row => row.evidence_complete ? 'complete' : 'partial'), ['complete', 'partial']),
    source_gate: count(rows.map(row => row.source_gate), ['pass', 'unknown']),
    ...Object.fromEntries(['atoms', 'groups'].map(kind => [kind, Object.fromEntries(rows[0][kind].map(item =>
      [item.id, count(rows.map(row => row[kind].find(value => value.id === item.id).truth), ['true', 'false', 'unknown'])]))])),
  };
  const b = reply.result.universe.breadth;
  b.cutoff_present = baselines.filter(row => row.cutoff_present).length;
  b.cutoff_valid = baselines.filter(row => row.cutoff_valid).length;
  for (const field of fields) {
    b[`${field}_valid`] = baselines.filter(row => row[field] !== null).length;
    b.metrics[field] = count(baselines.map(row => row[field] !== null ? 'eligible' : row[`${field}_reason`] === 'cutoff_missing' ? 'missing'
      : row[`${field}_reason`] === 'history_insufficient' ? 'short_history' : 'invalid'), ['eligible', 'missing', 'invalid', 'short_history']);
  }
  const valid = baselines.filter(row => row.momentum !== null);
  b.positive = valid.filter(row => row.momentum > 0).length; b.zero = valid.filter(row => row.momentum === 0).length;
  b.negative = valid.filter(row => row.momentum < 0).length;
  b.positive_momentum_fraction = valid.length ? b.positive / valid.length : null;
  b.momentum_coverage = valid.length / rows.length; b.cutoff_coverage = b.cutoff_valid / rows.length;
}
export function indexReportedTruths(member) {
  for (const group of member.groups) {
    group.false_atoms = group.atom_ids.filter(id => member.atoms.find(atom => atom.id === id).truth === 'false');
    group.unknown_atoms = group.atom_ids.filter(id => member.atoms.find(atom => atom.id === id).truth === 'unknown');
  }
  member.proof_groups = member.groups.filter(group => group.truth === 'true').map(group => group.id);
}
export function unavailableFact(reply, index, field, reason = 'numerical_failure') {
  const member = reply.result.members[index], base = reply.result.universe.members.find(row => row.snapshot_id === member.snapshot_id);
  member.facts[field] = { value: null, reason, comparison_type: field === 'volatility' ? 'float64_estimate' : 'source_fraction', exact: null,
    ...(field === 'volatility' ? { estimate_text: null, float_hex: null } : {}) };
  base[field] = null; base[`${field}_reason`] = reason; if (field === 'momentum') base.rank = null;
}
export async function makeFilterFixture({ groups = goldenDraftGroups, lookback = 2, cutoff = '2026-01-03' } = {}) {
  const ids = ['a'.repeat(64), 'b'.repeat(64)], request = await buildFilterRequest(ids, cutoff, lookback, groups);
  const conditions = [...new Map(request.expected.canonicalRule.any_of.flatMap(group => group.all_of).map(atom => [JSON.stringify(atom), atom])).values()]
    .sort((a, b) => a.field < b.field ? -1 : a.field > b.field ? 1 : a.threshold < b.threshold ? -1 : a.threshold > b.threshold ? 1 : 0)
    .map((atom, i) => ({ ...atom, id: `a${i + 1}` }));
  const sourceIds = ['1'.repeat(64), '2'.repeat(64)], windowIds = ['3'.repeat(64), '4'.repeat(64)], contractId = '5'.repeat(64);
  const inputs = ids.map((snapshot_id, i) => ({ snapshot_id, query_id: (i ? 'd' : 'c').repeat(64) }));
  const sourceContract = {
    id: contractId, source_contract_id: present('synthetic-contract'), format_id: present('synthetic'), contract_version: present(1),
    versions: absent(), semantics_scope: present('documented_meaning_only'),
    semantics: Object.fromEntries(['price_unit', 'adjustment', 'label_definition', 'closed', 'known_at', 'first_published_at'].map(key =>
      [key, { value: absent(), status: absent(), reason: absent(), applicability: absent() }])),
  };
  sourceContract.semantics.price_unit = { value: present('CNY'), status: present('known'), reason: present('documented_meaning_only'), applicability: present('unverified') };
  sourceContract.semantics.adjustment.value = present(null);
  const sources = inputs.map((input, i) => ({ ...input, identity: identity(i), id: sourceIds[i], contract_ref: contractId,
    raw_sha256: present((i ? '7' : '6').repeat(64)), metadata: Object.fromEntries(['period', 'source', 'source_code', 'source_venue', 'source_symbol',
      'requested_symbol', 'requested_adjustment', 'capture_version', 'capture_mode', 'header_cardinality', 'transport_evidence',
      'provenance_hash_verification', 'interpretation_status', 'source_claims_status'].map(key => [key, absent()])) }));
  sources[0].metadata.requested_adjustment = present('none');
  sources[0].metadata.transport_evidence = present('legacy');
  const baselines = inputs.map((input, i) => ({ snapshot_id: input.snapshot_id, identity: identity(i), cutoff_present: true, cutoff_valid: true,
    momentum: 0, volatility: 0, max_drawdown: 0, momentum_reason: null, volatility_reason: null, max_drawdown_reason: null,
    start_date: '2026-01-01', end_date: cutoff, n_prices: lookback + 1, n_returns: lookback, rank: 1, coverage: coverage(lookback + 1) }));
  const members = inputs.map((input, i) => ({ identity: identity(i), snapshot_id: input.snapshot_id, source_ref: sourceIds[i], window_ref: windowIds[i],
    window: { ...input, cutoff, lookback, method: FILTER_POLICIES.window, start_date: '2026-01-01', end_date: cutoff,
      id: windowIds[i], unit: 'source_date_groups', expected_groups: lookback + 1, actual_groups: lookback + 1,
      n_prices: lookback + 1, n_returns: lookback, first: { date: '2026-01-01', ordinal: 1, close: '100' },
      last: { date: cutoff, ordinal: lookback + 1, close: '100' },
      drawdown_witness: { peak: { date: '2026-01-01', ordinal: 1, close: '100' }, trough: { date: '2026-01-01', ordinal: 1, close: '100' } } },
    source_gate: 'pass', logical_truth: 'true', selection_state: 'selected', evidence_complete: true, partial_evidence: false,
    facts: Object.fromEntries(fields.map(field => [field, { value: 0, reason: null,
      comparison_type: field === 'volatility' ? 'float64_estimate' : 'source_fraction',
      exact: field === 'volatility' ? null : { numerator: '0', denominator: '1' },
      ...(field === 'volatility' ? { estimate_text: '0.0', float_hex: '0x0.0p+0' } : {}) }])),
    atoms: conditions.map(atom => ({ id: atom.id, truth: 'true', fact_ref: atom.field, reason_refs: [] })),
    groups: request.expected.canonicalRule.any_of.map((group, index) => ({ id: `g${index + 1}`, truth: 'true',
      atom_ids: group.all_of.map(atom => conditions.find(condition => condition.field === atom.field && condition.op === atom.op && condition.threshold === atom.threshold).id),
      false_atoms: [], unknown_atoms: [] })), reasons: [], primary_reason: null,
    proof_groups: request.expected.canonicalRule.any_of.map((_, index) => `g${index + 1}`),
  }));
  const reply = {
    method_id: 'selected-source-price-filter-v1', inputs,
    parameters: { cutoff, lookback, canonical_rule: structuredClone(request.expected.canonicalRule), policy_versions: { ...FILTER_POLICIES } },
    rule_id: request.expected.ruleId, source_metadata_id: '8'.repeat(64), analysis_id: '9'.repeat(64), base_analysis_id: '0'.repeat(64),
    mode: 'retrospective', qualification: 'conditional_source_price_filter',
    limitations: ['retrospective_source_version', 'adjustment_basis_unverified', 'historical_availability_unverified',
      'calendar_and_bar_closure_unverified', 'descriptive_estimates_not_trading_returns', 'current_selected_membership', 'source_identity_not_security_master_verified'],
    result: { universe: { members: baselines, breadth: { selected: ids.length, metrics: {} }, cutoff, parameters: { lookback, volatility_ddof: 1 },
      estimate_type: 'float64', window_unit: 'source_date_groups', window_price_count: lookback + 1,
      membership: 'selected_sample_no_historical_sector_inference', qualification: 'conditional_located_source_values',
      units: { momentum: 'source_close_change', volatility: 'log_return_per_source_interval', max_drawdown: 'nonpositive_close_path_drawdown' },
      ranking: 'momentum_descending_competition_then_symbol' }, sources, source_contracts: [sourceContract], conditions,
      reason_example_fields: ['date', 'ordinal'], members, counts: {} },
  };
  recountFilter(reply); return { request, expected: request.expected, reply };
}
