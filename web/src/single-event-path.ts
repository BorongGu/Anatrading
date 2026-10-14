import type { ResearchExpected } from './research-model.ts';
import type { EventCounts, EventPartition, ResearchEnvelope, SingleResult } from './research-types.ts';

// Input contract: JSON accepted by assertResearchReply. Published reports and
// existing consumers are read-only. Only the bounded owned projection is frozen.
export type EventPathReport = ResearchEnvelope<SingleResult>;
export interface EventPathContext {
  ownerQueryId: string; snapshotId: string; cutoff: string | null;
  ordinalStart: number | null; ordinalEnd: number | null;
}
export type EventPathCode = 'identity' | 'cutoff' | 'event_link' | 'endpoint' | 'label_state' | 'evaluation_state' | 'partition_counts' | 'price_text' | 'slot_structure' | 'resource';
export class EventPathError extends Error {
  readonly code: EventPathCode;
  constructor(code: EventPathCode) { super('event_path_inconsistent'); this.code = code; }
}
function check(value: unknown, code: EventPathCode): asserts value { if (!value) throw new EventPathError(code); }
export function isEventPathPrice(value: unknown): value is string {
  return typeof value === 'string' && value.length <= 40 && /^-?(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(value) && !/[\r\n]/.test(value) && value !== '-0';
}
const positive = (v: string | null) => v !== null && v !== '0' && !v.startsWith('-');
function price(value: unknown): asserts value is string | null { check(value === null || isEventPathPrice(value), 'price_text'); }
function day(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.length !== 10) return false;
  const [y, m, d] = value.split('-').map(Number), leap = y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0);
  return y > 0 && m >= 1 && m <= 12 && d >= 1 && d <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1];
}
const integer = (v: unknown, min = 0, max = Number.MAX_SAFE_INTEGER) => typeof v === 'number' && Number.isSafeInteger(v) && v >= min && v <= max;
const id = (v: unknown) => typeof v === 'string' && v.length === 64 && /^[a-f0-9]{64}$/.test(v);
const countKeys = ['raw_events', 'selected_events', 'overlap_excluded', 'valid', 'invalid', 'immature', 'purged'] as const;
type LedgerCounts = Pick<EventCounts, typeof countKeys[number]>;
const newCounts = (): LedgerCounts => ({ raw_events: 0, selected_events: 0, overlap_excluded: 0, valid: 0, invalid: 0, immature: 0, purged: 0 });
function compareCounts(part: EventPartition, counts: LedgerCounts) {
  check(part && countKeys.every(key => integer(part.counts?.[key], 0, 20_000) && part.counts[key] === counts[key]) && part.statistics?.count === counts.valid, 'partition_counts');
}
export interface AcceptedEventPath {
  readonly token: object;
  readonly report: EventPathReport;
  readonly context: Readonly<EventPathContext>;
}
export function eventPathBelongs(accepted: AcceptedEventPath, report: EventPathReport | null, context: EventPathContext): boolean {
  const a = accepted.context;
  return accepted.report === report && a.ownerQueryId === context.ownerQueryId && a.snapshotId === context.snapshotId && a.cutoff === context.cutoff
    && a.ordinalStart === context.ordinalStart && a.ordinalEnd === context.ordinalEnd;
}
export function acceptEventPath(report: EventPathReport, context: EventPathContext, expected: ResearchExpected): AcceptedEventPath {
  const { series, events } = report.result, p = report.parameters;
  check(expected.kind === 'single' && report.method_id === 'daily-causal-research-v1' && report.mode === 'retrospective'
    && id(report.analysis_id) && id(context.ownerQueryId) && id(context.snapshotId) && report.inputs.length === 1
    && report.inputs[0].snapshot_id === context.snapshotId && id(report.inputs[0].query_id)
    && expected.snapshotIds.length === 1 && expected.snapshotIds[0] === context.snapshotId
    && p.horizon === 5 && p.lookback === expected.parameters.lookback && integer(p.lookback, 2, 252)
    && p.horizon === expected.parameters.horizon && p.test_start === expected.parameters.test_start
    && p.cutoff === expected.parameters.cutoff && p.cutoff === context.cutoff, 'identity');
  const cutoff = context.cutoff, split = events.test_start;
  check((cutoff === null || day(cutoff)) && (split === null || day(split)) && split === p.test_start
    && events.lookback === p.lookback && events.horizon === 5, 'cutoff');
  check(Array.isArray(series) && Array.isArray(events.rows) && series.length <= 20_000 && events.rows.length <= series.length, 'resource');
  const end = cutoff ?? series.at(-1)?.date ?? null;
  check(events.evaluation_as_of === end && (end === null || day(end)), 'cutoff');
  let previousDate = '';
  for (const row of series) {
    check(day(row.date) && row.date > previousDate && end !== null && row.date <= end, 'cutoff'); previousDate = row.date;
  }
  const partitionNames = split === null ? ['descriptive'] : ['train', 'test'];
  check(events.mode === (split === null ? 'descriptive' : 'time_split_descriptive')
    && Object.keys(events.partitions).length === partitionNames.length && partitionNames.every(name => Object.hasOwn(events.partitions, name)), 'partition_counts');
  const total = newCounts(), groups = new Map(partitionNames.map(name => [name, newCounts()]));
  let lastIndex = -1;
  for (const event of events.rows) {
    check(integer(event.index, 0, series.length - 1) && event.index > lastIndex && integer(event.ordinal, 1), 'event_link');
    lastIndex = event.index; const start = series[event.index], finish = series[event.index + 5];
    check(event.date === start.date && event.ordinal === start.ordinal && start.breakout === true && event.signal_as_of === event.date && event.evaluation_as_of === end, 'event_link');
    check(Object.hasOwn(event, 'start_close') && Object.hasOwn(event, 'end_close'), 'endpoint');
    price(event.start_close); price(event.end_close);
    check(positive(event.start_close) && event.start_close === start.close && event.end_close === (finish?.close ?? null), 'endpoint');
    const partition = split === null ? 'descriptive' : event.date < split ? 'train' : 'test';
    check(event.partition === partition && typeof event.selected === 'boolean', 'evaluation_state');
    check(['valid', 'invalid', 'immature'].includes(event.label_status), 'label_state');
    if (!finish) check(event.label_status === 'immature' && event.label_end === null && event.end_close === null && event.price_change === null && event.label_reason === 'insufficient_future_records', 'label_state');
    else {
      check(event.label_status !== 'immature' && event.label_end === finish.date, 'label_state');
      if (event.label_status === 'valid') check(event.label_reason === null && typeof event.price_change === 'number' && Number.isFinite(event.price_change) && positive(event.end_close), 'label_state');
      else check(event.price_change === null && ['invalid_label_window', 'numerical_failure'].includes(event.label_reason ?? ''), 'label_state');
    }
    const evaluation = !event.selected ? 'overlap_excluded' : partition === 'train' && event.label_end !== null && split !== null && event.label_end >= split ? 'purged' : event.label_status;
    check(event.evaluation_status === evaluation, 'evaluation_state');
    for (const counts of [total, groups.get(partition)!]) {
      counts.raw_events++; if (event.selected) counts.selected_events++;
      if (evaluation === 'valid') counts.valid++;
      else if (evaluation === 'invalid') counts.invalid++;
      else if (evaluation === 'immature') counts.immature++;
      else if (evaluation === 'purged') counts.purged++;
      else counts.overlap_excluded++;
    }
  }
  compareCounts(events, total); for (const [name, counts] of groups) compareCounts(events.partitions[name], counts);
  return { token: {}, report, context: Object.freeze({ ...context }) };
}
export interface EventPathSlot { readonly offset: number; readonly exists: boolean; readonly date: string | null; readonly ordinal: number | null; readonly close: string | null; readonly status: string | null; readonly reason: string | null }
export interface EventPathProjection {
  readonly identity: Readonly<{ snapshotId: string; ownerQueryId: string; researchQueryId: string; analysisId: string }>;
  readonly parameters: Readonly<{ lookback: number; horizon: 5; testStart: string | null; requestedCutoff: string | null; evaluationAsOf: string | null }>;
  readonly event: Readonly<SingleResult['events']['rows'][number]>;
  readonly slots: readonly EventPathSlot[];
}
export function captureEventPath(accepted: AcceptedEventPath, eventPosition: number): EventPathProjection {
  const { report } = accepted, { series, events } = report.result;
  check(integer(eventPosition, 0, events.rows.length - 1), 'event_link');
  const e = events.rows[eventPosition], slots: EventPathSlot[] = [];
  for (let offset = 0; offset < 6; offset++) {
    const row = series[e.index + offset];
    if (!row) { slots.push(Object.freeze({ offset, exists: false, date: null, ordinal: null, close: null, status: null, reason: null })); continue; }
    price(row.close);
    check(day(row.date) && (row.ordinal === null || integer(row.ordinal, 1)) && ['computed', 'warming_up', 'invalid'].includes(row.status)
      && (row.reason === null || typeof row.reason === 'string' && row.reason.length > 0 && row.reason.length <= 4096), 'slot_structure');
    check(row.status === 'invalid' ? row.reason !== null : row.reason === null, 'slot_structure');
    check((row.ordinal === null || row.reason === 'duplicate_date') ? row.ordinal === null && row.close === null && row.status === 'invalid' && row.reason === 'duplicate_date' : true, 'slot_structure');
    if (e.label_status === 'valid') check(positive(row.close) && row.ordinal !== null && (row.reason === null || row.reason === 'numerical_failure'), 'label_state');
    slots.push(Object.freeze({ offset, exists: true, date: row.date, ordinal: row.ordinal, close: row.close, status: row.status, reason: row.reason }));
  }
  check(e.label_status !== 'valid' || slots.every(slot => slot.exists), 'label_state');
  // Explicit scalar copies: never freeze or retain mutable report children here.
  const event = Object.freeze({ index: e.index, date: e.date, ordinal: e.ordinal, partition: e.partition, selected: e.selected,
    label_status: e.label_status, label_reason: e.label_reason, evaluation_status: e.evaluation_status, label_end: e.label_end,
    start_close: e.start_close, end_close: e.end_close, price_change: e.price_change, signal_as_of: e.signal_as_of, evaluation_as_of: e.evaluation_as_of });
  return Object.freeze({ identity: Object.freeze({ snapshotId: accepted.context.snapshotId, ownerQueryId: accepted.context.ownerQueryId, researchQueryId: report.inputs[0].query_id, analysisId: report.analysis_id }),
    parameters: Object.freeze({ lookback: events.lookback, horizon: 5 as const, testStart: events.test_start, requestedCutoff: accepted.context.cutoff, evaluationAsOf: events.evaluation_as_of }), event, slots: Object.freeze(slots) });
}
export function eventPathPartitionName(value: string): string {
  return value === 'descriptive' ? '全段描述' : value === 'train' ? '训练段' : value === 'test' ? '测试段' : '未识别分段';
}
export function eventPathMembership(projection: EventPathProjection, displayedPartition: string): string {
  const e = projection.event, original = eventPathPartitionName(e.partition), current = eventPathPartitionName(displayedPartition);
  if (e.selected && e.evaluation_status === 'valid') return e.partition === displayedPartition
    ? `按原报告，此事件计入当前${current}的有效事件样本。`
    : `按原报告，此事件属于${original}的有效事件样本；当前上方显示${current}，本条不计入该分段。`;
  const reason = e.evaluation_status === 'overlap_excluded' ? '与此前已保留事件重叠' : e.evaluation_status === 'purged' ? '后续窗口跨过分段日期' : e.evaluation_status === 'immature' ? '后续记录尚未满5步' : '原标签无效';
  return `本条未计入当前上方的有效事件样本：${reason}。原所属分段为${original}。`;
}
