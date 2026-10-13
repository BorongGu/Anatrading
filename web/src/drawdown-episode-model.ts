/** Independently verify every summary against all admitted source endpoints. */
import { jsonRequest } from './api.ts';
import { canonicalJson } from './filter-model.ts';
import { validGroupDate } from './group-endpoint-model.ts';
export const DRAWDOWN_METHOD = 'observed-drawdown-episodes-v1';
export const DRAWDOWN_RULE = 'all-member-grid-last-peak-first-valley-exact-v1';
export interface DrawdownPoint {
  index: number;
  date: string;
  ordinal: string;
  close_exact: string;
}

export interface DrawdownEpisode {
  peak: DrawdownPoint;
  valley: DrawdownPoint;
  recovery: DrawdownPoint | null;
  observed_end: DrawdownPoint;
  depth_fraction: { numerator: string; denominator: string };
  depth_display: string;
  status: 'open' | 'recovered';
  peak_to_valley_intervals: number;
  peak_to_recovery_intervals: number | null;
  valley_to_recovery_intervals: number | null;
  observed_intervals: number;
  observed_is_lower_bound: boolean;
  underwater_observations: number;
}
interface Summary {
  episode_count: number | null;
  recovered_count: number | null;
  open_count: number | null;
  deepest: DrawdownEpisode | null;
  longest_observed: DrawdownEpisode | null;
  current_open: DrawdownEpisode | null;
}

export interface DrawdownMember extends Summary {
  snapshot_id: string;
  batch_id: string;
  query_id: string;
  symbol: string | null;
  source_qualified: boolean;
  window_qualified: boolean;
  comparison_available: boolean;
  date_array: string[] | null;
  window_length: number | null;
  cutoff_present: boolean | null;
  endpoints: DrawdownPoint[] | null;
  reasons: string[];
  anomalies: {
    total: number;
    counts: Record<string, number>;
    examples: {
      date: string | null;
      ordinal: string;
      scope: string;
      codes: string[];
    }[];
    examples_truncated: boolean;
  } | null;
}

export interface DrawdownReport {
  method_id: string;
  rule_version: string;
  source_rule_version: string;
  analysis_id: string;
  parameters: { cutoff: string; lookback: number };
  comparison_available: boolean;
  dates: string[] | null;
  counts: {
    selected: number;
    source_qualified: number;
    window_qualified: number;
    computable: number;
  };
  members: DrawdownMember[];
  limitations: Record<string, string | boolean>;
}

export interface DrawdownExpected {
  ids: string[];
  cutoff: string;
  lookback: number;
}

const summaryKeys = ['episode_count', 'recovered_count', 'open_count', 'deepest', 'longest_observed', 'current_open'] as const;
const limitations = {
  window_preceding_peak: 'unknown',
  trading_calendar: 'unknown',
  adjustment: 'request_declared_semantics_unverified',
  corporate_action_coverage: 'unknown',
  historical_availability: 'unverified',
  membership: 'current_members_retrospective',
  economic_return_qualified: false,
  recovery_prediction: 'not_provided',
  current_open_depth: 'deepest_so_far',
  interval_unit: 'source_interval'
};
const sourceReasons = [
  'known_negative_source',
  'source_identity_conflict',
  'source_adjustment_conflict',
  'source_structure_failed',
  'unsupported_source_check',
  'scope_conflict',
  'unsupported_source',
  'unsupported_period'
];
const localReasons = [
  'cutoff_missing',
  'history_insufficient',
  'date_grid_mismatch',
  'endpoint_integrity_unknown',
  'global_source_conflict',
  'local_source_conflict',
  'unclassified_source_failure',
  'duplicate_endpoint',
  'unlocated_endpoint',
  'missing_endpoint',
  'missing_ohlc',
  'invalid_price',
  'invalid_ohlc',
  'endpoint_price_check_failed'
];
function ensure(value: unknown): asserts value {
  if (!value) throw new Error('invalid_drawdown_response');
}

function keys(value: unknown, names: readonly string[]) {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value));
  ensure(Object.keys(value).length === names.length && names.every(k => Object.hasOwn(value, k)));
}

function equal(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object' || Array.isArray(a) !== Array.isArray(b)) return false;
  const left = a as Record<string, unknown>, right = b as Record<string, unknown>, names = Object.keys(left);
  return names.length === Object.keys(right).length && names.every(k => Object.hasOwn(right, k) && equal(left[k], right[k]));
}
const hash = (s: unknown) => typeof s === 'string' && /^[a-f0-9]{64}$/.test(s);
const integer = (n: unknown, max = 20000) => typeof n === 'number' && Number.isSafeInteger(n) && n >= 0 && n <= max;
const ordinal = (s: unknown) => typeof s === 'string' && /^[1-9]\d{0,19}$/.test(s);
function codes(value: unknown, allowed?: string[]): asserts value is string[] {
  ensure(Array.isArray(value) &&
    value.every(c => typeof c === 'string' &&
    /^[a-z][a-z0-9_.]{0,80}$/.test(c) &&
    (!allowed || allowed.includes(c))) &&
    new Set(value).size === value.length);
}

function price(s: unknown): bigint {
  ensure(typeof s === 'string' && s.length <= 39 && /^(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(s));
  const [whole, fraction = ''] = s.split('.');
  const value = BigInt(whole)*10n**18n+BigInt(fraction.padEnd(18, '0'));
  ensure(value>0n && value<10n**38n);
  return value;
}

function fraction(n: bigint, d: bigint) {
  let a = n, b = d;
  while (b) {
    const r = a%b;
    a = b;
    b = r;
  }
  return {
    numerator: (n / a).toString(),
    denominator: (d / a).toString()
  };
}

function display(n: bigint, d: bigint) {
  const scaled = n * 1000000n;
  let q = scaled / d;
  const r = scaled % d;
  if (r * 2n > d || r * 2n === d && q % 2n === 1n) q++;
  return q === 0n ? '小于0.0001%' : `${q/10000n}.${(q%10000n).toString().padStart(4,'0')}%`;
}

function derive(points: DrawdownPoint[]): Summary {
  // Enumerate maximal underwater runs from exact prefix maxima. Deliberately
  // distinct from the server's open-episode state machine.
  const prices = points.map(p => price(p.close_exact));
  const episodes: DrawdownEpisode[] = [];
  let high = prices[0], index = 1;
  while (index < prices.length) {
    if (prices[index] >= high) {
      high = prices[index++];
      continue;
    }
    const peak = index - 1;
    let valley = index;
    while (index < prices.length && prices[index] < high) {
      if (prices[index] < prices[valley]) valley = index;
      index++;
    }
    const recovery = index < prices.length?index: null, end = recovery ?? prices.length-1;
    const n = prices[peak]-prices[valley], d = prices[peak];
    episodes.push({
      peak: points[peak], valley: points[valley], recovery: recovery === null ? null : points[recovery], observed_end: points[end],
      depth_fraction: fraction(n, d), depth_display: display(n, d), status: recovery === null ? 'open' : 'recovered',
      peak_to_valley_intervals: valley-peak, peak_to_recovery_intervals: recovery === null ? null : recovery-peak,
      valley_to_recovery_intervals: recovery === null ? null : recovery-valley, observed_intervals: end-peak,
      observed_is_lower_bound: recovery === null, underwater_observations: recovery === null ? end - peak : recovery - peak - 1
    });
    if (recovery !== null) high = prices[recovery];
  }
  let deepest: DrawdownEpisode | null = null;
  let longest: DrawdownEpisode | null = null;
  for (const e of episodes) {
    const d = e.depth_fraction, old = deepest?.depth_fraction;
    if (!old || BigInt(d.numerator)*BigInt(old.denominator)>BigInt(old.numerator)*BigInt(d.denominator)) deepest = e;
    if (!longest || e.observed_intervals>longest.observed_intervals) longest = e;
  }
  const current = episodes.find(e => e.status === 'open') ?? null;
  return {
    episode_count: episodes.length, recovered_count: episodes.length-Number(current !== null), open_count: Number(current !== null), deepest, longest_observed: longest, current_open: current
  };
}

export function assertDrawdownEpisodes(value: unknown, expected: DrawdownExpected): asserts value is DrawdownReport {
  keys(value, ['method_id', 'rule_version', 'source_rule_version', 'analysis_id', 'parameters', 'comparison_available', 'dates', 'counts', 'members', 'limitations']);
  const report = value as DrawdownReport;
  ensure(new TextEncoder().encode(JSON.stringify(report)).length <= 2*1024*1024);
  ensure(report.method_id === DRAWDOWN_METHOD &&
    report.rule_version === DRAWDOWN_RULE &&
    report.source_rule_version === 'peer-relative-eligibility-v1' &&
    hash(report.analysis_id));
  keys(report.parameters, ['cutoff', 'lookback']);
  ensure(report.parameters.cutoff === expected.cutoff && report.parameters.lookback === expected.lookback);
  ensure(equal(report.limitations, limitations) && typeof report.comparison_available === 'boolean');
  ensure(Array.isArray(report.members) && report.members.length === expected.ids.length && report.members.length >= 2 && report.members.length <= 50);
  const ids = [...expected.ids].sort(), symbols = new Set<string>();
  let sourceCount = 0, windowCount = 0;
  for (const [i, member] of report.members.entries()) {
    keys(member, ['snapshot_id', 'batch_id', 'query_id', 'symbol', 'source_qualified', 'window_qualified', 'comparison_available', 'date_array', 'window_length', 'cutoff_present', 'endpoints', 'reasons', 'anomalies', ...summaryKeys]);
    ensure(member.snapshot_id === ids[i] && hash(member.snapshot_id) && hash(member.batch_id) && hash(member.query_id));
    ensure(member.symbol === null || typeof member.symbol === 'string' &&
      /^[A-Z0-9][A-Z0-9.-]{0,31}\.(SH|SZ|BJ|HK|NYSE|NASDAQ|AMEX)$/.test(member.symbol));
    if (member.symbol !== null) {
      ensure(!symbols.has(member.symbol));
      symbols.add(member.symbol);
    }
    ensure(typeof member.source_qualified === 'boolean' &&
      typeof member.window_qualified === 'boolean' &&
      member.comparison_available === report.comparison_available);
    codes(member.reasons, [...sourceReasons, ...localReasons]);
    if (!member.source_qualified) {
      ensure(!member.window_qualified &&
        member.date_array === null &&
        member.window_length === null &&
        member.cutoff_present === null &&
        member.endpoints === null &&
        member.anomalies === null);
      ensure(member.reasons.length === 1 && sourceReasons.includes(member.reasons[0]));
    } else {
      sourceCount++;
      ensure(member.symbol !== null && /^\d{6}\.(SH|SZ)$/.test(member.symbol));
      ensure(member.reasons.every(c => localReasons.includes(c)));
      ensure(Array.isArray(member.date_array) &&
        member.date_array.length <= expected.lookback + 1 &&
        member.date_array.every((day, j) => typeof day === 'string' &&
        validGroupDate(day) &&
        day <= expected.cutoff &&
        (!j || member.date_array![j-1]<day)));
      ensure(member.window_length === member.date_array.length && member.cutoff_present === member.date_array.includes(expected.cutoff));
      ensure(member.reasons.includes('cutoff_missing') === !member.cutoff_present &&
        member.reasons.includes('history_insufficient') === (member.window_length !== expected.lookback + 1));
      ensure(member.window_qualified === member.reasons.every(c => c === 'date_grid_mismatch'));
      const anomalies = member.anomalies;
      keys(anomalies, ['total', 'counts', 'examples', 'examples_truncated']);
      ensure(anomalies !== null && integer(anomalies.total));
      ensure(anomalies.counts !== null && typeof anomalies.counts === 'object' && !Array.isArray(anomalies.counts));
      for (const [code, count] of Object.entries(anomalies.counts)) {
        codes([code]);
        ensure(integer(count) && count > 0 && count <= anomalies.total);
      }
      ensure(Array.isArray(anomalies.examples) &&
        anomalies.examples.length === Math.min(anomalies.total, 20) &&
        anomalies.examples_truncated === (anomalies.total > 20));
      // Raw check names independently imply mandatory derived failures.
      // Use aggregate global checks even when the first 20 examples omit them.
      const globalChecks = [
        'source_code', 'instrument_identity', 'declared_instrument', 'declared_venue',
        'source_adjustflag', 'source_adjustment', 'declared_adjustment',
        'structure', 'known_negative_sample',
      ];
      const priceChecks = ['ohlc_bounds', 'nonnegative_prices', 'numeric.open', 'numeric.high', 'numeric.low', 'numeric.close'];
      if (globalChecks.some(code => (anomalies.counts[code] ?? 0) > 0)) {
        ensure((anomalies.counts.global_source_conflict ?? 0) > 0);
      }
      const observed: Record<string, number> = {};
      const seen = new Set<string>();
      for (const example of anomalies.examples) {
        keys(example, ['date', 'ordinal', 'scope', 'codes']);
        ensure(ordinal(example.ordinal) && !seen.has(example.ordinal));
        seen.add(example.ordinal);
        ensure(example.date === null || typeof example.date === 'string' && validGroupDate(example.date));
        const inside = example.date !== null && member.date_array.length>0 && example.date >= member.date_array[0] && example.date <= expected.cutoff;
        ensure(example.scope === (example.date === null?'unknown': inside?'inside_interval': 'outside_interval'));
        codes(example.codes);
        ensure(example.codes.length > 0);
        if (example.date === null) {
          ensure(example.codes.includes('endpoint_integrity_unknown'));
        }
        if (globalChecks.some(code => example.codes.includes(code))) {
          ensure(example.codes.includes('global_source_conflict'));
          ensure(example.codes.includes('local_source_conflict'));
        }
        if (inside) {
          // Duplicate candidates stop the shared endpoint helper before prices.
          // Preserve that unevaluated distinction instead of inventing a failure.
          if (!example.codes.includes('duplicate_endpoint') && priceChecks.some(code => example.codes.includes(code))) {
            ensure(example.codes.includes('endpoint_price_check_failed'));
          }
          if (example.codes.includes('label') || example.codes.includes('unlocated_label')) ensure(example.codes.includes('unlocated_endpoint'));
          if (example.codes.includes('duplicate_label')) ensure(example.codes.includes('duplicate_endpoint'));
          if (example.codes.includes('source_date_range')) ensure(example.codes.includes('local_source_conflict'));
        }

        for (const c of example.codes) {
          observed[c] = (observed[c] ?? 0)+1;
          ensure(observed[c] <= anomalies.counts[c]);
        }
      }
      for (const code of ['global_source_conflict', 'endpoint_integrity_unknown']) ensure(member.reasons.includes(code) === ((anomalies.counts[code] ?? 0)>0));
      const scopedReasons = ['local_source_conflict', 'unclassified_source_failure', 'duplicate_endpoint', 'unlocated_endpoint', 'missing_ohlc', 'invalid_price', 'invalid_ohlc', 'endpoint_price_check_failed'];
      for (const example of anomalies.examples) {
        if (example.scope === 'outside_interval') continue;
        for (const code of example.codes) {
          if (scopedReasons.includes(code)) ensure(member.reasons.includes(code));
        }
      }
      for (const code of scopedReasons) {
        if (member.reasons.includes(code)) ensure((anomalies.counts[code] ?? 0) > 0);
      }
      if (!anomalies.examples_truncated) ensure(equal(observed, anomalies.counts));
      if (member.window_qualified) {
        windowCount++;
        ensure(Array.isArray(member.endpoints) && member.endpoints.length === expected.lookback + 1);
        const ordinals = new Set<string>();
        for (const [j, p] of member.endpoints.entries()) {
          keys(p, ['index', 'date', 'ordinal', 'close_exact']);
          ensure(p.index === j && p.date === member.date_array[j] && ordinal(p.ordinal) && !ordinals.has(p.ordinal));
          ordinals.add(p.ordinal);
          price(p.close_exact);
        }
      } else ensure(member.endpoints === null);
    }
    if (report.comparison_available) {
      ensure(member.window_qualified && member.reasons.length === 0);
      const derived = derive(member.endpoints!);
      for (const key of summaryKeys) ensure(equal(member[key], derived[key]));
    } else {
      for (const key of summaryKeys) ensure(member[key] === null);
    }
  }
  const grids = new Set(report.members.filter(member => member.window_qualified).map(member => JSON.stringify(member.date_array)));
  ensure(report.comparison_available === (windowCount === report.members.length && grids.size === 1));
  for (const member of report.members) {
    if (member.window_qualified) ensure(member.reasons.includes('date_grid_mismatch') === (grids.size > 1));
  }
  ensure(report.comparison_available?equal(report.dates, report.members[0].date_array): report.dates === null);
  ensure(equal(report.counts, {
    selected: report.members.length, source_qualified: sourceCount, window_qualified: windowCount, computable: report.comparison_available?report.members.length: 0
  }));
}

export function drawdownEpisodeRequest(input: DrawdownExpected) {
  const { cutoff, lookback } = input;
  const ids = [...input.ids].sort();
  if (ids.length<2 || ids.length>50 || ids.some(id => !hash(id)) || new Set(ids).size !== ids.length) throw new Error('invalid_member_count');
  if (!validGroupDate(cutoff)) throw new Error('invalid_cutoff');
  if (!Number.isInteger(lookback) || lookback < 2 || lookback > 252) throw new Error('invalid_lookback');
  return {
    path: '/api/research/drawdown-episodes?'+new URLSearchParams({
      snapshot_ids: ids.join(','), cutoff, lookback: String(lookback)
    }), expected: {
      ids, cutoff, lookback
    }
  };
}

export async function verifyDrawdownIdentity(report: DrawdownReport) {
  const identity = {
    method_id: report.method_id, rule_version: report.rule_version, source_rule_version: report.source_rule_version,
    parameters: report.parameters, sources: report.members.map(m => ({
      snapshot_id: m.snapshot_id, batch_id: m.batch_id, query_id: m.query_id, date_array: m.date_array
    }))
  };
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(identity)));
  ensure(Array.from(new Uint8Array(bytes), v => v.toString(16).padStart(2, '0')).join('') === report.analysis_id);
}

export async function fetchDrawdownEpisodes(request: ReturnType<typeof drawdownEpisodeRequest>, signal: AbortSignal): Promise<DrawdownReport> {
  const value = await jsonRequest<unknown>(request.path, { signal });
  assertDrawdownEpisodes(value, request.expected);
  await verifyDrawdownIdentity(value);
  return value;
}

export function explainDrawdownError(error: unknown): string {
  const code = error instanceof Error?error.message: '';
  if (code === 'invalid_drawdown_response') return '回撤结果未通过原价证据核对，请重新运行。';
  if (code === 'drawdown_result_limit') return '完整结果超过大小上限，请减少成员或观察窗口后重试。成员没有被自动删减。';
  if (code === 'research_row_limit') return '完整来源记录超过本次读取上限，请选择更小的数据版本。';
  return '回撤研究未完成，请核对成员、截止日期和来源区间后重试。';
}
