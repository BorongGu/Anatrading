import test from 'node:test';
import assert from 'node:assert/strict';
import { buildPlot, Generation, queryParameters, assertReply } from '../src/model.ts';
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
