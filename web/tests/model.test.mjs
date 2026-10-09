import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPlot, buildChannelPlot, Generation, queryParameters, assertReply } from '../src/model.ts';
import { geometry, queryId } from './geometry-fixtures.mjs';

// Artificial records prove UI boundaries only; they are not market evidence.
const row = (ordinal, label, values = {}) => ({
  ordinal, label, source_label: label, locator: `synthetic:${ordinal}`,
  tokens: {}, values: { open: '1', high: '2', low: '1', close: '2', volume: '3', amount: '6', ...values },
  checks: [], volume_shares: null, amount_cny: null,
});
const display = (ordinal, extra = {}) => ({ ordinal, direction: 'up', ohlc_drawable: true, precision_lost: false, ...extra });
const reply = (rows, displays) => ({
  query: { snapshot_id: 's', query_id: queryId, rows, unlocated: [], manifest: { qualification: 'source_evidence_retrospective_only' },
    selection: { snapshot_id: 's', cutoff: null, ordinal_start: null, ordinal_end: null, mode: 'retrospective' },
    counts: { selected_rows: rows.length, unlocated_rows: 0 } },
  geometry: geometry(rows), display: displays, navigation: { previous_label: null, next_label: null },
});

const channelRow = (ordinal, upper = '13', lower = '8', reason = null) => ({ ordinal, upper, lower, width: upper === lower ? '0' : '5', reason });
const channelQuery = rows => ({ query_id: queryId, metadata: { period: '1d' }, rows });
const channelReport = rows => ({ query_id: queryId, lookback: 20, rows });

test('channel overlay uses source sequence positions and splits across unavailable bounds', () => {
  const q = channelQuery([row(7, 'A'), row(8, 'B'), row(9, 'B'), row(10, 'D'), row(11, 'E')]);
  const report = channelReport([channelRow(7), channelRow(8, null, null, 'history_insufficient'), channelRow(9), channelRow(10), channelRow(11)]);
  const frozen = JSON.stringify(report);
  const plot = buildChannelPlot(q, report);
  assert.equal(plot.skipped, 1);
  assert.deepEqual(plot.segments.map(segment => segment.upper), [[{ time: 0, value: 13 }], [{ time: 2, value: 13 }, { time: 3, value: 13 }, { time: 4, value: 13 }]]);
  assert.deepEqual(plot.segments.map(segment => segment.lower.map(point => point.time)), [[0], [2, 3, 4]]);
  assert.equal(JSON.stringify(report), frozen);
});

test('stale query, wrong period and mismatched source ordinals cannot overlay', () => {
  const q = channelQuery([row(1, 'A')]);
  const report = channelReport([channelRow(1)]);
  assert.equal(buildChannelPlot(q, null), null);
  assert.equal(buildChannelPlot({ ...q, query_id: 'stale' }, report), null);
  assert.equal(buildChannelPlot({ ...q, metadata: { period: '1m' } }, report), null);
  assert.equal(buildChannelPlot(q, channelReport([channelRow(2)])), null);
  assert.equal(buildChannelPlot(q, channelReport([])), null);
});

test('channel invalid coordinates and collapsed unequal bounds stay undrawn; true zero width remains valid', () => {
  const q = channelQuery([row(1, 'A'), row(2, 'B'), row(3, 'C'), row(4, 'D')]);
  const report = channelReport([channelRow(1, 'Infinity'), channelRow(2, 'bad'),
    channelRow(3, '99999999999999999999.999999999999999999', '99999999999999999999.999999999999999998'), channelRow(4, '0', '0')]);
  const plot = buildChannelPlot(q, report);
  assert.equal(plot.skipped, 3);
  assert.deepEqual(plot.segments, [{ upper: [{ time: 3, value: 0 }], lower: [{ time: 3, value: 0 }] }]);
});

test('duplicate labels retain independent sequence positions and exact strings', () => {
  const rows = [row(1, '2021-01-04', { volume: '9007199254740993' }), row(2, '2021-01-04')];
  const frozen = JSON.stringify(rows);
  const plot = buildPlot(rows, [display(1), display(2)]);
  assert.deepEqual(plot.candles.map(x => x.time), [0, 1]);
  assert.deepEqual(plot.labels, ['2021-01-04', '2021-01-04']);
  assert.ok(plot.status.every(x => x.includes('重复标签')));
  assert.equal(JSON.stringify(rows), frozen);
  assert.equal(rows[0].values.volume, '9007199254740993');
});

test('bad OHLC remains whitespace at its actual position; independent quantity is retained', () => {
  const plot = buildPlot([row(1, 'A'), row(2, 'B')], [display(1, { ohlc_drawable: false }), display(2)]);
  assert.deepEqual(plot.candles[0], { time: 0 });
  assert.equal(plot.volumes[0].value, 3);
  assert.equal(plot.candles[1].time, 1);
});

test('float collision never becomes a normal candle; precise direction remains backend-owned', () => {
  const r = row(1, 'A', { open: '9007199254740992', close: '9007199254740993' });
  const plot = buildPlot([r], [display(1, { precision_lost: true, direction: 'down' })]);
  assert.deepEqual(plot.candles[0], { time: 0 });
  assert.ok(plot.status[0].includes('显示分辨率不足'));
  assert.equal(plot.volumes[0].color, '#16836d');
});

test('zero and null quantity have distinct geometry and status', () => {
  const plot = buildPlot([row(1, 'A', { volume: '0' }), row(2, 'B', { volume: null })], [display(1), display(2)]);
  assert.equal(plot.volumes[0].value, 0);
  assert.deepEqual(plot.volumes[1], { time: 1 });
  assert.ok(plot.status[0].includes('数量为零'));
  assert.ok(plot.status[1].includes('数量缺失或不可绘制'));
});

test('nonfinite coordinates fail closed; no fabricated normal candle', () => {
  const plot = buildPlot([row(1, 'A', { close: 'Infinity', volume: 'NaN' })], [display(1)]);
  assert.deepEqual(plot.candles[0], { time: 0 });
  assert.deepEqual(plot.volumes[0], { time: 0 });
});

test('generation rejects stale success, stale failure and A-B-A reuse', () => {
  const gate = new Generation();
  const firstA = gate.invalidate();
  gate.invalidate();
  const latestA = gate.invalidate();
  assert.equal(gate.isCurrent(firstA), false);
  assert.equal(gate.isCurrent(latestA), true);
  gate.invalidate(); // latest request or export failed and cleared the view
  assert.equal(gate.isCurrent(latestA), false);
  assert.equal(gate.isCurrent(firstA), false);
});

test('source cutoff stays a string, ordinal bounds are inclusive and explicit', () => {
  const p = queryParameters({ snapshot: 's', cutoff: '2020-12-15T14:08', start: '1', end: '20000' }, 20001, 20000);
  assert.equal(p.get('cutoff'), '2020-12-15T14:08');
  assert.equal(p.get('ordinal_start'), '1');
  assert.equal(p.get('ordinal_end'), '20000');
});

test('oversized batch requires bounded selection, rejects inverted/oversized/noninteger windows', () => {
  const base = { snapshot: 's', cutoff: '', start: '', end: '' };
  for (const draft of [base, { ...base, start: '1' }, { ...base, start: '2', end: '1' },
    { ...base, start: '1', end: '20001' }, { ...base, start: '1.5', end: '3' }, { ...base, start: '-1', end: '2' }]) {
    assert.throws(() => queryParameters(draft, 20001, 20000));
  }
});

test('aligned response accepted; mismatched display identity or count is rejected', () => {
  const r = reply([row(1, 'A')], [display(1)]);
  assert.doesNotThrow(() => assertReply(r, { snapshot: 's', cutoff: '', start: '', end: '' }, 20000));
  r.display[0].ordinal = 2;
  assert.throws(() => assertReply(r, { snapshot: 's', cutoff: '', start: '', end: '' }, 20000));
});

test('selected plus unlocated budget is checked, including an empty located result', () => {
  const r = reply([], []);
  r.query.unlocated = [row(1, null), row(2, null)];
  r.query.counts.unlocated_rows = 2;
  r.geometry.unlocated = geometry(r.query.unlocated).rows;
  assert.throws(() => assertReply(r, { snapshot: 's', cutoff: '', start: '', end: '' }, 1));
  assert.doesNotThrow(() => assertReply(r, { snapshot: 's', cutoff: '', start: '', end: '' }, 2));
});

test('response for a different cutoff or snapshot cannot publish', () => {
  const r = reply([row(1, 'A')], [display(1)]);
  assert.throws(() => assertReply(r, { snapshot: 'other', cutoff: '', start: '', end: '' }, 20000));
  assert.throws(() => assertReply(r, { snapshot: 's', cutoff: '2021-01-01', start: '', end: '' }, 20000));
});
