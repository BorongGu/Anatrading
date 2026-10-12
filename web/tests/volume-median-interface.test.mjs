import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { volumeFixture } from './volume-median-fixtures.mjs';

// Actual components + actual helper, synthetic HTTP replies and a tiny hook scheduler.
// No browser/DOM/layout/focus evidence. The pinned React dispatcher is test-only.
const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { DailyVolume } = await server.ssrLoadModule('/src/DailyVolume.tsx');
const { VolumeAnalysis } = await server.ssrLoadModule('/src/VolumeAnalysis.tsx');
const text = html => html.replace(/<[^>]+>/g, '');
const tick = () => new Promise(resolve => setImmediate(resolve));
function harness(Component, initialProps) {
  const internals = React.__CLIENT_INTERNALS_DO_NOT_USE_OR_WARN_USERS_THEY_CANNOT_UPGRADE;
  assert.ok(internals && Object.hasOwn(internals, 'H'), 'update this test scheduler if pinned React changes');
  const slots = [], effects = []; let cursor = 0, dirty = true, tree, html, props = initialProps;
  const dispatcher = {
    useState(initial) {
      const i = cursor++; if (!(i in slots)) slots[i] = typeof initial === 'function' ? initial() : initial;
      return [slots[i], value => { const next = typeof value === 'function' ? value(slots[i]) : value;
        if (!Object.is(next, slots[i])) { slots[i] = next; dirty = true; } }];
    },
    useEffect(effect, dependencies) {
      const i = cursor++, previous = slots[i];
      if (!previous || dependencies.some((value, j) => !Object.is(value, previous.dependencies[j]))) {
        slots[i] = { dependencies, cleanup: previous?.cleanup };
        effects.push(() => { slots[i].cleanup?.(); slots[i].cleanup = effect(); });
      }
    },
  };
  const api = {
    render(nextProps = props) {
      props = nextProps; let iterations = 0;
      do {
        assert.ok(iterations++ < 10); dirty = false; cursor = 0;
        const previous = internals.H; internals.H = dispatcher;
        try { tree = Component(props); } finally { internals.H = previous; }
        html = renderToStaticMarkup(tree); while (effects.length) effects.shift()();
      } while (dirty);
      return text(html);
    },
    async settle() { await tick(); await tick(); return api.render(); },
    html: () => html,
    select(n) {
      const find = node => {
        if (!node) return null; if (Array.isArray(node)) return node.map(find).find(Boolean);
        if (node.type === 'select') return node; return find(node.props?.children);
      };
      find(tree).props.onChange({ target: { value: String(n) } }); api.render();
    },
    unmount() { for (const slot of slots) slot?.cleanup?.(); },
  };
  api.render(); return api;
}
function fixture(kind, n = 20, offset = 0) {
  const isDaily = kind === 'daily', f = volumeFixture(Array.from({ length: n }, (_, i) => String(i === n - 1 ? 10000 + offset : 100 + offset)), isDaily ? 'daily' : 'regular');
  const row = { ordinal: 10, label: `2025-01-01${isDaily ? '' : 'T09:32'}` };
  const query = { query_id: `query-${kind}`, snapshot_id: `snapshot-${kind}`, selection: { cutoff: row.label, ordinal_start: 10, ordinal_end: 10, mode: 'retrospective' }, metadata: { period: isDaily ? '1d' : '1m' }, rows: [row], unlocated: [] };
  const report = { query_id: query.query_id, lookback: n, method_id: isDaily ? 'prior-source-daily-volume-v1' : 'source-volume-at-time-v1', qualification: 'conditional_source_values',
    context_query_id: 'synthetic-full-history', volume_id: 'synthetic-volume-id', context_unlocated_rows: 0, unreadable_date_rows: 0, excluded_unlocated_rows: 0, outside_template_rows: 0,
    rows: [isDaily ? f.comparison : { ordinal: 10, history_dates: f.historyDates, reason: null, regular: f.comparison, cumulative: volumeFixture(Array(n).fill('500'), 'cumulative').comparison }], unlocated: [] };
  return { query, report, row };
}
async function scenario(kind, action, n = 20) {
  const previous = globalThis.fetch, requests = [], f = fixture(kind, n); let run;
  globalThis.fetch = (url, options) => new Promise((resolve, reject) => requests.push({ url, options, reject, reply: data => resolve({ ok: true, json: async () => data }) }));
  let props = { query: f.query, selected: null, lookback: n, onLookbackSelect: value => { props = { ...props, lookback: value }; run.render(props); } };
  try {
    run = harness(kind === 'daily' ? DailyVolume : VolumeAnalysis, props);
    await action({ f, run, requests, props, replace: next => { props = next; return run.render(props); } });
  } finally { run?.unmount(); globalThis.fetch = previous; }
}
for (const kind of ['daily', 'minute']) {
  test(`${kind} actual SSR shows exact median beside original mean/ratio, complete closed details and limitations`, () => scenario(kind, async ({ f, run, requests }) => {
    requests[0].reply(f.report); const output = await run.settle(), html = run.html();
    assert.match(output, /历史中位数（源数量）\s*100（精确）/);
    assert.match(output, /当前\/均量的分母仍为均值，中位数供并列核对/);
    assert.match(output, /单位/); assert.match(output, /当前 \/ .*均量/);
    assert.equal((output.match(/历史中位数/g) ?? []).length, kind === 'daily' ? 1 : 2);
    assert.match(html, /<details><summary>/); assert.doesNotMatch(html, /<details open/);
    assert.match(output, /2024-01-01/); assert.match(output, /10000/);
    assert.doesNotMatch(output, /中位数比|当前 \/ 中位数|NaN|Infinity|胜率|异常量/);
    if (kind === 'minute') { assert.match(output, /500（精确）/); assert.match(output, /同一次早槽变化可延续到后续累计/); }
  }));
  test(`${kind} changing N clears old summary until a correctly matched report arrives; N2 notice stays explicit`, () => scenario(kind, async ({ f, run, requests }) => {
    requests[0].reply(f.report); await run.settle(); run.select(2);
    assert.match(text(run.html()), /正在计算/); assert.doesNotMatch(text(run.html()), /100（精确）/);
    const next = fixture(kind, 2); requests.at(-1).reply(next.report);
    assert.match(await run.settle(), /5050（精确）/); assert.match(text(run.html()), /2个历史值的中位数与均值相同/);
    assert.equal(new URL(requests.at(-1).url, 'http://synthetic.test').searchParams.get('lookback'), '2');
    if (kind === 'minute') assert.match(text(run.html()), /均值容易受单日影响/);
  }));
  test(`${kind} selected record, clear selection, future row rewrite and cropped display use matched full members only`, () => scenario(kind, async ({ f, run, requests, props, replace }) => {
    const next = fixture(kind, 20, 800), futureRow = { ordinal: 11, label: f.row.label.replace('01-01', '01-02') };
    f.query.rows.push(futureRow); next.report.rows[0].ordinal = 11; f.report.rows.push(next.report.rows[0]);
    requests[0].reply(f.report); assert.match(await run.settle(), /900（精确）/);
    assert.match(replace({ ...props, selected: f.row }), /100（精确）/);
    if (kind === 'daily') f.report.rows[1].members[0].value = '99999'; else f.report.rows[1].regular.members[0].value = '99999';
    assert.match(replace({ ...props, selected: f.row }), /100（精确）/);
    assert.doesNotMatch(replace({ ...props, selected: null }), /100（精确）/);
    const crop = structuredClone(f.query); crop.query_id = 'cropped-display'; crop.rows = [f.row]; crop.selection.ordinal_end = 10;
    assert.doesNotMatch(replace({ ...props, query: crop, selected: null }), /（精确）/);
    const report = { ...f.report, query_id: crop.query_id, rows: [f.report.rows[0]] };
    requests.at(-1).reply(report); assert.match(await run.settle(), /100（精确）/);
  }));
  test(`${kind} source/period replacement aborts prior request; late success/failure and unmount cannot restore a median`, () => scenario(kind, async ({ f, run, requests, props, replace }) => {
    const first = requests[0], secondQuery = { ...f.query, query_id: 'new-source', snapshot_id: 'new-snapshot', metadata: { period: 'unsupported' } };
    replace({ ...props, query: secondQuery }); assert.equal(first.options.signal.aborted, true);
    first.reply(f.report); assert.doesNotMatch(await run.settle(), /（精确）/);
    const second = requests.at(-1); replace({ ...props, query: { ...secondQuery, query_id: 'third-source' } });
    second.reject(new Error('invalid_query_response')); assert.doesNotMatch(await run.settle(), /响应与当前选择/);
    const last = requests.at(-1); run.unmount(); assert.equal(last.options.signal.aborted, true);
    last.reply({ ...f.report, query_id: 'third-source' }); assert.doesNotMatch(await run.settle(), /（精确）/);
  }));
  test(`${kind} source failures differ from invalid summaries; readable original members, mean and ratio survive corruption`, () => scenario(kind, async ({ f, run, requests }) => {
    const c = kind === 'daily' ? f.report.rows[0] : f.report.rows[0].regular;
    c.baseline_sum = '123'; requests[0].reply(f.report); let output = await run.settle();
    assert.match(output, /中位数摘要无法核对/); assert.match(output, /≈595\.0000/); assert.match(output, /2024-01-01/);
    assert.match(output, /≈0\.3361/); assert.match(run.html(), /<details><summary>/);
    c.reason = '__proto__'; assert.match(run.render(), /中位数摘要无法核对/); c.reason = null;
    c.members = {}; output = run.render(); assert.match(output, /中位数摘要无法核对/); assert.match(output, /≈595\.0000/);
    c.members = [null, { date: '2024-01-01', value: '100', reason: null }]; c.baseline_mean = { display: {}, numerator: {}, denominator: {} };
    assert.match(run.render(), /中位数摘要无法核对/); assert.match(text(run.html()), /2024-01-01/);
    if (kind === 'minute') { f.report.rows[0].history_dates = {}; assert.match(run.render(), /中位数摘要无法核对/); }
  }));
  for (const corrupt of ['method_id', 'query_id', 'ordinal']) test(`${kind} invalid ${corrupt} stays rejected by the original gate`, () => scenario(kind, async ({ f, run, requests }) => {
    if (corrupt === 'ordinal') f.report.rows[0].ordinal = 999; else f.report[corrupt] = 'unexpected';
    requests[0].reply(f.report);
    assert.match(await run.settle(), /响应与当前选择或显示映射不一致/); assert.doesNotMatch(text(run.html()), /（精确）/);
  }));
}
test('minute regular remains available when cumulative is incomplete, with no invented summary ratio', () => scenario('minute', async ({ f, run, requests }) => {
  const c = f.report.rows[0].cumulative; Object.assign(c.members[0], { value: null, reason: 'missing_slot' });
  Object.assign(c, { baseline_sum: null, baseline_mean: null, ratio: null, reason: 'missing_slot' });
  requests[0].reply(f.report); const output = await run.settle();
  assert.match(output, /历史中位数（源数量）\s*∅/); assert.match(output, /所需时槽缺失/); assert.match(output, /100（精确）/);
  assert.doesNotMatch(output, /中位数摘要无法核对/);
}));
test('zero median leaves the positive mean ratio intact and all-zero retains zero_baseline', () => scenario('daily', async ({ f, run, requests }) => {
  const original = volumeFixture([...Array(19).fill('0'), '100'], 'daily'); f.report.rows[0] = original.comparison;
  requests[0].reply(f.report); assert.match(await run.settle(), /历史中位数（源数量）\s*0（精确）/);
  assert.match(text(run.html()), /当前 \/ 前序均量 ≈40\.0000/);
  f.report.rows[0] = volumeFixture(Array(20).fill('0'), 'daily').comparison;
  assert.match(run.render(), /历史均量为零，比值未定义/); assert.match(text(run.html()), /当前 \/ 前序均量 ∅/);
}));
