import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { assertAggregationReport, buildAggregationPlot } from '../src/model.ts';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { AggregationDetails } = await server.ssrLoadModule('/src/MinuteAggregation.tsx');

function example() {
  const rows = Array.from({ length: 6 }, (_, i) => ({ ordinal: i + 1, label: `2026-09-28T09:${31 + i}` }));
  const query = { snapshot_id: 'a'.repeat(64), query_id: 'b'.repeat(64), selection: { cutoff: null }, rows, unlocated: [] };
  const empty = { open: null, high: null, low: null, close: null, volume: null, amount: null };
  const values = { open: '10', high: '12', low: '9', close: '11', volume: '500', amount: '5000' };
  const buckets = [0, 1].map(i => {
    const expected = Array.from({ length: 5 }, (_, j) => `2026-09-28T09:${31 + i * 5 + j}`);
    const members = rows.slice(i * 5, i * 5 + 5);
    return { bucket_id: (i ? 'd' : 'c').repeat(64), first_label: expected[0], end_label: expected.at(-1), segment: 'morning_labels',
      expected_labels: expected, members, missing_labels: expected.slice(members.length), duplicate_labels: [], future_labels: expected.slice(members.length),
      last_observed_label: members.at(-1).label, template_complete: i === 0, membership_reason: i ? 'right_labels_not_observed' : null,
      values: i ? { ...empty } : { ...values }, observed_values: i ? { ...values, volume: '100', amount: '1000' } : { ...values },
      reasons: { ohlc: null, volume: null, amount: null }, observed_reasons: { ohlc: null, volume: null, amount: null },
      display: { direction: i ? 'unknown' : 'up', ohlc_drawable: i === 0, precision_lost: false } };
  });
  const report = { method_id: 'selected-minute-label-aggregation-v1', aggregation_id: 'e'.repeat(64), query_id: query.query_id,
    snapshot_id: query.snapshot_id, target_minutes: 5, as_of_label: rows.at(-1).label, template_id: 'observed-600059-240-clocks-v1',
    qualification: 'conditional_source_values', member_scope: 'selected_records_only', bucket_label_semantics: 'nominal_last_template_label',
    completeness_semantics: 'selected_template_members_present_not_market_bar_closed', unknown_date_ordinals: [], unknown_clock_dates: [], excluded: [], buckets };
  return { query, report };
}

test('future nominal bucket stays in table and is omitted from the complete-end chart', () => {
  const { query, report } = example();
  assertAggregationReport(query, report, 5);
  const plot = buildAggregationPlot(report);
  assert.equal(plot.buckets.length, 1);
  assert.deepEqual(plot.labels, ['2026-09-28T09:35']);
  assert.equal(plot.candles[0].open, 10);
  assert.equal(plot.volumes[0].value, 500);
  assert.equal(report.buckets.length, 2);
});

test('past incomplete bucket is retained as whitespace and never replaced with partial values', () => {
  const { report } = example();
  const bucket = report.buckets[0];
  bucket.template_complete = false; bucket.membership_reason = 'not_in_selected_records';
  bucket.values = Object.fromEntries(Object.keys(bucket.values).map(key => [key, null]));
  bucket.display = { direction: 'unknown', ohlc_drawable: false, precision_lost: false };
  const plot = buildAggregationPlot(report);
  assert.deepEqual(plot.candles, [{ time: 0 }]);
  assert.deepEqual(plot.volumes, [{ time: 0 }]);
});

test('identity, member mapping and completeness bind the response', () => {
  const { query, report } = example();
  for (const change of [r => r.query_id = 'old', r => r.target_minutes = 15, r => r.snapshot_id = 'old',
    r => r.as_of_label = '2026-09-28T09:35', r => r.buckets[0].members[0].ordinal = 99,
    r => r.buckets[0].members.reverse(), r => r.buckets[1].template_complete = true,
    r => r.buckets[0].members.pop(), r => r.buckets[0].values.volume = '501', r => r.buckets.pop()]) {
    const wrong = structuredClone(report); change(wrong);
    assert.throws(() => assertAggregationReport(query, wrong, 5), /invalid_query_response/);
  }
});

test('component retains exact values, partial fields and original source links', () => {
  const { query, report } = example();
  const exact = '100000000000000003999.999999999999999999';
  report.buckets[0].values.amount = report.buckets[0].observed_values.amount = exact;
  const html = renderToStaticMarkup(createElement(AggregationDetails, { query, report, selected: query.rows[0], onChoose() {} }));
  assert.ok(html.includes(exact));
  assert.match(html, /源序号1/);
  assert.match(html, /右端标签尚未观察到/);
  assert.match(html, /齐备值/);
  assert.match(html, /交易闭合仍未核/);
});

test('display resolution loss keeps exact table values and suppresses collapsed candle', () => {
  const { report } = example();
  report.buckets[0].display.precision_lost = true;
  assert.deepEqual(buildAggregationPlot(report).candles, [{ time: 0 }]);
});
