import test from 'node:test';
import assert from 'node:assert/strict';
import { pairHistoryPage, pairHistoryIdentity } from '../src/pair-history.ts';

for (const n of [0, 1, 49, 50, 51, 100, 101, 20000]) test(`pair history keeps every ordered row, n=${n}`, () => {
  const series = Array.from({ length: n }, (_, i) => Object.freeze({ date: String(i), return_correlation: i % 2 ? null : 0, reason: i % 2 ? 'history_insufficient' : null }));
  Object.freeze(series);
  const seen = [];
  for (let p = 0; p < Math.max(1, Math.ceil(n / 50)); p++) {
    const result = pairHistoryPage(series, p);
    assert.equal(result.total, n); assert.equal(result.page, p); assert.ok(result.rows.length <= 50);
    seen.push(...result.rows);
  }
  assert.deepEqual(seen, [...series].reverse());
  assert.equal(pairHistoryPage(series, -1).page, 0);
  assert.equal(pairHistoryPage(series, Infinity).page, Math.max(0, Math.ceil(n / 50) - 1));
});
test('a page reads at most 50 rows and observes current objects without caching', () => {
  let reads = 0;
  const rows = new Proxy(Array.from({ length: 20000 }, (_, i) => ({ date: String(i) })), { get(target, key, receiver) { if (/^\d+$/.test(String(key))) reads++; return Reflect.get(target, key, receiver); } });
  assert.equal(pairHistoryPage(rows, 2).rows[0].date, '19899'); assert.equal(reads, 50);
  rows[19899].date = 'updated'; assert.equal(pairHistoryPage(rows, 2).rows[0].date, 'updated');
  rows.length = 1; assert.equal(pairHistoryPage(rows, 399).page, 0);
});
test('small identity includes ordered roles, query, method, analysis and parameters', () => {
  const report = { method_id: 'pair', analysis_id: 'a', inputs: [{snapshot_id:'A',query_id:'qa'},{snapshot_id:'B',query_id:'qb'}], parameters: {cutoff:'2026-01-01',lookback:20}, result: {series:[]} };
  const original = pairHistoryIdentity(report,20);
  for (const mutate of [r=>r.method_id='other',r=>r.analysis_id='b',r=>r.inputs.reverse(),r=>r.inputs[0].snapshot_id='C',r=>r.inputs[0].query_id='qc',r=>r.parameters.cutoff='2026-01-02',r=>r.parameters.lookback=21]) {
    const copy=structuredClone(report);mutate(copy);assert.notEqual(pairHistoryIdentity(copy,20),original);
  }
  assert.notEqual(pairHistoryIdentity(report,21),original);
  report.result.series.push({date:'anything'});assert.equal(pairHistoryIdentity(report,20),original);
});
