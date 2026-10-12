import { checkedFetch } from './api.ts';
import { fields } from './types.ts';
import type { Check, Query, Row, SourceContract } from './types.ts';

export interface MinuteHistoryFraction { numerator: string; denominator: string; display: string }
export interface MinuteHistoryDay {
  source_date: string; kind: 'current' | 'history'; start: Row[]; end: Row[];
  unknown_clock_ordinals: number[]; reason: string | null;
  change: MinuteHistoryFraction | null; magnitude: MinuteHistoryFraction | null;
}
export interface MinuteHistoryReport {
  method_id: 'minute-source-label-history-v1'; history_id: string; snapshot_id: string; batch_id: string;
  query_id: string; context_query_id: string; raw_sha256: string; versions: unknown;
  metadata: Query['metadata']; contract: SourceContract | null; batch_checks: Check[];
  source_date: string; start_clock: string; end_clock: string; as_of_label: string; lookback: 5;
  window_status: 'complete' | 'insufficient' | 'unresolved_dates'; unknown_date_ordinals: number[];
  history_dates: string[]; missing_history_dates: number | null; nominal_minutes: number;
  assumption: 'same_price_scale_between_endpoints'; qualification: 'retrospective_source_endpoint_arithmetic';
  display_policy: { places: 8; rounding: 'half_even' }; days: MinuteHistoryDay[];
}
export interface MinuteHistoryRequest {
  key: string; path: string; query: Query; row: Row; sourceDate: string; startClock: string; endClock: string;
}
const hex = /^[a-f0-9]{64}$/;
const clock = /^(?:[01]\d|2[0-3]):[0-5]\d$/;
const integer = /^(?:0|-?[1-9]\d{0,99})$/;
const positive = /^[1-9]\d{0,99}$/;
const reasons = new Set(['missing_endpoint', 'duplicate_endpoint', 'endpoint_uniqueness_unknown',
  'source_identity_conflict', 'source_adjustment_conflict', 'source_adjustment_check_failed',
  'source_label_conflict', 'source_structure_failed', 'price_scale_conflict', 'missing_close',
  'invalid_close', 'nonpositive_close', 'source_quarantined']);
const invalid = (): never => { throw new Error('invalid_query_response'); };
const object = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);

/** Stable JSON for request keys and the Store's sorted-key, UTF-8 identity contract. */
function canonical(value: unknown): string {
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(',')}]`;
  if (object(value)) return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${canonical(value[key])}`).join(',')}}`;
  return invalid();
}
const same = (left: unknown, right: unknown) => canonical(left) === canonical(right);
function validDate(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [year, month, day] = value.split('-').map(Number);
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return year > 0 && month >= 1 && month <= 12 && day >= 1 && day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}
export function minuteHistorySourceDate(row: Row): string | null {
  const value = row.label?.slice(0, 10);
  return validDate(value) ? value : null;
}
export function minuteHistorySourceKey(query: Query, row: Row): string {
  // JSON round-trip omits absent optional properties in partial read-only render fixtures.
  return canonical(JSON.parse(JSON.stringify({ query_id: query.query_id, snapshot_id: query.snapshot_id,
    batch_id: query.batch_id, selection: query.selection, manifest: query.manifest, metadata: query.metadata,
    batch_checks: query.batch_checks, row })));
}
export function minuteHistoryInputIssue(query: Query, row: Row, start: string, end: string): string | null {
  const date = minuteHistorySourceDate(row);
  if (!['1m', '5m'].includes(query.metadata.period ?? '')) return '仅适用于1分钟或5分钟来源。';
  if (!date) return '所选记录缺少可用于此功能的规范日期标签，请选择日期标签有效的记录。';
  if (!(query.rows.includes(row) || query.unlocated.includes(row))) return '记录已不属于当前查询，请重新选择。';
  if (!clock.test(start) || !clock.test(end)) return '请明确填写两个 HH:MM 标签。';
  if (start >= end) return '终点标签须晚于起点，且两端不能相同。';
  if (query.selection.cutoff !== null && query.selection.cutoff < `${date}T${end}`) return '终点晚于当前查询截止，请先调整截止标签。';
  return null;
}
export function buildMinuteHistoryRequest(query: Query, row: Row, start: string, end: string): MinuteHistoryRequest {
  if (minuteHistoryInputIssue(query, row, start, end)) throw new Error('invalid_minute_label_history');
  const sourceDate = minuteHistorySourceDate(row)!;
  const parameters = new URLSearchParams({ query_id: query.query_id, mode: query.selection.mode,
    source_date: sourceDate, start_clock: start, end_clock: end });
  for (const field of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
    if (query.selection[field] !== null) parameters.set(field, String(query.selection[field]));
  }
  return { key: `${minuteHistorySourceKey(query, row)}\n${start}\n${end}`,
    path: `/api/minute-label-history/${encodeURIComponent(query.snapshot_id)}?${parameters}`,
    query: structuredClone(query), row: structuredClone(row), sourceDate, startClock: start, endClock: end };
}
function ordinals(value: unknown): value is number[] {
  return Array.isArray(value) && value.every((item, i) => Number.isSafeInteger(item) && item > 0 && (i === 0 || item > value[i - 1]));
}
function validChecks(value: unknown): value is Check[] {
  return Array.isArray(value) && value.every(check => object(check) && typeof check.name === 'string'
    && ['pass', 'fail', 'not_evaluated'].includes(check.outcome as string)
    && (check.reason == null || typeof check.reason === 'string') && (check.assumption == null || typeof check.assumption === 'string'));
}
function validRow(row: Row, label: string): boolean {
  return object(row) && Number.isSafeInteger(row.ordinal) && row.ordinal > 0 && row.label === label
    && typeof row.locator === 'string' && !!row.locator && (row.source_label === null || typeof row.source_label === 'string')
    && object(row.tokens) && Object.values(row.tokens).every(value => value === null || typeof value === 'string')
    && object(row.values) && fields.every(field => row.values[field] === null || typeof row.values[field] === 'string')
    && validChecks(row.checks) && row.volume_shares === null && row.amount_cny === null;
}
function gcd(a: bigint, b: bigint): bigint {
  while (b !== 0n) [a, b] = [b, a % b];
  return a < 0n ? -a : a;
}
function fraction(value: MinuteHistoryFraction | null): value is MinuteHistoryFraction {
  if (!object(value) || typeof value.numerator !== 'string' || !integer.test(value.numerator)
    || typeof value.denominator !== 'string' || !positive.test(value.denominator)
    || typeof value.display !== 'string' || !/^-?(?:0|[1-9]\d{0,99})\.\d{8}$/.test(value.display)) return false;
  const numerator = BigInt(value.numerator), denominator = BigInt(value.denominator);
  let rounded = (numerator < 0n ? -numerator : numerator) * 100_000_000n / denominator;
  const remainder = (numerator < 0n ? -numerator : numerator) * 100_000_000n % denominator;
  if (remainder * 2n > denominator || (remainder * 2n === denominator && rounded % 2n === 1n)) rounded += 1n;
  const display = `${numerator < 0n && rounded !== 0n ? '-' : ''}${rounded / 100_000_000n}.${String(rounded % 100_000_000n).padStart(8, '0')}`;
  return gcd(numerator, denominator) === 1n && value.display === display;
}
function exactPositivePrice(value: string | null): [bigint, bigint] | null {
  if (value === null) return null;
  const match = /^\+?(\d{1,100})(?:\.(\d{0,100}))?(?:[eE]([+-]?\d{1,4}))?$/.exec(value);
  if (!match) return null;
  let digits = (match[1] + (match[2] ?? '')).replace(/^0+/, ''), exponent = Number(match[3] ?? 0) - (match[2]?.length ?? 0);
  if (!digits) return null;
  while (digits.endsWith('0')) { digits = digits.slice(0, -1); exponent += 1; }
  // The source Decimal(38,18) bound applies after insignificant zero removal.
  if (exponent < -18 || digits.length + exponent > 20) return null;
  return exponent >= 0 ? [BigInt(digits) * 10n ** BigInt(exponent), 1n] : [BigInt(digits), 10n ** BigInt(-exponent)];
}
// These guards use only evidence already present on the page or returned endpoints.
// They reject known contradictions; they do not certify unseen full-context rows.
function sourceDay(row: Row): string | null {
  const labelDate = minuteHistorySourceDate(row);
  if (labelDate) return labelDate;
  const raw = row.tokens?.source_date || row.tokens?.date;
  const value = typeof raw === 'string' ? (/^\d{8}$/.test(raw)
    ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6)}` : raw.replaceAll('/', '-')) : null;
  return validDate(value) ? value : null;
}
function locatedLabel(row: Row): string | null {
  return row.label !== null && row.label.length === 16 && row.label[10] === 'T'
    && validDate(row.label.slice(0, 10)) && clock.test(row.label.slice(11)) ? row.label : null;
}
function visibleContext(request: MinuteHistoryRequest): Row[] {
  const asof = `${request.sourceDate}T${request.endClock}`;
  return [...request.query.rows, ...request.query.unlocated].filter(row => {
    const date = sourceDay(row), label = locatedLabel(row);
    return (date === null || date <= request.sourceDate) && (label === null || label <= asof);
  });
}
function assertVisibleEvidence(report: MinuteHistoryReport, rows: Row[], selected: Map<number, Row>): void {
  const history = [...new Set([...report.history_dates, ...rows.map(sourceDay)
    .filter((date): date is string => date !== null && date < report.source_date)])].sort().slice(-5);
  if (!same(history, report.history_dates)) return invalid();
  for (const ordinal of report.unknown_date_ordinals) {
    const known = selected.get(ordinal);
    if (known && sourceDay(known) !== null) return invalid();
  }
  for (const day of report.days) for (const ordinal of day.unknown_clock_ordinals) {
    const known = selected.get(ordinal);
    if (known && (sourceDay(known) !== day.source_date || locatedLabel(known) !== null)) return invalid();
  }
  const byDate = new Map(report.days.map(day => [day.source_date, day]));
  for (const row of rows) {
    const date = sourceDay(row), label = locatedLabel(row);
    if (date === null) { if (!report.unknown_date_ordinals.includes(row.ordinal)) return invalid(); continue; }
    const day = byDate.get(date);
    if (!day) continue; // An older visible day may be displaced by unseen, newer context dates.
    if (label === null) { if (!day.unknown_clock_ordinals.includes(row.ordinal)) return invalid(); continue; }
    for (const [side, clock] of [['start', report.start_clock], ['end', report.end_clock]] as const) {
      if (label === `${date}T${clock}` && !day[side].some(endpoint => endpoint.ordinal === row.ordinal)) return invalid();
    }
  }
}
const commonFailures = new Set(['source_code', 'source_venue', 'declared_instrument', 'declared_venue', 'instrument_identity',
  'source_adjustflag', 'source_adjustment', 'declared_adjustment', 'price_scale', 'price_scaling', 'same_price_scale',
  'label', 'source_date_range', 'label_semantics', 'source_label']);
function failed(checks: Check[], endpoint = false): boolean {
  return checks.some(check => check.outcome === 'fail' && (commonFailures.has(check.name)
    || endpoint && ['structure', 'numeric.close'].includes(check.name)));
}
const venueAliases: Record<string, string> = { SSE: 'SH', XSHG: 'SH', SZSE: 'SZ', XSHE: 'SZ', BSE: 'BJ',
  HKEX: 'HK', SEHK: 'HK', XHKG: 'HK', XNAS: 'NASDAQ', XNYS: 'NYSE' };
const markets = new Set(['SH', 'SZ', 'BJ', 'HK', 'NYSE', 'NASDAQ', 'AMEX']);
const venueClaim = (value: unknown): string | null => typeof value === 'string' && value.trim()
  ? venueAliases[value.trim().toUpperCase()] ?? value.trim().toUpperCase() : null;
function identityConflict(rows: Row[], metadata: Query['metadata']): boolean {
  const codes = new Set<string>(), venues = new Set<string>();
  function collect(value: unknown, venue: unknown): boolean {
    let market = venueClaim(venue), code = typeof value === 'string' ? value.trim().toUpperCase() : '';
    let embedded: string | null = null;
    const parts = code.split('.');
    if (parts.length >= 2 && markets.has(venueClaim(parts.at(-1)) ?? '')) { embedded = venueClaim(parts.pop()); code = parts.join('.'); }
    else if (parts.length >= 2 && markets.has(venueClaim(parts[0]) ?? '')) { embedded = venueClaim(parts.shift()); code = parts.join('.'); }
    else if (/^(SH|SZ|BJ)\d{6}$/.test(code)) { embedded = code.slice(0, 2); code = code.slice(2); }
    if (embedded !== null && market !== null && embedded !== market) return true;
    market = embedded ?? market;
    // Unrecognised claims stay unknown, consistent with the source identity boundary.
    if (code && (!/^[A-Z0-9][A-Z0-9.-]{0,31}$/.test(code) || ['SH', 'SZ', 'BJ'].includes(market ?? '') && !/^\d{6}$/.test(code))) return false;
    if (code) codes.add(code);
    if (market) venues.add(market);
    return codes.size > 1 || venues.size > 1;
  }
  const declaration = object(metadata.interpretation) ? metadata.interpretation : {};
  if (collect(metadata.source_code, metadata.source_venue) || collect(declaration.instrument, declaration.venue)) return true;
  return rows.some(row => ['code', 'source_code'].some(code => ['venue', 'source_venue'].some(venue => collect(row.tokens[code], row.tokens[venue]))));
}
function knownDisqualification(day: MinuteHistoryDay, rows: Row[], currentRows: Row[], query: Query): boolean {
  const endpoints = [...day.start, ...day.end], evidence = [...rows, ...endpoints];
  if (query.metadata.quarantined === true || failed(query.batch_checks, true)
    || query.batch_checks.some(check => check.name === 'known_negative_sample' && check.outcome === 'fail')
    || ['conflict', 'failed', 'rejected'].includes(query.manifest.contract?.price_scaling?.status ?? '')
    || endpoints.some(row => failed(row.checks, true)) || evidence.some(row => failed(row.checks))
    || identityConflict(evidence, query.metadata)) return true;
  for (const [field, claim] of [['adjustflag', 'source_adjustflag'], ['source_adjustment', 'source_adjustment']] as const) {
    if (evidence.some(row => row.tokens[field] != null && query.metadata[claim] != null && row.tokens[field] !== query.metadata[claim])) return true;
  }
  for (const field of ['price_scale', 'price_unit', 'adjustflag', 'source_adjustment', 'label_semantics']) {
    if (new Set(evidence.map(row => row.tokens[field]).filter(value => value != null && value !== '')).size > 1) return true;
  }
  const semantics = (members: Row[]) => members.map(row => row.tokens.label_semantics).filter(value => value != null && value !== '');
  const current = semantics(currentRows), historical = semantics(evidence);
  return current.length > 0 && historical.length > 0 && new Set([...current, ...historical]).size > 1;
}
/** Reject malformed or cross-bound evidence before any endpoint values are rendered. */
export function assertMinuteHistoryReport(report: MinuteHistoryReport, request: MinuteHistoryRequest): void {
  const q = request.query, asof = `${request.sourceDate}T${request.endClock}`;
  if (!object(report) || report.method_id !== 'minute-source-label-history-v1'
    || report.query_id !== q.query_id || report.snapshot_id !== q.snapshot_id || report.batch_id !== q.batch_id
    || typeof report.history_id !== 'string' || !hex.test(report.history_id)
    || typeof report.context_query_id !== 'string' || !hex.test(report.context_query_id)
    || report.raw_sha256 !== q.manifest.raw_sha256 || typeof report.raw_sha256 !== 'string' || !hex.test(report.raw_sha256)
    || !same(report.versions, q.manifest.versions) || !same(report.metadata, q.metadata)
    || !same(report.contract, q.manifest.contract ?? null) || !validChecks(report.batch_checks) || !same(report.batch_checks, q.batch_checks)
    || report.source_date !== request.sourceDate || report.start_clock !== request.startClock || report.end_clock !== request.endClock
    || report.as_of_label !== asof || report.lookback !== 5 || report.assumption !== 'same_price_scale_between_endpoints'
    || report.qualification !== 'retrospective_source_endpoint_arithmetic'
    || !same(report.display_policy, { places: 8, rounding: 'half_even' })
    || !ordinals(report.unknown_date_ordinals) || !Array.isArray(report.history_dates) || report.history_dates.length > 5
    || report.history_dates.some((date, i) => !validDate(date) || date >= request.sourceDate || (i > 0 && date <= report.history_dates[i - 1]))
    || !Array.isArray(report.days) || report.days.length !== report.history_dates.length + 1) return invalid();
  const minutes = (value: string) => Number(value.slice(0, 2)) * 60 + Number(value.slice(3));
  if (report.nominal_minutes !== minutes(request.endClock) - minutes(request.startClock)) return invalid();
  const unresolved = report.unknown_date_ordinals.length > 0;
  if (report.window_status !== (unresolved ? 'unresolved_dates' : report.history_dates.length === 5 ? 'complete' : 'insufficient')
    || report.missing_history_dates !== (unresolved ? null : 5 - report.history_dates.length)) return invalid();
  const visible = visibleContext(request);
  const seen = new Set(report.unknown_date_ordinals), selected = new Map([...q.rows, ...q.unlocated].map(row => [row.ordinal, row]));
  const currentRows = visible.filter(row => sourceDay(row) === request.sourceDate);
  for (const [index, day] of report.days.entries()) {
    if (!object(day) || day.source_date !== (index === 0 ? request.sourceDate : report.history_dates[index - 1])
      || day.kind !== (index === 0 ? 'current' : 'history') || !ordinals(day.unknown_clock_ordinals)
      || (day.reason !== null && (typeof day.reason !== 'string' || !reasons.has(day.reason)))) return invalid();
    for (const ordinal of day.unknown_clock_ordinals) { if (seen.has(ordinal)) return invalid(); seen.add(ordinal); }
    for (const [side, label] of [['start', request.startClock], ['end', request.endClock]] as const) {
      if (!Array.isArray(day[side])) return invalid();
      let previous = 0;
      for (const row of day[side]) {
        if (!validRow(row, `${day.source_date}T${label}`) || row.ordinal <= previous || seen.has(row.ordinal)
          || (selected.has(row.ordinal) && !same(row, selected.get(row.ordinal)))) return invalid();
        previous = row.ordinal; seen.add(row.ordinal);
      }
    }
    if (day.reason !== null) {
      if (day.change !== null || day.magnitude !== null
        || day.reason === 'missing_endpoint' && day.start.length > 0 && day.end.length > 0
        || day.reason === 'duplicate_endpoint' && day.start.length < 2 && day.end.length < 2
        || day.reason === 'endpoint_uniqueness_unknown' && day.unknown_clock_ordinals.length === 0) return invalid();
      continue;
    }
    if (knownDisqualification(day, visible.filter(row => sourceDay(row) === day.source_date),
      [...currentRows, ...report.days[0].start, ...report.days[0].end], q)) return invalid();
    if (day.start.length !== 1 || day.end.length !== 1 || day.unknown_clock_ordinals.length
      || !fraction(day.change) || !fraction(day.magnitude)) return invalid();
    const start = exactPositivePrice(day.start[0].values.close), end = exactPositivePrice(day.end[0].values.close);
    if (!start || !end) return invalid();
    const numerator = end[0] * start[1] - start[0] * end[1], denominator = start[0] * end[1];
    const change = BigInt(day.change.numerator), magnitude = BigInt(day.magnitude.numerator);
    if (change * denominator !== numerator * BigInt(day.change.denominator)
      || magnitude !== (change < 0n ? -change : change) || day.magnitude.denominator !== day.change.denominator
      || day.magnitude.display.startsWith('-')) return invalid();
  }
  assertVisibleEvidence(report, visible, selected);
  if (seen.size > 20_000) return invalid();
}
async function hash(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(value));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(byte => byte.toString(16).padStart(2, '0')).join('');
}
export async function loadMinuteHistory(request: MinuteHistoryRequest, signal: AbortSignal): Promise<MinuteHistoryReport> {
  const response = await checkedFetch(request.path, { signal });
  const reader = response.body?.getReader();
  if (!reader) return invalid();
  const chunks: Uint8Array[] = []; let size = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > 2 * 1024 * 1024) { await reader.cancel(); throw new Error('response_limit'); }
    chunks.push(value);
  }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  let report: MinuteHistoryReport;
  try { report = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) as MinuteHistoryReport; } catch { return invalid(); }
  assertMinuteHistoryReport(report, request);
  const contextId = await hash({ ...request.query.selection, cutoff: `${request.sourceDate}T${request.endClock}`,
    ordinal_start: null, ordinal_end: null });
  if (report.context_query_id !== contextId) return invalid();
  const { history_id: historyId, ...identity } = report;
  if (historyId !== await hash(identity)) return invalid();
  return report;
}

/** Shared by the component and race tests; cancelling invalidates success and failure alike. */
export class MinuteHistoryGate {
  private active: { key: string; controller: AbortController } | null = null;
  begin(key: string) { this.cancel(); const token = { key, controller: new AbortController() }; this.active = token; return token; }
  cancel() { this.active?.controller.abort(); this.active = null; }
  isCurrent(token: ReturnType<MinuteHistoryGate['begin']>, key: string) {
    return this.active === token && token.key === key && !token.controller.signal.aborted;
  }
}
