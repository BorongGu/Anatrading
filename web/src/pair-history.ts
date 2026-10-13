import type { PairRow, PairResult, ResearchEnvelope } from './research-types.ts';

export const PAIR_HISTORY_PAGE_SIZE = 50;
// The validated source is chronological. Read only the selected reverse page;
// never sort, filter, mutate or scan the complete source on a render.
export function pairHistoryPage(series: PairRow[], requestedPage: number) {
  const total = series.length;
  const pages = Math.max(1, Math.ceil(total / PAIR_HISTORY_PAGE_SIZE));
  const page = Math.min(pages - 1, Math.max(0, Math.trunc(requestedPage) || 0));
  const end = total - page * PAIR_HISTORY_PAGE_SIZE;
  return { total, pages, page, rows: series.slice(Math.max(0, end - PAIR_HISTORY_PAGE_SIZE), end).reverse() };
}

// Only the small request identity is serialized; source rows are never hashed.
export function pairHistoryIdentity(report: ResearchEnvelope<PairResult>, lookback: number): string {
  return JSON.stringify([report.method_id, report.analysis_id, report.inputs.map(input => [input.snapshot_id, input.query_id]), report.parameters.cutoff, report.parameters.lookback, lookback]);
}
