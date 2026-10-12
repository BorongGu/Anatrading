import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { makeFilterFixture, goldenDraftGroups, recountFilter, indexReportedTruths, unavailableFact } from './filter-fixtures.mjs';

// Synthetic render-only evidence. This suite never claims browser clicks, layout,
// focus, font rendering, screen-reader navigation or genuine market compatibility.
const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { FilterEditor, FilterResults, FilterMemberDetails } = await server.ssrLoadModule('/src/UniverseFilter.tsx');
const { UniverseResearch, createUniverseDraft } = await server.ssrLoadModule('/src/UniverseResearch.tsx');
const render = (component, props = {}) => renderToStaticMarkup(createElement(component, props));
const text = html => html.replace(/<[^>]+>/g, '').replaceAll('&gt;', '>').replaceAll('&lt;', '<');
const snapshot = id => ({ snapshot_id: id, row_count: 30, metadata: { period: '1d', source_code: id.slice(0, 6), source_name: '合成界面样本' }, manifest: {} });
const results = async () => {
  const f = await makeFilterFixture();
  return { ...f, props: { report: f.reply, groupLabels: f.expected.groupLabels, name: '合成自选', onOpen() {} } };
};
function partial(reply, index = 0, state = 'selected') {
  const member = reply.result.members[index];
  unavailableFact(reply, index, 'volatility');
  member.reasons = [{ id: 'r1', code: 'numerical_failure', scope: 'metric', field: 'volatility', count: 1, examples: [], omitted_count: 0 }];
  member.primary_reason = 'numerical_failure';
  const v = member.atoms.find(atom => atom.fact_ref === 'volatility'); v.truth = 'unknown'; v.reason_refs = ['r1'];
  member.groups[1].truth = 'unknown'; member.evidence_complete = false; member.partial_evidence = true;
  member.selection_state = state; member.logical_truth = state === 'selected' ? 'true' : state === 'excluded' ? 'false' : 'unknown';
  if (state !== 'selected') {
    member.atoms.find(atom => atom.fact_ref === 'max_drawdown').truth = 'false'; member.groups[0].truth = 'false';
    if (state === 'excluded') { member.atoms.find(atom => atom.fact_ref === 'momentum').truth = 'false'; member.groups[1].truth = 'false'; }
  }
  indexReportedTruths(member); recountFilter(reply); return member;
}

test('editor uses native bounded groups, fixed directions and exact human previews', () => {
  const html = render(FilterEditor, { draft: { enabled: true, groups: goldenDraftGroups }, onChange() {} });
  const content = text(html);
  assert.equal((html.match(/<fieldset/g) ?? []).length, 2);
  assert.equal((html.match(/<legend/g) ?? []).length, 2);
  assert.match(content, /同时满足/); assert.match(content, /或，再加一组/);
  assert.match(content, /回撤 ≥ −10%/); assert.match(content, /log 单位（未年化）/);
  assert.match(html, /type="text" inputMode="decimal"/);
  assert.doesNotMatch(html, /type="number"/);
  assert.match(html, /id="filter-add-group" disabled=""/);
});

test('editing precision is not rounded and local error is associated with its input', () => {
  const html = render(FilterEditor, { draft: { enabled: true, groups: [[{ field: 'momentum', threshold: '5.0000000000000001' }]] }, onChange() {}, inputError: { groupIndex: 0, atomIndex: 0 } });
  assert.match(text(html), /收盘变化 ≥ 5\.0000000000000001%/);
  assert.match(html, /aria-invalid="true"/); assert.match(html, /aria-describedby="filter-0-0-hint universe-error-summary"/);
  assert.match(html, /aria-label="删除第 1 组条件 1" disabled=""/);
});

test('first open preserves old no-condition workflow and distinguishes search from numeric conditions', () => {
  const ids = ['a'.repeat(64), 'b'.repeat(64)]; const draft = { ...createUniverseDraft(), ids, cutoff: '2026-01-03' };
  const content = text(render(UniverseResearch, { snapshots: ids.map(snapshot), onImport() {}, onOpen() {}, draft }));
  assert.match(content, /搜索代码或名称/); assert.match(content, /查看已选 2 个版本/);
  assert.match(content, /研究所选股票/); assert.match(content, /添加条件/);
  assert.doesNotMatch(content, /筛选已导入日线|按条件研究/);
  assert.match(content, /输入已保留/); assert.match(content, /每股实际起点可能不同/);
});

test('missing catalog version stays selected, is removable and cannot silently shrink a research request', () => {
  const ids = ['a'.repeat(64), 'b'.repeat(64)]; const draft = { ...createUniverseDraft(), ids, cutoff: '2026-01-03' };
  const html = render(UniverseResearch, { snapshots: [snapshot(ids[0])], onImport() {}, onOpen() {}, draft });
  assert.match(text(html), /已选 2 \/ 50/); assert.match(text(html), /1 个已选版本暂不可用/);
  assert.ok(html.includes(ids[1])); assert.match(html, /disabled="">研究所选股票/);
});

test('all members, original rank, actual dates and legal zeros remain visible', async () => {
  const { props } = await results(); const content = text(render(FilterResults, props));
  assert.match(content, /600001\.SH/); assert.match(content, /000001\.SZ/); assert.match(content, /原名次 1/);
  assert.match(content, /0\.00%/); assert.match(content, /0\.00000 log \/ 来源区间/);
  assert.match(content, /2026-01-01 → 2026-01-03/);
  assert.match(content, /沪深北市场分组/); assert.doesNotMatch(content, /已核 A 股|收益波动|买入信号|年化 2%/);
});

test('canonical group order maps back to submitted editor labels', async () => {
  const { props } = await results(); const content = text(render(FilterResults, props));
  assert.match(content, /第 2 组：收盘路径回撤 ≥ −10%，且 收盘变化 ≥ 0%/);
  assert.match(content, /第 1 组：收盘变化 ≥ 0%，且 来源区间波动 ≤ 0\.02 log/);
});

for (const state of ['selected', 'excluded', 'undetermined']) test(`${state} keeps partial reasons alongside its definitive or unresolved status`, async () => {
  const { reply, props } = await results(); const member = partial(reply, 0, state);
  const content = text(render(FilterResults, props));
  assert.match(content, /仍有条件待核/); assert.match(content, /数值估计失败/);
  const detail = text(render(FilterMemberDetails, { ...props, member }));
  assert.match(detail, /第 1 组/); assert.match(detail, /第 2 组/); assert.match(detail, /数值估计失败/);
  assert.match(detail, /精确比例/); assert.match(detail, /按精确值判定，显示值已舍入/);
});

test('unselected failed metric is a baseline reason without manufacturing partial evidence', async () => {
  const f = await makeFilterFixture({ groups: [[{ field: 'momentum', threshold: '0' }]] });
  unavailableFact(f.reply, 0, 'volatility'); recountFilter(f.reply);
  const content = text(render(FilterResults, { report: f.reply, groupLabels: f.expected.groupLabels, name: '', onOpen() {} }));
  assert.match(content, /0 只仍有条件待核/); assert.match(content, /数值估计失败/);
  assert.equal(f.reply.result.members[0].partial_evidence, false);
});

test('date gate unknown preserves available diagnostics but never labels them usable for filtering', async () => {
  const { props, reply } = await results(); const m = reply.result.members[0];
  m.source_gate = 'unknown'; m.logical_truth = 'unknown'; m.selection_state = 'undetermined'; m.evidence_complete = false; m.partial_evidence = true;
  m.reasons = [{ id: 'r1', code: 'date_set_integrity_unknown', scope: 'source_date', field: null, count: 1, examples: [], omitted_count: 0 }];
  m.primary_reason = 'date_set_integrity_unknown'; m.atoms.forEach(a => { a.truth = 'unknown'; a.reason_refs = ['r1']; }); m.groups.forEach(g => { g.truth = 'unknown'; });
  indexReportedTruths(m); recountFilter(reply);
  assert.match(text(render(FilterResults, props)), /仅作诊断，未用于此次筛选/);
  const details = text(render(FilterMemberDetails, { ...props, member: m }));
  assert.match(details, /存在无法定位日期的记录/);
});

test('missing cutoff displays no invented actual endpoint while the old baseline still carries request D', async () => {
  const { props, reply } = await results(); const m = reply.result.members[0];
  for (const field of ['momentum', 'volatility', 'max_drawdown']) unavailableFact(reply, 0, field, 'cutoff_missing');
  Object.assign(m.window, { start_date: null, end_date: null, first: null, last: null, actual_groups: 0, n_prices: 0, n_returns: 0, drawdown_witness: null });
  const details = text(render(FilterMemberDetails, { ...props, member: m }));
  assert.match(details, /请求截止 2026-01-03；实际 — → —/);
  assert.match(details, /缺少截止日期记录，未形成此次窗口/);
  assert.equal(reply.result.universe.members[0].end_date, '2026-01-03');
});

test('source details retain shared-contract applicability, absent/null and legacy distinctions', async () => {
  const { props, reply } = await results();
  const content = text(render(FilterMemberDetails, { ...props, member: reply.result.members[0] }));
  assert.match(content, /CNY/); assert.match(content, /documented_meaning_only/); assert.match(content, /unverified/);
  assert.match(content, /文档定义的单位，本样本适用性未核/); assert.match(content, /来源未提供/); assert.match(content, /明确为空/);
  assert.match(content, /legacy/); assert.match(content, /请求未复权不等于复权口径已核/);
  assert.match(content, /来源规则编号synthetic-contract/); assert.match(content, /规则版本1/);
  assert.doesNotMatch(content, /快照|合同|门禁|数据证据工作台/);
});

test('reason tuples retain null ordinals and explicit omitted counts', async () => {
  const f = await makeFilterFixture({ lookback: 19, cutoff: '2026-01-20' }); const m = f.reply.result.members[0];
  m.reasons = [{ id: 'r1', code: 'duplicate_date', scope: 'window_slot', field: null, count: 20,
    examples: Array.from({ length: 8 }, (_, i) => [`2026-01-${String(i + 1).padStart(2, '0')}`, null]), omitted_count: 12 }];
  const content = text(render(FilterMemberDetails, { member: m, report: f.reply, groupLabels: f.expected.groupLabels, onOpen() {} }));
  assert.match(content, /20 个日期槽/); assert.match(content, /无法唯一定位源序号/); assert.match(content, /另有 12 个日期槽/);
  assert.match(content, /同槽的其他检查可回查原始记录/);
});

test('view-only empty category never changes the complete denominator or rewrites ranks', async () => {
  const { props } = await results(); const html = render(FilterResults, { ...props, view: 'excluded' });
  assert.match(text(html), /当前显示类别为 0 只；全部 2 只仍保留/);
  assert.match(html, /aria-pressed="true">排除 0/);
  assert.match(html, /<tbody><\/tbody>/); assert.doesNotMatch(html, /原名次 (?:\d|—)/);
});


test('all three original metric denominators and the new identity limitation stay readable', async () => {
  const { props } = await results(); const content = text(render(FilterResults, props));
  assert.match(content, /三项原集合指标的有效与失败数量（全部所选为分母）/);
  assert.match(content, /有效缺失无效历史不足/);
  assert.match(content, /证券身份未经证券主数据核验/);
  assert.doesNotMatch(content, /未识别状态（source_identity_not_security_master_verified）/);
});
