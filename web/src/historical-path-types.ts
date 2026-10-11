import type { ResearchEnvelope } from './research-types.ts';

export type PathMethod = 'path' | 'endpoint' | 'recent';
export interface PathWindow {
  start_index: number; end_index: number; start_date: string; end_date: string; calendar_days: number;
  ordinals: number[]; prices: string[]; relative_path: string[]; endpoint_change: string;
  max_drawdown: { value: string; peak_step: number; trough_step: number };
  distance: string; endpoint_distance: string; max_point_difference: { value: string; step: number }; differences: string[];
}
export interface PathCounts { total: number; valid: number; invalid: number; selected: number; overlap_excluded: number; remaining: number }
export type PathLedgerStatus = [number | null, number | null] | null;
export type PathLedgerRow = [number, string | null, string | null, string | null, PathLedgerStatus, PathLedgerStatus, PathLedgerStatus, number | null];
export interface HistoricalPathResult {
  identity: { symbol: string; code: string; venue: string; market: string; qualification: string };
  cutoff: string; parameters: { steps: 20; max_matches: 3; metric: string; qualification_rule: string; display_rule: string };
  groups: string[]; query: PathWindow; windows: PathWindow[]; selections: Record<PathMethod, number[]>;
  nonprice_check_failures?: Record<string, number>;
  counts: Record<PathMethod, PathCounts>; ledger_columns: string[]; ledger: PathLedgerRow[];
}
export type HistoricalPathEnvelope = ResearchEnvelope<HistoricalPathResult>;
export interface HistoricalPathRequest { path: string; expected: { snapshotId: string; cutoff: string } }
export interface HistoricalPathState {
  status: 'idle' | 'dirty' | 'loading' | 'ready' | 'error' | 'cancelled';
  report: HistoricalPathEnvelope | null; error: unknown; selected: number | null; rejected: boolean;
}
