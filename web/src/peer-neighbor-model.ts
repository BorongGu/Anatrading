/** Exact ranking belongs to the server; bounded decimal strings only describe display. */
import { jsonRequest, safeCode } from './api.ts';
import { canonicalJson, explainFilter } from './filter-model.ts';
import { validGroupDate, groupReason } from './group-endpoint-model.ts';
import type { SourceEndpoint } from './two-group-model.ts';

export const PEER_METHOD = 'explicit-peer-neighbors-simple-v1';

export const PEER_RULE = 'target-grid-60x2-exact-correlation-v1';
const rules = {
  intervals_per_window: 60,
  source_endpoints: 121,
  transform: 'source_simple_change',
  anchor: 'target_source_dates_exact_cutoff',
  panel: 'all_selected_complete',
  integer_bits: 65536,
  display_precision: 50,
  display_rounding: 'ROUND_HALF_EVEN',
  ranking: 'signed_descending_exact_competition',
  events: 'not_supported'
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

export interface PeerEstimate {
  estimate: string;
  display: string
}

export interface PeerCorrelation extends PeerEstimate {
  sign: 'positive' | 'zero' | 'negative';
  exact_boundary: 'positive_one' | 'negative_one' | 'zero' | 'none'
}

export interface PeerCell {
  correlation: PeerCorrelation | null;
  rank: number | null;
  tie_size: number | null;
  reason: string | null
}

export interface PeerCandidate {
  snapshot_id: string;
  previous: PeerCell;
  current: PeerCell;
  difference: (PeerEstimate & {
    direction: 'increased' | 'decreased' | 'equal'
  }) | null
}

export interface PeerMember {
  symbol: string | null;
  snapshot_id: string;
  batch_id: string;
  query_id: string;
  role: 'target' | 'candidate';
  source_qualified: boolean;
  evaluation: 'evaluated' | 'not_evaluated';
  panel_complete: boolean;
  endpoints: SourceEndpoint[] | null;
  reasons: string[];
  date_mismatch: {
    missing_count: number;
    extra_count: number;
    missing_examples: string[];
    extra_examples: string[];
    truncated: boolean
  } | null;
  anomalies: {
    total: number;
    counts: Record<string, number>;
    examples: {
      date: string | null;
      ordinal: number;
      scope: string;
      codes: string[]
    }[];
    truncated: boolean
  } | null;
}

export interface PeerWindow {
  start: string | null;
  end: string | null;
  intervals: 60;
  available: number;
  target_reason: string | null;
  order: string[]
}

export interface PeerNeighborReport {
  method_id: string;
  rule_version: string;
  source_rule_version: string;
  analysis_id: string;
  parameters: {
    target_snapshot_id: string;
    cutoff: string;
    rules: typeof rules
  };
  scope: typeof scope;
  events: unknown[];
  used_dates: string[];
  anchor: {
    reasons: string[];
    located_dates: number;
    last_date: string | null;
    examples: string[];
    truncated: boolean
  };
  members: PeerMember[];
  candidates: PeerCandidate[];
  windows: Record<'previous' | 'current', PeerWindow>;
  counts: {
    selected: number;
    candidates: number;
    source_qualified: number;
    panel_complete: number
  };
  source_panel_complete: boolean;
  reasons: string[];
  status: 'complete' | 'partial' | 'unavailable';
  limitations: typeof limitations;
}

export interface PeerExpected {
  ids: string[];
  target: string;
  cutoff: string
}
const hash = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const integer = (v: unknown, max = 20000): v is number => typeof v === 'number' &&
  Number.isSafeInteger(v) &&
  v >= 0 &&
  v <= max;
const same = (a: unknown, b: unknown) => canonicalJson(a) === canonicalJson(b);

function ensure(v: unknown): asserts v {
  if (!v) throw new Error('invalid_peer_neighbor_response');
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
  'anchor_window_unavailable',
  'endpoint_integrity_unknown',
  'global_source_conflict',
  'local_source_conflict',
  'unclassified_source_failure',
  'extra_source_dates',
  ...endpointReasons,
];
const anchorReasons = ['anchor_source_unavailable', 'endpoint_integrity_unknown', 'cutoff_missing', 'anchor_history_insufficient'];
const cellReasons = ['source_panel_unavailable', 'target_constant_source_change', 'constant_source_change'];

function decimalParts(value: unknown, bound: number) {
  ensure(typeof value === 'string' && value.length <= 80);
  if (value === '0') return { sign: 0, coefficient: 0n, exponent: 0, digits: 1 };
  const match = /^(-?)([1-9])(?:\.([0-9]{1,49}))?E([+-][0-9]{1,5})$/.exec(value);
  ensure(match);
  const fraction = match[3] ?? '';
  const exponent = Number(match[4]);
  ensure(match[4] === (exponent < 0 ? String(exponent) : '+' + exponent));
  ensure(exponent >= -10000 && exponent <= 0 && (!fraction || !fraction.endsWith('0')));
  const coefficient = BigInt(match[2] + fraction);
  if (exponent === 0) ensure(coefficient <= BigInt(bound) * 10n ** BigInt(fraction.length));
  return { sign: match[1] ? -1 : 1, coefficient, exponent, digits: 1 + fraction.length };
}

/** Uses at most 50 coefficient digits. Very small exponents never create huge BigInts. */
export function peerDisplay(value: string, bound = 1): string {
  const parts = decimalParts(value, bound);
  const shift = parts.exponent - parts.digits + 1 + 4;
  let rounded = 0n;
  if (shift >= 0) {
    rounded = parts.coefficient * 10n ** BigInt(shift);
  } else if (-shift <= parts.digits + 1) {
    const divisor = 10n ** BigInt(-shift);
    const quotient = parts.coefficient / divisor;
    const remainder = parts.coefficient % divisor;
    rounded = quotient + (
      remainder * 2n > divisor || remainder * 2n === divisor && quotient % 2n === 1n ? 1n : 0n
    );
  }
  const sign = parts.sign < 0 && rounded !== 0n ? '-' : '';
  return `${sign}${rounded / 10000n}.${(rounded % 10000n).toString().padStart(4, '0')}`;
}

function compareEstimates(a: string, b: string) {
  const left = decimalParts(a, 1);
  const right = decimalParts(b, 1);
  if (left.sign !== right.sign) return Math.sign(left.sign - right.sign);
  if (!left.sign) return 0;
  if (left.exponent !== right.exponent) return left.sign * Math.sign(left.exponent - right.exponent);
  const leftCoefficient = left.coefficient * 10n ** BigInt(50 - left.digits);
  const rightCoefficient = right.coefficient * 10n ** BigInt(50 - right.digits);
  return left.sign * (leftCoefficient > rightCoefficient ? 1 : leftCoefficient < rightCoefficient ? -1 : 0);
}

function knownCorrelationOrder(a: PeerCorrelation, b: PeerCorrelation): number | null {
  const signs = {
    negative: -1,
    zero: 0,
    positive: 1
  };
  if (a.sign !== b.sign) return Math.sign(signs[a.sign] - signs[b.sign]);
  if (a.exact_boundary !== 'none' && a.exact_boundary === b.exact_boundary) return 0;
  if (a.exact_boundary === 'positive_one' || b.exact_boundary === 'negative_one') return 1;
  if (a.exact_boundary === 'negative_one' || b.exact_boundary === 'positive_one') return -1;
  const order = compareEstimates(a.estimate, b.estimate);
  return order || null;
}

function estimate(v: PeerEstimate, bound: number) {
  ensure(v.display === peerDisplay(v.estimate, bound));
  return decimalParts(v.estimate, bound);
}

function correlation(v: PeerCorrelation) {
  keys(v, ['estimate', 'display', 'sign', 'exact_boundary']);
  const p = estimate(v, 1);
  ensure(v.sign === ({
    [-1]: 'negative',
    0: 'zero',
    1: 'positive'
  } as Record<number, string>)[p.sign]);
  ensure(['positive_one', 'negative_one', 'zero', 'none'].includes(v.exact_boundary));
  if (v.exact_boundary === 'zero') ensure(p.sign === 0);
  else if (v.exact_boundary === 'positive_one' || v.exact_boundary === 'negative_one') {
    ensure(v.estimate === (v.exact_boundary === 'positive_one' ? '1E+0' : '-1E+0'));
  }
  else ensure(p.sign !== 0);
  ensure((v.sign === 'zero') === (v.exact_boundary === 'zero'));
}

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

export function assertPeerNeighbors(value: unknown, expected: PeerExpected): asserts value is PeerNeighborReport {
  const report = value as PeerNeighborReport;
  keys(report, [
    'method_id',
    'rule_version',
    'source_rule_version',
    'analysis_id',
    'parameters',
    'scope',
    'events',
    'used_dates',
    'anchor',
    'members',
    'candidates',
    'windows',
    'counts',
    'source_panel_complete',
    'reasons',
    'status',
    'limitations',
  ]);
  ensure(new TextEncoder().encode(JSON.stringify(report)).length <= 2 * 1024 * 1024);
  ensure(report.method_id === PEER_METHOD &&
    report.rule_version === PEER_RULE &&
    report.source_rule_version === 'peer-relative-eligibility-v1' &&
    hash(report.analysis_id));
  keys(report.parameters, ['target_snapshot_id', 'cutoff', 'rules']);
  ensure(report.parameters.target_snapshot_id === expected.target &&
    report.parameters.cutoff === expected.cutoff &&
    same(report.parameters.rules, rules));
  ensure(same(report.scope, scope) &&
    same(report.limitations, limitations) &&
    Array.isArray(report.events) &&
    report.events.length === 0);

  // The target alone fixes the source-date grid.
  dates(report.used_dates, 121);
  ensure(report.used_dates.length === 0 || report.used_dates.length === 121 &&
    report.used_dates[120] === expected.cutoff);
  keys(report.anchor, ['reasons', 'located_dates', 'last_date', 'examples', 'truncated']);
  codes(report.anchor.reasons, anchorReasons);
  ensure(integer(report.anchor.located_dates) && report.anchor.truncated === (report.anchor.located_dates>20));
  dates(report.anchor.examples, 20);
  ensure(report.anchor.examples.length === Math.min(20, report.anchor.located_dates) &&
    report.anchor.last_date === (report.anchor.examples.at(-1) ?? null) &&
    report.anchor.examples.every(d => d <= expected.cutoff));
  ensure((report.used_dates.length === 121) === (report.anchor.reasons.length === 0));
  if (report.used_dates.length) ensure(report.anchor.located_dates >= 121 &&
    same(report.anchor.examples, report.used_dates.slice(-20)));
  ensure(Array.isArray(report.members) &&
    report.members.length === expected.ids.length &&
    report.members.length >= 2 &&
    report.members.length <= 50);

  // Preserve every original member, including all rejected or incomplete rows.
  const ids = [...expected.ids].sort();
  const symbols = new Set<string>();
  const queries = new Set<string>();
  for (let i = 0; i < report.members.length; i++) {
    const member = report.members[i];
    keys(member, [
      'symbol',
      'snapshot_id',
      'batch_id',
      'query_id',
      'role',
      'source_qualified',
      'evaluation',
      'panel_complete',
      'endpoints',
      'date_mismatch',
      'anomalies',
      'reasons',
    ]);
    ensure(member.snapshot_id === ids[i] &&
      hash(member.batch_id) &&
      hash(member.query_id) &&
      !queries.has(member.query_id));
    queries.add(member.query_id);
    ensure(member.role === (member.snapshot_id === expected.target?'target': 'candidate') &&
      typeof member.source_qualified === 'boolean' &&
      typeof member.panel_complete === 'boolean');
    ensure(member.symbol === null || sourceSymbol(member.symbol, member.source_qualified) &&
      !symbols.has(member.symbol));
    if (member.symbol !== null) symbols.add(member.symbol);
    if (!member.source_qualified) {
      codes(member.reasons, sourceReasons);
      ensure(member.reasons.length === 1 &&
        member.evaluation === 'not_evaluated' &&
        member.endpoints === null &&
        member.anomalies === null &&
        member.date_mismatch === null &&
        !member.panel_complete);
      if (member.reasons[0] === 'source_identity_conflict') ensure(member.symbol === null);
      continue;
    }
    ensure(member.symbol !== null);
    codes(member.reasons, memberReasons);
    if (!report.used_dates.length) {
      ensure(member.evaluation === 'not_evaluated' &&
        member.endpoints === null &&
        member.date_mismatch === null &&
        !member.panel_complete &&
        member.reasons.includes('anchor_window_unavailable') &&
        member.reasons.every(code => [
          'anchor_window_unavailable',
          'global_source_conflict',
          'endpoint_integrity_unknown',
        ].includes(code)));
    } else {
      ensure(member.evaluation === 'evaluated' && Array.isArray(member.endpoints) && member.endpoints.length === 121);
      member.endpoints.forEach((p, j) => endpoint(p, report.used_dates[j]));
      ensure(member.endpoints.every(p => p.reasons.every(code => member.reasons.includes(code))));
      const ordinals = member.endpoints.flatMap(p => p.ordinal === null?[]: [p.ordinal]);
      ensure(new Set(ordinals).size === ordinals.length);
      ensure(member.panel_complete === (member.reasons.length === 0));
      if (member.panel_complete) ensure(member.endpoints.every(p => p.ordinal !== null &&
        p.close_exact !== null &&
        p.close_exact !== '0' &&
        !p.close_exact.startsWith('-') &&
        p.reasons.length === 0));
      const mismatch = member.date_mismatch;
      keys(mismatch, ['missing_count', 'extra_count', 'missing_examples', 'extra_examples', 'truncated']);
      ensure(mismatch);
      ensure(integer(mismatch.missing_count, 121) && integer(mismatch.extra_count));
      dates(mismatch.missing_examples, 20);
      dates(mismatch.extra_examples, 20);
      ensure(mismatch.missing_examples.length === Math.min(20, mismatch.missing_count) &&
        mismatch.extra_examples.length === Math.min(20, mismatch.extra_count) &&
        mismatch.truncated === (mismatch.missing_count>20 || mismatch.extra_count>20));
      ensure(mismatch.missing_count === member.endpoints.filter(p => p.reasons.includes('missing_endpoint')).length);
      ensure(same(mismatch.missing_examples, member.endpoints.filter(p => p.reasons.includes('missing_endpoint')).slice(0, 20).map(p => p.date)));
      ensure(mismatch.extra_examples.every(day => day >= report.used_dates[0] &&
        day <= expected.cutoff &&
        !report.used_dates.includes(day)) &&
        (mismatch.extra_count>0) === member.reasons.includes('extra_source_dates'));
    }
    const anomalies = member.anomalies;
    keys(anomalies, ['total', 'counts', 'examples', 'truncated']);
    ensure(anomalies);
    ensure(integer(anomalies.total) &&
      Array.isArray(anomalies.examples) &&
      anomalies.examples.length === Math.min(20, anomalies.total) &&
      anomalies.truncated === (anomalies.total>20));
    ensure(anomalies.counts !== null && typeof anomalies.counts === 'object' && !Array.isArray(anomalies.counts));
    ensure(Object.entries(anomalies.counts).every(([code, count]) => code.trim().length>0 &&
      integer(count, anomalies.total) &&
      count>0));
    const seen = new Set<number>();
    const counted: Record<string, number> = Object.create(null);
    for (const example of anomalies.examples) {
      keys(example, ['date', 'ordinal', 'scope', 'codes']);
      ensure(integer(example.ordinal, Number.MAX_SAFE_INTEGER) && example.ordinal>0 && !seen.has(example.ordinal));
      seen.add(example.ordinal);
      ensure(example.date === null || typeof example.date === 'string' && validGroupDate(example.date));
      ensure(example.scope === (example.date === null?'unknown': !report.used_dates.length?'window_unavailable': example.date >= report.used_dates[0] &&
        example.date <= expected.cutoff?'inside_interval': 'outside_interval'));
      rawCodes(example.codes);
      ensure(example.codes.length>0);
      for (const code of example.codes) {
        counted[code] = (counted[code] ?? 0) + 1;
        ensure(Object.hasOwn(anomalies.counts, code) && anomalies.counts[code] >= counted[code]);
      }
      if (report.used_dates.length && (example.scope === 'inside_interval' || example.scope === 'unknown')) {
        for (const code of ['local_source_conflict', 'unclassified_source_failure', 'endpoint_integrity_unknown']) {
          if (example.codes.includes(code)) ensure(member.reasons.includes(code));
        }
      }
    }
    if (!anomalies.truncated) ensure(Object.keys(counted).length === Object.keys(anomalies.counts).length &&
      Object.entries(counted).every(([code, count]) => Object.hasOwn(anomalies.counts, code) &&
      anomalies.counts[code] === count));
    for (const code of ['global_source_conflict', 'endpoint_integrity_unknown']) {
      if (Object.hasOwn(anomalies.counts, code)) ensure(member.reasons.includes(code));
    }
    if ([
      'source_code', 'instrument_identity', 'declared_instrument', 'declared_venue',
      'source_adjustflag', 'source_adjustment', 'declared_adjustment', 'structure', 'known_negative_sample',
    ].some(code => Object.hasOwn(anomalies.counts, code))) {
      ensure(member.reasons.includes('global_source_conflict'));
    }
  }

  // Aggregate counts and cell availability must agree with the member rows.
  keys(report.counts, ['selected', 'candidates', 'source_qualified', 'panel_complete']);
  const memberCount = report.members.length;
  ensure(report.counts.selected === memberCount &&
    report.counts.candidates === memberCount - 1 &&
    report.counts.source_qualified === report.members.filter(member => member.source_qualified).length &&
    report.counts.panel_complete === report.members.filter(member => member.panel_complete).length);
  ensure(report.source_panel_complete === (report.used_dates.length === 121 &&
    report.counts.panel_complete === memberCount));
  codes(report.reasons, ['source_panel_unavailable']);
  ensure(same(report.reasons, report.source_panel_complete?[]: ['source_panel_unavailable']));
  const peers = ids.filter(id => id !== expected.target);
  ensure(Array.isArray(report.candidates) && same(report.candidates.map(candidate => candidate.snapshot_id), peers));
  for (const candidate of report.candidates) {
    keys(candidate, ['snapshot_id', 'previous', 'current', 'difference']);
    for (const name of ['previous', 'current'] as const) {
      const cell = candidate[name];
      keys(cell, ['correlation', 'rank', 'tie_size', 'reason']);
      if (cell.correlation === null) ensure(cell.rank === null &&
        cell.tie_size === null &&
        cellReasons.includes(cell.reason ?? ''));
      else {
        correlation(cell.correlation);
        ensure(report.source_panel_complete &&
          cell.reason === null &&
          integer(cell.rank, memberCount - 1) &&
          cell.rank>0 &&
          integer(cell.tie_size, memberCount - 1) &&
          cell.tie_size>0);
      }
      if (!report.source_panel_complete) ensure(cell.reason === 'source_panel_unavailable');
    }
    if (candidate.previous.correlation && candidate.current.correlation) {
      const difference = candidate.difference;
      keys(difference, ['estimate', 'display', 'direction']);
      ensure(difference);
      const parts = estimate(difference, 2);
      ensure(['equal', 'increased', 'decreased'].includes(difference.direction));
      ensure(difference.direction === 'equal'?parts.sign === 0: difference.direction === 'increased'?parts.sign >= 0: parts.sign <= 0);
      const previous = decimalParts(candidate.previous.correlation.estimate, 1);
      const current = decimalParts(candidate.current.correlation.estimate, 1);
      if (previous.sign !== current.sign) ensure(difference.direction === (current.sign>previous.sign?'increased': 'decreased'));
      const known = knownCorrelationOrder(candidate.current.correlation, candidate.previous.correlation);
      if (known !== null) ensure(difference.direction === (known>0?'increased': known<0?'decreased': 'equal'));
      const exact = {
        negative_one: -1,
        zero: 0,
        positive_one: 1
      };
      const old = candidate.previous.correlation.exact_boundary;
      const now = candidate.current.correlation.exact_boundary;
      if (old !== 'none' && now !== 'none') {
        const delta = exact[now] - exact[old];
        ensure(difference.estimate === (delta?`${delta}E+0`: '0') &&
          difference.direction === (delta>0?'increased': delta<0?'decreased': 'equal'));
      }
    } else ensure(candidate.difference === null);
  }

  // Validate each full order, competition rank and exact-boundary tie group.
  keys(report.windows, ['previous', 'current']);
  let total = 0;
  for (const [name, offset] of [['previous', 0], ['current', 60]] as const) {
    const window = report.windows[name];
    keys(window, ['start', 'end', 'intervals', 'available', 'target_reason', 'order']);
    ensure(window.start === (report.used_dates[offset] ?? null) &&
      window.end === (report.used_dates[offset + 60] ?? null) &&
      window.intervals === 60);
    const available = report.candidates.filter(candidate => candidate[name].correlation !== null);
    ensure(window.available === available.length);
    total += window.available;
    ensure(Array.isArray(window.order) && same([...window.order].sort(), peers));
    ensure(
      window.target_reason === null ||
      window.target_reason === 'source_panel_unavailable' ||
      window.target_reason === 'target_constant_source_change',
    );
    if (!report.source_panel_complete) ensure(window.target_reason === 'source_panel_unavailable');
    else ensure(window.target_reason !== 'source_panel_unavailable');
    if (window.target_reason === 'target_constant_source_change') ensure(window.available === 0 &&
      report.candidates.every(candidate => candidate[name].reason === 'target_constant_source_change'));
    else if (report.source_panel_complete) {
      ensure(report.candidates.every(candidate =>
        candidate[name].reason === null || candidate[name].reason === 'constant_source_change',
      ));
    }
    const byId = new Map(report.candidates.map(candidate => [candidate.snapshot_id, candidate]));
    let position = 0;
    let previous: PeerCorrelation | null = null;
    const boundaryRanks = new Map<string, number>();
    while (position<window.available) {
      const first = byId.get(window.order[position])![name];
      ensure(first.correlation &&
        first.rank === position + 1 &&
        first.tie_size !== null &&
        position + first.tie_size <= window.available);
      const group = window.order.slice(position, position + first.tie_size);
      ensure(same(group, [...group].sort()));
      for (const id of group) {
        const v = byId.get(id)![name];
        ensure(v.correlation &&
          v.rank === first.rank &&
          v.tie_size === first.tie_size &&
          same(v.correlation, first.correlation));
      }
      if (previous) {
        const order = knownCorrelationOrder(previous, first.correlation);
        ensure(order === null || order >= 0);
      }
      previous = first.correlation;
      if (first.correlation.exact_boundary !== 'none') {
        const boundary = first.correlation.exact_boundary;
        ensure(!boundaryRanks.has(boundary));
        boundaryRanks.set(boundary, first.rank);
      }
      position += first.tie_size;
    }
    const tail = window.order.slice(window.available);
    ensure(same(tail, [...tail].sort()) && tail.every(id => byId.get(id)![name].correlation === null));
  }
  ensure(report.status === (total === 2 * (memberCount - 1)?'complete': total?'partial': 'unavailable'));
  ensure(new TextEncoder().encode(JSON.stringify(report)).length <= 2 * 1024 * 1024);
}

export async function verifyPeerNeighborIdentity(r: PeerNeighborReport) {
  const identity = {
    method_id: r.method_id,
    rule_version: r.rule_version,
    source_rule_version: r.source_rule_version,
    parameters: r.parameters,
    sources: r.members.map(m => ({
      symbol: m.symbol,
      snapshot_id: m.snapshot_id,
      batch_id: m.batch_id,
      query_id: m.query_id
    })),
    used_dates: r.used_dates,
    scope: r.scope,
    events: r.events
  };
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonicalJson(identity)));
  ensure(Array.from(new Uint8Array(digest), v => v.toString(16).padStart(2, '0')).join('') === r.analysis_id);
}

export function peerNeighborRequest(expected: PeerExpected) {
  if (
    expected.ids.length < 2 || expected.ids.length > 50 ||
    !expected.ids.every(hash) || new Set(expected.ids).size !== expected.ids.length
  ) {
    throw new Error('research_member_limit');
  }
  if (!expected.ids.includes(expected.target) || !hash(expected.target)) throw new Error('invalid_target');
  if (!validGroupDate(expected.cutoff)) throw new Error('invalid_dates');
  const copy = {
    ...expected,
    ids: [...expected.ids].sort()
  };
  const params = new URLSearchParams({
    snapshot_ids: copy.ids.join(','),
    target_snapshot_id: copy.target,
    cutoff: copy.cutoff
  });
  return {
    path: `/api/research/peer-neighbors?${params}`,
    expected: copy
  };
}

export async function fetchPeerNeighbors(request: ReturnType<typeof peerNeighborRequest>, signal: AbortSignal) {
  const result = await jsonRequest<unknown>(request.path, {
    signal
  });
  assertPeerNeighbors(result, request.expected);
  await verifyPeerNeighborIdentity(result);
  return result;
}

const explanations: Record<string, string> = {
  invalid_target: '请从当前已选版本中明确选择目标股票',
  invalid_peer_neighbor_response: '双窗响应与本次输入或格式约定不符，旧结果已清空',
  peer_neighbor_integer_limit: '精确计算超过整数预算，本次没有发布排名',
  peer_neighbor_display_failure: '相关小数显示无法核对，本次没有发布排名',
  peer_neighbor_arithmetic_failure: '精确相关不变量核验失败，本次没有发布排名',
  peer_neighbor_result_limit: '双窗结果超过2 MiB，整组未显示，请减少明确成员后重新核验',
  source_panel_unavailable: '完整组来源面板未齐，两窗相关均未计算',
  anchor_source_unavailable: '目标来源资格未通过，窗口未建立',
  anchor_history_insufficient: '目标在截止日及以前不足121个来源日期',
  cutoff_missing: '目标没有指定截止日记录，未回退日期',
  anchor_window_unavailable: '目标窗口未建立，端点尚未评估',
  extra_source_dates: '本成员在使用区间含目标网格之外的额外日期',
  global_source_conflict: '完整来源含全局身份、调整或结构反证',
  constant_source_change: '本窗简单源价变化为常量，相关未定义',
  target_constant_source_change: '目标本窗简单源价变化为常量，本窗全部相关未定义',
};
export const peerReason = (code: string) => Object.hasOwn(explanations, code)?explanations[code]: groupReason(code);

export function explainPeerNeighborError(error: unknown) {
  const code = safeCode(error);
  return Object.hasOwn(explanations, code)?`${explanations[code]}（${code}）`: explainFilter(error);
}

export function peerSign(value: PeerCorrelation | null) {
  if (!value) return '不可算';
  return {
    positive: '正向',
    negative: '反向',
    zero: '零相关'
  }[value.sign] + (value.sign !== 'zero' && value.display === '0.0000'?'，显示舍入': '');
}
