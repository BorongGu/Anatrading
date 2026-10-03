import type { Display, Reply, Row, SelectionDraft } from './types.ts';

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

export function assertReply(reply: Reply, draft: SelectionDraft, limit: number): void {
  const q = reply?.query;
  const selection = q?.selection;
  if (!q || !Array.isArray(q.rows) || !Array.isArray(q.unlocated) || !Array.isArray(reply.display)
    || typeof q.query_id !== 'string' || !q.query_id || q.snapshot_id !== draft.snapshot
    || selection?.snapshot_id !== draft.snapshot || selection.mode !== 'retrospective'
    || selection.cutoff !== (draft.cutoff || null)
    || selection.ordinal_start !== (draft.start === '' ? null : Number(draft.start))
    || selection.ordinal_end !== (draft.end === '' ? null : Number(draft.end))
    || q.rows.length + q.unlocated.length > limit
    || q.counts.selected_rows !== q.rows.length || q.counts.unlocated_rows !== q.unlocated.length
    || reply.display.length !== q.rows.length || !reply.navigation) throw new Error('invalid_query_response');
  const ordinals = new Set<number>();
  q.rows.forEach((row, index) => {
    const d = reply.display[index];
    if (typeof row.label !== 'string' || !row.label || ordinals.has(row.ordinal)
      || d.ordinal !== row.ordinal || !(d.direction in directionColors)
      || typeof d.ohlc_drawable !== 'boolean' || typeof d.precision_lost !== 'boolean') throw new Error('invalid_query_response');
    ordinals.add(row.ordinal);
  });
}
