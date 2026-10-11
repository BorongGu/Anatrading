import test from 'node:test';
import assert from 'node:assert/strict';
import { assertHistoricalPathReply, buildHistoricalPathRequest, fetchHistoricalPath, formatPathPercent, HistoricalPathController, PATH_RESPONSE_LIMIT } from '../src/historical-path-model.ts';
import { historicalPathFixture, shown } from './historical-path-fixtures.mjs';

const badResponse = /invalid_path_match_response/;
test('strict mandatory cutoff and snapshot identity fail before any request', () => {
  const id = 'a'.repeat(64);
  for (const date of ['', '2025-2-01', '2025-02-29', '2026-02-30', '0000-01-01', '2025-01-01T00:00', null]) assert.throws(() => buildHistoricalPathRequest(id, date), /invalid_cutoff/);
  for (const snapshot of ['', 'A'.repeat(64), '../x', null]) assert.throws(() => buildHistoricalPathRequest(snapshot, '2025-01-01'), /invalid_snapshot_id/);
  const request = buildHistoricalPathRequest(id, '2024-02-29');
  assert.equal(request.path, `/api/research/path-match/${id}?cutoff=2024-02-29`);
});
test('full-prefix report identity is checked without imposing the unrelated chart query id', () => {
  const { reply, request } = historicalPathFixture(), before = structuredClone(reply);
  assertHistoricalPathReply(reply, request.expected); assert.deepEqual(reply, before);
  reply.inputs[0].query_id = 'f'.repeat(64); assertHistoricalPathReply(reply, request.expected);
});
test('short history without candidates and invalid slots retain honest empty selections and counts', () => {
  for (const [count, invalid] of [[21, []], [41, []], [42, [0]], [84, [0, 1, 2]]]) {
    const { reply, request } = historicalPathFixture(count, invalid); assertHistoricalPathReply(reply, request.expected);
  }
});
test('identity, method, cutoff, fixed rules and malformed payloads fail closed', () => {
  const mutations = [
    r => r.method_id = 'daily-causal-research-v1', r => r.mode = 'live', r => r.analysis_id = 'bad',
    r => r.inputs[0].snapshot_id = 'c'.repeat(64), r => r.inputs[0].query_id = 'bad', r => r.inputs.push(r.inputs[0]),
    r => r.parameters.cutoff = '2025-03-24', r => r.result.cutoff = '2025-03-24', r => r.parameters.model.steps = 19,
    r => r.result.parameters.max_matches = 4, r => r.result.parameters.metric = 'correlation', r => r.result.parameters.extra = true,
    r => r.parameters.future = true, r => r.limitations = [], r => r.extra = true, r => r.result.extra = { x: Infinity },
    r => r.result.groups.push('2025-03-26'), r => r.result.groups[1] = r.result.groups[0], r => r.result.groups[0] = '2025-02-30',
    r => r.result.identity.symbol = '', r => r.result.windows.push(r.result.windows[0]),
  ];
  for (const mutate of mutations) { const { reply, request } = historicalPathFixture(); mutate(reply); assert.throws(() => assertHistoricalPathReply(reply, request.expected), badResponse); }
});
test('window dates, original price domain, exact21 points and source-step links are validated', () => {
  const mutations = [
    w => w.start_date = '2025-01-02', w => w.end_index = 19, w => w.calendar_days = 19,
    w => w.prices[0] = '0', w => w.prices[0] = '-1', w => w.prices[0] = '1e21', w => w.prices[0] = '1.0000000000000000001',
    w => w.prices[0] = '100000000000000000000', w => w.prices.pop(), w => w.ordinals[0] = null, w => w.ordinals[0] = w.ordinals[1],
    w => w.relative_path[0] = shown(1), w => w.relative_path[5] = 'NaN', w => w.relative_path.pop(), w => w.endpoint_change = shown(.01),
    w => w.max_drawdown.value = shown(-.1), w => w.max_drawdown.peak_step = 21, w => w.max_drawdown.trough_step = -1,
    w => w.max_point_difference.step = 21, w => w.distance = shown(-1), w => w.differences[0] = shown(.1),
  ];
  for (const mutate of mutations) { const { reply, request } = historicalPathFixture(); mutate(reply.result.windows[0]); assert.throws(() => assertHistoricalPathReply(reply, request.expected), badResponse); }
});
test('candidate eligibility, each method nonoverlap, ledger references and count conservation are bound', () => {
  const mutations = [
    r => r.result.selections.path.push(63), r => r.result.selections.path = [0, 0], r => r.result.selections.path = [0, 1],
    r => r.result.counts.path.total++, r => r.result.counts.endpoint.selected--,
    r => r.result.ledger.pop(), r => r.result.ledger[1][0] = 0, r => r.result.ledger[1][4] = [null, 42],
    r => r.result.ledger[0][4] = [2, null], r => r.result.ledger[0][2] = shown(.4), r => r.result.ledger_columns.reverse(),
    r => r.result.query.distance = shown(.01), r => r.result.query.differences[1] = shown(.1),
  ];
  for (const mutate of mutations) { const { reply, request } = historicalPathFixture(); mutate(reply); assert.throws(() => assertHistoricalPathReply(reply, request.expected), badResponse); }
  const { reply, request } = historicalPathFixture(42, [0]); reply.result.ledger[0][7] = 21;
  assert.throws(() => assertHistoricalPathReply(reply, request.expected), badResponse);
});
test('percentage display shifts decimal strings without additional floating point rounding', () => {
  assert.equal(formatPathPercent('0E+0'), '0%');
  assert.equal(formatPathPercent('5E-1'), '50%');
  assert.equal(formatPathPercent('1.25E-2'), '1.25%');
  assert.equal(formatPathPercent('1.23456789012e-02'), '1.23456789012%');
  assert.equal(formatPathPercent('1.23456789012e-03'), '0.123456789012%');
  assert.equal(formatPathPercent('0.00000000000e+11'), '0%');
  assert.equal(formatPathPercent('-2.00000000000e-01'), '−20%');
  assert.equal(formatPathPercent('1.23456789012e+37'), '1.23456789012e+39%');
  for (const value of ['NaN', '', null, '1.23']) assert.equal(formatPathPercent(value), '—');
});
test('loader uses same-origin readonly no-cache request and validates the returned contract', async () => {
  const { reply, request } = historicalPathFixture(), calls = [], signal = new AbortController().signal;
  const result = await fetchHistoricalPath(request, signal, async (url, options) => { calls.push([url, options]); return Response.json(reply); });
  assert.deepEqual(result, reply); assert.equal(calls.length, 1);
  assert.deepEqual(calls[0], [request.path, { method: 'GET', signal, cache: 'no-store', credentials: 'same-origin' }]);
  await assert.rejects(fetchHistoricalPath(request, signal, async () => Response.json({ error: 'raw_object_corrupt' }, { status: 409 })), /raw_object_corrupt/);
  await assert.rejects(fetchHistoricalPath(request, signal, async () => Response.json({ error: '/private/data.txt' }, { status: 400 })), badResponse);
});
test('streamed response cap applies before parsing success and error bodies', async () => {
  const { request } = historicalPathFixture(), signal = new AbortController().signal;
  for (const status of [200, 500]) {
    let cancelled = false;
    const stream = new ReadableStream({ start(controller) { controller.enqueue(new Uint8Array(PATH_RESPONSE_LIMIT)); controller.enqueue(new Uint8Array(1)); }, cancel() { cancelled = true; } });
    await assert.rejects(fetchHistoricalPath(request, signal, async () => new Response(stream, { status })), /path_match_response_limit/);
    assert.equal(cancelled, true);
  }
});
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b; }); return { promise, resolve, reject }; };
test('actual controller clears results and selection on rerun, date/source changes and explicit cancellation', async () => {
  const { reply, request } = historicalPathFixture(), updates = [], c = new HistoricalPathController(s => updates.push(s));
  const load = async () => reply;
  await c.run(request.expected.snapshotId, request.expected.cutoff, load); c.select(0);
  assert.equal(c.state.selected, 0); c.select(null, true); assert.equal(c.state.rejected, true); c.select(21); assert.equal(c.state.rejected, false);
  c.select(200); assert.equal(c.state.selected, 21);
  c.invalidate(); assert.equal(c.state.report, null); assert.equal(c.state.selected, null); assert.equal(c.state.rejected, false);
  await c.run(request.expected.snapshotId, request.expected.cutoff, load); c.select(0);
  const late = deferred(); let signal;
  const pending = c.run(request.expected.snapshotId, request.expected.cutoff, async (_request, s) => { signal = s; return late.promise; });
  assert.equal(c.state.status, 'loading'); assert.equal(c.state.report, null); assert.equal(c.state.selected, null);
  c.cancel(); assert.equal(signal.aborted, true); late.resolve(reply); await pending;
  assert.equal(c.state.status, 'cancelled'); assert.equal(c.state.report, null); c.dispose();
});
for (const finish of ['resolve', 'reject']) test(`superseding request ignores stale ${finish} even when transport ignores abort`, async () => {
  const { reply, request } = historicalPathFixture(), c = new HistoricalPathController(() => {}), older = deferred(); let oldSignal;
  const pending = c.run(request.expected.snapshotId, request.expected.cutoff, async (_r, s) => { oldSignal = s; return older.promise; });
  await c.run(request.expected.snapshotId, request.expected.cutoff, async () => reply);
  assert.equal(oldSignal.aborted, true); c.select(21);
  older[finish](finish === 'resolve' ? reply : new Error('raw_object_corrupt')); await pending;
  assert.equal(c.state.status, 'ready'); assert.equal(c.state.selected, 21); assert.equal(c.state.report, reply); c.dispose();
});
test('invalid draft, load failure, no candidates and disposal never retain a previous candidate', async () => {
  const { reply, request } = historicalPathFixture(), c = new HistoricalPathController(() => {});
  await c.run(request.expected.snapshotId, request.expected.cutoff, async () => reply); c.select(0);
  let calls = 0; await c.run(request.expected.snapshotId, '', async () => { calls++; return reply; });
  assert.equal(calls, 0); assert.equal(c.state.status, 'error'); assert.equal(c.state.report, null); assert.equal(c.state.selected, null);
  await c.run(request.expected.snapshotId, request.expected.cutoff, async () => { throw new Error('raw_object_missing'); });
  assert.equal(c.state.status, 'error'); assert.equal(c.state.report, null);
  await c.run(request.expected.snapshotId, request.expected.cutoff, async () => historicalPathFixture(21).reply);
  c.select(0); assert.equal(c.state.selected, null);
  const late = deferred(), pending = c.run(request.expected.snapshotId, request.expected.cutoff, () => late.promise);
  c.dispose(); late.resolve(reply); await pending; assert.equal(c.state.report, null);
});

test('exact source exponent and insignificant trailing zeroes stay intact without float coercion', () => {
  for (const price of ['1E-18', '1.0000000000000000000', '10000000000000000000', '9.9999999999999999999999999999999999999E19']) {
    const { reply, request } = historicalPathFixture(); reply.result.windows[0].prices[0] = price;
    assertHistoricalPathReply(reply, request.expected); assert.equal(reply.result.windows[0].prices[0], price);
  }
});
