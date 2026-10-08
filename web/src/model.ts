import { fields } from './types.ts';
import type { Display, GeometryEnvelope, GeometryRow, Reply, Row, SelectionDraft } from './types.ts';

export class Generation {
  private value = 0;
  invalidate(): number { return ++this.value; }
  current(): number { return this.value; }
  isCurrent(value: number): boolean { return value === this.value; }
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
