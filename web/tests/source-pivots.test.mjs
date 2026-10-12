import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { assertPivotReport, buildPivotPlot } from '../src/model.ts';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { PivotAnalysis } = await server.ssrLoadModule('/src/PivotAnalysis.tsx');

// Synthetic timing/mapping boundaries, not market or predictive evidence.
function example() {
  const rows = Array.from({ length: 5 }, (_, i) => ({ ordinal: i + 1, label: `2026-09-0${i + 1}` }));
  const query = { query_id: 'a'.repeat(64), metadata: { period: '1d' }, selection: { cutoff: null }, rows, unlocated: [] };
  const high = { pivot_id: 'd'.repeat(64), kind: 'high', price: '6', anchor_ordinal: 3, anchor_label: rows[2].label,
    confirmation_ordinal: 5, confirmation_label: rows[4].label, delay_source_labels: 2 };
  const low = { ...high, pivot_id: 'e'.repeat(64), kind: 'low', price: '0' };
  const decision = id => ({ is_pivot: true, reason: null, pivot_id: id });
  const report = { method_id: 'source-window-pivots-v1', query_id: query.query_id, context_query_id: 'b'.repeat(64), pivots_id: 'c'.repeat(64),
    qualification: 'conditional_source_values', radius: 2, as_of_label: rows[4].label, anchor_scope: 'selected_source_rows',
    window_unit: 'located_source_labels', tie_policy: 'strict_no_ties', confirmation_semantics: 'right_source_window_present', members: [],
    rows: rows.map((row, i) => ({ ...row, reason: i === 2 ? null : 'incomplete', window_labels: [], left_count: Math.min(i, 2), right_count: Math.min(4 - i, 2),
      confirmation_label: i === 2 ? rows[4].label : null, confirmation_ordinal: i === 2 ? 5 : null,
      high: i === 2 ? decision(high.pivot_id) : { is_pivot: null, reason: null, pivot_id: null },
      low: i === 2 ? decision(low.pivot_id) : { is_pivot: null, reason: null, pivot_id: null } })),
    unlocated: [], events: [high, low] };
  const reply = { query, display: rows.map(row => ({ ordinal: row.ordinal, ohlc_drawable: true })) };
  return { query, report, reply };
}

test('both markers appear on confirmation index, never the historical anchor', () => {
  const { query, report, reply } = example();
  const before = JSON.stringify(report);
  assertPivotReport(query, report, 2);
  const plot = buildPivotPlot(reply, report);
  assert.deepEqual(plot.markers.map(m => m.time), [4, 4]);
  assert.deepEqual(plot.markers.map(m => m.position), ['aboveBar', 'belowBar']);
  assert.equal(plot.skipped, 0);
  assert.equal(JSON.stringify(report), before);
});

test('query, parameters, origin order and future confirmation bind the response', () => {
  const { query, report, reply } = example();
  for (const change of [r => r.query_id = 'old', r => r.radius = 5, r => r.rows.reverse(),
    r => r.events[0].confirmation_label = '2026-09-06', r => r.events[0].confirmation_label = '2026-09-03',
    r => r.events[0].anchor_ordinal = 4, r => r.events.pop(), r => r.events.push({ ...r.events[0] })]) {
    const wrong = structuredClone(report); change(wrong);
    assert.throws(() => assertPivotReport(query, wrong, 2), /invalid_query_response/);
  }
  assert.equal(buildPivotPlot({ ...reply, query: { ...query, query_id: 'old' } }, report), null);
});

test('missing or undrawable confirmation cannot shift to another bar', () => {
  const { query, report, reply } = example();
  reply.display[4].ohlc_drawable = false;
  assert.deepEqual(buildPivotPlot(reply, report), { markers: [], skipped: 2 });
  const selected = { ...query, rows: [query.rows[2], query.rows[3]] };
  const narrowed = { ...report, rows: report.rows.slice(2, 4), as_of_label: '2026-09-04' };
  assert.throws(() => assertPivotReport(selected, narrowed, 2), /invalid_query_response/);
});

test('confirmation in unselected context stays in the report and remains undrawn', () => {
  const { query, report, reply } = example();
  // Label 5 is within asof via another selected source row; original confirmation ordinal is absent.
  query.rows[4] = { ordinal: 9, label: '2026-09-05' };
  report.rows[4] = { ...report.rows[4], ordinal: 9 };
  reply.display[4].ordinal = 9;
  assertPivotReport(query, report, 2);
  assert.deepEqual(buildPivotPlot(reply, report), { markers: [], skipped: 2 });
});

function render(query, report, radius = 2) {
  return renderToStaticMarkup(createElement(PivotAnalysis, { query, report, radius, selected: query.rows[4],
    onChoose() {}, onRadiusSelect() {}, onReport() {} })).replace(/<[^>]+>/g, '');
}

test('component distinguishes selected confirmation bar from the earlier extreme center', () => {
  const { query, report } = example();
  report.rows[4].reason = 'pending_right_window';
  const text = render(query, report);
  assert.match(text, /2026-09-05 · 源序号5作为中心：右侧来源窗口尚未齐备/);
  assert.match(text, /在当前标签确认高点，极值中心为 2026-09-03 · 源序号3，源价 6/);
  assert.match(text, /中心记录类型／精确源价来源窗口确认记录确认延迟/);
  assert.match(text, /基于当前数据版本的回顾判断/);
  assert.match(text, /闭合、当时可得及复权可比性未核/);
  assert.match(text, /尚未验证去噪效果或预测价值/);
  assert.match(text, /固定数据版本和对应来源窗口内比较，来源修订后另存版本/);
  assert.doesNotMatch(text, /快照|合同|门禁|数据证据工作台/);
});

test('component renders extreme price text exactly without Number conversion', () => {
  const { query, report } = example();
  const price = '99999999999999999999.999999999999999994';
  report.events[0].price = price;
  assert.ok(render(query, report).includes(price));
});

test('component cannot publish stale query or radius events', () => {
  const { query, report } = example();
  for (const props of [{ query: { ...query, query_id: 'old' }, report, radius: 2 }, { query, report, radius: 5 }]) {
    assert.doesNotMatch(render(props.query, props.report, props.radius), /在当前标签确认高点|严格高点 · 6/);
  }
});
