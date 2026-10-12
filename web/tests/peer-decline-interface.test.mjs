import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { declineFixture, setSourcePrices } from './peer-decline-fixtures.mjs';

const server = await createServer({
  server: { middlewareMode: true, hmr: false, ws: false },
  appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] },
});
after(() => server.close());
const { PeerNeighborResults } = await server.ssrLoadModule('/src/PeerNeighborResults.tsx');
const render = (report, onOpen = () => {}) => renderToStaticMarkup(
  createElement(PeerNeighborResults, { report, name: '明确自选组', onOpen }),
);

function findNodes(node, predicate, found = []) {
  if (!node || typeof node !== 'object') return found;
  if (Array.isArray(node)) {
    node.forEach(child => findNodes(child, predicate, found));
    return found;
  }
  if (predicate(node)) found.push(node);
  findNodes(node.props?.children, predicate, found);
  return found;
}

function detailNodes(report, onOpen = () => {}) {
  const tree = PeerNeighborResults({ report, name: '', onOpen });
  return findNodes(tree, node => node.props?.className === 'peer-decline-details');
}

test('each original candidate gains one closed detail with two four-cell tables and separate flats', () => {
  const { report } = declineFixture();
  const nodes = detailNodes(report);
  assert.equal(nodes.length, report.candidates.length);
  for (const node of nodes) {
    assert.equal(node.type, 'details');
    assert.equal(node.props.open, undefined);
    const html = renderToStaticMarkup(node);
    assert.match(html, /同跌明细/);
    assert.match(html, /前60区间/);
    assert.match(html, /当前60区间/);
    assert.match(html, /目标 \/ 同伴/);
    assert.match(html, /同伴跌/);
    assert.match(html, /同伴未跌/);
    assert.match(html, /未跌包含持平/);
    assert.match(html, /仅记源价方向/);
    assert.match(html, /不表示含分红经济收益或未来概率/);
    assert.match(html, /持平：目标 60，同伴 60（已计入未跌）/);
    assert.equal((html.match(/<table /g) ?? []).length, 2);
    assert.equal((html.match(/<td>60<\/td>/g) ?? []).length, 8);
    assert.equal((html.match(/同跌日期 0 条/g) ?? []).length, 2);
    assert.doesNotMatch(html, /<input|<select|<details[^>]* open|%|上涨|显著性|稳定徽章/);
  }
  const html = render(report);
  assert.match(html, /目标本窗简单源价变化为常量/);
  assert.match(html, /全部原成员保留/);
  assert.match(html, /未共享变化行/);
  assert.match(html, /当前明确自选组的来源回顾/);
  assert.match(html, /历史当时可得性均未核实/);
  assert.match(html, /不自动聚焦源序号/);
  assert.match(html, /实际省时与判断改善未验/);
  for (const member of report.members) assert.ok(html.includes(member.snapshot_id));
});

test('table axes and four cells show distinct counts and complete row/column margins', () => {
  const { report, targetId, peerId } = declineFixture();
  setSourcePrices(report, targetId, ['100', '99', '98', '97', '97', '97', '97']);
  setSourcePrices(report, peerId, ['100', '99', '99', '99', '98', '97', '96']);
  const node = detailNodes(report)[report.windows.current.order.indexOf(peerId)];
  const tables = findNodes(node, element => element.type === 'table');
  const rows = findNodes(tables[0], element => element.type === 'tr');
  const values = rows.slice(1).map(row => findNodes(row, element => element.type === 'td')
    .map(cell => cell.props.children));
  assert.deepEqual(values, [[1, 2, 3], [3, 54, 57], [4, 56, 60]]);
});

test('joint dates preserve both source identities and exact end dates, with no extra HTTP', () => {
  const { report, targetId, peerId } = declineFixture();
  const downIndices = [2, 60, 61, 120];
  let price = 200;
  const prices = Array.from({ length: 121 }, (_, index) => {
    if (downIndices.includes(index)) price--;
    return String(price);
  });
  setSourcePrices(report, targetId, prices);
  setSourcePrices(report, peerId, prices);
  const before = structuredClone(report);
  const calls = [];
  const oldFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = () => { requests++; throw new Error('unexpected HTTP'); };
  try {
    const nodes = detailNodes(report, (...args) => calls.push(args));
    for (const node of nodes) {
      renderToStaticMarkup(node);
      for (const button of findNodes(node, element => element.type === 'button')) button.props.onClick();
    }
    assert.deepEqual(calls, downIndices.flatMap(index => [
      [targetId, report.used_dates[index]], [peerId, report.used_dates[index]],
    ]));
    const html = render(report);
    for (const index of downIndices) {
      assert.ok(html.includes(`${report.used_dates[index - 1]} → ${report.used_dates[index]}`));
      assert.ok(html.includes(`打开目标至${report.used_dates[index]}`));
      assert.ok(html.includes(`打开同伴至${report.used_dates[index]}`));
    }
    assert.equal(requests, 0);
    assert.deepEqual(report, before);
  } finally {
    globalThis.fetch = oldFetch;
  }
});

test('closed source panel preserves all candidates and old reasons without false zero counts', () => {
  const { report } = declineFixture();
  report.source_panel_complete = false;
  report.reasons = ['source_panel_unavailable'];
  report.members[0].panel_complete = false;
  report.members[0].reasons = ['missing_endpoint'];
  report.members[0].endpoints[60].close_exact = null;
  report.members[0].endpoints[60].reasons = ['missing_endpoint'];
  const nodes = detailNodes(report);
  assert.equal(nodes.length, report.candidates.length);
  for (const node of nodes) {
    const html = renderToStaticMarkup(node);
    assert.match(html, /完整组来源未齐，无法核对同跌明细/);
    assert.doesNotMatch(html, /<table|同跌日期 0|持平：/);
  }
  const html = render(report);
  assert.match(html, /完整组来源面板未齐，两窗均未计算/);
  assert.match(html, /共同日期缺少记录/);
  assert.match(html, /没有自动删除成员或前移日期/);
  for (const member of report.members) assert.ok(html.includes(member.snapshot_id));
});
