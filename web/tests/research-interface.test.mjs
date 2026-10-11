import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { default: App } = await server.ssrLoadModule('/src/App.tsx');
const { CrossResearch, PairResults, UniverseResults } = await server.ssrLoadModule('/src/CrossResearch.tsx');
const { DistributionTable } = await server.ssrLoadModule('/src/SingleResearch.tsx');
const { EstimatePlot } = await server.ssrLoadModule('/src/ResearchResults.tsx');
const render = (component, props = {}) => renderToStaticMarkup(createElement(component, props));
const text = html => html.replace(/<[^>]+>/g, '');
const sid = c => c.repeat(64);
// Artificial UI fixtures verify labels and rendering only. They are not market evidence.
const identity = symbol => ({ symbol, market: 'CN_A', qualification: 'source_claim' });
const snapshot = (id, period) => ({ snapshot_id: sid(id), row_count: 30, metadata: { period, source_name: '合成界面样本', source_code: id }, manifest: {} });
const envelope = result => ({ method_id: 'synthetic-render-only', analysis_id: sid('a'), mode: 'retrospective', parameters: {}, limitations: [], inputs: [], result });
const distribution = value => ({ count: 3, mean: value, median: value, q05: value, q25: value, q75: value, q95: value, positive_count: 0, zero_count: 3, negative_count: 0, positive_fraction: 0 });

test('first-run view has four real workspaces and an import-first path', () => {
  const html = render(App); const content = text(html);
  for (const label of ['个股研究', '双股对比', '多股研究', '数据管理', '导入第一份行情']) assert.ok(content.includes(label));
  assert.match(html, /aria-current="page"/);
  assert.doesNotMatch(content, /全市场日线覆盖|源序号起|精确字段|展开详细指标/);
  assert.match(content, /历史回顾/);
});

test('pair requires two daily datasets and distinguishes left/right roles', () => {
  const props = { kind: 'pair', snapshots: [snapshot('a', '1d'), snapshot('b', '1m')], onImport() {}, onOpen() {} };
  assert.match(text(render(CrossResearch, props)), /至少两份日线行情/);
  props.snapshots.push(snapshot('c', '1d'));
  const html = render(CrossResearch, props);
  assert.match(text(html), /左侧股票 A（被解释侧）/);
  assert.match(text(html), /右侧股票 B（解释侧）/);
  assert.match(html, /type="date" required=""/);
  assert.doesNotMatch(html, new RegExp(`value="${sid('b')}"`));
});

test('event distribution preserves true zeros and never displays missing statistics as zero', () => {
  const content = text(render(DistributionTable, { event: distribution(0), baseline: { ...distribution(null), count: 0 } }));
  assert.match(content, /0\.00%/); assert.match(content, /—/);
  assert.match(content, /全部日期基线/); assert.doesNotMatch(content, /胜率|收益率保证/);
});

test('pair results expose sample counts, as-of mismatch and reasons alongside missing metrics', () => {
  const side = { source_rows: 30, duplicate_groups: 1, invalid_groups: 1, unlocated_rows: 2 };
  const report = envelope({ roles: { left: identity('600000.SH'), right: identity('600001.SH') }, baseline: { date: '2026-01-01' }, alignment: { left: side, right: side, common_dates: 29, valid_common_dates: 28, left_only_dates: 1, right_only_dates: 0 }, series: [{ date: '2026-02-01', return_correlation: 0, return_beta: 0, residual_deviation: null, deviation_reason: 'residual_scale_too_small', relative_strength: 0, n_prices: 20, n_returns: 20 }] });
  const content = text(render(PairResults, { report, cutoff: '2026-02-02', lookback: 20 }));
  assert.match(content, /截止当天没有共同记录/); assert.match(content, /拟合残差尺度过小/);
  assert.match(content, /0\.000/); assert.match(content, /未做协整或均值回归检验/);
});

test('universe exposes selected denominator and missing-cutoff state without rollback', () => {
  const member = { identity: identity('600001.SH'), snapshot_id: sid('b'), cutoff_present: false, cutoff_valid: false, momentum: null, volatility: null, max_drawdown: null, momentum_reason: 'cutoff_missing', volatility_reason: 'cutoff_missing', max_drawdown_reason: 'cutoff_missing', rank: null, n_prices: 0, n_returns: 0 };
  const report = envelope({ members: [member], breadth: { selected: 2, cutoff_present: 1, cutoff_valid: 1, positive: 0, momentum_valid: 1, positive_momentum_fraction: 0, metrics: {} } });
  const content = text(render(UniverseResults, { report, cutoff: '2026-02-02', lookback: 20, name: '合成自选', onOpen() {} }));
  assert.match(content, /1 \/ 2/); assert.match(content, /0\.0%/); assert.match(content, /缺少截止日期记录/);
  assert.match(content, /缺截止当日价不回退/); assert.match(content, /来源区间/);
});

test('estimate chart breaks across missing data and explicit resets', () => {
  const html = render(EstimatePlot, { label: '合成估计绘图测试', series: [{ name: '估计', color: '#111111', points: [{ date: '2026-01-01', value: 0 }, { date: '2026-01-02', value: null }, { date: '2026-01-03', value: 1 }, { date: '2026-01-04', value: 2, reset: true }] }] });
  const path = html.match(/<path[^>]*d="([^"]*)"/)?.[1];
  assert.ok(path); assert.equal((path.match(/M/g) ?? []).length, 3); assert.equal((path.match(/L/g) ?? []).length, 0);
  assert.match(html, /role="img"/);
});
