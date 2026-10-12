import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { assertHistoricalPathReply } from '../src/historical-path-model.ts';
import { actualHistoricalPathFixture, historicalPathFixture } from './historical-path-fixtures.mjs';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { HistoricalPathResearch, HistoricalPathResults, HistoricalPathPlot, PathPointTable, HistoricalPathProvenance } = await server.ssrLoadModule('/src/HistoricalPathResearch.tsx');
const { SingleResearch } = await server.ssrLoadModule('/src/SingleResearch.tsx');
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const text = html => html.replace(/<[^>]+>/g, '');
const props = fixture => ({ report: fixture.reply, onSelect() {}, onReject() {} });
const query = { query_id: 'e'.repeat(64), snapshot_id: 'a'.repeat(64), selection: { cutoff: '2025-03-25', ordinal_start: 80, ordinal_end: 84 }, metadata: { period: '1d' }, rows: [] };

test('manual date form makes fixed20 steps/21 observations and full-prefix scope clear', () => {
  const html = render(HistoricalPathResearch, { query }), content = text(html);
  assert.match(html, /type="date" required=""/); assert.match(content, /20个来源区间、21个观测/);
  assert.match(content, /检索历史参照/); assert.match(content, /实际起止与自然日跨度在结果中核对/);
  assert.match(content, /缺少该日期或查询窗口无效时不回退/); assert.doesNotMatch(html, /<svg/);
  const integrated = text(render(SingleResearch, { query }));
  assert.match(integrated, /趋势与历史事件/); assert.match(integrated, /突破观察窗/); assert.match(integrated, /历史来源路径检索/);
});
test('results show authoritative dates, both baselines, transparent counts and no default overlay', () => {
  const f = historicalPathFixture(), html = render(HistoricalPathResults, props(f)), content = text(html);
  for (const expected of ['先核对所查区间', '20来源步 · 21个观测 · 相隔20个自然日', '整段路径最近', '终点变化最近', '最近发生的旧区间', '尚未选择参照', '排名最接近也可能不宜参考', '重叠排除', '其余']) assert.ok(content.includes(expected), expected);
  assert.ok(content.includes(`${f.reply.result.query.start_date} → ${f.reply.result.query.end_date}`));
  assert.equal((html.match(/class="historical-path-candidate"/g) ?? []).length, 9);
  assert.doesNotMatch(html, /aria-pressed="true"|<svg/); assert.doesNotMatch(content, /相似率|相似百分比|胜率/);
});
test('choosing a candidate exposes separate dates, raw prices, source steps and signed percentage-point differences', () => {
  const f = historicalPathFixture(), html = render(HistoricalPathResults, { ...props(f), selected: 21 }), content = text(html);
  assert.match(content, /已选路径对照/); assert.match(content, /最大逐点差20 个百分点/);
  assert.match(content, /第20步：查询 2025-03-25 \/ 参照 2025-02-11/);
  assert.match(content, /100\.000000000000000000/); assert.match(content, /查询第0…20来源步/);
  assert.match(content, /差异（查询−参照）/); assert.match(html, /stroke-dasharray="6 4"/);
  assert.match(html, /aria-pressed="true"/); assert.doesNotMatch(html, /NaN|Infinity/);
});
test('point table has21 rows and never merges the two real-date axes', () => {
  const { reply } = historicalPathFixture(), html = render(PathPointTable, { result: reply.result, candidate: reply.result.windows[0] });
  assert.equal((html.match(/<tbody>.*?<\/tbody>/s)[0].match(/<tr/g) ?? []).length, 21);
  assert.match(text(html), /查询日期 \/ 源序号/); assert.match(text(html), /参照日期 \/ 源序号/);
  assert.match(text(html), /首个最大差异/); assert.match(html, /tabindex="0"/);
});
test('overlay has exactly two bounded paths with21 points and labels relative source steps', () => {
  const { reply } = historicalPathFixture(), html = render(HistoricalPathPlot, { query: reply.result.query, candidate: reply.result.windows[0] });
  const paths = [...html.matchAll(/<path[^>]*d="([^"]+)"/g)].map(m => m[1]); assert.equal(paths.length, 2);
  for (const path of paths) { assert.equal((path.match(/M/g) ?? []).length, 1); assert.equal((path.match(/L/g) ?? []).length, 20); }
  assert.match(html, /role="img"/); assert.match(text(html), /查询第0…20来源步/);
  assert.match(text(html), /SVG仅用显示值布点/); assert.match(text(html), /未含分红/);
});
test('empty candidates and reject-all remain explicit without fabricated charts or selections', () => {
  const f = historicalPathFixture(21), empty = render(HistoricalPathResults, props(f));
  assert.match(text(empty), /没有有效的旧区间可供参照/); assert.doesNotMatch(empty, /<svg|historical-path-candidate/);
  const rejected = render(HistoricalPathResults, { ...props(historicalPathFixture()), rejected: true });
  assert.match(text(rejected), /这些参照都不采用/); assert.match(text(rejected), /已记录本页选择/); assert.doesNotMatch(rejected, /<svg/);
});
test('source panel distinguishes exact sorting, displayed rounding and retained quantity-check failures', () => {
  const f = historicalPathFixture(); f.reply.result.nonprice_check_failures = { 'numeric.volume': 3 };
  const content = text(render(HistoricalPathProvenance, { report: f.reply }));
  assert.match(content, /精确整数与有理数/); assert.match(content, /12位有效数字、半偶舍入/);
  assert.match(content, /完整前缀查询标识/); assert.match(content, /numeric.volume：3项/);
  assert.match(content, /不把数量、金额或单位核验视为已通过/); assert.doesNotMatch(content, /模型估计使用浮点数/);
});
test('fresh synthetic Store→HTTP envelope passes frontend validation and renders actual core paths', async () => {
  await actualHistoricalPathFixture(async ({ reply, request }) => {
    assertHistoricalPathReply(reply, request.expected);
    const selected = reply.result.selections.path[0], candidate = reply.result.windows.find(w => w.start_index === selected);
    const html = render(HistoricalPathResults, { report: reply, selected, onSelect() {}, onReject() {} }), content = text(html);
    assert.match(content, /2025-03-21 → 2025-04-10/); assert.ok(content.includes(candidate.prices[0]));
    assert.ok(content.includes(candidate.distance)); assert.ok(content.includes(reply.inputs[0].query_id));
    assert.match(content, /0%/); assert.doesNotMatch(content, /NaN|Infinity|未识别状态/);
    assert.match(html, /<svg/); assert.equal(reply.result.query.prices.length, 21);
  });
});
