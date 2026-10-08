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
export interface Reply extends GeometryEnvelope { display: Display[]; navigation: { previous_label: string | null; next_label: string | null } }
export interface Config { csrf_token: string; formats: string[]; max_upload_bytes: number; max_query_rows: number; mode: string }
export interface Attempt { attempt_id: string; status: string; snapshot_id?: string | null; error_code?: string | null; filename?: string; started_at?: string; format_id?: string }
