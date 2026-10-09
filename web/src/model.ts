import { fields } from './types.ts';
import type { AggregationReport, ChannelReport, Display, GapReport, GeometryEnvelope, GeometryRow, PivotReport, Query, Reply, Row, SelectionDraft } from './types.ts';

export class Generation {
  private value = 0;
  invalidate(): number { return ++this.value; }
  current(): number { return this.value; }
  isCurrent(value: number): boolean { return value === this.value; }
}

export function minuteReadNotice(query: Pick<Query, 'metadata' | 'rows' | 'unlocated'>): string {
  const labels = query.rows.map(row => row.label).filter((label): label is string => label !== null);
  let first: string | null = null, last: string | null = null;
  for (const label of labels) {
    if (first === null || label < first) first = label;
    if (last === null || label > last) last = label;
  }
  const end = query.metadata.source_end_time;
  const target = typeof end === 'string' && /^[0-9]{14}$/.test(end)
    ? `${end.slice(0, 4)}-${end.slice(4, 6)}-${end.slice(6, 8)}` : null;
  const observed = target !== null && labels.some(label => label.slice(0, 10) === target);
  const range = first === null ? '没有可定位分钟标签' : `实际源标签 ${first}～${last}`;
  const requested = target === null ? '最新交易日覆盖未核' : `请求截止日期 ${target} · ${observed ? '已出现该日期' : '可定位记录未出现该日期'}`;
  const beyond = target !== null && last !== null && last.slice(0, 10) > target ? ' · 包含请求日期之后的标签，时间范围待核' : '';
  return `分钟数据已保存 · 返回${query.rows.length + query.unlocated.length}条 · ${range} · 标签无法定位 ${query.unlocated.length}条 · ${requested}${beyond} · 完整性与闭合未核`;
}

export const directionColors = { up: '#c64d57', down: '#16836d', equal: '#66758b', unknown: '#94a0af' };
function coordinate(value: string | null): number | null {
  if (value === null || !/^-?\d+(?:\.\d+)?$/.test(value)) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function buildPlot(rows: Row[], display: Display[]) {
  const occurrences = new Map<string | null, number>();
  for (const row of rows) occurrences.set(row.label, (occurrences.get(row.label) ?? 0) + 1);
  const status: string[][] = [];
  const candles: ({ time: number } | { time: number; open: number; high: number; low: number; close: number; color: string; borderColor: string; wickColor: string })[] = [];
  const volumes: ({ time: number } | { time: number; value: number; color: string })[] = [];
  rows.forEach((row, time) => {
    const d = display[time];
    const color = directionColors[d.direction];
    const notes: string[] = [];
    const [open, high, low, close] = ['open', 'high', 'low', 'close'].map(k => coordinate(row.values[k as keyof Row['values']]));
    if (d.ohlc_drawable && !d.precision_lost && open !== null && high !== null && low !== null && close !== null) {
      candles.push({ time, open, high, low, close, color, borderColor: color, wickColor: color });
    } else {
      candles.push({ time });
      notes.push(d.precision_lost ? '显示分辨率不足' : 'OHLC 不可绘制');
    }
    const volume = coordinate(row.values.volume);
    if (volume !== null && volume >= 0) {
      volumes.push({ time, value: volume, color });
      if (volume === 0) notes.push('数量为零');
    } else {
      volumes.push({ time });
      notes.push('数量缺失或不可绘制');
    }
    if ((occurrences.get(row.label) ?? 0) > 1) notes.push('重复标签');
    if (row.checks.some(c => c.outcome === 'fail')) notes.push('质量检查未通过');
    status.push(notes);
  });
  return { candles, volumes, labels: rows.map(row => row.label ?? ''), status };
}

export function assertAggregationReport(query: Query, report: AggregationReport, targetMinutes: number): void {
  let asof = query.rows.reduce<string | null>((last, row) => last === null || row.label! > last ? row.label : last, null);
  if (asof !== null && query.selection.cutoff !== null && query.selection.cutoff < asof) asof = query.selection.cutoff;
  if (!report || report.method_id !== 'selected-minute-label-aggregation-v1' || report.query_id !== query.query_id
    || report.snapshot_id !== query.snapshot_id || report.target_minutes !== targetMinutes || report.as_of_label !== asof
    || report.template_id !== 'observed-600059-240-clocks-v1' || report.member_scope !== 'selected_records_only'
    || report.qualification !== 'conditional_source_values' || report.bucket_label_semantics !== 'nominal_last_template_label'
    || report.completeness_semantics !== 'selected_template_members_present_not_market_bar_closed'
    || !hexId.test(report.aggregation_id) || !Array.isArray(report.buckets) || !Array.isArray(report.excluded)) throw new Error('invalid_query_response');
  const source = new Map([...query.rows, ...query.unlocated].map(row => [row.ordinal, row.label]));
  const accounted = new Set<number>(), ids = new Set<string>();
  function account(ordinal: number, label: string | null) {
    if (!source.has(ordinal) || source.get(ordinal) !== label || accounted.has(ordinal)) throw new Error('invalid_query_response');
    accounted.add(ordinal);
  }
  let previous = '';
  for (const bucket of report.buckets) {
    if (!hexId.test(bucket.bucket_id) || ids.has(bucket.bucket_id) || bucket.end_label <= previous
      || !Array.isArray(bucket.expected_labels) || bucket.expected_labels.length !== targetMinutes
      || bucket.first_label !== bucket.expected_labels[0] || bucket.end_label !== bucket.expected_labels.at(-1)
      || !Array.isArray(bucket.members) || !bucket.values || !bucket.observed_values
      || !bucket.display || typeof bucket.template_complete !== 'boolean'
      || !Object.hasOwn(directionColors, bucket.display.direction) || typeof bucket.display.ohlc_drawable !== 'boolean'
      || typeof bucket.display.precision_lost !== 'boolean') throw new Error('invalid_query_response');
    ids.add(bucket.bucket_id); previous = bucket.end_label;
    for (const member of bucket.members) {
      if (!bucket.expected_labels.includes(member.label) || (asof !== null && member.label > asof)) throw new Error('invalid_query_response');
      account(member.ordinal, member.label);
    }
    if (bucket.last_observed_label !== (bucket.members.at(-1)?.label ?? null)
      || (bucket.template_complete && (bucket.membership_reason !== null || bucket.missing_labels.length || bucket.duplicate_labels.length || bucket.future_labels.length
        || bucket.members.length !== targetMinutes || new Set(bucket.members.map(member => member.label)).size !== targetMinutes
        || fields.some(key => bucket.values[key] !== bucket.observed_values[key])))
      || (!bucket.template_complete && (bucket.membership_reason === null || fields.some(key => bucket.values[key] !== null)))) throw new Error('invalid_query_response');
    for (const key of fields) for (const scope of ['values', 'observed_values'] as const) {
      if (bucket[scope][key] !== null && (typeof bucket[scope][key] !== 'string' || !/^\d+(?:\.\d+)?$/.test(bucket[scope][key]!))) throw new Error('invalid_query_response');
    }
  }
  for (const row of report.excluded) account(row.ordinal, row.label);
  if (accounted.size !== source.size) throw new Error('invalid_query_response');
}

export function buildAggregationPlot(report: AggregationReport) {
  // Future nominal ends remain in the partial table and never move onto the chart.
  const buckets = report.buckets.filter(bucket => report.as_of_label !== null && bucket.end_label <= report.as_of_label);
  const rows: Row[] = buckets.map((bucket, index) => ({ ordinal: index + 1, label: bucket.end_label,
    source_label: null, locator: `derived-bucket:${bucket.bucket_id}`, tokens: {}, values: bucket.values,
    checks: [], volume_shares: null, amount_cny: null }));
  return { ...buildPlot(rows, buckets.map((bucket, index) => ({ ordinal: index + 1, ...bucket.display }))), buckets };
}

export function buildChannelPlot(query: Query, report: ChannelReport | null) {
  if (!report || query.metadata.period !== '1d' || report.query_id !== query.query_id
    || report.rows.length !== query.rows.length || report.rows.some((row, i) => row.ordinal !== query.rows[i].ordinal)) return null;
  const segments: { upper: { time: number; value: number }[]; lower: { time: number; value: number }[] }[] = [];
  let segment: typeof segments[number] | null = null;
  let skipped = 0;
  report.rows.forEach((row, time) => {
    const upper = coordinate(row.upper), lower = coordinate(row.lower);
    if (row.reason || upper === null || lower === null || lower < 0 || upper < lower
      || (upper === lower && row.width !== '0')) {
      segment = null; skipped += 1;
      return;
    }
    if (!segment) { segment = { upper: [], lower: [] }; segments.push(segment); }
    segment.upper.push({ time, value: upper });
    segment.lower.push({ time, value: lower });
  });
  return { segments, skipped };
}

export function queryParameters(draft: SelectionDraft, batchRows: number, limit: number): URLSearchParams {
  const parameters = new URLSearchParams();
  if (draft.cutoff) parameters.set('cutoff', draft.cutoff);
  const ordinals = [draft.start, draft.end].map(value => {
    if (value === '') return null;
    if (!/^\d+$/.test(value) || !Number.isSafeInteger(Number(value)) || Number(value) < 1) throw new Error('invalid_ordinal_range');
    return Number(value);
  });
  const [start, end] = ordinals;
  if (batchRows > limit && (start === null || end === null)) throw new Error('explicit_window_required');
  if (start !== null && end !== null && (start > end || end - start + 1 > limit)) throw new Error('invalid_ordinal_range');
  if (start !== null) parameters.set('ordinal_start', String(start));
  if (end !== null) parameters.set('ordinal_end', String(end));
  return parameters;
}

const hexId = /^[a-f0-9]{64}$/;
const lengthText = /^(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/;
const numeratorText = /^(?:0|[1-9]\d{0,37})$/;
const denominatorText = /^[1-9]\d{0,37}$/;
const percentText = /^(?:(?:0|[1-9]\d?)\.\d{2}|100\.00)$/;
const ratioKeys = ['body', 'upper_shadow', 'lower_shadow', 'close_location'] as const;
const lengthKeys = ['range', 'body', 'upper_shadow', 'lower_shadow'] as const;
function fixedKeys(value: unknown, keys: readonly string[]): boolean {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function validGeometryRow(g: GeometryRow): boolean {
  if (!fixedKeys(g, ['ordinal', 'status', 'reason', 'direction', ...lengthKeys, 'ratios', 'ratio_reason'])
    || !fixedKeys(g.ratios, ratioKeys)) return false;
  if (g.status === 'not_evaluated') return ['missing_ohlc', 'invalid_price', 'negative_price', 'invalid_ohlc'].includes(g.reason ?? '')
    && g.direction === null && lengthKeys.every(key => g[key] === null)
    && ratioKeys.every(key => g.ratios[key] === null) && g.ratio_reason === null;
  if (g.status !== 'computed' || g.reason !== null || !['up', 'down', 'equal'].includes(g.direction ?? '')
    || !lengthKeys.every(key => typeof g[key] === 'string' && lengthText.test(g[key]))) return false;
  if (g.range === '0') return g.direction === 'equal' && lengthKeys.every(key => g[key] === '0')
    && ratioKeys.every(key => g.ratios[key] === null) && g.ratio_reason === 'zero_range';
  return g.ratio_reason === null && ratioKeys.every(key => {
    const r = g.ratios[key];
    return fixedKeys(r, ['numerator', 'denominator', 'percent_display']) && r !== null
      && typeof r.numerator === 'string' && numeratorText.test(r.numerator)
      && typeof r.denominator === 'string' && denominatorText.test(r.denominator)
      && (r.numerator !== '0' || r.denominator === '1')
      && typeof r.percent_display === 'string' && percentText.test(r.percent_display);
  });
}

export function assertGeometryEnvelope(envelope: GeometryEnvelope, draft: SelectionDraft, limit: number): void {
  const q = envelope?.query;
  const g = envelope?.geometry;
  const selection = q?.selection;
  if (!q || !Array.isArray(q.rows) || !Array.isArray(q.unlocated)
    || typeof q.query_id !== 'string' || !hexId.test(q.query_id) || q.snapshot_id !== draft.snapshot
    || selection?.snapshot_id !== draft.snapshot || selection.mode !== 'retrospective'
    || selection.cutoff !== (draft.cutoff || null)
    || selection.ordinal_start !== (draft.start === '' ? null : Number(draft.start))
    || selection.ordinal_end !== (draft.end === '' ? null : Number(draft.end))
    || q.rows.length + q.unlocated.length > limit
    || q.counts?.selected_rows !== q.rows.length || q.counts.unlocated_rows !== q.unlocated.length
    || !fixedKeys(g, ['method_id', 'query_id', 'geometry_id', 'qualification', 'source_qualification', 'assumption', 'display_policy', 'rows', 'unlocated'])
    || typeof g.geometry_id !== 'string' || !hexId.test(g.geometry_id) || g.query_id !== q.query_id
    || g.method_id !== 'source-candle-geometry-v1' || g.qualification !== 'source_observation_description'
    || typeof q.manifest?.qualification !== 'string' || g.source_qualification !== q.manifest.qualification
    || g.assumption !== 'same_price_scale_within_row'
    || !fixedKeys(g.display_policy, ['percent_places', 'rounding'])
    || g.display_policy.percent_places !== 2 || g.display_policy.rounding !== 'half_even'
    || !Array.isArray(g.rows) || !Array.isArray(g.unlocated)
    || g.rows.length !== q.rows.length || g.unlocated.length !== q.unlocated.length) throw new Error('invalid_query_response');
  const ordinals = new Set<number>();
  for (const scope of ['rows', 'unlocated'] as const) q[scope].forEach((row, index) => {
    const derived = g[scope][index];
    if (!row || !Number.isSafeInteger(row.ordinal) || row.ordinal < 1 || ordinals.has(row.ordinal)
      || (scope === 'rows' ? typeof row.label !== 'string' || !row.label : row.label !== null)
      || !row.values || !fields.every(field => row.values[field] === null || typeof row.values[field] === 'string')
      || !derived || derived.ordinal !== row.ordinal || !validGeometryRow(derived)) throw new Error('invalid_query_response');
    ordinals.add(row.ordinal);
  });
}

export function assertReply(reply: Reply, draft: SelectionDraft, limit: number): void {
  assertGeometryEnvelope(reply, draft, limit);
  const q = reply.query;
  if (!Array.isArray(reply.display) || reply.display.length !== q.rows.length || !reply.navigation) throw new Error('invalid_query_response');
  q.rows.forEach((row, index) => {
    const d = reply.display[index];
    if (!d || d.ordinal !== row.ordinal || !Object.hasOwn(directionColors, d.direction)
      || typeof d.ohlc_drawable !== 'boolean' || typeof d.precision_lost !== 'boolean') throw new Error('invalid_query_response');
  });
}

export function assertGapReport(query: Query, report: GapReport): void {
  let asof = query.rows.reduce<string | null>((value, row) => value === null || row.label! > value ? row.label : value, null);
  if (asof !== null && query.selection.cutoff !== null && query.selection.cutoff < asof) asof = query.selection.cutoff;
  if (!report || report.method_id !== 'source-price-gaps-v1' || report.query_id !== query.query_id
    || report.qualification !== 'conditional_source_values' || report.as_of_label !== asof
    || report.origin_scope !== 'selected_source_rows' || report.observation_scope !== 'full_source_context_to_asof'
    || report.adjacency !== 'adjacent_located_labels' || report.first_event_scope !== 'first_unique_valid_located_before_interruption'
    || !hexId.test(report.gaps_id) || !hexId.test(report.context_query_id)) throw new Error('invalid_query_response');
  for (const scope of ['rows', 'unlocated'] as const) {
    if (!Array.isArray(report[scope]) || report[scope].length !== query[scope].length) throw new Error('invalid_query_response');
    report[scope].forEach((row, index) => {
      if (row.ordinal !== query[scope][index].ordinal || row.label !== query[scope][index].label) throw new Error('invalid_query_response');
      const gap = row.gap;
      if (!gap) return;
      if (!hexId.test(gap.gap_id) || !['up', 'down'].includes(gap.direction)
        || ![gap.lower, gap.upper, gap.width].every(value => typeof value === 'string' && /^\d+(\.\d+)?$/.test(value))
        || row.label === null || asof === null) throw new Error('invalid_query_response');
      for (const event of [gap.near_event, gap.far_event]) {
        if (event && (!Number.isSafeInteger(event.ordinal) || event.ordinal < 1 || event.label <= row.label || event.label > asof
          || typeof event.extreme !== 'string' || typeof event.contains_boundary !== 'boolean'
          || !['equal', 'beyond'].includes(event.relation) || !['overlaps_interval', 'passed_without_overlap'].includes(event.range_relation))) throw new Error('invalid_query_response');
      }
      if (gap.far_event && (!gap.near_event || gap.near_event.label > gap.far_event.label)) throw new Error('invalid_query_response');
      if (gap.interrupted_at && (gap.interrupted_at.label <= row.label || gap.interrupted_at.label > asof
        || [gap.near_event, gap.far_event].some(event => event && event.label >= gap.interrupted_at!.label))) throw new Error('invalid_query_response');
    });
  }
}

export function assertPivotReport(query: Query, report: PivotReport, radius: number): void {
  let asof = query.rows.reduce<string | null>((value, row) => value === null || row.label! > value ? row.label : value, null);
  if (asof !== null && query.selection.cutoff !== null && query.selection.cutoff < asof) asof = query.selection.cutoff;
  if (!report || report.method_id !== 'source-window-pivots-v1' || report.query_id !== query.query_id
    || report.qualification !== 'conditional_source_values' || report.radius !== radius || !Number.isInteger(radius) || radius < 1 || radius > 20
    || report.as_of_label !== asof || report.anchor_scope !== 'selected_source_rows' || report.window_unit !== 'located_source_labels'
    || report.tie_policy !== 'strict_no_ties' || report.confirmation_semantics !== 'right_source_window_present'
    || !hexId.test(report.pivots_id) || !hexId.test(report.context_query_id) || !Array.isArray(report.events)
    || !Array.isArray(report.members)) throw new Error('invalid_query_response');
  const expected = new Map<string, { ordinal: number; kind: string; label: string; confirmation: string; confirmationOrdinal: number }>();
  for (const scope of ['rows', 'unlocated'] as const) {
    if (!Array.isArray(report[scope]) || report[scope].length !== query[scope].length) throw new Error('invalid_query_response');
    report[scope].forEach((row, index) => {
      if (row.ordinal !== query[scope][index].ordinal || row.label !== query[scope][index].label) throw new Error('invalid_query_response');
      for (const kind of ['high', 'low'] as const) {
        const decision = row[kind];
        if (!decision || ![true, false, null].includes(decision.is_pivot)) throw new Error('invalid_query_response');
        if (decision.is_pivot === true) {
          if (!decision.pivot_id || !hexId.test(decision.pivot_id) || expected.has(decision.pivot_id) || row.reason !== null || decision.reason !== null
            || row.label === null || row.confirmation_label === null || row.confirmation_label <= row.label || asof === null || row.confirmation_label > asof
            || row.left_count !== radius || row.right_count !== radius || !Number.isSafeInteger(row.confirmation_ordinal) || row.confirmation_ordinal! < 1) throw new Error('invalid_query_response');
          expected.set(decision.pivot_id, { ordinal: row.ordinal, kind, label: row.label, confirmation: row.confirmation_label, confirmationOrdinal: row.confirmation_ordinal! });
        } else if (decision.pivot_id !== null) throw new Error('invalid_query_response');
      }
    });
  }
  if (expected.size !== report.events.length) throw new Error('invalid_query_response');
  for (const event of report.events) {
    const origin = expected.get(event.pivot_id);
    if (!origin || origin.ordinal !== event.anchor_ordinal || origin.kind !== event.kind || origin.label !== event.anchor_label
      || origin.confirmation !== event.confirmation_label || origin.confirmationOrdinal !== event.confirmation_ordinal
      || event.delay_source_labels !== radius || typeof event.price !== 'string' || !/^\d+(\.\d+)?$/.test(event.price)) throw new Error('invalid_query_response');
    expected.delete(event.pivot_id);
  }
}

export function buildPivotPlot(reply: Reply, report: PivotReport | null) {
  if (!report || !['1d', '1m'].includes(reply.query.metadata.period ?? '')) return null;
  try { assertPivotReport(reply.query, report, report.radius); } catch { return null; }
  const positions = new Map(reply.query.rows.map((row, index) => [row.ordinal, index]));
  const markers: { time: number; position: 'aboveBar' | 'belowBar'; shape: 'arrowDown' | 'arrowUp'; color: string; text: string }[] = [];
  let skipped = 0;
  for (const event of report.events) {
    const time = positions.get(event.confirmation_ordinal);
    if (time === undefined || reply.query.rows[time].label !== event.confirmation_label || !reply.display[time]?.ohlc_drawable) { skipped += 1; continue; }
    markers.push({ time, position: event.kind === 'high' ? 'aboveBar' : 'belowBar', shape: event.kind === 'high' ? 'arrowDown' : 'arrowUp',
      color: event.kind === 'high' ? '#4169a1' : '#ad6717', text: event.kind === 'high' ? '确高' : '确低' });
  }
  markers.sort((a, b) => a.time - b.time);
  return { markers, skipped };
}
