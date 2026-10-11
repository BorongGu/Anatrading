import { safeCode } from './api.ts';
import { assertResearchReply, buildResearchRequest, explainResearch } from './research-model.ts';
import type { CanonicalRule, FilterCondition, FilterDraftAtom, FilterEnvelope, FilterExpected, FilterField,
  FilterPolicies, FilterRequest, ResearchRequestState, RequestStatus } from './filter-types.ts';

export const FILTER_POLICIES: Readonly<FilterPolicies> = Object.freeze({ rule_schema: 'bounded-price-filter-v1',
  window: 'daily-source-date-groups-v1', logic: 'strong-kleene-eager-v1', comparison: 'fraction-and-binary64-v1', source_gate: 'source-date-locatability-v1' });
export const FILTER_RESPONSE_LIMIT = 512 * 1024;
export const FILTER_RULE_LIMIT = 2048;
const fields: FilterField[] = ['momentum', 'volatility', 'max_drawdown'];
const hex = /^[a-f0-9]{64}$/;
const codePattern = /^[a-z][a-z0-9_]{0,79}$/;
const limitations = ['retrospective_source_version', 'adjustment_basis_unverified', 'historical_availability_unverified',
  'calendar_and_bar_closure_unverified', 'descriptive_estimates_not_trading_returns', 'current_selected_membership', 'source_identity_not_security_master_verified'];
const asciiCompare = (a: string, b: string) => a < b ? -1 : a > b ? 1 : 0;

export class FilterInputError extends Error {
  groupIndex?: number; atomIndex?: number;
  constructor(code: string, groupIndex?: number, atomIndex?: number) {
    super(code); this.name = 'FilterInputError'; this.groupIndex = groupIndex; this.atomIndex = atomIndex;
  }
}
function normalizedDecimal(text: string): string {
  const negative = text.startsWith('-');
  const [whole, tail = ''] = (negative ? text.slice(1) : text).split('.');
  const fraction = tail.replace(/0+$/, ''), magnitude = `${whole}${fraction ? `.${fraction}` : ''}`;
  return negative && magnitude !== '0' ? `-${magnitude}` : magnitude;
}
function magnitudeAtMost(text: string, maximum: string): boolean {
  const [whole, fraction = ''] = text.replace(/^-/, '').split('.');
  return whole.length < maximum.length || (whole.length === maximum.length &&
    (whole < maximum || whole === maximum && !/[1-9]/.test(fraction)));
}
/** Unit conversion uses only bounded decimal strings, never a binary number. */
export function thresholdToWire(field: FilterField, text: string): string {
  if (!fields.includes(field)) throw new FilterInputError('unsupported_filter_field');
  const precision = field === 'volatility' ? 18 : 16;
  if (typeof text !== 'string' || text.length > 24 || !new RegExp(`^-?(0|[1-9][0-9]{0,3})(\\.[0-9]{1,${precision}})?$`).test(text))
    throw new FilterInputError('invalid_filter_threshold');
  const normalized = normalizedDecimal(text), negative = normalized.startsWith('-');
  if (field !== 'momentum' && negative || !magnitudeAtMost(normalized, field === 'volatility' ? '1' : field === 'max_drawdown' || negative ? '100' : '1000'))
    throw new FilterInputError('invalid_filter_threshold');
  if (field === 'volatility') return normalized;
  const [whole, fraction = ''] = normalized.replace(/^-/, '').split('.');
  const padded = whole.padStart(3, '0');
  const shifted = normalizedDecimal(`${padded.slice(0, -2)}.${padded.slice(-2)}${fraction}`);
  return shifted !== '0' && (negative || field === 'max_drawdown') ? `-${shifted}` : shifted;
}
export function thresholdPreview(field: FilterField, text: string): string {
  thresholdToWire(field, text);
  const value = normalizedDecimal(text).replace('-', '−');
  return field === 'momentum' ? `收盘变化 ≥ ${value}%` : field === 'volatility' ? `来源区间波动 ≤ ${value} log 单位（未年化）`
    : `最大跌幅不超过 ${value}%（回撤 ≥ ${value === '0' ? '0' : `−${value}`}%）`;
}
/** Sorted ASCII keys and compact separators match Python Store._json for this ASCII-only identity. */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (typeof value === 'string') {
    if (!/^[\x20-\x7e]*$/.test(value)) throw new Error('invalid_filter_rule');
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort(asciiCompare).map(key => `${canonicalJson(key)}:${canonicalJson((value as Record<string, unknown>)[key])}`).join(',')}}`;
  throw new Error('invalid_filter_rule');
}
export function checkRuleByteLimit(text: string): void {
  if (new TextEncoder().encode(text).byteLength > FILTER_RULE_LIMIT) throw new FilterInputError('filter_rule_limit');
}
export function prepareFilterRule(groups: readonly (readonly FilterDraftAtom[])[]): { canonicalRule: CanonicalRule; groupLabels: number[] } {
  if (!Array.isArray(groups) || !groups.length) throw new FilterInputError('invalid_filter_rule');
  if (groups.length > 2) throw new FilterInputError('filter_rule_limit');
  const normalized = groups.map((group, groupIndex) => {
    if (!Array.isArray(group) || !group.length) throw new FilterInputError('invalid_filter_rule', groupIndex);
    if (group.length > 3) throw new FilterInputError('filter_rule_limit', groupIndex);
    const seen = new Set<string>();
    const all_of: FilterCondition[] = group.map((atom, atomIndex) => {
      try {
        if (!atom || typeof atom !== 'object' || Array.isArray(atom) || Object.keys(atom).sort().join(',') !== 'field,threshold') throw new FilterInputError('invalid_filter_rule');
        if (seen.has(atom.field)) throw new FilterInputError('duplicate_filter_field');
        seen.add(atom.field);
        return { field: atom.field, op: atom.field === 'volatility' ? 'lte' : 'gte', threshold: thresholdToWire(atom.field, atom.threshold) };
      } catch (error) { throw new FilterInputError(safeCode(error), groupIndex, atomIndex); }
    });
    all_of.sort((a, b) => asciiCompare(a.field, b.field) || asciiCompare(a.op, b.op) || asciiCompare(a.threshold, b.threshold));
    return { group: { all_of }, label: groupIndex + 1 };
  }).sort((a, b) => asciiCompare(canonicalJson(a.group), canonicalJson(b.group)));
  if (normalized.length === 2 && canonicalJson(normalized[0].group) === canonicalJson(normalized[1].group)) throw new FilterInputError('duplicate_filter_group', 1);
  const canonicalRule = { any_of: normalized.map(item => item.group) };
  checkRuleByteLimit(canonicalJson(canonicalRule));
  return { canonicalRule, groupLabels: normalized.map(item => item.label) };
}
export async function hashFilterRule(rule: CanonicalRule, policies: FilterPolicies = FILTER_POLICIES, subtle = globalThis.crypto?.subtle): Promise<string> {
  if (!subtle) throw new Error('filter_crypto_unavailable');
  const bytes = new TextEncoder().encode(canonicalJson({ canonical_rule: rule, policy_versions: policies }));
  const digest = await subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(digest)].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
export async function buildFilterRequest(ids: readonly string[], cutoff: string, lookback: number, groups: readonly (readonly FilterDraftAtom[])[]): Promise<FilterRequest> {
  const base = buildResearchRequest('universe', ids, cutoff, lookback);
  const { canonicalRule, groupLabels } = prepareFilterRule(groups);
  const ruleId = await hashFilterRule(canonicalRule);
  const query = new URLSearchParams({ snapshot_ids: base.expected.snapshotIds.join(','), cutoff, lookback: String(lookback), rule: canonicalJson(canonicalRule) });
  return { path: `/api/research/universe-filter?${query}`, expected: { snapshotIds: [...base.expected.snapshotIds], cutoff, lookback,
    canonicalRule, groupLabels, ruleId, policyVersions: { ...FILTER_POLICIES } } };
}

// Deliberately separate from checkedFetch: errors must pass the same streaming cap.
export async function readFilterJson(response: Response): Promise<unknown> {
  if (!response.body) throw new Error('invalid_filter_response');
  const reader = response.body.getReader(), chunks: Uint8Array[] = [];
  let size = 0;
  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > FILTER_RESPONSE_LIMIT) {
        // Cancel before parsing or retaining the oversize chunk; cancellation failure cannot hide the cap.
        void reader.cancel().catch(() => {});
        throw new Error('filter_response_limit');
      }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  try { return JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); }
  catch { throw new Error('invalid_filter_response'); }
}
export async function fetchFilter(request: FilterRequest, signal: AbortSignal, fetcher: typeof fetch = fetch): Promise<FilterEnvelope> {
  const response = await fetcher(request.path, { method: 'GET', signal, cache: 'no-store', credentials: 'same-origin' });
  const value = await readFilterJson(response);
  if (!response.ok) {
    const error = value !== null && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>).error : null;
    throw new Error(typeof error === 'string' && codePattern.test(error) ? error : 'invalid_filter_response');
  }
  assertFilterReply(value, request.expected); return value;
}

/** One synchronous admission lock covers async preparation (including hashing), fetch and publication. */
export class ResearchRequestController<Spec, Result> {
  state: ResearchRequestState<Spec, Result> = { status: 'idle', result: null, error: null, spec: null };
  private generation = 0; private locked = false; private disposed = false; private aborter: AbortController | null = null;
  private onState: (state: ResearchRequestState<Spec, Result>) => void;
  constructor(onState: (state: ResearchRequestState<Spec, Result>) => void) { this.onState = onState; }
  private publish(state: ResearchRequestState<Spec, Result>): void { this.state = state; if (!this.disposed) this.onState(state); }
  private reset(status: RequestStatus): void {
    ++this.generation; const previous = this.aborter; this.aborter = null; this.locked = false;
    previous?.abort(); this.publish({ status, result: null, error: null, spec: null });
  }
  invalidate(): void { if (!this.disposed) this.reset('dirty'); }
  cancel(): void { if (!this.disposed) this.reset('cancelled'); }
  dispose(): void { if (!this.disposed) { this.disposed = true; this.reset('cancelled'); } }
  async run(prepare: () => Spec | Promise<Spec>, load: (spec: Spec, signal: AbortSignal) => Promise<Result>): Promise<boolean> {
    if (this.disposed || this.locked) return false;
    this.locked = true;
    const generation = ++this.generation, aborter = new AbortController(); this.aborter = aborter;
    const current = () => !this.disposed && generation === this.generation && this.aborter === aborter;
    this.publish({ status: 'loading', result: null, error: null, spec: null });
    let spec: Spec | null = null;
    try {
      spec = await prepare();
      if (!current()) return true;
      const result = await load(spec, aborter.signal);
      if (current()) this.publish({ status: 'ready', result, error: null, spec });
    } catch (error) {
      if (current()) this.publish({ status: 'error', result: null, error, spec });
    } finally { if (current()) { this.locked = false; this.aborter = null; } }
    return true;
  }
}

const explanations: Record<string, string> = {
  invalid_filter_rule: '请至少填写一组完整条件，每组最多三项', filter_rule_limit: '条件超过两组、每组三项或 2,048 字节限制',
  unsupported_filter_field: '请选择收盘变化、来源区间波动或收盘路径最大跌幅', invalid_filter_operator: '条件比较方向不符合当前格式约定',
  invalid_filter_threshold: '请填写范围内的十进制数；百分比最多16位小数，波动最多18位，不支持科学计数',
  duplicate_filter_field: '同一组不能重复选择同一字段', duplicate_filter_group: '两组条件完全相同，请修改或删除一组',
  filter_crypto_unavailable: '当前环境无法进行规则身份核对，请使用支持 Web Crypto 的本地安全页面',
  filter_response_limit: '筛选响应超过 512 KiB，整组结果未显示，请减少成员后重新核验',
  invalid_filter_response: '筛选响应与当前输入或格式约定不符，整组结果已清空',
};
export function explainFilter(error: unknown): string {
  const code = safeCode(error); return Object.hasOwn(explanations, code) ? `${explanations[code]}（${code}）` : explainResearch(error);
}

// Frozen wire-shape, binding and conservation checks. No metric, comparison,
// Kleene expression, selection decision, rank or source identity is recalculated.
type JsonObject = Record<string, unknown>;
function requireThat(condition: unknown): asserts condition { if (!condition) throw new Error('invalid_filter_response'); }
function object(value: unknown, exactKeys?: readonly string[]): JsonObject {
  requireThat(value !== null && typeof value === 'object' && !Array.isArray(value));
  const item = value as JsonObject;
  if (exactKeys) requireThat(Object.keys(item).length === exactKeys.length && exactKeys.every(key => Object.hasOwn(item, key)));
  return item;
}
function list(value: unknown, maximum = 50): unknown[] { requireThat(Array.isArray(value) && value.length <= maximum); return value; }
function isInteger(value: unknown, min = 0, max = 20000): value is number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max; }
function isId(value: unknown): value is string { return typeof value === 'string' && hex.test(value); }
function isCode(value: unknown): value is string { return typeof value === 'string' && codePattern.test(value); }
function isDay(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number), leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  return y > 0 && m >= 1 && m <= 12 && d >= 1 && d <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
}
function isTruth(value: unknown): boolean { return value === 'true' || value === 'false' || value === 'unknown'; }
function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
  const aa = a as JsonObject, bb = b as JsonObject, keys = Object.keys(aa);
  return keys.length === Object.keys(bb).length && keys.every(key => Object.hasOwn(bb, key) && sameValue(aa[key], bb[key]));
}
function safeValue(value: unknown, depth = 0): void {
  requireThat(depth <= 16);
  if (value === null || typeof value === 'boolean') return;
  if (typeof value === 'string') { requireThat(value.length <= 4096); return; }
  if (typeof value === 'number') { requireThat(Number.isFinite(value)); return; }
  if (Array.isArray(value)) { requireThat(value.length <= 20000); value.forEach(item => safeValue(item, depth + 1)); return; }
  const item = object(value); requireThat(Object.keys(item).length <= 128);
  for (const [key, child] of Object.entries(item)) { requireThat(key.length <= 128); safeValue(child, depth + 1); }
}
function presence(value: unknown): void {
  const p = object(value, ['present', 'value']);
  requireThat(typeof p.present === 'boolean' && (p.present || p.value === null));
}
function identityMatches(value: unknown, expected: unknown): void {
  const i = object(value, ['symbol', 'code', 'venue', 'market', 'qualification']);
  requireThat(sameValue(i, expected));
  requireThat(['source_claim', 'source_claim_and_declared', 'declared'].includes(i.qualification as string));
}
const metadataKeys = ['period', 'source', 'source_code', 'source_venue', 'source_symbol', 'requested_symbol',
  'requested_adjustment', 'capture_version', 'capture_mode', 'header_cardinality', 'transport_evidence',
  'provenance_hash_verification', 'interpretation_status', 'source_claims_status'];
const semanticKeys = ['price_unit', 'adjustment', 'label_definition', 'closed', 'known_at', 'first_published_at'];
function point(value: unknown, cutoff: string, firstDate?: string): JsonObject {
  const p = object(value, ['date', 'ordinal', 'close']);
  requireThat(isDay(p.date) && p.date <= cutoff && (firstDate === undefined || p.date >= firstDate));
  requireThat(p.ordinal === null || isInteger(p.ordinal, 1, Number.MAX_SAFE_INTEGER));
  requireThat(p.close === null || typeof p.close === 'string' && /^-?(0|[1-9][0-9]{0,19})(\.[0-9]{1,18})?$/.test(p.close)
    && normalizedDecimal(p.close) === p.close);
  return p;
}
function namedCounts(value: unknown, names: readonly string[], rows: JsonObject[], field: string): void {
  const c = object(value, names);
  for (const name of names) requireThat(isInteger(c[name], 0, rows.length) && c[name] === rows.filter(row => row[field] === name).length);
  requireThat(Object.values(c).reduce<number>((sum, count) => sum + (count as number), 0) === rows.length);
}
function references(value: unknown, permitted: readonly string[], maximum = 6): string[] {
  const refs = list(value, maximum);
  requireThat(refs.every(ref => typeof ref === 'string' && permitted.includes(ref)) && new Set(refs).size === refs.length);
  return refs as string[];
}
function conditionDefinitions(rule: CanonicalRule): (FilterCondition & { id: string })[] {
  const unique = new Map<string, FilterCondition>();
  for (const group of rule.any_of) for (const condition of group.all_of) unique.set(canonicalJson(condition), condition);
  return [...unique.values()].sort((a, b) => asciiCompare(a.field, b.field) || asciiCompare(a.op, b.op) || asciiCompare(a.threshold, b.threshold))
    .map((condition, i) => ({ ...condition, id: `a${i + 1}` }));
}
export function assertFilterReply(value: unknown, expected: FilterExpected): asserts value is FilterEnvelope {
  try { validateFilterReply(value, expected); }
  catch { throw new Error('invalid_filter_response'); }
}
function validateFilterReply(value: unknown, expected: FilterExpected): void {
  safeValue(value);
  const e = object(value, ['method_id', 'inputs', 'parameters', 'rule_id', 'source_metadata_id', 'analysis_id', 'base_analysis_id', 'mode', 'qualification', 'limitations', 'result']);
  requireThat(e.method_id === 'selected-source-price-filter-v1' && e.mode === 'retrospective' && e.qualification === 'conditional_source_price_filter');
  for (const key of ['rule_id', 'source_metadata_id', 'analysis_id', 'base_analysis_id']) requireThat(isId(e[key]));
  requireThat(e.rule_id === expected.ruleId);
  const params = object(e.parameters, ['cutoff', 'lookback', 'canonical_rule', 'policy_versions']);
  requireThat(params.cutoff === expected.cutoff && params.lookback === expected.lookback
    && sameValue(params.canonical_rule, expected.canonicalRule) && sameValue(params.policy_versions, FILTER_POLICIES)
    && sameValue(params.policy_versions, expected.policyVersions));
  const restrictions = list(e.limitations, 100);
  requireThat(restrictions.every(isCode) && new Set(restrictions).size === restrictions.length && limitations.every(item => restrictions.includes(item)));
  const inputs = list(e.inputs).map(item => object(item, ['snapshot_id', 'query_id']));
  requireThat(inputs.length === expected.snapshotIds.length && inputs.every((item, i) => item.snapshot_id === expected.snapshotIds[i] && isId(item.query_id))
    && new Set(inputs.map(item => item.query_id)).size === inputs.length);
  const r = object(e.result, ['universe', 'sources', 'source_contracts', 'conditions', 'reason_example_fields', 'members', 'counts']);
  requireThat(sameValue(r.reason_example_fields, ['date', 'ordinal']));
  const universe = object(r.universe);
  // An explicit validation-only adapter exercises the unchanged, strict legacy
  // universe validator. The new report itself is never cast to an old envelope.
  const baseExpected = buildResearchRequest('universe', expected.snapshotIds, expected.cutoff, expected.lookback).expected;
  assertResearchReply({ method_id: baseExpected.methodId, analysis_id: e.base_analysis_id, inputs: e.inputs,
    parameters: { cutoff: expected.cutoff, lookback: expected.lookback, model: universe.parameters },
    mode: e.mode, limitations: e.limitations, result: universe }, baseExpected);
  requireThat(universe.window_unit === 'source_date_groups' && universe.window_price_count === expected.lookback + 1
    && universe.membership === 'selected_sample_no_historical_sector_inference' && universe.qualification === 'conditional_located_source_values'
    && universe.ranking === 'momentum_descending_competition_then_symbol'
    && sameValue(universe.units, { momentum: 'source_close_change', volatility: 'log_return_per_source_interval', max_drawdown: 'nonpositive_close_path_drawdown' }));
  const baselines = new Map(list(universe.members).map(item => { const row = object(item); return [row.snapshot_id, row]; }));
  const contracts = list(r.source_contracts).map(item => object(item, ['id', 'source_contract_id', 'format_id', 'contract_version', 'versions', 'semantics_scope', 'semantics']));
  requireThat(contracts.length > 0);
  const contractIds = new Set<string>();
  for (const c of contracts) {
    requireThat(isId(c.id) && !contractIds.has(c.id)); contractIds.add(c.id);
    for (const key of ['source_contract_id', 'format_id', 'contract_version', 'versions', 'semantics_scope']) presence(c[key]);
    const semantics = object(c.semantics, semanticKeys);
    for (const name of semanticKeys) {
      const item = object(semantics[name], ['value', 'status', 'reason', 'applicability']);
      Object.values(item).forEach(presence);
    }
  }
  const sources = list(r.sources).map(item => object(item, ['snapshot_id', 'query_id', 'identity', 'raw_sha256', 'metadata', 'id', 'contract_ref']));
  requireThat(sources.length === inputs.length);
  const sourceIds = new Set<string>(), usedContracts = new Set<string>();
  sources.forEach((source, index) => {
    const input = inputs[index]; requireThat(source.snapshot_id === input.snapshot_id && source.query_id === input.query_id);
    requireThat(isId(source.id) && !sourceIds.has(source.id)); sourceIds.add(source.id);
    requireThat(typeof source.contract_ref === 'string' && contractIds.has(source.contract_ref)); usedContracts.add(source.contract_ref);
    identityMatches(source.identity, baselines.get(source.snapshot_id)?.identity);
    presence(source.raw_sha256);
    const raw = object(source.raw_sha256); requireThat(raw.value === null || isId(raw.value));
    Object.values(object(source.metadata, metadataKeys)).forEach(presence);
  });
  requireThat(usedContracts.size === contractIds.size);
  const definitions = conditionDefinitions(expected.canonicalRule);
  requireThat(sameValue(r.conditions, definitions));
  const atomIds = definitions.map(item => item.id), groupIds = expected.canonicalRule.any_of.map((_, i) => `g${i + 1}`);
  const members = list(r.members).map(item => object(item, ['identity', 'snapshot_id', 'source_ref', 'window_ref', 'window', 'source_gate', 'logical_truth',
    'selection_state', 'evidence_complete', 'partial_evidence', 'facts', 'atoms', 'groups', 'reasons', 'primary_reason', 'proof_groups']));
  requireThat(members.length === inputs.length);
  const windowIds = new Set<string>();
  members.forEach((m, index) => {
    const input = inputs[index], source = sources[index], baseline = baselines.get(input.snapshot_id)!;
    requireThat(m.snapshot_id === input.snapshot_id && m.source_ref === source.id);
    identityMatches(m.identity, baseline.identity);
    requireThat(['pass', 'unknown'].includes(m.source_gate as string) && isTruth(m.logical_truth)
      && ['selected', 'excluded', 'undetermined'].includes(m.selection_state as string));
    requireThat(m.source_gate === (object(baseline.coverage).coverage_known ? 'pass' : 'unknown'));
    // Validate the legal pairing of two returned enums; do not reduce groups or
    // create a replacement selection decision in the client.
    if (m.source_gate === 'pass') requireThat(
      [['true', 'selected'], ['false', 'excluded'], ['unknown', 'undetermined']]
        .some(([truth, state]) => m.logical_truth === truth && m.selection_state === state));
    requireThat(typeof m.evidence_complete === 'boolean' && typeof m.partial_evidence === 'boolean' && m.evidence_complete !== m.partial_evidence);
    const w = object(m.window, ['snapshot_id', 'query_id', 'cutoff', 'lookback', 'method', 'start_date', 'end_date', 'id', 'unit', 'expected_groups', 'actual_groups', 'n_prices', 'n_returns', 'first', 'last', 'drawdown_witness']);
    requireThat(w.snapshot_id === input.snapshot_id && w.query_id === input.query_id && w.cutoff === expected.cutoff && w.lookback === expected.lookback
      && w.method === FILTER_POLICIES.window && w.unit === 'source_date_groups' && w.expected_groups === expected.lookback + 1
      && isId(w.id) && w.id === m.window_ref && !windowIds.has(w.id)); windowIds.add(w.id as string);
    requireThat(isInteger(w.actual_groups, 0, expected.lookback + 1) && isInteger(w.n_prices, 0, w.actual_groups)
      && isInteger(w.n_returns, 0, Math.max(0, w.actual_groups - 1)) && w.n_prices === baseline.n_prices && w.n_returns === baseline.n_returns
      && w.start_date === baseline.start_date);
    const actualGroups = w.actual_groups;
    if (actualGroups === 0) requireThat(w.start_date === null && w.end_date === null && w.first === null && w.last === null
      && w.drawdown_witness === null && baseline.cutoff_present === false);
    else {
      requireThat(isDay(w.start_date) && isDay(w.end_date) && w.end_date === expected.cutoff && w.start_date <= w.end_date
        && (w.actual_groups === 1 ? w.start_date === w.end_date : w.start_date < w.end_date) && baseline.cutoff_present === true);
      requireThat(point(w.first, expected.cutoff).date === w.start_date && point(w.last, expected.cutoff).date === w.end_date);
      if (w.actual_groups === 1) requireThat(sameValue(w.first, w.last));
      if (w.drawdown_witness !== null) {
        const witness = object(w.drawdown_witness, ['peak', 'trough']);
        const peak = point(witness.peak, expected.cutoff, w.start_date), trough = point(witness.trough, expected.cutoff, w.start_date);
        requireThat((peak.date as string) <= (trough.date as string));
      }
    }
    const facts = object(m.facts, fields);
    for (const field of fields) {
      const fact = object(facts[field], ['value', 'reason', 'comparison_type', 'exact', ...(field === 'volatility' ? ['estimate_text', 'float_hex'] : [])]);
      requireThat(fact.value === baseline[field] && fact.reason === baseline[`${field}_reason`] && (fact.value === null) === (fact.reason !== null));
      requireThat(fact.reason === null || isCode(fact.reason));
      requireThat(fact.comparison_type === (field === 'volatility' ? 'float64_estimate' : 'source_fraction'));
      if (field === 'volatility') {
        requireThat(fact.exact === null);
        if (fact.value === null) requireThat(fact.estimate_text === null && fact.float_hex === null);
        else requireThat(typeof fact.estimate_text === 'string' && /^-?(0|[1-9][0-9]*)(\.[0-9]+)?(e[+-]?[0-9]+)?$/.test(fact.estimate_text)
          && Number.isFinite(Number(fact.estimate_text)) && Number(fact.estimate_text) === fact.value && typeof fact.float_hex === 'string' && /^-?0x[01]\.[0-9a-f]{1,13}p[+-][0-9]{1,4}$/.test(fact.float_hex));
      } else if (fact.value === null) requireThat(fact.exact === null);
      else {
        const exact = object(fact.exact, ['numerator', 'denominator']);
        requireThat(typeof exact.numerator === 'string' && /^(0|-?[1-9][0-9]{0,255})$/.test(exact.numerator)
          && typeof exact.denominator === 'string' && /^[1-9][0-9]{0,255}$/.test(exact.denominator));
      }
    }
    const reasons = list(m.reasons, 32).map(item => object(item, ['code', 'scope', 'field', 'count', 'examples', 'omitted_count', 'id']));
    const reasonIds = reasons.map((reason, i) => {
      requireThat(reason.id === `r${i + 1}` && isCode(reason.code) && ['source_date', 'window_slot', 'source', 'metric', 'window'].includes(reason.scope as string)
        && (reason.field === null || fields.includes(reason.field as FilterField)) && isInteger(reason.count, 1) && isInteger(reason.omitted_count));
      requireThat(reason.scope === 'metric' ? fields.includes(reason.field as FilterField) : reason.field === null);
      const examples = list(reason.examples, 8);
      for (const value of examples) {
        const tuple = list(value, 2);
        requireThat(tuple.length === 2 && isDay(tuple[0]) && tuple[0] <= expected.cutoff
          && (tuple[1] === null || isInteger(tuple[1], 1, Number.MAX_SAFE_INTEGER)));
        requireThat(w.start_date !== null && tuple[0] >= (w.start_date as string));
      }
      if (reason.scope === 'window_slot') requireThat(reason.count === examples.length + (reason.omitted_count as number)
        && examples.length === Math.min(reason.count, 8) && reason.count <= actualGroups
        && examples.every((item, i) => i === 0 || ((examples[i - 1] as unknown[])[0] as string) < ((item as unknown[])[0] as string)));
      else requireThat(reason.count === 1 && examples.length === 0 && reason.omitted_count === 0);
      return reason.id as string;
    });
    requireThat(m.primary_reason === (reasons[0]?.code ?? null));
    const atoms = list(m.atoms, 6).map(item => object(item, ['id', 'truth', 'fact_ref', 'reason_refs']));
    requireThat(atoms.length === definitions.length);
    atoms.forEach((atom, i) => {
      requireThat(atom.id === definitions[i].id && atom.fact_ref === definitions[i].field && isTruth(atom.truth));
      const reasonRefs = references(atom.reason_refs, reasonIds, 32);
      const fact = object(facts[definitions[i].field]);
      const usable = m.source_gate === 'pass' && fact.value !== null && fact.reason === null;
      requireThat((atom.truth !== 'unknown') === usable);
      const relevantRefs = reasons.filter(reason => reason.scope === 'source_date' || fact.reason !== null
        && (['window', 'window_slot', 'source'].includes(reason.scope as string) || reason.field === definitions[i].field)).map(reason => reason.id);
      requireThat(sameValue(reasonRefs, relevantRefs) && (atom.truth !== 'unknown' || reasonRefs.length > 0));
    });
    // Evidence completeness is an inventory count of supplied unknown atoms.
    requireThat(m.partial_evidence === (atoms.filter(atom => atom.truth === 'unknown').length > 0));
    // A source-date gate can withhold all conditions, never authorize admission.
    if (m.source_gate === 'unknown') requireThat(m.selection_state === 'undetermined' && m.logical_truth === 'unknown'
      && atoms.every(atom => atom.truth === 'unknown'));
    const groups = list(m.groups, 2).map(item => object(item, ['id', 'atom_ids', 'truth', 'false_atoms', 'unknown_atoms']));
    requireThat(groups.length === groupIds.length);
    groups.forEach((group, i) => {
      const definitionIds = expected.canonicalRule.any_of[i].all_of.map(condition => definitions.find(item => item.field === condition.field && item.op === condition.op && item.threshold === condition.threshold)!.id);
      requireThat(group.id === groupIds[i] && isTruth(group.truth) && sameValue(group.atom_ids, definitionIds));
      const falseRefs = references(group.false_atoms, definitionIds), unknownRefs = references(group.unknown_atoms, definitionIds);
      // These are indexes into reported atom states, not a recomputation of group truth.
      requireThat(sameValue(falseRefs, definitionIds.filter(id => atoms.find(atom => atom.id === id)?.truth === 'false'))
        && sameValue(unknownRefs, definitionIds.filter(id => atoms.find(atom => atom.id === id)?.truth === 'unknown')));
    });
    requireThat(sameValue(references(m.proof_groups, groupIds, 2), groups.filter(group => group.truth === 'true').map(group => group.id)));
  });
  const counts = object(r.counts, ['selected_members', 'selection', 'logical', 'evidence', 'source_gate', 'atoms', 'groups']);
  requireThat(counts.selected_members === members.length);
  namedCounts(counts.selection, ['selected', 'excluded', 'undetermined'], members, 'selection_state');
  namedCounts(counts.logical, ['true', 'false', 'unknown'], members, 'logical_truth');
  namedCounts(counts.source_gate, ['pass', 'unknown'], members, 'source_gate');
  namedCounts(counts.evidence, ['complete', 'partial'], members.map(member => ({ evidence: member.evidence_complete ? 'complete' : 'partial' })), 'evidence');
  for (const kind of ['atoms', 'groups'] as const) {
    const ids = kind === 'atoms' ? atomIds : groupIds, totals = object(counts[kind], ids);
    for (const id of ids) namedCounts(totals[id], ['true', 'false', 'unknown'], members.map(member => list(member[kind], 6).map(objectValue => object(objectValue)).find(item => item.id === id)!), 'truth');
  }
}
