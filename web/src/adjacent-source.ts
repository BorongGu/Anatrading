import type { Query, Row } from './types.ts';
import type { ResearchEnvelope, SingleResult } from './research-types.ts';
import { reversalContextMatches } from './close-reversal.ts';
import type { ReversalContext } from './close-reversal.ts';

// The same small captured context owns both the panel and published consumers.
export interface SourceResearchContext extends ReversalContext {
  sourceCode: string | undefined; sourceAdjustflag: string | undefined; batchUnlocatedRows: number | undefined;
  period: string | undefined; qualification: string | undefined; knownNegative: boolean; quarantined: boolean;
}
export function sourceResearchContext(query: Query): SourceResearchContext {
  return { ownerQueryId: query.query_id, snapshotId: query.snapshot_id, batchId: query.batch_id,
    cutoff: query.selection.cutoff ?? null, ordinalStart: query.selection.ordinal_start ?? null, ordinalEnd: query.selection.ordinal_end ?? null,
    sourceCode: query.metadata.source_code, sourceAdjustflag: query.metadata.source_adjustflag, batchUnlocatedRows: query.counts?.batch_unlocated_rows,
    period: query.metadata.period, qualification: query.manifest?.qualification, quarantined: query.metadata.quarantined === true,
    knownNegative: query.batch_checks?.some(check => check.name === 'known_negative_sample' && check.outcome === 'fail') ?? false };
}
export function sourceResearchContextMatches(a: SourceResearchContext, b: SourceResearchContext): boolean {
  return reversalContextMatches(a, b) && a.period === b.period && a.qualification === b.qualification
    && a.knownNegative === b.knownNegative && a.quarantined === b.quarantined
    && a.sourceCode === b.sourceCode && a.sourceAdjustflag === b.sourceAdjustflag && a.batchUnlocatedRows === b.batchUnlocatedRows;
}
export interface SourceResearchBinding { queryId: string; report: ResearchEnvelope<SingleResult>; context: SourceResearchContext }

// A late result or invalidation from an unmounted query cannot replace current evidence.
export function bindSourceResearch(query: Query | null | undefined, queryId: string, report: ResearchEnvelope<SingleResult> | null): SourceResearchBinding | null | undefined {
  if (query?.query_id !== queryId) return undefined;
  return report ? { queryId, report, context: sourceResearchContext(query) } : null;
}

// Select from the validated full-prefix recurrence, never the visible raw page.
export function adjacentSource(query: Query, row: Row, binding: SourceResearchBinding | null) {
  const unavailable = (reason: string) => ({ reason, current: null, previous: null, days: null, value: null });
  if (!binding || binding.queryId !== query.query_id) return unavailable('研究结果尚未可用；请等待或更新日线研究。');
  if (!sourceResearchContextMatches(binding.context, sourceResearchContext(query))) return unavailable('研究来源或查询条件不匹配，未关联。');
  const report = binding.report;
  if (report.inputs.length !== 1 || report.inputs[0].snapshot_id !== query.snapshot_id
    || report.parameters.cutoff !== query.selection.cutoff) return unavailable('研究来源或截止日期不匹配，未关联。');
  if (!(query.rows.includes(row) || query.unlocated.includes(row))) return unavailable('记录不属于当前查询，未关联。');
  if (row.label === null) return unavailable('原记录无法定位，未关联相邻日期。');
  const index = report.result.series.findIndex(item => item.date === row.label);
  const current = report.result.series[index];
  if (!current) return unavailable('完整研究范围内没有对应日期，未关联。');
  if (current.ordinal !== row.ordinal) return unavailable(current.reason === 'duplicate_date'
    ? '同一日期有重复来源记录，无法确定唯一相邻原价。' : '日期与源序号不匹配，未关联。');
  const previous = index > 0 ? report.result.series[index - 1] : null;
  const days = previous ? (Date.parse(current.date) - Date.parse(previous.date)) / 86_400_000 : null;
  // Defensive linkage validation does not recalculate or replace missing estimates.
  if (current.log_return !== null && (!previous || previous.ordinal === null || previous.reason !== null
    || current.reason !== null || current.segment_id !== previous.segment_id || current.segment_observations <= 1)) {
    return unavailable('相邻记录资格不一致，未关联。');
  }
  return { current, previous, days, value: current.log_return,
    reason: current.log_return === null ? current.reason ?? current.reset_reason ?? 'no_return' : null };
}
