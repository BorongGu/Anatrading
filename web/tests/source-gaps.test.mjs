import test from 'node:test';
import assert from 'node:assert/strict';
import { assertGapReport } from '../src/model.ts';

// Synthetic response boundaries only; price correctness is checked against private originals by Python.
function example() {
  const query = { query_id: 'a'.repeat(64), selection: { cutoff: null }, unlocated: [], rows: [
    { ordinal: 2, label: '2026-09-02' }, { ordinal: 3, label: '2026-09-03' },
  ] };
  const report = { method_id: 'source-price-gaps-v1', query_id: query.query_id, context_query_id: 'b'.repeat(64), gaps_id: 'c'.repeat(64),
    qualification: 'conditional_source_values', as_of_label: '2026-09-03', origin_scope: 'selected_source_rows',
    observation_scope: 'full_source_context_to_asof', adjacency: 'adjacent_located_labels',
    first_event_scope: 'first_unique_valid_located_before_interruption', unlocated: [], rows: [
      { ordinal: 2, label: '2026-09-02', gap: { gap_id: 'd'.repeat(64), direction: 'up', lower: '10', upper: '12', width: '2', near_event: null, far_event: null, interrupted_at: null } },
      { ordinal: 3, label: '2026-09-03', gap: null },
    ] };
  return { query, report };
}
function event(label = '2026-09-03', ordinal = 3) {
  return { ordinal, label, extreme: '10', relation: 'equal', contains_boundary: true, range_relation: 'overlaps_interval' };
}

test('report binds current query, source sequence, horizon and observation scope', () => {
  const { query, report } = example();
  assertGapReport(query, report);
  for (const mutation of [r => r.query_id = 'old', r => r.rows.reverse(), r => r.rows.pop(),
    r => r.as_of_label = '2026-09-04', r => r.observation_scope = 'selected_only']) {
    const wrong = structuredClone(report); mutation(wrong);
    assert.throws(() => assertGapReport(query, wrong), /invalid_query_response/);
  }
});

test('formation or future bars cannot be first observations; far cannot precede near', () => {
  const { query, report } = example();
  for (const label of ['2026-09-02', '2026-09-04']) {
    const wrong = structuredClone(report); wrong.rows[0].gap.near_event = event(label);
    assert.throws(() => assertGapReport(query, wrong), /invalid_query_response/);
  }
  report.rows[0].gap.far_event = event();
  assert.throws(() => assertGapReport(query, report), /invalid_query_response/);
  report.rows[0].gap.near_event = event();
  assertGapReport(query, report); // both on one source bar are allowed.
});

test('events outside selected source rows are allowed before asof; interruption blocks later first', () => {
  const { query, report } = example();
  report.rows[0].gap.near_event = event('2026-09-03', 9);
  assertGapReport(query, report);
  report.rows[0].gap.interrupted_at = { label: '2026-09-03', ordinals: [8], reason: 'duplicate_label' };
  assert.throws(() => assertGapReport(query, report), /invalid_query_response/);
});
