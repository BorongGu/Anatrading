/** 051: validate a bounded complete report; no second Pearson calculation. */
import { jsonRequest, safeCode } from './api.ts';
import { canonicalJson, explainFilter } from './filter-model.ts';
import { validGroupDate } from './group-endpoint-model.ts';
import { peerDisplay, peerReason } from './peer-neighbor-model.ts';
import type { PeerCorrelation, PeerMember } from './peer-neighbor-model.ts';
import type { SourceEndpoint } from './two-group-model.ts';
export const GROUP_PAIR_METHOD = 'complete-group-pairs-simple-v1';
export const GROUP_PAIR_RULE = 'all-member-grid-60x2-exact-pairs-v1';
const rules = {
  intervals_per_window: 60, source_endpoints: 121, transform: 'source_simple_change',
  anchor: 'all_member_source_dates_exact_cutoff', panel: 'all_selected_complete',
  integer_bits: 65536, display_precision: 50, display_rounding: 'ROUND_HALF_EVEN',
  pairs: 'all_unique_snapshot_id_order', events: 'not_supported'
};
const scope = Object.fromEntries(Object.entries({
  asset_type: 'stock',
  share_class: 'A_share',
  price_currency: 'CNY',
  daily_label_basis: 'CN_exchange_date'
}).map(([key, value]) => [key, {
  value,
  evidence_status: 'assumed'
}]));
const limitations = {
  economic_return_qualified: false,
  total_return_qualified: false,
  historical_availability: 'unverified',
  closure: 'unknown',
  trading_calendar: 'unknown',
  corporate_action_coverage: 'unknown',
  halt_event_coverage: 'unknown',
  adjustment: 'request_declared_semantics_unverified',
  source_integrity: 'trusted_store_boundary',
  membership: 'current_members_retrospective',
  source_semantics: 'unverified',
  statistical_or_trading_advantage: 'not_evaluated',
  user_efficiency: 'not_evaluated',
  windows: 'nonoverlapping_changes_shared_price_boundary',
  log_correlation_equivalent: false
};


export interface GroupPairMember extends Omit<PeerMember, 'role' | 'date_mismatch'> {
  date_array: string[];
  constant: Record<'previous' | 'current', boolean | null>;
}
export interface GroupPairCell { correlation: PeerCorrelation | null; reason: 'source_panel_unavailable' | 'constant_source_change' | null; constant_members: string[] }
export interface GroupPair { left_snapshot_id: string; right_snapshot_id: string; previous: GroupPairCell; current: GroupPairCell }
export interface GroupPairWindow { start: string | null; end: string | null; intervals: 60; total: number; available: number; unavailable: number }
export interface GroupPairReport {
  method_id: string; rule_version: string; source_rule_version: string; analysis_id: string;
  parameters: { cutoff: string; rules: typeof rules }; scope: typeof scope; limitations: typeof limitations; events: unknown[];
  used_dates: string[]; grid_reasons: string[]; members: GroupPairMember[]; pairs: GroupPair[];
  windows: Record<'previous' | 'current', GroupPairWindow>;
  counts: { selected: number; pairs: number; source_qualified: number; panel_complete: number };
  source_panel_complete: boolean; reasons: string[]; status: 'complete' | 'partial' | 'unavailable';
}
export interface GroupPairExpected { ids: string[]; cutoff: string }
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const integer = (v: unknown, max = 20000): v is number => typeof v === 'number' &&
  Number.isSafeInteger(v) &&
  v >= 0 &&
  v <= max;
const same = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);

function ensure(v: unknown): asserts v {
  if (!v) throw new Error('invalid_group_pair_response');
}

function keys(v: unknown, names: string[]) {
  ensure(v !== null && typeof v === 'object' && !Array.isArray(v));
  ensure(Object.keys(v).length === names.length && names.every(k => Object.hasOwn(v, k)));
}

function codes(v: unknown, allowed?: string[]): asserts v is string[] {
  ensure(Array.isArray(v) &&
    v.length <= 64 &&
    v.every(x => typeof x === 'string' &&
    /^[a-z][a-z0-9_.]{0,79}$/.test(x) &&
    (!allowed || allowed.includes(x))) &&
    new Set(v).size === v.length);
}

function rawCodes(v: unknown): asserts v is string[] {
  ensure(Array.isArray(v) && v.every(x => typeof x === 'string' && x.trim().length>0) && new Set(v).size === v.length);
}

function sourceSymbol(v: unknown, qualified: boolean): v is string {
  return typeof v === 'string' &&
    (qualified?/^[0-9]{6}\.(SH|SZ)$/: /^[A-Z0-9][A-Z0-9.-]{0,31}\.(SH|SZ|BJ|HK|NYSE|NASDAQ|AMEX)$/).test(v);
}

function dates(v: unknown, max: number): asserts v is string[] {
  ensure(Array.isArray(v) &&
    v.length <= max &&
    v.every((d, i) => typeof d === 'string' &&
    validGroupDate(d) &&
    (!i || d>v[i -1])));
}

const sourceReasons = [
  'known_negative_source',
  'source_identity_conflict',
  'source_adjustment_conflict',
  'source_structure_failed',
  'unsupported_source_check',
  'scope_conflict',
  'unsupported_source',
  'unsupported_period',
];
const endpointReasons = [
  'duplicate_endpoint',
  'unlocated_endpoint',
  'missing_endpoint',
  'missing_ohlc',
  'invalid_price',
  'invalid_ohlc',
  'endpoint_price_check_failed',
];
const memberReasons = [
  'history_insufficient', 'cutoff_missing',
  'endpoint_integrity_unknown',
  'global_source_conflict',
  'local_source_conflict',
  'unclassified_source_failure',
  'extra_source_dates',
  ...endpointReasons,
];
function endpoint(p: SourceEndpoint, day: string) {
  keys(p, ['date', 'ordinal', 'close_token', 'close_exact', 'reasons']);
  ensure(p.date === day && (p.ordinal === null || integer(p.ordinal, Number.MAX_SAFE_INTEGER) && p.ordinal>0));
  ensure(p.close_token === null || typeof p.close_token === 'string' && p.close_token.length <= 128);
  ensure(p.close_exact === null || typeof p.close_exact === 'string' &&
    p.close_exact.length <= 40 &&
    /^-?(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(p.close_exact) &&
    p.close_exact !== '-0');
  codes(p.reasons, endpointReasons);
}

function correlation(v: PeerCorrelation) {
  keys(v, ['estimate', 'display', 'sign', 'exact_boundary']);
  // Bounded exact decimal validation, never Number underflow.
  try { ensure(v.display === peerDisplay(v.estimate)); } catch { ensure(false); }
  const sign = v.estimate === '0' ? 'zero' : v.estimate.startsWith('-') ? 'negative' : 'positive';
  ensure(v.sign === sign && ['positive_one','negative_one','zero','none'].includes(v.exact_boundary));
  ensure((v.exact_boundary === 'zero') === (sign === 'zero'));
  if (v.exact_boundary === 'positive_one') ensure(v.estimate === '1E+0');
  if (v.exact_boundary === 'negative_one') ensure(v.estimate === '-1E+0');
  // A non-boundary value may round to +/-1 at the finite estimate precision.
}
function positivePrice(value: string | null) {
  ensure(typeof value === 'string' && /^(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(value));
  const [whole, fraction = ''] = value.split('.');
  const price = BigInt(whole + fraction.padEnd(18, '0'));
  ensure(price > 0n && price < 10n ** 38n);
  return price;
}
function constantPrices(member: GroupPairMember, offset: number) {
  const prices = member.endpoints!.slice(offset, offset + 61).map(p => positivePrice(p.close_exact));
  const difference = prices[1] - prices[0];
  return prices.slice(1).every((p, i) => (p - prices[i]) * prices[0] === difference * prices[i]);
}
function anomalies(member: GroupPairMember, cutoff: string) {
  const a = member.anomalies;
  keys(a, ['total','counts','examples','truncated']); ensure(a);
  ensure(integer(a.total) && Array.isArray(a.examples) && a.examples.length === Math.min(20,a.total) && a.truncated === (a.total > 20));
  ensure(a.counts !== null && typeof a.counts === 'object' && !Array.isArray(a.counts));
  ensure(Object.entries(a.counts).every(([code,count]) => code.trim().length > 0 && integer(count,a.total) && count > 0));
  const ordinals = new Set<number>(), counted: Record<string,number> = Object.create(null);
  for (const e of a.examples) {
    keys(e,['date','ordinal','scope','codes']);
    ensure(integer(e.ordinal,Number.MAX_SAFE_INTEGER) && e.ordinal > 0 && !ordinals.has(e.ordinal)); ordinals.add(e.ordinal);
    ensure(e.date === null || typeof e.date === 'string' && validGroupDate(e.date));
    ensure(e.scope === (e.date === null ? 'unknown' : !member.date_array.length ? 'window_unavailable' : e.date >= member.date_array[0] && e.date <= member.date_array.at(-1)! ? 'inside_interval' : 'outside_interval'));
    rawCodes(e.codes); ensure(e.codes.length > 0);
    for (const code of e.codes) { counted[code] = (counted[code] ?? 0)+1; ensure(Object.hasOwn(a.counts,code) && a.counts[code] >= counted[code]); }
    if (e.scope === 'inside_interval' || e.scope === 'unknown') for (const code of ['local_source_conflict','unclassified_source_failure','endpoint_integrity_unknown']) {
      if (e.codes.includes(code)) ensure(member.reasons.includes(code));
    }
  }
  if (!a.truncated) ensure(same(counted,a.counts));
  for (const code of ['global_source_conflict','endpoint_integrity_unknown']) if (Object.hasOwn(a.counts,code)) ensure(member.reasons.includes(code));
  if (['source_code','instrument_identity','declared_instrument','declared_venue','source_adjustflag','source_adjustment','declared_adjustment','structure','known_negative_sample'].some(c => Object.hasOwn(a.counts,c))) ensure(member.reasons.includes('global_source_conflict'));
  ensure(member.date_array.every(d => d <= cutoff));
}
export function assertGroupPairs(value: unknown, expected: GroupPairExpected): asserts value is GroupPairReport {
  const r = value as GroupPairReport;
  keys(r,['method_id','rule_version','source_rule_version','analysis_id','parameters','scope','limitations','events','used_dates','grid_reasons','members','pairs','windows','counts','source_panel_complete','reasons','status']);
  ensure(new TextEncoder().encode(canonicalJson(r)).length <= 2*1024*1024);
  ensure(r.method_id === GROUP_PAIR_METHOD && r.rule_version === GROUP_PAIR_RULE && r.source_rule_version === 'peer-relative-eligibility-v1' && hash(r.analysis_id));
  keys(r.parameters,['cutoff','rules']); ensure(r.parameters.cutoff === expected.cutoff && validGroupDate(expected.cutoff) && same(r.parameters.rules,rules));
  ensure(same(r.scope,scope) && same(r.limitations,limitations) && Array.isArray(r.events) && r.events.length === 0);
  const ids = [...expected.ids].sort();
  ensure(ids.length >= 2 && ids.length <= 50 && ids.every(hash) && new Set(ids).size === ids.length);
  ensure(Array.isArray(r.members) && same(r.members.map(m => m.snapshot_id),ids));
  const symbols = new Set<string>(), queries = new Set<string>(), batches = new Set<string>();
  for (const m of r.members) {
    keys(m,['symbol','snapshot_id','batch_id','query_id','source_qualified','evaluation','panel_complete','date_array','endpoints','anomalies','reasons','constant']);
    ensure(hash(m.batch_id) && hash(m.query_id) && !queries.has(m.query_id) && !batches.has(m.batch_id)); queries.add(m.query_id); batches.add(m.batch_id);
    ensure(typeof m.source_qualified === 'boolean' && typeof m.panel_complete === 'boolean');
    ensure(m.symbol === null || sourceSymbol(m.symbol,m.source_qualified) && !symbols.has(m.symbol)); if (m.symbol !== null) symbols.add(m.symbol);
    dates(m.date_array,121); keys(m.constant,['previous','current']);
    if (!m.source_qualified) {
      codes(m.reasons,sourceReasons);
      ensure(m.reasons.length === 1 && m.evaluation === 'not_evaluated' && !m.panel_complete && m.endpoints === null && m.anomalies === null && m.date_array.length === 0);
      if (m.reasons[0] === 'source_identity_conflict') ensure(m.symbol === null);
    } else {
      ensure(m.symbol !== null && m.evaluation === 'evaluated'); codes(m.reasons,memberReasons);
      ensure(Array.isArray(m.endpoints) && m.endpoints.length === m.date_array.length);
      m.endpoints.forEach((p,i) => endpoint(p,m.date_array[i]));
      const ordinals = m.endpoints.flatMap(p => p.ordinal === null ? [] : [p.ordinal]); ensure(new Set(ordinals).size === ordinals.length);
      ensure(m.endpoints.every(p => p.reasons.every(code => m.reasons.includes(code))));
      ensure(m.reasons.includes('history_insufficient') === (m.date_array.length < 121));
      ensure(m.reasons.includes('cutoff_missing') === (m.date_array.at(-1) !== expected.cutoff));
      ensure(m.panel_complete === (m.reasons.length === 0));
      if (m.panel_complete) m.endpoints.forEach(p => { ensure(p.ordinal !== null && p.reasons.length === 0); positivePrice(p.close_exact); });
      anomalies(m,expected.cutoff);
    }
  }
  dates(r.used_dates,121); codes(r.grid_reasons,['member_grid_unavailable','member_date_arrays_differ']);
  const gridUnavailable = r.members.some(m => m.date_array.length !== 121 || m.date_array.at(-1) !== expected.cutoff);
  const gridMismatch = !gridUnavailable && r.members.some(m => !same(m.date_array,r.members[0].date_array));
  ensure(same(r.grid_reasons,gridUnavailable ? ['member_grid_unavailable'] : gridMismatch ? ['member_date_arrays_differ'] : []));
  ensure(same(r.used_dates,r.grid_reasons.length ? [] : r.members[0].date_array));
  const n = ids.length, total = n*(n-1)/2;
  keys(r.counts,['selected','pairs','source_qualified','panel_complete']);
  ensure(same(r.counts,{selected:n,pairs:total,source_qualified:r.members.filter(m => m.source_qualified).length,panel_complete:r.members.filter(m => m.panel_complete).length}));
  ensure(r.source_panel_complete === (r.used_dates.length === 121 && r.members.every(m => m.panel_complete)));
  ensure(same(r.reasons,r.source_panel_complete ? [] : ['source_panel_unavailable']));
  for (const m of r.members) for (const [name,offset] of [['previous',0],['current',60]] as const) ensure(m.constant[name] === (r.source_panel_complete ? constantPrices(m,offset) : null));
  ensure(Array.isArray(r.pairs) && r.pairs.length === total);
  const members = new Map(r.members.map(m => [m.snapshot_id,m])); let index = 0;
  for (let i=0;i<n;i++) for (let j=i+1;j<n;j++) {
    const p = r.pairs[index++]; keys(p,['left_snapshot_id','right_snapshot_id','previous','current']);
    ensure(p.left_snapshot_id === ids[i] && p.right_snapshot_id === ids[j]);
    for (const name of ['previous','current'] as const) {
      const c = p[name]; keys(c,['correlation','reason','constant_members']);
      const constants = r.source_panel_complete ? [ids[i],ids[j]].filter(id => members.get(id)!.constant[name]) : [];
      ensure(same(c.constant_members,constants));
      const reason = !r.source_panel_complete ? 'source_panel_unavailable' : constants.length ? 'constant_source_change' : null;
      ensure(c.reason === reason);
      if (reason !== null) ensure(c.correlation === null); else { ensure(c.correlation !== null); correlation(c.correlation); }
    }
  }
  keys(r.windows,['previous','current']); let availableTotal = 0;
  for (const [name,offset] of [['previous',0],['current',60]] as const) {
    const w = r.windows[name]; keys(w,['start','end','intervals','total','available','unavailable']);
    const available = r.pairs.filter(p => p[name].correlation !== null).length; availableTotal += available;
    ensure(same(w,{start:r.used_dates[offset] ?? null,end:r.used_dates[offset+60] ?? null,intervals:60,total,available,unavailable:total-available}));
  }
  ensure(r.status === (availableTotal === 2*total ? 'complete' : availableTotal ? 'partial' : 'unavailable'));
}
export async function verifyGroupPairIdentity(r: GroupPairReport) {
  const identity = { method_id:r.method_id,rule_version:r.rule_version,source_rule_version:r.source_rule_version,
    parameters:r.parameters,sources:r.members.map(({symbol,snapshot_id,batch_id,query_id,date_array}) => ({symbol,snapshot_id,batch_id,query_id,date_array})),
    used_dates:r.used_dates,scope:r.scope,limitations:r.limitations,events:r.events };
  const digest = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonicalJson(identity)));
  ensure(Array.from(new Uint8Array(digest),v => v.toString(16).padStart(2,'0')).join('') === r.analysis_id);
}
export function groupPairRequest(expected: GroupPairExpected) {
  if (expected.ids.length < 2 || expected.ids.length > 50 || !expected.ids.every(hash) || new Set(expected.ids).size !== expected.ids.length) throw new Error('research_member_limit');
  if (!validGroupDate(expected.cutoff)) throw new Error('invalid_dates');
  const copy = {ids:[...expected.ids].sort(),cutoff:expected.cutoff};
  return {path:`/api/research/group-pairs?${new URLSearchParams({snapshot_ids:copy.ids.join(','),cutoff:copy.cutoff})}`,expected:copy};
}
export async function fetchGroupPairs(request: ReturnType<typeof groupPairRequest>, signal: AbortSignal) {
  const result = await jsonRequest<unknown>(request.path,{signal});
  assertGroupPairs(result,request.expected); await verifyGroupPairIdentity(result); return result;
}
const explanations: Record<string,string> = {
  invalid_group_pair_response:'全成对响应与输入或格式约定不符，结果已清空',
  group_pair_result_limit:'完整成对结果超过2MiB，本次整组未发布',
  member_grid_unavailable:'有成员未具备截止当日完整121日期组，未回退或补足',
  member_date_arrays_differ:'各成员121个来源日期数组不同，未取交集',
  history_insufficient:'截止及以前不足121个来源日期组',
  cutoff_missing:'本成员缺少指定截止日记录',
};
export const groupPairReason = (code: string) => Object.hasOwn(explanations, code) ? explanations[code] : peerReason(code);
export function explainGroupPairError(error: unknown) {
  const code = safeCode(error); return Object.hasOwn(explanations, code) ? `${explanations[code]}（${code}）` : ['peer_neighbor_integer_limit', 'peer_neighbor_display_failure', 'peer_neighbor_arithmetic_failure'].includes(code) ? `精确相关计算失败，整组未发布（${code}）` : explainFilter(error);
}
