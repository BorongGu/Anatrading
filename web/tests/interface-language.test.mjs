import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { explain } from '../src/api.ts';
import { researchReason } from '../src/research-model.ts';

// Text and SSR checks only; no browser, layout or font verification is implied.
const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { DailyScreen } = await server.ssrLoadModule('/src/DailyScreen.tsx');
const { DailyBackground } = await server.ssrLoadModule('/src/DailyBackground.tsx');
const { SnapshotEvidence } = await server.ssrLoadModule('/src/App.tsx');
const render = (component, props) => renderToStaticMarkup(createElement(component, props)).replace(/<[^>]+>/g, '');
const legacyWords = /快照|合同|门禁|数据证据工作台/;

test('source UI copy uses plain data-version and format wording', () => {
  const sourceRoot = new URL('../src/', import.meta.url);
  for (const name of readdirSync(sourceRoot).filter(name => /\.tsx?$/.test(name))) {
    assert.doesNotMatch(readFileSync(new URL(name, sourceRoot), 'utf8'), legacyWords, name);
  }
});

test('error wording keeps stable diagnostic codes and the actual rejected data conditions', () => {
  for (const [code, expected] of [
    ['daily_cache_evidence_mismatch', '批次数据版本不一致'],
    ['followup_screen_mismatch', '当前参数或数据版本不一致'],
    ['snapshot_not_found', '数据版本不存在'],
    ['invalid_snapshot_id', '数据版本编号无效'],
    ['invalid_import_spec', '导入格式或声明不符合格式要求'],
    ['background_period_mismatch', '1分钟数据版本与日线数据版本'],
    ['unsupported_bao_period', '当前支持范围'],
    ['invalid_bao_fields', '已验证的来源格式'],
    ['invalid_bao_cells', '记录结构或字段数量不符，或含有非字符串值'],
    ['invalid_interpretation', '字段名或值不符合格式要求'],
    ['mode_not_supported', '目前仅支持历史回顾查询'],
    ['query_row_limit', '当前选择超过 20,000 条上限'],
  ]) {
    const text = explain(new Error(code));
    assert.ok(text.includes(expected), code);
    assert.ok(text.endsWith(`（${code}）`), code);
    assert.doesNotMatch(text, legacyWords);
  }
  assert.equal(researchReason('invalid_research_response'), '研究响应与当前选择或数据格式要求不符');
});

test('daily screening describes fixed versions without weakening missing-date or research limits', () => {
  const text = render(DailyScreen, { runIds: [], onSelect() {} });
  assert.match(text, /所选批次的固定数据版本/);
  assert.match(text, /缺少该日时不使用更早记录替代/);
  assert.match(text, /条件全部成立才匹配/);
  assert.match(text, /全部留空仅列出无条件数据记录/);
  assert.match(text, /复权、数量口径、闭合与历史可得时点未核/);
  assert.match(text, /匹配不代表收益或买入建议/);
  assert.doesNotMatch(text, legacyWords);
});

test('daily background names the chosen data version and preserves same-day exclusion and unknowns', () => {
  const text = render(DailyBackground, { query: { snapshot_id: 'synthetic-minute', rows: [] }, selected: null,
    snapshots: [], dailySnapshot: '', onSelect() {}, window: '60', onWindowSelect() {},
    channelLookback: 20, onChannelLookbackSelect() {}, atrPeriod: 14, onAtrPeriodSelect() {},
    dailyVolumeLookback: 20, onDailyVolumeLookbackSelect() {}, efficiencyLookback: 10, onEfficiencyLookbackSelect() {} });
  assert.match(text, /选择用于对照的日线数据版本/);
  assert.match(text, /选择日线数据版本，再点击分钟图或使用标签回放/);
  assert.match(text, /同日完整日线不参与背景/);
  assert.match(text, /证券声明匹配仅为 assumed/);
  assert.match(text, /闭合、历史可得时点及跨来源尺度、复权可比性未核/);
  assert.doesNotMatch(text, legacyWords);
});

test('source details retain full version and raw hash with unknown-unit and availability qualifications', () => {
  const snapshot = { snapshot_id: 'a'.repeat(64), metadata: {}, manifest: { raw_sha256: 'b'.repeat(64) } };
  const text = render(SnapshotEvidence, { snapshot });
  assert.match(text, /仅展示当前数据版本的源值/);
  assert.ok(text.includes(`数据版本编号${snapshot.snapshot_id}`));
  assert.ok(text.includes(`原件 SHA-256${snapshot.manifest.raw_sha256}`));
  assert.match(text, /单位未核实/);
  assert.match(text, /单位、柱闭合及历史可得性未验证时，不推断可交易信号/);
  assert.match(text, /source_evidence_retrospective_only/);
  assert.doesNotMatch(text, legacyWords);
});
