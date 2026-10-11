import type { Identity, UniverseResult } from './research-types.ts';

export type FilterField = 'momentum' | 'volatility' | 'max_drawdown';
export type FilterTruth = 'true' | 'false' | 'unknown';
export type SelectionState = 'selected' | 'excluded' | 'undetermined';
export interface FilterDraftAtom { field: FilterField; threshold: string }
export interface FilterDraft { enabled: boolean; groups: FilterDraftAtom[][] }
export interface FilterCondition { field: FilterField; op: 'gte' | 'lte'; threshold: string }
export interface CanonicalRule { any_of: { all_of: FilterCondition[] }[] }
export interface FilterPolicies { rule_schema: string; window: string; logic: string; comparison: string; source_gate: string }
export interface FilterExpected {
  snapshotIds: string[]; cutoff: string; lookback: number; canonicalRule: CanonicalRule;
  ruleId: string; policyVersions: FilterPolicies;
  /** canonical gN -> the submitted editor's one-based group number */
  groupLabels: number[];
}
export interface FilterRequest { path: string; expected: FilterExpected }
export interface SourcePresence { present: boolean; value: unknown }
export interface FilterSource {
  snapshot_id: string; query_id: string; identity: Identity; raw_sha256: SourcePresence;
  metadata: Record<string, SourcePresence>; id: string; contract_ref: string;
}
export interface FilterSourceContract {
  id: string; source_contract_id: SourcePresence; format_id: SourcePresence; contract_version: SourcePresence;
  versions: SourcePresence; semantics_scope: SourcePresence;
  semantics: Record<string, { value: SourcePresence; status: SourcePresence; reason: SourcePresence; applicability: SourcePresence }>;
}
export interface FilterPoint { date: string; ordinal: number | null; close: string | null }
export interface FilterWindow {
  snapshot_id: string; query_id: string; cutoff: string; lookback: number; method: string;
  start_date: string | null; end_date: string | null; id: string; unit: 'source_date_groups';
  expected_groups: number; actual_groups: number; n_prices: number; n_returns: number;
  first: FilterPoint | null; last: FilterPoint | null;
  drawdown_witness: { peak: FilterPoint; trough: FilterPoint } | null;
}
export interface FilterFact {
  value: number | null; reason: string | null; comparison_type: 'source_fraction' | 'float64_estimate';
  exact: { numerator: string; denominator: string } | null;
  estimate_text?: string | null; float_hex?: string | null;
}
export interface FilterAtom { id: string; truth: FilterTruth; fact_ref: FilterField; reason_refs: string[] }
export interface FilterGroup { id: string; atom_ids: string[]; truth: FilterTruth; false_atoms: string[]; unknown_atoms: string[] }
export interface FilterReason {
  id: string; code: string; scope: 'source_date' | 'window_slot' | 'source' | 'metric' | 'window';
  field: FilterField | null; count: number; examples: [string, number | null][]; omitted_count: number;
}
export interface FilterMember {
  identity: Identity; snapshot_id: string; source_ref: string; window_ref: string; window: FilterWindow;
  source_gate: 'pass' | 'unknown'; logical_truth: FilterTruth; selection_state: SelectionState;
  evidence_complete: boolean; partial_evidence: boolean; facts: Record<FilterField, FilterFact>;
  atoms: FilterAtom[]; groups: FilterGroup[]; reasons: FilterReason[]; primary_reason: string | null; proof_groups: string[];
}
export type TruthCounts = Record<FilterTruth, number>;
export interface FilterCounts {
  selected_members: number; selection: Record<SelectionState, number>; logical: TruthCounts;
  evidence: { complete: number; partial: number }; source_gate: { pass: number; unknown: number };
  atoms: Record<string, TruthCounts>; groups: Record<string, TruthCounts>;
}
export interface FilterEnvelope {
  method_id: 'selected-source-price-filter-v1'; inputs: { snapshot_id: string; query_id: string }[];
  parameters: { cutoff: string; lookback: number; canonical_rule: CanonicalRule; policy_versions: FilterPolicies };
  rule_id: string; source_metadata_id: string; analysis_id: string; base_analysis_id: string;
  mode: 'retrospective'; qualification: 'conditional_source_price_filter'; limitations: string[];
  result: {
    universe: UniverseResult; sources: FilterSource[]; source_contracts: FilterSourceContract[];
    conditions: (FilterCondition & { id: string })[]; reason_example_fields: ['date', 'ordinal'];
    members: FilterMember[]; counts: FilterCounts;
  };
}
export type RequestStatus = 'idle' | 'dirty' | 'loading' | 'ready' | 'error' | 'cancelled';
export interface ResearchRequestState<Spec, Result> { status: RequestStatus; result: Result | null; error: unknown | null; spec: Spec | null }
