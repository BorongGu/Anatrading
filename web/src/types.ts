export const fields = ['open', 'high', 'low', 'close', 'volume', 'amount'] as const;
export type Field = typeof fields[number];
export const fieldNames: Record<Field, string> = { open: '开', high: '高', low: '低', close: '收', volume: '源数量', amount: '源金额' };
export interface Check { name: string; outcome: 'pass' | 'fail' | 'not_evaluated'; reason?: string | null; assumption?: string | null }
export interface Row {
  ordinal: number; locator: string; source_label: string | null; label: string | null;
  tokens: Record<string, string | null>; values: Record<Field, string | null>; checks: Check[];
  volume_shares: null; amount_cny: null;
}
export interface Display { ordinal: number; direction: 'up' | 'down' | 'equal' | 'unknown'; ohlc_drawable: boolean; precision_lost: boolean }
export interface AggregateBucket {
  bucket_id: string; first_label: string; end_label: string; segment: string;
  expected_labels: string[]; members: { ordinal: number; label: string }[];
  missing_labels: string[]; duplicate_labels: string[]; future_labels: string[];
  last_observed_label: string | null; template_complete: boolean; membership_reason: string | null;
  values: Record<Field, string | null>; observed_values: Record<Field, string | null>;
  reasons: Record<'ohlc' | 'volume' | 'amount', string | null>; observed_reasons: AggregateBucket['reasons'];
  display: Omit<Display, 'ordinal'>;
}
export interface AggregationReport {
  method_id: 'selected-minute-label-aggregation-v1'; aggregation_id: string; query_id: string; snapshot_id: string;
  target_minutes: number; as_of_label: string | null; template_id: 'observed-600059-240-clocks-v1';
  qualification: 'conditional_source_values'; member_scope: 'selected_records_only';
  bucket_label_semantics: 'nominal_last_template_label'; completeness_semantics: string;
  unknown_date_ordinals: number[]; unknown_clock_dates: string[];
  excluded: { ordinal: number; label: string | null; reason: string }[]; buckets: AggregateBucket[];
}
export interface Evidence { value?: unknown; status?: string; reason?: string; applicability?: string }
export interface SourceContract {
  format_id?: string;
  source_semantics?: { scope?: string; fields?: Record<string, Evidence> };
  price_scaling?: Evidence; standard_units?: Evidence; temporal_semantics?: Evidence;
  documented_units?: unknown; [key: string]: unknown;
}
export interface Snapshot {
  snapshot_id: string; batch_id: string; row_count: number;
  metadata: {
    period?: string; source_code?: string; source_name?: string; source_venue?: string;
    source_adjustment?: string; source_adjustflag?: string; instrument_id?: string | null;
    interpretation?: Record<string, string>; interpretation_status?: string;
    [key: string]: unknown;
  };
  manifest: {
    raw_sha256?: string; qualification?: string; versions?: unknown;
    contract?: SourceContract;
    [key: string]: unknown;
  };
}
export interface SelectionDraft { snapshot: string; cutoff: string; start: string; end: string }
export interface Query {
  snapshot_id: string; query_id: string; batch_id: string;
  selection: { snapshot_id: string; mode: string; cutoff: string | null; ordinal_start: number | null; ordinal_end: number | null; fields: string[]; versions: unknown };
  rows: Row[]; unlocated: Row[]; manifest: Snapshot['manifest']; metadata: Snapshot['metadata'];
  counts: { selected_rows: number; unlocated_rows: number; batch_rows: number; batch_unlocated_rows: number };
  quality: Record<string, { pass: number; fail: number; not_evaluated: number }>;
  unlocated_quality: Query['quality']; batch_checks: Check[];
  totals: Record<string, { known_sum: string; available_rows: number; unavailable_rows: number; meaning: string }>;
}
export interface GeometryRatio { numerator: string; denominator: string; percent_display: string }
export interface GeometryRow {
  ordinal: number; status: 'computed' | 'not_evaluated';
  reason: 'missing_ohlc' | 'invalid_price' | 'negative_price' | 'invalid_ohlc' | null;
  direction: 'up' | 'down' | 'equal' | null;
  range: string | null; body: string | null; upper_shadow: string | null; lower_shadow: string | null;
  ratios: Record<'body' | 'upper_shadow' | 'lower_shadow' | 'close_location', GeometryRatio | null>;
  ratio_reason: 'zero_range' | null;
}
export interface GeometryReport {
  method_id: 'source-candle-geometry-v1'; query_id: string; geometry_id: string;
  qualification: 'source_observation_description'; source_qualification: string;
  assumption: 'same_price_scale_within_row'; display_policy: { percent_places: 2; rounding: 'half_even' };
  rows: GeometryRow[]; unlocated: GeometryRow[];
}
export interface GeometryEnvelope { query: Query; geometry: GeometryReport }
export interface ReconciliationValues {
  selected_minute_sum: string | null; daily_source_value: string | null; difference: string | null;
  minute_reason: string | null; daily_reason: string | null;
}
export interface ReconciliationReport {
  method_id: 'selected-minute-daily-source-reconciliation-v1'; qualification: 'retrospective_source_arithmetic';
  reconciliation_id: string; minute_query_id: string; daily_query_id: string;
  minute_snapshot_id: string; daily_snapshot_id: string; pairing_status: 'assumed_text_match';
  amount_multiplier: 1 | 10000 | null; template_id: 'observed-600059-240-clocks-v1';
  unreadable_minute_date_ordinals: number[]; unreadable_daily_date_ordinals: number[];
  days: { source_date: string; selected_count: number; minute_ordinals: number[]; daily_ordinals: number[];
    quantity: ReconciliationValues; amount: ReconciliationValues;
    coverage: { template_slots: number; observed_template_slots: number; missing_clocks: string[];
      extra_clocks: string[]; duplicate_clocks: string[]; unlocated_clock_ordinals: number[] } }[];
}
export interface VolumeFraction { numerator: string; denominator: string; display: string }
export interface VolumeComparison {
  current: string | null; baseline_sum: string | null; baseline_mean: VolumeFraction | null;
  ratio: VolumeFraction | null; reason: string | null;
  members: { date: string; value: string | null; reason: string | null }[];
}
export interface VolumeRow {
  ordinal: number; history_dates: string[]; regular: VolumeComparison | null;
  cumulative: VolumeComparison | null; reason: string | null;
}
export interface VolumeReport {
  method_id: 'source-volume-at-time-v1'; query_id: string; context_query_id: string; volume_id: string;
  qualification: 'conditional_source_values'; lookback: number;
  excluded_unlocated_rows: number; outside_template_rows: number;
  rows: VolumeRow[]; unlocated: VolumeRow[];
}
export interface DailyVolumeRow extends VolumeComparison { ordinal: number; history_dates: string[] }
export interface DailyVolumeReport {
  method_id: 'prior-source-daily-volume-v1'; query_id: string; context_query_id: string; volume_id: string;
  qualification: 'conditional_source_values'; lookback: number; unreadable_date_rows: number; context_unlocated_rows: number;
  rows: DailyVolumeRow[]; unlocated: DailyVolumeRow[];
}
export interface EfficiencyRow {
  ordinal: number; window_dates: string[];
  members: { date: string; ordinals: number[]; close: string | null; reason: string | null }[];
  net_change: string | null; path_length: string | null; direction: 'up' | 'down' | 'flat' | null;
  efficiency: VolumeFraction | null; reason: string | null;
}
export interface EfficiencyReport {
  method_id: 'source-close-path-efficiency-v1'; query_id: string; context_query_id: string; efficiency_id: string;
  qualification: 'conditional_source_values'; lookback: number; flat_policy: 'zero_with_explicit_reason';
  unreadable_date_rows: number; context_unlocated_rows: number; rows: EfficiencyRow[]; unlocated: EfficiencyRow[];
}
export interface Reply extends GeometryEnvelope { display: Display[]; navigation: { previous_label: string | null; next_label: string | null } }
export interface ChannelMember { date: string; ordinals: number[]; high: string | null; low: string | null; reason: string | null }
export interface ChannelRow {
  ordinal: number; history_dates: string[]; members: ChannelMember[];
  upper: string | null; lower: string | null; width: string | null;
  range_relation: 'both' | 'upper_only' | 'lower_only' | 'neither' | null;
  close_relation: 'above' | 'below' | 'touch_upper' | 'touch_lower' | 'touch_both' | 'inside' | null;
  touch_upper: boolean | null; touch_lower: boolean | null; reason: string | null; comparison_reason: string | null;
}
export interface ChannelReport {
  method_id: 'prior-source-price-channel-v1'; query_id: string; context_query_id: string; channel_id: string;
  qualification: 'conditional_source_values'; lookback: number; unreadable_date_rows: number; context_unlocated_rows: number;
  rows: ChannelRow[]; unlocated: ChannelRow[];
}
export interface GapEvent {
  ordinal: number; label: string; extreme: string; relation: 'equal' | 'beyond';
  contains_boundary: boolean; range_relation: 'overlaps_interval' | 'passed_without_overlap';
}
export interface SourceGap {
  gap_id: string; direction: 'up' | 'down'; lower: string; upper: string; width: string;
  near_event: GapEvent | null; far_event: GapEvent | null;
  interrupted_at: { label: string; ordinals: number[]; reason: string } | null;
  state: 'far_boundary_observed' | 'observation_interrupted' | 'near_boundary_observed' | 'not_observed_before_asof';
}
export interface GapRow {
  ordinal: number; label: string | null; previous_label: string | null; previous_ordinals: number[];
  open_close_change: string | null; gap: SourceGap | null; reason: string | null;
}
export interface GapReport {
  method_id: 'source-price-gaps-v1'; query_id: string; context_query_id: string; gaps_id: string;
  qualification: 'conditional_source_values'; as_of_label: string | null;
  origin_scope: 'selected_source_rows'; observation_scope: 'full_source_context_to_asof';
  adjacency: 'adjacent_located_labels'; first_event_scope: 'first_unique_valid_located_before_interruption';
  context_unlocated_rows: number; coverage_reason: string | null; rows: GapRow[]; unlocated: GapRow[];
}
export interface PivotDecision { is_pivot: boolean | null; reason: string | null; pivot_id: string | null }
export interface PivotRow {
  ordinal: number; label: string | null; left_count: number; right_count: number; window_labels: string[];
  confirmation_label: string | null; confirmation_ordinal: number | null; reason: string | null;
  high: PivotDecision; low: PivotDecision;
}
export interface SourcePivot {
  pivot_id: string; kind: 'high' | 'low'; price: string; anchor_ordinal: number; anchor_label: string;
  confirmation_ordinal: number; confirmation_label: string; delay_source_labels: number;
}
export interface PivotReport {
  method_id: 'source-window-pivots-v1'; query_id: string; context_query_id: string; pivots_id: string;
  qualification: 'conditional_source_values'; radius: number; as_of_label: string | null;
  anchor_scope: 'selected_source_rows'; window_unit: 'located_source_labels'; tie_policy: 'strict_no_ties';
  confirmation_semantics: 'right_source_window_present'; context_unlocated_rows: number; coverage_reason: string | null;
  members: { label: string; ordinals: number[]; high: string | null; low: string | null; reason: string | null }[];
  rows: PivotRow[]; unlocated: PivotRow[]; events: SourcePivot[];
}
export interface RangeEstimate { value: string; lower: string; upper: string; display: string | null; display_reason: string | null }
export interface RangeRow {
  ordinal: number; previous_date: string | null; previous_ordinals: number[];
  components: Record<'high_low' | 'high_previous_close' | 'low_previous_close', string | null>;
  tr: string | null; tr_reason: string | null; atr: RangeEstimate | null; atr_reason: string | null;
  atr_blocked_date: string | null; prior_atr: RangeEstimate | null; tr_over_prior_atr: RangeEstimate | null; ratio_reason: string | null;
}
export interface RangeReport {
  method_id: 'source-wilder-range-v1'; query_id: string; context_query_id: string; range_id: string;
  qualification: 'conditional_source_values'; period: number; seed_policy: 'first_period_subsequent_tr_mean';
  seed_previous_date: string | null; seed_dates: string[]; unreadable_date_rows: number; context_unlocated_rows: number;
  rows: RangeRow[]; unlocated: RangeRow[];
}
export interface DailyBackgroundReport {
  method_id: 'prior-source-date-background-v1'; background_id: string; daily_query_id: string;
  anchor: { snapshot_id: string; ordinal: number; label: string };
  pairing_status: 'assumed_text_match'; qualification: 'source_date_retrospective_only';
  latest_source_date: string | null; calendar_gap_days: number | null; daily: Reply;
  requested_rows: number | null; context_unlocated_rows: number;
}
export interface Config { csrf_token: string; formats: string[]; max_upload_bytes: number; max_query_rows: number; mode: string; capabilities?: { file_import: boolean; daily_research: boolean; tdx_client: boolean } }
export interface ReferenceReport {
  method_id: 'tdx-reference-view-v1'; kind: 'calendar' | 'actions'; target: string; source_method: string;
  selection: { start: string; end: string }; qualification: 'unverified_source_reference'; coverage: 'unverified';
  returned_count: number; selected_count: number; before_start: number; after_end: number; duplicate_date_rows: number;
  rows: { ordinal: number; date: string; source_date: string; source_type?: string; type_name?: string | null;
    values?: Record<'Bonus' | 'AllotPrice' | 'ShareBonus' | 'Allotment', string> }[];
  capture_id: string; captured_at: string; request_sha256: string; response_sha256: string;
  historical_available_at: null; standard_units: 'unverified';
  empty_shape: 'value_only_empty' | null;
}
export interface Attempt { attempt_id: string; status: string; snapshot_id?: string | null; error_code?: string | null; filename?: string; started_at?: string; format_id?: string }
export interface ActionCapture {
  capture_id: string; status: string; target?: string; captured_at?: string;
  selection?: { start: string; end: string }; returned_count?: number; error_code?: string;
}
export interface ActionWindow {
  method_id: 'source-action-window-v1'; query_id: string; action_window_id: string; capture_id: string;
  target: string; start_exclusive: string; end_inclusive: string; qualification: 'retrospective_source_records';
  captured_at: string; request_sha256: string; response_sha256: string;
  pairing_status: 'assumed_text_match'; coverage: 'unverified'; historical_available_at: null;
  request_range_status: string; capture_selection: { start: string; end: string }; returned_count: number;
  observation_status: string; selected_count: number; duplicate_selected_date_rows: number;
  unreadable_query_date_ordinals: number[];
  rows: (ReferenceReport['rows'][number] & { query_ordinals: number[]; link_reason: string | null })[];
}
