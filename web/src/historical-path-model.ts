import { safeCode } from './api.ts';
import { Generation } from './model.ts';
import { explainResearch, researchReason } from './research-model.ts';
import type { HistoricalPathEnvelope, HistoricalPathRequest, HistoricalPathState, PathLedgerStatus } from './historical-path-types.ts';

export const PATH_METHOD_ID = 'historical-source-path-retrieval-v1';
export const PATH_RULES = { steps: 20, max_matches: 3, metric: 'source_ratio_squared_mean_v1',
  qualification_rule: 'strict_daily_groups_v1', display_rule: '12_significant_half_even_scientific_v1' } as const;
export const PATH_METHODS = ['path', 'endpoint', 'recent'] as const;
export const PATH_RESPONSE_LIMIT = 4 * 1024 * 1024;
const columns = ['start_index', 'reason', 'distance', 'endpoint_distance', 'path', 'endpoint', 'recent', 'first_invalid_index'];
const hex = /^[a-f0-9]{64}$/;
const code = /^[a-z][a-z0-9_]{0,79}$/;
const scientific = /^-?\d(?:\.\d{1,11})?[eE][+-]\d{1,3}$/;
const integer = (value: unknown, min = 0, max = 20_000): value is number => typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max;
export function isPathDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number), leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  return y > 0 && m >= 1 && m <= 12 && d >= 1 && d <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
}
export function buildHistoricalPathRequest(snapshotId: string, cutoff: string): HistoricalPathRequest {
  if (typeof snapshotId !== 'string' || !hex.test(snapshotId)) throw new Error('invalid_snapshot_id');
  if (!isPathDate(cutoff)) throw new Error('invalid_cutoff');
  return { path: `/api/research/path-match/${snapshotId}?${new URLSearchParams({ cutoff })}`, expected: { snapshotId, cutoff } };
}
function ensure(condition: unknown): asserts condition { if (!condition) throw new Error('invalid_path_match_response'); }
type Obj = Record<string, unknown>;
function object(value: unknown, keys?: readonly string[]): Obj {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value));
  const obj = value as Obj;
  if (keys) ensure(Object.keys(obj).length === keys.length && keys.every(key => Object.hasOwn(obj, key)));
  return obj;
}
function list(value: unknown, max = 20_000): unknown[] { ensure(Array.isArray(value) && value.length <= max); return value; }
function shown(value: unknown, nonnegative = false): value is string {
  return typeof value === 'string' && scientific.test(value) && Number.isFinite(Number(value)) && (Number(value) !== 0 || !/[1-9]/.test(value.split(/[eE]/)[0])) && (!nonnegative || Number(value) >= 0);
}
function safeJson(value: unknown, depth = 0): void {
  ensure(depth <= 12);
  if (value === null || typeof value === 'boolean') return;
  if (typeof value === 'number') { ensure(Number.isFinite(value)); return; }
  if (typeof value === 'string') { ensure(value.length <= 4096); return; }
  if (Array.isArray(value)) { ensure(value.length <= 20_000); value.forEach(item => safeJson(item, depth + 1)); return; }
  const obj = object(value); ensure(Object.keys(obj).length <= 128);
  for (const [key, child] of Object.entries(obj)) { ensure(key.length <= 128); safeJson(child, depth + 1); }
}
function rules(value: unknown): void {
  const obj = object(value, Object.keys(PATH_RULES));
  for (const [key, rule] of Object.entries(PATH_RULES)) ensure(obj[key] === rule);
}
function positivePrice(value: unknown): boolean {
  if (typeof value !== 'string' || value.length > 4096) return false;
  const match = value.match(/^\+?(\d+)(?:\.(\d+))?(?:[eE]([+-]?\d{1,4}))?$/);
  if (!match) return false;
  const rawDigits = (match[1] + (match[2] ?? '')).replace(/^0+/, '');
  const digits = rawDigits.replace(/0+$/, '');
  if (!digits) return false;
  // Match decimal_value: insignificant trailing zeroes do not enlarge scale.
  const unitsExponent = Number(match[3] ?? 0) + 18 - (match[2]?.length ?? 0) + rawDigits.length - digits.length;
  if (unitsExponent < 0 || digits.length + unitsExponent > 38) return false;
  const units = BigInt(digits) * 10n ** BigInt(unitsExponent);
  return units > 0n && units < 10n ** 38n;
}
const daySpan = (start: string, end: string) => (Date.parse(`${end}T00:00:00Z`) - Date.parse(`${start}T00:00:00Z`)) / 86_400_000;
function windowValue(value: unknown, groups: string[]): Obj {
  const w = object(value);
  ensure(integer(w.start_index, 0, groups.length - 21) && w.end_index === w.start_index + 20
    && w.start_date === groups[w.start_index] && w.end_date === groups[w.end_index as number]
    && w.calendar_days === daySpan(w.start_date as string, w.end_date as string));
  const prices = list(w.prices, 21), ordinals = list(w.ordinals, 21), path = list(w.relative_path, 21), differences = list(w.differences, 21);
  ensure(prices.length === 21 && prices.every(positivePrice) && ordinals.length === 21 && ordinals.every(item => integer(item, 1, Number.MAX_SAFE_INTEGER))
    && new Set(ordinals).size === 21 && path.length === 21 && path.every(item => shown(item))
    && differences.length === 21 && differences.every(item => shown(item)) && Number(path[0]) === 0 && Number(differences[0]) === 0
    && shown(w.endpoint_change) && w.endpoint_change === path[20] && shown(w.distance, true) && shown(w.endpoint_distance, true));
  const dd = object(w.max_drawdown, ['value', 'peak_step', 'trough_step']);
  ensure(shown(dd.value, true) && Number(dd.value) <= 1 && integer(dd.peak_step, 0, 20) && integer(dd.trough_step, dd.peak_step, 20));
  const diff = object(w.max_point_difference, ['value', 'step']); ensure(shown(diff.value, true) && integer(diff.step, 0, 20));
  return w;
}
/** Bind and validate the server contract; never rerank rounded values or recompute the research. */
export function assertHistoricalPathReply(value: unknown, expected: HistoricalPathRequest['expected']): asserts value is HistoricalPathEnvelope {
  safeJson(value);
  const report = object(value, ['method_id', 'analysis_id', 'inputs', 'parameters', 'mode', 'limitations', 'result']);
  ensure(report.method_id === PATH_METHOD_ID && typeof report.analysis_id === 'string' && hex.test(report.analysis_id) && report.mode === 'retrospective');
  const inputs = list(report.inputs, 1); ensure(inputs.length === 1);
  const input = object(inputs[0], ['snapshot_id', 'query_id']);
  // Full-prefix identity intentionally differs from a bounded chart's query_id.
  ensure(input.snapshot_id === expected.snapshotId && typeof input.query_id === 'string' && hex.test(input.query_id));
  const parameters = object(report.parameters, ['cutoff', 'model']); ensure(parameters.cutoff === expected.cutoff); rules(parameters.model);
  const limitations = list(report.limitations, 128); ensure(limitations.length > 0 && limitations.every(item => typeof item === 'string' && code.test(item)));
  const result = object(report.result); rules(result.parameters); ensure(result.cutoff === expected.cutoff);
  ensure(result.qualification === 'conditional_source_close_paths' && result.selection_rule === 'three_greedy_nonoverlapping_windows_not_global_optimum'
    && result.ranking_rule === 'exact_distance_then_earlier_start' && result.difference_direction === 'query_minus_candidate' && result.display_policy === 'rounded_display_exact_ranking');
  const unknowns = list(result.unknowns, 32);
  for (const item of ['adjustment', 'corporate_actions', 'calendar', 'coverage', 'bar_closure', 'known_at']) ensure(unknowns.includes(item));
  ensure(unknowns.every(item => typeof item === 'string' && code.test(item)));
  if (result.nonprice_check_failures !== undefined) for (const [name, count] of Object.entries(object(result.nonprice_check_failures))) ensure(/^[a-z][a-z0-9_.]{0,79}$/.test(name) && integer(count, 1, 20_001));
  const identity = object(result.identity); for (const field of ['symbol', 'code', 'venue', 'market', 'qualification']) ensure(typeof identity[field] === 'string' && (identity[field] as string).length > 0);
  const groups = list(result.groups) as string[];
  ensure(groups.length >= 21 && groups.every((day, i) => isPathDate(day) && day <= expected.cutoff && (i === 0 || day > groups[i - 1])) && groups.at(-1) === expected.cutoff);
  const query = windowValue(result.query, groups); ensure(query.end_date === expected.cutoff && query.end_index === groups.length - 1
    && Number(query.distance) === 0 && Number(query.endpoint_distance) === 0 && Number(object(query.max_point_difference).value) === 0
    && (query.differences as string[]).every(item => Number(item) === 0));
  const windows = list(result.windows, 9).map(item => windowValue(item, groups));
  const windowIds = new Set(windows.map(w => w.start_index)); ensure(windowIds.size === windows.length && windows.every(w => (w.end_index as number) < (query.start_index as number)));
  const selections = object(result.selections, PATH_METHODS), counts = object(result.counts, PATH_METHODS);
  const picked = new Set<number>();
  for (const method of PATH_METHODS) {
    const ids = list(selections[method], 3); ensure(ids.every(id => integer(id) && windowIds.has(id)) && new Set(ids).size === ids.length);
    for (const [i, id] of ids.entries()) { ensure(ids.every((other, j) => i === j || Math.abs((other as number) - (id as number)) > 20)); picked.add(id as number); }
    const c = object(counts[method], ['total', 'valid', 'invalid', 'selected', 'overlap_excluded', 'remaining']);
    ensure(Object.values(c).every(v => integer(v)) && c.total === (c.valid as number) + (c.invalid as number)
      && c.valid === (c.selected as number) + (c.overlap_excluded as number) + (c.remaining as number) && c.selected === ids.length);
  }
  ensure(picked.size === windowIds.size);
  ensure(JSON.stringify(result.ledger_columns) === JSON.stringify(columns));
  const ledger = list(result.ledger); ensure(ledger.length === Math.max(0, (query.start_index as number) - 20));
  const actual = Object.fromEntries(PATH_METHODS.map(method => [method, { total: ledger.length, valid: 0, invalid: 0, selected: 0, overlap_excluded: 0, remaining: 0 }]));
  ledger.forEach((entry, index) => {
    const row = list(entry, 8); ensure(row.length === 8 && row[0] === index);
    const valid = row[1] === null;
    ensure(valid ? shown(row[2], true) && shown(row[3], true) && row[7] === null
      : typeof row[1] === 'string' && code.test(row[1]) && row[2] === null && row[3] === null && integer(row[7], index, index + 20));
    PATH_METHODS.forEach((method, offset) => {
      const ids = selections[method] as number[], selectedRank = ids.indexOf(index), overlap = ids.find(id => Math.abs(id - index) <= 20);
      const state = row[offset + 4] as PathLedgerStatus;
      if (!valid) { ensure(state === null); actual[method].invalid++; return; }
      actual[method].valid++;
      ensure(Array.isArray(state) && state.length === 2);
      if (selectedRank >= 0) { ensure(state[0] === selectedRank + 1 && state[1] === null); actual[method].selected++; }
      else if (overlap !== undefined) { ensure(state[0] === null && state[1] === overlap); actual[method].overlap_excluded++; }
      else { ensure(state[0] === null && state[1] === null); actual[method].remaining++; }
    });
    const detailed = windows.find(w => w.start_index === index);
    if (detailed) ensure(valid && detailed.distance === row[2] && detailed.endpoint_distance === row[3]);
  });
  for (const method of PATH_METHODS) for (const [key, count] of Object.entries(actual[method])) ensure(object(counts[method])[key] === count);
}

export async function fetchHistoricalPath(request: HistoricalPathRequest, signal: AbortSignal, fetcher: typeof fetch = fetch): Promise<HistoricalPathEnvelope> {
  const response = await fetcher(request.path, { method: 'GET', signal, cache: 'no-store', credentials: 'same-origin' });
  if (!response.body) throw new Error('invalid_path_match_response');
  const reader = response.body.getReader(), chunks: Uint8Array[] = []; let size = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read(); if (done) break;
      size += value.byteLength;
      if (size > PATH_RESPONSE_LIMIT) { void reader.cancel().catch(() => {}); throw new Error('path_match_response_limit'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  let value: unknown;
  try { value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)); } catch { throw new Error('invalid_path_match_response'); }
  if (!response.ok) { const error = value && typeof value === 'object' && !Array.isArray(value) ? (value as Obj).error : null; throw new Error(typeof error === 'string' && code.test(error) ? error : 'invalid_path_match_response'); }
  assertHistoricalPathReply(value, request.expected); return value;
}

export const emptyHistoricalPathState = (): HistoricalPathState => ({ status: 'idle', report: null, error: null, selected: null, rejected: false });
/** The component and tests share cancellation, supersession and selection invalidation. */
export class HistoricalPathController {
  state = emptyHistoricalPathState();
  private generation = new Generation(); private aborter: AbortController | null = null; private disposed = false;
  private onState: (state: HistoricalPathState) => void;
  constructor(onState: (state: HistoricalPathState) => void) { this.onState = onState; }
  private publish(state: HistoricalPathState): void { this.state = state; if (!this.disposed) this.onState(state); }
  private reset(status: HistoricalPathState['status']): void { this.generation.invalidate(); this.aborter?.abort(); this.aborter = null; this.publish({ ...emptyHistoricalPathState(), status }); }
  invalidate(): void { if (!this.disposed) this.reset('dirty'); }
  cancel(): void { if (!this.disposed) this.reset('cancelled'); }
  dispose(): void { if (!this.disposed) { this.disposed = true; this.reset('cancelled'); } }
  select(start: number | null, rejected = false): void {
    if (this.disposed || this.state.status !== 'ready' || !this.state.report) return;
    if (start !== null && !this.state.report.result.windows.some(w => w.start_index === start)) return;
    this.publish({ ...this.state, selected: start, rejected: start === null && rejected });
  }
  async run(snapshotId: string, cutoff: string, loader = fetchHistoricalPath): Promise<void> {
    if (this.disposed) return;
    this.reset('loading'); const generation = this.generation.current(), aborter = new AbortController(); this.aborter = aborter;
    const current = () => !this.disposed && this.generation.isCurrent(generation);
    try {
      const request = buildHistoricalPathRequest(snapshotId, cutoff), report = await loader(request, aborter.signal);
      if (current()) this.publish({ status: 'ready', report, error: null, selected: null, rejected: false });
    } catch (error) { if (current()) this.publish({ ...emptyHistoricalPathState(), status: 'error', error }); }
    finally { if (current()) this.aborter = null; }
  }
}

/** Decimal point movement only: no float rounding is applied to server displays. */
export function formatPathPercent(value: string): string {
  if (!shown(value)) return '—';
  const [mantissa, exponent] = value.split(/[eE]/), negative = mantissa.startsWith('-'), digits = mantissa.replace('-', '').replace('.', '');
  if (!/[1-9]/.test(digits)) return '0%';
  const power = Number(exponent) + 2, sign = negative ? '−' : '';
  if (power < -6 || power > 12) return `${sign}${mantissa.replace('-', '')}e${power >= 0 ? '+' : ''}${power}%`;
  const point = power + 1;
  const decimal = point <= 0 ? `0.${'0'.repeat(-point)}${digits}` : point >= digits.length ? digits + '0'.repeat(point - digits.length) : `${digits.slice(0, point)}.${digits.slice(point)}`;
  return `${sign}${decimal.includes('.') ? decimal.replace(/0+$/, '').replace(/\.$/, '') : decimal}%`;
}
const reasons: Record<string, string> = {
  invalid_path_match_response: '路径检索响应与当前输入或格式约定不符，结果已清空',
  path_match_response_limit: '路径检索响应超过4 MiB预算，整份结果未显示',
  path_match_row_limit: '完整研究前缀超过20,000行预算，未裁剪历史',
  path_match_numeric_failure: '精确数值核验未通过，整份检索已停止',
  path_query_invalid: '查询窗口含无效来源组，请核对原记录',
  path_history_insufficient: '截止前不足21个来源组，无法形成查询窗口',
  path_cutoff_missing: '来源中缺少所选终点日期，未回退到较早记录',
  path_numerical_failure: '精确数值核验未通过，整份检索已停止',
  path_result_limit: '路径检索结果超过预算，整份结果未显示',
  path_unreadable_date: '存在无法定位日期的来源记录，无法确定完整历史前缀',
  path_source_check_failed: '来源级检查未通过，当前数据不能用于路径检索',
  invalid_source_checks: '来源检查结构无效，请核对原始数据版本',
  source_price_check_failed: '来源价格检查未通过',
  source_structure_failed: '来源记录结构检查未通过',
  source_position_check_failed: '来源日期或记录顺序检查未通过',
  unclassified_source_failure: '存在未分类的来源检查失败',
  source_ratio_paths_not_prediction: '来源路径距离未验证预测能力',
  closest_is_not_necessarily_similar: '排名最接近不保证足够相似',
  greedy_nonoverlap_not_independent_samples: '各栏分别贪心去重，候选之间不视为独立金融样本',
};
export function pathReason(value: string): string { return reasons[value] ?? researchReason(value); }
export function explainHistoricalPath(error: unknown): string { const value = safeCode(error); return reasons[value] ? `${reasons[value]}（${value}）` : explainResearch(error); }
