export interface ResearchEnvelope<T> {
  method_id: string; analysis_id: string; inputs: { snapshot_id: string; query_id: string }[];
  parameters: Record<string, unknown>; mode: 'retrospective'; limitations: string[]; result: T;
}
export interface Distribution {
  count: number; mean: number | null; median: number | null; q05: number | null; q25: number | null;
  q75: number | null; q95: number | null; positive_count: number; zero_count: number; negative_count: number; positive_fraction: number | null;
}
export interface EventCounts {
  candidate_dates: number; rule_computable: number; raw_events: number; overlap_excluded: number; selected_events: number;
  valid: number; immature: number; invalid: number; purged: number;
}
export interface EventPartition {
  counts: EventCounts; statistics: Distribution;
  baseline: { counts: { candidate_dates: number; valid: number; immature: number; invalid: number; purged: number }; statistics: Distribution };
}
export interface SingleRow {
  date: string; ordinal: number | null; close: string | null; segment_id: number | null; segment_observations: number;
  warmup: boolean; status: 'warming_up' | 'computed' | 'invalid'; reason: string | null; reset_reason: string | null;
  kalman_level: number | null; kalman_slope: number | null; kalman_price: number | null; ema_log: number | null; ema_price: number | null;
  kalman_price_reason: string | null; ema_price_reason: string | null; model_deviation: number | null; log_return: number | null; ewma_volatility: number | null; return_shock: number | null;
  return_shock_reason: string | null; prior_high: string | null; breakout: boolean | null; breakout_reason: string | null;
}
export interface SingleResult {
  series: SingleRow[];
  events: EventPartition & {
    rows: { date: string; ordinal: number; index: number; partition: string; selected: boolean; evaluation_status: string; label_status: string;
      label_reason: string | null; label_end: string | null; price_change: number | null; signal_as_of: string; evaluation_as_of: string }[];
    partitions: Record<string, EventPartition>; test_start: string | null; evaluation_as_of: string | null;
    mode: string; lookback: number; horizon: number;
  };
  coverage: Record<string, unknown>; parameters: Record<string, unknown>; numeric_kind: string; qualification: string;
}
export interface Identity { symbol: string; code: string; venue: string; market: string; qualification: string }
export interface PairRow {
  date: string; left_ordinal: number | null; right_ordinal: number | null; return_start_date: string | null;
  left_log_return: number | null; right_log_return: number | null; return_correlation: number | null; return_beta: number | null;
  log_price_alpha: number | null; log_price_beta: number | null; residual_scale: number | null; residual_deviation: number | null;
  relative_strength: number | null; n_prices: number; n_returns: number; price_start_date: string | null; price_end_date: string | null;
  returns_start_date: string | null; returns_end_date: string | null; reason: string | null; correlation_reason: string | null;
  return_beta_reason: string | null; price_regression_reason: string | null; deviation_reason: string | null;
  relative_strength_reason: string | null; coverage_reason: string | null;
}
export interface PairResult {
  series: PairRow[];
  alignment: { left_only_dates: number; right_only_dates: number; common_dates: number; valid_common_dates: number;
    left: { source_rows: number; date_groups: number; duplicate_groups: number; invalid_groups: number; unlocated_rows: number; coverage_known: boolean };
    right: { source_rows: number; date_groups: number; duplicate_groups: number; invalid_groups: number; unlocated_rows: number; coverage_known: boolean } };
  roles: { left: Identity; right: Identity }; baseline: { date: string; left_close: string; right_close: string } | null;
}
export interface UniverseMember {
  identity: Identity; snapshot_id: string; cutoff_present: boolean; cutoff_valid: boolean; momentum: number | null;
  volatility: number | null; max_drawdown: number | null; momentum_reason: string | null; volatility_reason: string | null;
  max_drawdown_reason: string | null; start_date: string | null; end_date: string | null; n_prices: number; n_returns: number;
  rank: number | null; coverage: Record<string, unknown>;
}
export interface UniverseResult {
  members: UniverseMember[];
  breadth: { selected: number; cutoff_present: number; cutoff_valid: number; momentum_valid: number; volatility_valid: number;
    max_drawdown_valid: number; positive: number; zero: number; negative: number; positive_momentum_fraction: number | null;
    momentum_coverage: number | null; cutoff_coverage: number | null;
    metrics: Record<string, { eligible: number; missing: number; invalid: number; short_history: number }> };
}
