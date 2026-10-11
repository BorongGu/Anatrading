import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { adjacentSource, bindSourceResearch } = await server.ssrLoadModule('/src/adjacent-source.ts');
const { RecordDetails } = await server.ssrLoadModule('/src/RecordDetails.tsx');
function fixture() {
  const row = { ordinal: 82, label: '2026-01-12', locator: 'row:82', values: { close: '10.000000000000000002' }, checks: [], tokens: {} };
  const query = { query_id: 'visible-window', snapshot_id: 'frozen-version', metadata: { period: '1d' }, selection: { cutoff: '2026-01-12', ordinal_start: 82, ordinal_end: 82 }, rows: [row], unlocated: [] };
  const series = [
    { date: '2026-01-09', ordinal: 7, close: '10.000000000000000001', reason: null, reset_reason: 'initial_observation', segment_id: 1, segment_observations: 1, log_return: null },
    { date: row.label, ordinal: row.ordinal, close: row.values.close, reason: null, reset_reason: null, segment_id: 1, segment_observations: 2, log_return: 0 },
  ];
  const report = { inputs: [{ snapshot_id: query.snapshot_id, query_id: 'full-prefix' }], parameters: { cutoff: query.selection.cutoff }, result: { series } };
  return { query, row, report, binding: bindSourceResearch(query, query.query_id, report) };
}
const inspect = f => adjacentSource(f.query, f.row, f.binding);
const render = f => renderToStaticMarkup(createElement(RecordDetails, { row: f.row, sourceQuery: f.query, sourceResearch: f.binding })).replace(/<[^>]+>/g, '');
test('window/page never supplies predecessor; exact endpoints and actual 3-day interval remain visible', () => {
  const f = fixture(), evidence = inspect(f);
  assert.equal(evidence.previous.ordinal, 7); assert.equal(evidence.days, 3); assert.equal(evidence.value, 0);
  assert.equal(f.query.rows.length, 1);
  const text = render(f);
  for (const expected of ['2026-01-09', '2026-01-12', '源序号 7', '源序号 82', '10.000000000000000001', '10.000000000000000002', '相隔 3 个自然日', '对数价格变化（近似值）：0', '交易日历、覆盖与复权/公司行动未核实', '不能认作经济收益']) assert.ok(text.includes(expected), expected);
});
test('reuse reported estimate exactly rather than derive it from precise prices or calendar span', () => {
  const f = fixture(); f.report.result.series[1].log_return = 0.123456789012345;
  assert.equal(inspect(f).value, 0.123456789012345); assert.match(render(f), /0\.123456789012345/);
});
test('missing first, invalid and reset values stay unavailable with original reason, never zero', () => {
  for (const reason of ['initial_observation', 'missing_ohlc', 'numerical_failure', 'duplicate_date']) {
    const f = fixture(), current = f.report.result.series[1];
    current.log_return = null; current.reset_reason = reason; current.segment_observations = 1; current.segment_id = 2;
    assert.equal(inspect(f).value, null); assert.equal(inspect(f).reason, reason); assert.match(render(f), /近似值）：—/);
  }
  const f = fixture(); f.report.result.series.splice(0, 1); Object.assign(f.report.result.series[0], { log_return: null, reset_reason: 'initial_observation', segment_observations: 1 });
  assert.equal(inspect(f).previous, null); assert.match(render(f), /无前序来源日期组/);
});
test('duplicate current date and unlocated raw rows never borrow another record', () => {
  const f = fixture(); Object.assign(f.report.result.series[1], { ordinal: null, reason: 'duplicate_date', log_return: null });
  assert.match(inspect(f).reason, /重复/); assert.equal(inspect(f).current, null);
  f.row.label = null; assert.match(inspect(f).reason, /无法定位/);
});
test('invalid predecessor, reset mismatch, and ordinal mismatch cannot fabricate adjacency', () => {
  for (const mutate of [f => { f.report.result.series[0].reason = 'invalid_ohlc'; }, f => { f.report.result.series[1].segment_id = 2; }, f => { f.report.result.series[1].ordinal = 99; }]) {
    const f = fixture(); mutate(f); assert.equal(inspect(f).current, null); assert.equal(inspect(f).value, null);
  }
});
test('source version, cutoff, selected row membership and query identity gate evidence', () => {
  for (const mutate of [f => { f.report.inputs[0].snapshot_id = 'other-version'; }, f => { f.report.parameters.cutoff = '2026-01-11'; }, f => { f.binding.queryId = 'old-query'; }, f => { f.query.rows = []; }]) {
    const f = fixture(); mutate(f); assert.equal(inspect(f).current, null); assert.equal(inspect(f).value, null);
  }
});
test('loading, parameter invalidation, late success and late invalidation preserve current query boundary', () => {
  const f = fixture(); f.binding = null; assert.match(render(f), /研究结果尚未可用/);
  assert.equal(bindSourceResearch(f.query, 'old-query', f.report), undefined);
  assert.equal(bindSourceResearch(f.query, 'old-query', null), undefined);
  assert.equal(bindSourceResearch(null, f.query.query_id, f.report), undefined);
  assert.equal(bindSourceResearch(f.query, f.query.query_id, null), null);
  const source = readFileSync(new URL('../src/SingleResearch.tsx', import.meta.url), 'utf8');
  assert.match(source, /function invalidate\(\).*onReport\?\.\(query.query_id, null\)/);
  assert.ok(source.indexOf('if (!gate.current.isCurrent(generation)) return;') < source.indexOf('onReport?.(query.query_id, result)'));
  assert.ok(source.indexOf('assertResearchReply(result, request.expected)') < source.indexOf('onReport?.(query.query_id, result)'));
});
test('minute and compact raw details do not acquire daily research', () => {
  const f = fixture(); f.query.metadata.period = '1m'; assert.doesNotMatch(render(f), /相邻来源变化核对/);
  f.query.metadata.period = '1d';
  assert.doesNotMatch(renderToStaticMarkup(createElement(RecordDetails, { row: f.row, sourceQuery: f.query, sourceResearch: f.binding, compact: true })), /相邻来源变化核对/);
});
