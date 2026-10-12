import { withSyntheticBridge } from './synthetic-bridge.mjs';
import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { explain } from '../src/api.ts';
import { assertMinuteHistoryReport, buildMinuteHistoryRequest, loadMinuteHistory, MinuteHistoryGate,
  minuteHistoryInputIssue, minuteHistorySourceDate, minuteHistorySourceKey } from '../src/minute-label-history.ts';
const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { explainMinuteHistoryError, MinuteHistoryResults, MinuteLabelHistory } = await server.ssrLoadModule('/src/MinuteLabelHistory.tsx');
const { RecordDetails } = await server.ssrLoadModule('/src/RecordDetails.tsx');
const canonical = v => Array.isArray(v) ? `[${v.map(canonical).join(',')}]` : v && typeof v === 'object'
  ? `{${Object.keys(v).sort().map(k => `${JSON.stringify(k)}:${canonical(v[k])}`).join(',')}}` : JSON.stringify(v);
const hash = v => createHash('sha256').update(canonical(v)).digest('hex');
const render = (component, props) => renderToStaticMarkup(createElement(component, props));
const text = html => html.replace(/<[^>]+>/g, '');
function seal(r) { delete r.history_id; r.history_id = hash(r); return r; }
function row(date, clock, ordinal, close) {
  return { ordinal, label: `${date}T${clock}`, source_label: `${date.replaceAll('-', '/')} ${clock}`, locator: `line:${ordinal + 1}`,
    tokens: { date, time: clock, close, note: '合成原字段' }, values: { open: null, high: null, low: null, close, volume: null, amount: null },
    checks: [{ name: 'numeric.close', outcome: 'pass' }], volume_shares: null, amount_cny: null };
}
function fixture(period = '1m') {
  const date = '2026-10-09', history = ['2026-10-02', '2026-10-05', '2026-10-06', '2026-10-07', '2026-10-08'];
  const days = [...history, date].map((source_date, i) => ({ source_date, kind: i === 5 ? 'current' : 'history',
    start: [row(source_date, '14:57', i * 2 + 1, '100')], end: [row(source_date, '15:00', i * 2 + 2, '90')],
    unknown_clock_ordinals: [], reason: null, change: { numerator: '-1', denominator: '10', display: '-0.10000000' },
    magnitude: { numerator: '1', denominator: '10', display: '0.10000000' } }));
  const selected = days.at(-1).end[0], snapshot = 'a'.repeat(64), versions = { source: 'synthetic-v1', normalizer: 'test-v1' };
  const selection = { snapshot_id: snapshot, mode: 'retrospective', cutoff: `${date}T15:00`, ordinal_start: 12, ordinal_end: 12,
    fields: ['open', 'high', 'low', 'close', 'volume', 'amount'], versions };
  const query = { snapshot_id: snapshot, query_id: hash(selection), batch_id: 'b'.repeat(64), selection, rows: [selected], unlocated: [],
    manifest: { raw_sha256: 'd'.repeat(64), versions, contract: { format_id: 'synthetic', temporal_semantics: { status: 'unknown' } } },
    metadata: { period, source_code: '600059', source_venue: 'SH', source_name: '合成数据' }, batch_checks: [] };
  const request = buildMinuteHistoryRequest(query, selected, '14:57', '15:00');
  const report = seal({ method_id: 'minute-source-label-history-v1', snapshot_id: snapshot, batch_id: query.batch_id, query_id: query.query_id,
    context_query_id: hash({ ...selection, ordinal_start: null, ordinal_end: null }), raw_sha256: query.manifest.raw_sha256,
    versions: structuredClone(versions), metadata: structuredClone(query.metadata), contract: structuredClone(query.manifest.contract), batch_checks: [],
    source_date: date, start_clock: '14:57', end_clock: '15:00', as_of_label: `${date}T15:00`, lookback: 5,
    window_status: 'complete', unknown_date_ordinals: [], history_dates: history, missing_history_dates: 0, nominal_minutes: 3,
    assumption: 'same_price_scale_between_endpoints', qualification: 'retrospective_source_endpoint_arithmetic', display_policy: { places: 8, rounding: 'half_even' },
    days: [days.at(-1), ...days.slice(0, -1)] });
  return { query, selected, request, report };
}
const validate = f => assertMinuteHistoryReport(f.report, f.request);
function ratio(day, start, end, numerator, denominator, display) {
  day.start[0].values.close = start; day.end[0].values.close = end;
  day.change = { numerator, denominator, display };
  day.magnitude = { numerator: numerator.replace('-', ''), denominator, display: display.replace('-', '') };
}
async function load(f, body = JSON.stringify(f.report)) {
  const old = globalThis.fetch; let call;
  globalThis.fetch = async (path, options) => { call = { path, options }; return new Response(body); };
  try { return { result: await loadMinuteHistory(f.request, new AbortController().signal), call }; } finally { globalThis.fetch = old; }
}

test('explicit request retains current selection and selected date; history does not come from one visible row', () => {
  const f = fixture(), url = new URL(f.request.path, 'http://local.test');
  assert.equal(url.pathname, `/api/minute-label-history/${f.query.snapshot_id}`);
  assert.deepEqual(Object.fromEntries(url.searchParams), { query_id: f.query.query_id, mode: 'retrospective', source_date: '2026-10-09',
    start_clock: '14:57', end_clock: '15:00', cutoff: '2026-10-09T15:00', ordinal_start: '12', ordinal_end: '12' });
  assert.equal(f.query.rows.length, 1); validate(f);
});
test('empty, equal, reversed, malformed, unlocated, foreign and beyond-cutoff selections cannot request', () => {
  const f = fixture();
  for (const [a,b] of [['',''], ['14:57',''], ['14:57','14:57'], ['15:00','14:57'], ['9:00','15:00'], ['24:00','25:00'], ['14:57:00','15:00'], [' 14:57','15:00']])
    assert.throws(() => buildMinuteHistoryRequest(f.query, f.selected, a, b), /invalid_minute_label_history/);
  f.query.selection.cutoff = '2026-10-09'; assert.match(minuteHistoryInputIssue(f.query, f.selected, '14:57','15:00'), /截止/);
  f.query.selection.cutoff = null; f.selected.label = null; assert.match(minuteHistoryInputIssue(f.query, f.selected, '14:57','15:00'), /规范日期标签/);
  f.selected.label = '2026-02-30T15:00'; assert.equal(minuteHistorySourceDate(f.selected), null);
  f.selected.label = '2026-10-09T15:00'; f.query.rows = []; assert.match(minuteHistoryInputIssue(f.query, f.selected, '14:57','15:00'), /当前查询/);
});
test('submitted evidence is copied and binding changes with source, row or endpoint inputs', () => {
  const f = fixture(), key = minuteHistorySourceKey(f.query, f.selected);
  f.query.metadata.source_name = '更改后'; f.selected.locator = 'line:999';
  assert.equal(f.request.query.metadata.source_name, '合成数据'); assert.equal(f.request.row.locator, 'line:13');
  assert.notEqual(minuteHistorySourceKey(f.query, f.selected), key);
  assert.notEqual(buildMinuteHistoryRequest(f.query, f.selected, '14:58', '15:00').key, f.request.key);
});
test('1m and 5m bind UTF-8 provenance, full context and result hash; 14:57 to 15:00 remains three minutes', async () => {
  for (const period of ['1m','5m']) {
    const f = fixture(period); validate(f); const { result, call } = await load(f);
    assert.equal(result.nominal_minutes, 3); assert.equal(call.path, f.request.path);
    assert.equal(call.options.cache, 'no-store'); assert.equal(call.options.credentials, 'same-origin');
  }
});
test('wrong methods, identities, provenance, parameters or qualifications reject before rendering', () => {
  for (const change of [r => r.method_id='other', r=>r.query_id='e'.repeat(64),r=>r.snapshot_id='e'.repeat(64),r=>r.batch_id='e'.repeat(64),
    r=>r.raw_sha256='e'.repeat(64),r=>r.versions.source='other',r=>r.metadata.period='5m',r=>r.contract.format_id='other',
    r=>r.batch_checks.push({name:'identity',outcome:'fail'}),r=>r.source_date='2026-10-08',r=>r.start_clock='14:58',r=>r.end_clock='15:01',
    r=>r.as_of_label='2026-10-09T15:01',r=>r.nominal_minutes=5,r=>r.lookback=20,r=>r.assumption='verified',r=>r.qualification='return',
    r=>r.display_policy.rounding='half_up',r=>r.history_id=null,r=>r.context_query_id=null]) {
    const f=fixture(); change(f.report); assert.throws(()=>validate(f), /invalid_query_response/);
  }
});
test('window order, date membership and completeness are bound to current plus at most five prior days', () => {
  for(const change of [r=>r.history_dates.reverse(),r=>r.history_dates[0]=r.source_date,r=>r.history_dates[0]='2026-02-30',
    r=>r.history_dates.push('2026-10-01'),r=>r.days.pop(),r=>r.days.reverse(),r=>r.days[1].kind='current',
    r=>r.missing_history_dates=1,r=>r.window_status='unresolved_dates',r=>r.unknown_date_ordinals=[100,99]]) {
    const f=fixture(); change(f.report); assert.throws(()=>validate(f), /invalid_query_response/);
  }
});
test('missing and duplicate endpoints retain dates and all candidates; unreadable dates degrade the list', () => {
  const f=fixture(), d=f.report.days[2]; d.end=[];d.reason='missing_endpoint';d.change=d.magnitude=null;validate(f);
  let output=text(render(MinuteHistoryResults,{report:f.report})); assert.match(output,/2026-10-05/);assert.match(output,/缺少端点记录/);
  d.end=[row(d.source_date,'15:00',40,'90'),row(d.source_date,'15:00',41,'91')];d.reason='duplicate_endpoint';validate(f);
  assert.match(text(render(MinuteHistoryResults,{report:f.report})),/源序号 41/);
  f.report.unknown_date_ordinals=[90];f.report.window_status='unresolved_dates';f.report.missing_history_dates=null;validate(f);
  output=text(render(MinuteHistoryResults,{report:f.report}));assert.match(output,/降级的可读日期列表/);assert.match(output,/集合完整性未知/);assert.doesNotMatch(output,/已列出当天与此前五个/);
  d.unknown_clock_ordinals=[91];d.reason='endpoint_uniqueness_unknown';validate(f);assert.equal(f.report.days.length,6);
});
test('insufficient history remains short and explicit without padding', () => {
  const f=fixture();f.report.history_dates.splice(0,3);f.report.days.splice(1,3);f.report.window_status='insufficient';f.report.missing_history_dates=3;validate(f);
  assert.match(text(render(MinuteHistoryResults,{report:f.report})),/历史来源日期不足五日/);assert.equal(f.report.days.length,3);
});
test('candidate Row shapes, exact visible-row identity and globally distinct ordinals are required', () => {
  for(const change of [r=>r.days[0].end[0].values.close='91',r=>r.days[1].start[0].label='2026-10-02T14:58',
    r=>r.days[1].start[0].ordinal=12,r=>r.days[1].start[0].source_label=123,r=>r.days[1].start[0].tokens.close=123,
    r=>r.days[1].start[0].checks=[{}],r=>r.days[1].start[0].volume_shares=100,r=>delete r.days[1].start[0].values.high,
    r=>r.days[1].start[0].locator='',r=>r.days[1].unknown_clock_ordinals=[1]]) {
    const f=fixture();change(f.report);assert.throws(()=>validate(f),/invalid_query_response/);
  }
});
test('signed exact fractions support half-even ties, tiny changes, exponent strings and long decimal endpoints', () => {
  const f=fixture(),d=f.report.days[1];
  for(const values of [['100','90','-1','10','-0.10000000'],['100','110','1','10','0.10000000'],['100','100','0','1','0.00000000'],
    ['200000000','199999999','-1','200000000','0.00000000'],['200000000','199999997','-3','200000000','-0.00000002'],
    ['200000000','200000001','1','200000000','0.00000000'],['200000000','200000003','3','200000000','0.00000002'],
    ['1E-18','2E-18','1','1','1.00000000'],['10.000000000000000001','10.000000000000000002','1','10000000000000000001','0.00000000']]) {ratio(d,...values);validate(f);}
  assert.match(text(render(MinuteHistoryResults,{report:f.report})),/\+1\/10000000000000000001/);
  ratio(d,'200000000','199999999','-1','200000000','0.00000000');validate(f);
  const output=text(render(MinuteHistoryResults,{report:f.report}));assert.match(output,/-1\/200000000（≈0.00000000）/);assert.match(output,/精确分数为权威值/);
});
test('wrong ratios, rounding, nonpositive close and contradictory reason/value states are rejected', () => {
  for(const change of [d=>d.change.numerator='1',d=>d.change.denominator='0',d=>d.change.numerator='-01',
    d=>{d.change.numerator='-2';d.change.denominator='20';},d=>d.change.display='-0.10000001',d=>d.magnitude.numerator='-1',
    d=>d.magnitude.display='-0.10000000',d=>d.start[0].values.close='0E-18',d=>d.start[0].values.close=null,
    d=>d.reason='missing_endpoint',d=>{d.start=[];d.change=d.magnitude=null;}]) {
    const f=fixture();change(f.report.days[1]);assert.throws(()=>validate(f),/invalid_query_response/);
  }
});
test('nullable contract and irrelevant failed quantity checks retain readable source evidence', () => {
  const f=fixture();delete f.query.manifest.contract;f.request=buildMinuteHistoryRequest(f.query,f.selected,'14:57','15:00');f.report.contract=null;
  f.report.days[1].start[0].checks.push({name:'numeric.volume',outcome:'fail',reason:'integer_fraction'});validate(f);
  assert.match(text(render(MinuteHistoryResults,{report:f.report})),/integer_fraction/);
});
test('fetch rejects valid-looking but wrong context and result hashes and malformed JSON', async () => {
  let f=fixture();f.report.context_query_id='f'.repeat(64);seal(f.report);await assert.rejects(load(f),/invalid_query_response/);
  f=fixture();f.report.history_id='f'.repeat(64);await assert.rejects(load(f),/invalid_query_response/);
  f=fixture();f.report.days[1].start[0].source_label='changed';await assert.rejects(load(f),/invalid_query_response/);
  await assert.rejects(load(fixture(),'{'),/invalid_query_response/);
});
test('2 MiB streamed response ceiling rejects overflow without accepting a partial response', async () => {
  await assert.rejects(load(fixture(),' '.repeat(2*1024*1024+1)), error => {
    assert.equal(error.message, 'response_limit');
    assert.match(explainMinuteHistoryError(error), /2 MiB.*缩小显示源序号窗口无效.*仍须满足大小限制/);
    assert.notEqual(explainMinuteHistoryError(error), explain(error));
    return true;
  });
});
test('minute history server response-limit uses the same bounded recovery guidance', async () => {
  const f = fixture(), previous = globalThis.fetch;
  globalThis.fetch = async path => {
    assert.equal(path, f.request.path);
    return Response.json({ error: 'response_limit' }, { status: 400 });
  };
  try {
    await assert.rejects(loadMinuteHistory(f.request, new AbortController().signal), error => {
      assert.equal(error.message, 'response_limit');
      assert.equal(explainMinuteHistoryError(error), '历史同标签记录的响应超过 2 MiB 大小上限，缩小显示源序号窗口无效。可尝试较小来源数据版本；响应仍须满足大小限制。（response_limit）');
      return true;
    });
  } finally { globalThis.fetch = previous; }
});
test('minute history row-limit response explains the full-version budget without changing ordinary query guidance', async () => {
  const f = fixture(), previous = globalThis.fetch;
  globalThis.fetch = async path => {
    assert.equal(path, f.request.path);
    return Response.json({ error: 'query_row_limit' }, { status: 400 });
  };
  try {
    await assert.rejects(loadMinuteHistory(f.request, new AbortController().signal), error => {
      assert.equal(error.message, 'query_row_limit');
      assert.equal(explainMinuteHistoryError(error), '历史同标签记录需要整个数据版本的上下文，完整版本上限为 20,000 条。缩小显示源序号窗口无效，请改选不超过上限的较小来源数据版本。（query_row_limit）');
      assert.equal(explain(error), '当前选择超过 20,000 条上限，请缩小源序号窗口。（query_row_limit）');
      return true;
    });
  } finally { globalThis.fetch = previous; }
});
test('minute history keeps ordinary explanations and safe-code handling for every other error', () => {
  for (const error of [new Error('response_limit\n'), 'response_limit', { message: 'response_limit' }, new Error('invalid_query_response'), new Error('raw_object_corrupt'),
    new Error('unknown_safe_code'), new Error('/private/error.txt'), new Error('query_row_limit\n'),
    'query_row_limit', { message: 'query_row_limit' }, null]) {
    assert.equal(explainMinuteHistoryError(error), explain(error));
  }
});
test('request replacement, input edits, query switch and unmount invalidate both late success and failure', () => {
  const gate=new MinuteHistoryGate(),a=gate.begin('a');assert.equal(gate.isCurrent(a,'a'),true);
  const b=gate.begin('b');assert.equal(a.controller.signal.aborted,true);assert.equal(gate.isCurrent(a,'a'),false);assert.equal(gate.isCurrent(b,'c'),false);
  gate.cancel();assert.equal(b.controller.signal.aborted,true);assert.equal(gate.isCurrent(b,'b'),false);
  const c=gate.begin('b');assert.equal(gate.isCurrent(b,'b'),false);assert.equal(gate.isCurrent(c,'b'),true);gate.cancel();
  const source=readFileSync(new URL('../src/MinuteLabelHistory.tsx',import.meta.url),'utf8');
  assert.match(source,/key=\{minuteHistorySourceKey\(query, row\)\}/);assert.match(source,/useEffect\(\(\) => \(\) => gate.current.cancel\(\), \[\]\)/);
  assert.match(source,/function invalidate\(\).*gate.current.cancel\(\); setReport\(null\); setIssue\(''\); setLoading\(false\)/);
  assert.equal((source.match(/onChange=\{event => \{ invalidate\(\);/g)??[]).length,2);
  assert.ok(source.indexOf('if (!gate.current.isCurrent(token, latestKey.current)) return;')<source.indexOf('setReport({ key: request.key, value: result })'));
  assert.match(source,/catch \(error\) \{\s*if \(gate.current.isCurrent\(token, latestKey.current\)\) setIssue\(explainMinuteHistoryError\(error\)\);/);
  assert.match(source,/report\?\.key === key \? report.value : null/);
});
test('only noncompact 1m/5m details contain a closed drawer with empty explicit endpoint inputs', () => {
  for(const period of ['1m','5m']) {
    const f=fixture(period),html=render(RecordDetails,{row:f.selected,sourceQuery:f.query});assert.match(html,/<summary>历史同标签记录<\/summary>/);
    assert.doesNotMatch(html,/class="geometry-details minute-label-history" open/);
    assert.equal((html.match(/type="time" required="" step="60"[^>]*value=""/g)??[]).length,2);assert.match(html,/type="submit" disabled=""/);
    assert.doesNotMatch(render(RecordDetails,{row:f.selected,sourceQuery:f.query,compact:true}),/历史同标签记录/);
  }
  const f=fixture();f.query.metadata.period='1d';assert.doesNotMatch(render(RecordDetails,{row:f.selected,sourceQuery:f.query}),/历史同标签记录/);
  f.selected.label=null;assert.match(text(render(MinuteLabelHistory,{query:f.query,row:f.selected})),/缺少可用于此功能的规范日期标签/);
});
test('six-day SSR preserves labels, original closes, locators, signed fractions and expanded limits without scores', () => {
  const f=fixture(),html=render(MinuteHistoryResults,{report:f.report}),output=text(html);assert.equal((html.match(/同标签端点"/g)??[]).length,6);
  for(const expected of ['2026/10/09 14:57','2026-10-09T14:57','line:12','收盘 100','源序号 11','-1/10','1/10','名义时钟差 3 分钟',
    '未按分钟归一化','价格变化幅度（绝对值）','来源与不确定性','时区、柱边界','八位小数','完整上下文查询标识',f.report.raw_sha256]) assert.ok(output.includes(expected),expected);
  assert.doesNotMatch(output,/排名|百分位|胜率|评分|NaN|Infinity/);
});

test('fresh synthetic Store and in-process HTTP response passes actual frontend hash/DTO checks and SSR', async () => {
  const { fileURLToPath } = await import('node:url');
  const { resolve, join } = await import('node:path');
  const repo = resolve(fileURLToPath(new URL('../..', import.meta.url)));
  const python = join(repo, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const script = `
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_minute_label_history_api import synthetic_bundle, encoded
from anatrading.store import EvidenceStore
from anatrading.workbench import create_app
import httpx
root = Path(sys.argv[1]) / 'store'
with EvidenceStore(root) as store:
    sid = store.import_bytes(encoded(synthetic_bundle()), 'tdx-http-market-v1')['snapshot_id']
async def run():
    app = create_app(root)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://127.0.0.1:8765') as client:
            selection = dict(cutoff='2026-09-28T15:00', ordinal_start=16, ordinal_end=16, mode='retrospective')
            response = await client.get('/api/query/' + sid, params=selection)
            assert response.status_code == 200, response.text
            query = response.json()['query']
            response = await client.get('/api/minute-label-history/' + sid, params=dict(**selection,
                query_id=query['query_id'], source_date='2026-09-28', start_clock='14:57', end_clock='15:00'))
            assert response.status_code == 200, response.text
            print(json.dumps(dict(query=query, report=response.json())))
asyncio.run(run())
`;
  await withSyntheticBridge({ prefix: '045-ui-bridge-', command: python, args: ['-c', script], cwd: repo, maxBuffer: 4 * 1024 * 1024 }, async f => {
    f.request = buildMinuteHistoryRequest(f.query, f.query.rows[0], '14:57', '15:00');
    validate(f); const { result } = await load(f), output = text(render(MinuteHistoryResults, { report: result }));
    assert.equal(result.days.length, 6); assert.equal(result.days[0].start[0].tokens.close, '11.30');
    assert.equal(result.days[0].change.numerator, '-1'); assert.equal(result.days[0].change.denominator, '113');
    assert.match(output, /源序号 15/); assert.match(output, /-1\/113/); assert.match(output, /名义时钟差 3 分钟/);
  });
});

function rebind(f) { f.request = buildMinuteHistoryRequest(f.query, f.selected, '14:57', '15:00'); seal(f.report); return f; }
test('rehashing cannot hide a visible endpoint or reclassify its known date as unknown', async () => {
  for (const unknown of [false, true]) {
    const f = fixture(), day = f.report.days[0], ordinal = day.end[0].ordinal;
    day.end = []; day.reason = 'missing_endpoint'; day.change = day.magnitude = null;
    if (unknown) { f.report.unknown_date_ordinals = [ordinal]; f.report.window_status = 'unresolved_dates'; f.report.missing_history_dates = null; }
    seal(f.report); await assert.rejects(load(f), /invalid_query_response/);
  }
});
test('visible recent history dates cannot disappear even when a rehashed reply declares insufficient history', async () => {
  const f = fixture(); f.query.rows.unshift(f.report.days[1].start[0]);
  f.report.days.splice(1, 1); f.report.history_dates.shift(); f.report.window_status = 'insufficient'; f.report.missing_history_dates = 1;
  rebind(f); await assert.rejects(load(f), /invalid_query_response/);
});
test('visible unknown date/clock evidence must survive in the proper bucket; located rows cannot move to unknown clocks', async () => {
  const f = fixture(), unknown = row('2026-10-05', 'bad', 90, null); unknown.label = null; unknown.tokens.date = '20261005';
  f.query.unlocated.push(unknown); rebind(f); await assert.rejects(load(f), /invalid_query_response/);
  const day = f.report.days[2]; day.unknown_clock_ordinals = [90]; day.reason = 'endpoint_uniqueness_unknown'; day.change = day.magnitude = null;
  rebind(f); validate(f); await load(f);
  day.unknown_clock_ordinals = [12, 90]; rebind(f); await assert.rejects(load(f), /invalid_query_response/);
  const g = fixture(), undated = row('unreadable', 'bad', 91, null); undated.label = null; g.query.unlocated.push(undated);
  rebind(g); await assert.rejects(load(g), /invalid_query_response/);
  g.report.unknown_date_ordinals = [91]; g.report.window_status = 'unresolved_dates'; g.report.missing_history_dates = null;
  rebind(g); validate(g); await load(g);
});
test('partial ordinal views permit hidden endpoints, displaced older dates and reliable out-of-window bad rows', async () => {
  const f = fixture();
  // This visible date is genuinely earlier than every returned historical date.
  f.query.rows.unshift(row('2026-10-01', '15:00', 100, '1'));
  const older = row('2026-10-01', 'bad', 101, null), future = row('2026-10-10', 'bad', 102, null);
  older.label = future.label = null; older.checks = [{ name: 'source_code', outcome: 'fail' }];
  f.query.unlocated.push(older, future);
  // A later same-day observation also cannot disqualify arithmetic ending at 15:00.
  const later = row('2026-10-09', '15:01', 103, '0'); later.checks = [{ name: 'numeric.close', outcome: 'fail' }]; f.query.rows.push(later);
  rebind(f); validate(f); await load(f); assert.equal(f.report.days[0].start[0].ordinal, 11);
});
test('matching and rehashed endpoint/check metadata cannot grant qualified arithmetic to known disqualifications', async () => {
  const changes = [
    f => f.selected.checks.push({ name: 'numeric.close', outcome: 'fail' }),
    f => f.selected.checks.push({ name: 'structure', outcome: 'fail' }),
    f => { f.query.metadata.quarantined = f.report.metadata.quarantined = true; },
    f => { const check = { name: 'known_negative_sample', outcome: 'fail' }; f.query.batch_checks.push(check); f.report.batch_checks.push(check); },
    f => { const check = { name: 'price_scaling', outcome: 'fail' }; f.query.batch_checks.push(check); f.report.batch_checks.push(check); },
    f => { f.query.manifest.contract.price_scaling = f.report.contract.price_scaling = { status: 'conflict' }; },
    f => { f.selected.tokens.code = '000001.SZ'; f.query.metadata.source_code = f.report.metadata.source_code = '600000.SH'; },
    f => { f.selected.tokens.source_venue = 'SZ'; },
    f => { f.selected.tokens.adjustflag = '1'; f.query.metadata.source_adjustflag = f.report.metadata.source_adjustflag = '2'; },
    f => { f.report.days[0].start[0].tokens.price_scale = '1'; f.selected.tokens.price_scale = '100'; },
    f => { f.report.days[0].start[0].tokens.label_semantics = 'end'; f.report.days[1].start[0].tokens.label_semantics = 'start'; },
  ];
  for (const change of changes) { const f = fixture(); change(f); rebind(f); await assert.rejects(load(f), /invalid_query_response/); }
});
test('known disqualifications remain displayable when ratios are withheld, while equivalent identity aliases remain qualified', async () => {
  const f = fixture(); f.selected.checks.push({ name: 'numeric.close', outcome: 'fail' });
  f.report.days[0].reason = 'invalid_close'; f.report.days[0].change = f.report.days[0].magnitude = null;
  rebind(f); validate(f); await load(f);
  const g = fixture(); g.selected.tokens.code = 'SH.600059'; g.selected.tokens.source_code = '600059.XSHG';
  g.selected.tokens.venue = 'SSE'; g.selected.tokens.source_venue = 'XSHG'; rebind(g); validate(g); await load(g);
});
test('nonendpoint failures obey scope: known source conflicts reject, unrelated close and quantity failures do not', async () => {
  const f = fixture(), middle = row('2026-10-09', '14:58', 90, '0');
  middle.checks = [{ name: 'numeric.close', outcome: 'fail' }, { name: 'numeric.volume', outcome: 'fail' }];
  f.query.rows.push(middle); rebind(f); validate(f); await load(f);
  middle.checks.push({ name: 'source_label', outcome: 'fail' }); rebind(f); await assert.rejects(load(f), /invalid_query_response/);
});
