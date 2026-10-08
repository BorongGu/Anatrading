// Synthetic envelope tests validate presentation boundaries, not market data.
export const queryId = 'a'.repeat(64);
export const geometryId = 'b'.repeat(64);
export const draft = { snapshot: 's', cutoff: '', start: '', end: '' };
export const ratio = (numerator = '1', denominator = '1', percent_display = '100.00') => ({ numerator, denominator, percent_display });
export const entry = ordinal => ({ ordinal, status: 'computed', reason: null, direction: 'up', range: '1', body: '1', upper_shadow: '0', lower_shadow: '0', ratios: { body: ratio(), upper_shadow: ratio('0', '1', '0.00'), lower_shadow: ratio('0', '1', '0.00'), close_location: ratio() }, ratio_reason: null });
export const sourceRow = (ordinal, label = '2026-09-30') => ({ ordinal, label, source_label: label, locator: `synthetic:${ordinal}`, values: { open: '1', high: '2', low: '1', close: '2', volume: '3', amount: '6' }, tokens: {}, checks: [], volume_shares: null, amount_cny: null });
export const geometry = (rows, unlocated = []) => ({ method_id: 'source-candle-geometry-v1', query_id: queryId, geometry_id: geometryId, qualification: 'source_observation_description', source_qualification: 'source_evidence_retrospective_only', assumption: 'same_price_scale_within_row', display_policy: { percent_places: 2, rounding: 'half_even' }, rows: rows.map(r => entry(r.ordinal)), unlocated: unlocated.map(r => entry(r.ordinal)) });
export function envelope() {
  const rows = [sourceRow(1)];
  const unlocated = [sourceRow(2, null)];
  return { query: { snapshot_id: 's', query_id: queryId, selection: { snapshot_id: 's', cutoff: null, ordinal_start: null, ordinal_end: null, mode: 'retrospective' }, rows, unlocated, counts: { selected_rows: 1, unlocated_rows: 1 }, manifest: { qualification: 'source_evidence_retrospective_only' } }, geometry: geometry(rows, unlocated) };
}
