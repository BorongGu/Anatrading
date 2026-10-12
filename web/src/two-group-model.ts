import { canonicalJson, explainFilter } from './filter-model.ts';
import { jsonRequest, safeCode } from './api.ts';
export const TWO_GROUP_METHOD = 'two-group-frozen-source-v1';
export interface ExplanationModel {
  baseline: number; contributions: number[]; explained: number; residual: number;
  gamma: number[]; factor_mean: number[]; factor_sd: number[]; current_factor: number[];
  current_z: number[]; rank_ratio: number; tolerance: number; within_resolution: boolean;
}
export interface SourceEndpoint { date: string; ordinal: number | null; close_token: string | null; close_exact: string | null; reasons: string[] }
export interface ExplanationMember {
  symbol: string; snapshot_id: string; query_id: string; group: 'A' | 'B';
  endpoints: { start: SourceEndpoint; end: SourceEndpoint }; training_endpoints: SourceEndpoint[];
  raw_change: number | null; source_complete: boolean; model: ExplanationModel | null; reasons: string[];
  anomalies: { total: number; counts: Record<string, number>; examples: { date: string | null; ordinal: number; scope: string; codes: string[] }[]; truncated: boolean };
}
export interface ExplanationReport {
  method_id: string; rule_version: string; analysis_id: string;
  parameters: { groups: { A: string[]; B: string[] }; current_start: string; current_end: string; rules: Record<string, string | number> };
  scope: Record<string, { value: string; evidence_status: string }>; events: unknown[];
  training_dates: string[]; members: ExplanationMember[];
  counts: { selected: number; source_complete: number; model_available: number };
  status: 'complete' | 'partial' | 'unavailable'; reasons: string[]; limitations: Record<string, string | boolean>;
}
export interface ExplanationExpected { ids: string[]; groups: { A: string[]; B: string[] }; start: string; end: string }
const hash = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const finite = (v: unknown) => typeof v === 'number' && Number.isFinite(v);
const strings = (v: unknown): v is string[] => Array.isArray(v) && v.every(x => typeof x === 'string');
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
const sorted = (a: string[]) => [...a].sort();
const rules = { training_intervals: 60, decimal_precision: 80, rounding: 'ROUND_HALF_EVEN', sd_min: 1e-12, rank_min: 1e-10, rank_gray: 1e-12, tolerance_absolute: 1e-10, tolerance_relative: 1e-8, exclusion: 'each_target_from_own_group_train_and_current', unit: 'source_log_change' };
function ensure(value: unknown): asserts value { if (!value) throw new Error('invalid_research_response'); }
function exactKeys(value: unknown, names: string[]) {
  ensure(value && typeof value === 'object' && !Array.isArray(value) && same(Object.keys(value).sort(), names.sort()));
}
function accurateSum(values: number[]) {
  let sum = 0, correction = 0;
  for (const value of values) { const next = sum + value; correction += Math.abs(sum) >= Math.abs(value) ? (sum - next) + value : (value - next) + sum; sum = next; }
  return sum + correction;
}
function endpoint(value: SourceEndpoint, day: string) {
  exactKeys(value, ['date', 'ordinal', 'close_token', 'close_exact', 'reasons']);
  ensure(value && value.date === day && (value.ordinal === null || Number.isInteger(value.ordinal) && value.ordinal > 0));
  ensure((value.close_token === null || typeof value.close_token === 'string') && (value.close_exact === null || typeof value.close_exact === 'string') && strings(value.reasons));
}
export function assertExplanation(value: unknown, expected: ExplanationExpected): asserts value is ExplanationReport {
  const r = value as ExplanationReport;
  exactKeys(r, ['method_id','rule_version','analysis_id','parameters','scope','events','training_dates','members','counts','status','reasons','limitations']);
  ensure(r && r.method_id === TWO_GROUP_METHOD && r.rule_version === 'decimal80-qr2-reference-v1' && hash(r.analysis_id));
  exactKeys(r.parameters, ['groups','current_start','current_end','rules']);
  exactKeys(r.parameters.groups, ['A','B']);
  ensure(r.parameters?.current_start === expected.start && r.parameters.current_end === expected.end);
  ensure(same(r.parameters.groups?.A, sorted(expected.groups.A)) && same(r.parameters.groups?.B, sorted(expected.groups.B)));
  ensure(Object.keys(r.parameters.rules ?? {}).length === Object.keys(rules).length && Object.entries(rules).every(([k, v]) => r.parameters.rules[k] === v));
  ensure(strings(r.training_dates) && r.training_dates.length <= 61 && r.training_dates.every((d, i) => /^\d{4}-\d{2}-\d{2}$/.test(d) && d <= expected.start && (!i || d > r.training_dates[i-1])));
  ensure(Array.isArray(r.members) && r.members.length === expected.ids.length && same(r.members.map(m => m.snapshot_id), expected.ids));
  ensure(new Set(r.members.map(m => m.symbol)).size === r.members.length && new Set(r.members.map(m => m.query_id)).size === r.members.length);
  ensure(strings(r.reasons) && Array.isArray(r.events) && r.events.length === 0);
  const limitations = {trading_calendar:'unknown', historical_availability:'unverified', membership:'current_members_retrospective', source_semantics:'unverified', adjustment:'request_declared_semantics_unverified', corporate_action_coverage:'unknown', economic_return_qualified:false, predictive_advantage:'not_evaluated', residuals:'mutually_dependent_not_noise_or_probability', risk_standardized:false};
  exactKeys(r.limitations, Object.keys(limitations));
  ensure(Object.entries(limitations).every(([key, value]) => r.limitations[key] === value));
  for (const [key, required] of Object.entries({asset_type: 'stock', share_class: 'A_share', price_currency: 'CNY', daily_label_basis: 'CN_exchange_date'})) ensure(r.scope?.[key]?.value === required && r.scope[key].evidence_status === 'assumed');
  for (const m of r.members) {
    exactKeys(m, ['symbol','snapshot_id','query_id','group','endpoints','training_endpoints','raw_change','source_complete','model','reasons','anomalies']);
    exactKeys(m.endpoints, ['start','end']);
    ensure(hash(m.snapshot_id) && hash(m.query_id) && typeof m.symbol === 'string' && strings(m.reasons) && typeof m.source_complete === 'boolean');
    ensure(m.group === (expected.groups.A.includes(m.snapshot_id) ? 'A' : 'B'));
    endpoint(m.endpoints?.start, expected.start); endpoint(m.endpoints?.end, expected.end);
    ensure(Array.isArray(m.training_endpoints) && m.training_endpoints.length === r.training_dates.length + 1);
    [...r.training_dates, expected.end].forEach((day, i) => endpoint(m.training_endpoints[i], day));
    ensure(m.raw_change === null || finite(m.raw_change));
    const qualified = (p: SourceEndpoint) => p.ordinal !== null && p.close_exact !== null && /^(?:[0-9]+)(?:\.[0-9]+)?$/.test(p.close_exact) && Number(p.close_exact) > 0 && p.reasons.length === 0;
    if (m.raw_change !== null) ensure(qualified(m.endpoints.start) && qualified(m.endpoints.end));
    if (m.source_complete) ensure(r.training_dates.length === 61 && r.training_dates.at(-1) === expected.start && m.training_endpoints.every(qualified) && same(m.training_endpoints[60], m.endpoints.start) && same(m.training_endpoints[61], m.endpoints.end));
    exactKeys(m.anomalies, ['total','counts','examples','truncated']);
    ensure(m.anomalies && Number.isInteger(m.anomalies.total) && m.anomalies.total >= 0 && Array.isArray(m.anomalies.examples) && m.anomalies.examples.length <= 20 && m.anomalies.examples.length === Math.min(m.anomalies.total, 20) && m.anomalies.truncated === (m.anomalies.total > 20));
    ensure(m.anomalies.total <= 20000 && m.anomalies.counts && typeof m.anomalies.counts === 'object' && !Array.isArray(m.anomalies.counts));
    ensure(Object.entries(m.anomalies.counts).every(([code, count]) => code.length > 0 && Number.isInteger(count) && count > 0 && count <= m.anomalies.total));
    const ordinals = new Set<number>();
    for (const example of m.anomalies.examples) {
      exactKeys(example, ['date','ordinal','scope','codes']);
      ensure(Number.isInteger(example.ordinal) && example.ordinal > 0 && !ordinals.has(example.ordinal)); ordinals.add(example.ordinal);
      ensure(example.date === null || /^\d{4}-\d{2}-\d{2}$/.test(example.date));
      ensure(example.scope === (example.date === null ? 'unknown' : example.date >= (r.training_dates[0] ?? expected.start) && example.date <= expected.end ? 'inside_interval' : 'outside_interval'));
      ensure(strings(example.codes) && example.codes.length > 0 && new Set(example.codes).size === example.codes.length && example.codes.every(code => m.anomalies.counts[code] > 0));
    }
    ensure(m.anomalies.total === 0 ? Object.keys(m.anomalies.counts).length === 0 : Object.keys(m.anomalies.counts).length > 0);
    if (m.model === null) { ensure(m.reasons.length > 0); continue; }
    const model = m.model;
    exactKeys(model, ['baseline','contributions','explained','residual','gamma','factor_mean','factor_sd','current_factor','current_z','rank_ratio','tolerance','within_resolution']);
    ensure(m.source_complete && finite(m.raw_change) && m.reasons.length === 0 && r.reasons.length === 0 && r.training_dates.length === 61 && r.training_dates.at(-1) === expected.start);
    for (const key of ['baseline', 'explained', 'residual', 'rank_ratio', 'tolerance'] as const) ensure(finite(model[key]));
    for (const key of ['contributions', 'gamma', 'factor_mean', 'factor_sd', 'current_factor', 'current_z'] as const) ensure(Array.isArray(model[key]) && model[key].length === 2 && model[key].every(finite));
    ensure(model.factor_sd.every(v => v > 1e-12) && model.rank_ratio > 1.01e-10 && model.rank_ratio <= 1);
    const expectedTolerance = 1e-10 + 1e-8 * Math.max(Math.abs(m.raw_change as number), Math.abs(model.explained), Math.abs(model.residual));
    ensure(Math.abs(model.tolerance - expectedTolerance) <= 1e-7 * expectedTolerance);
    ensure(model.contributions.every((contribution, i) => Math.abs(contribution - model.gamma[i]*model.current_z[i]) <= 8*Number.EPSILON*Math.max(1, Math.abs(contribution))));
    ensure(Math.abs(accurateSum([model.baseline, ...model.contributions]) - model.explained) <= model.tolerance && Math.abs((m.raw_change as number) - model.explained - model.residual) <= model.tolerance);
    ensure(model.within_resolution === (Math.abs(model.residual) <= model.tolerance));
  }
  exactKeys(r.counts, ['selected','source_complete','model_available']);
  const available = r.members.filter(m => m.model !== null).length;
  ensure(r.counts?.selected === r.members.length && r.counts?.source_complete === r.members.filter(m => m.source_complete).length && r.counts.model_available === available);
  ensure(!available || r.counts.source_complete === r.counts.selected);
  ensure(r.status === (available === 0 ? 'unavailable' : available === r.members.length ? 'complete' : 'partial'));
}
export function explanationRequest(expected: ExplanationExpected) {
  const ids = expected.ids;
  ensure(ids.length >= 4 && ids.length <= 50 && ids.every(hash) && new Set(ids).size === ids.length);
  const all = [...expected.groups.A, ...expected.groups.B];
  if (expected.groups.A.length < 2 || expected.groups.B.length < 2 || new Set(all).size !== ids.length || all.length !== ids.length || all.some(id => !ids.includes(id))) throw new Error('invalid_groups');
  const params = new URLSearchParams({ snapshot_ids: ids.join(','), group_a: expected.groups.A.join(','), group_b: expected.groups.B.join(','), current_start: expected.start, current_end: expected.end });
  return { path: `/api/research/two-group-explanation?${params}`, expected: structuredClone(expected) };
}
export async function verifyExplanationIdentity(report: ExplanationReport) {
  // Numeric protocol strings are shared with Python, avoiding JSON float spelling differences.
  const numerical_protocol = Object.fromEntries(Object.entries(rules).map(([key, value]) => [key, typeof value === 'number' && value !== 60 && value !== 80 ? ({'1e-12':'1e-12','1e-10':'1e-10','1e-8':'1e-08'} as Record<string,string>)[String(value)] : String(value)]));
  const identity = {method_id: report.method_id, rule_version: report.rule_version,
    parameters: {groups: report.parameters.groups, current_start: report.parameters.current_start, current_end: report.parameters.current_end}, numerical_protocol,
    sources: report.members.map(m => ({symbol:m.symbol,snapshot_id:m.snapshot_id,query_id:m.query_id})).sort((a,b) => a.symbol < b.symbol ? -1 : a.symbol > b.symbol ? 1 : 0), scope:report.scope,events:report.events};
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(identity)));
  ensure(Array.from(new Uint8Array(digest), v => v.toString(16).padStart(2,'0')).join('') === report.analysis_id);
}
export async function fetchExplanation(request: ReturnType<typeof explanationRequest>, signal: AbortSignal) {
  const report = await jsonRequest<unknown>(request.path, { signal }); assertExplanation(report, request.expected); await verifyExplanationIdentity(report); return report;
}
export function sortExplanation(members: ExplanationMember[], residual: boolean) {
  return residual ? [...members].sort((a, b) => a.model === null ? b.model === null ? a.symbol.localeCompare(b.symbol) : 1 : b.model === null ? -1 : Math.abs(b.model.residual)-Math.abs(a.model.residual) || a.symbol.localeCompare(b.symbol)) : members;
}
export const explanationReasons: Record<string, string> = {
  duplicate_member: '同一证券只能选择一个数据版本，请移除重复证券。',
  source_adjustment_conflict: '来源存在复权声明冲突，请核对未复权请求及源记录。',
  source_identity_conflict: '来源证券身份互相冲突，请核对数据版本和原始证券代码。',
  scope_conflict: '来源与本方法的A股、CNY或中国日线日期范围冲突。',
  local_source_conflict: '使用区间的记录存在证券身份、调整或结构冲突，请打开原记录核对。',
  invalid_price: '使用日期的价格无效或不为正数，无法计算对数变化。',
  invalid_ohlc: '使用日期的开高低收关系不成立，请核对原始记录。',
  endpoint_price_check_failed: '使用日期的价格核验未通过，或原文价格与精确值不一致。',
  missing_ohlc: '使用日期缺少开高低收字段。',
  source_structure_failed: '来源整体结构核验失败，请核对导入格式。',
  unsupported_source_check: '来源包含本方法尚未支持的整体核验失败。',
  known_negative_source: '来源已标记为已知反例，不能用于模型解释。',
  unclassified_source_failure: '使用区间存在尚未分类的来源核验失败，不能自动忽略。',
  research_row_limit: '完整来源超过每股20,000条或合计200,000条预算。请减少成员或选择较小的数据版本；修改截止日期不会缩减本方法的完整来源读取。',
  global_source_conflict: '来源存在身份、复权或结构反证，全部模型已关闭。',
  invalid_groups: '请将全部成员明确分入A/B两组，每组至少两只。', invalid_dates: '当前起点须早于终点。',
  explanation_result_limit: '解释结果超过2 MiB预算，请减少成员。', training_window_incomplete: '当前起点之前不足61个所选源日期点。',
  current_interval_not_adjacent: '当前端点缺失，或中间存在所选来源日期，不能跨过。', source_panel_unavailable: '完整来源面板不合格，全部模型已关闭。',
  factor_scale_too_small: '参考组训练变化近乎恒定，无法稳定拟合。', factor_rank_unavailable: '两个参考组训练变化近乎共线，无法分开解释。', numerical_unstable: '两种数值核对不一致或超出有限精度，未显示模型。',
  endpoint_integrity_unknown: '存在日期未知或互相冲突的记录，无法确认区间完整。', missing_endpoint: '所用日期缺少记录。', duplicate_endpoint: '所用日期存在重复记录。', unlocated_endpoint: '所用日期的标签不合格。',
  corporate_action_unresolved: '使用区间存在未解决的公司行动。', halted_endpoint_source_value: '使用日期存在已知停牌。', unsupported_source: '当前仅支持已核对格式的腾讯日线来源。',
};
export const explainReason = (code: string) => Object.hasOwn(explanationReasons, code) ? explanationReasons[code] : `来源或数值限制：${code}`;
export function explainExplanationError(error: unknown): string {
  const code = safeCode(error);
  return Object.hasOwn(explanationReasons, code) ? explanationReasons[code] : explainFilter(error);
}
