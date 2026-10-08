import test from 'node:test';
import assert from 'node:assert/strict';
import { assertGeometryEnvelope, assertReply } from '../src/model.ts';
import { verifiedGeometryExportBlob } from '../src/api.ts';
import { envelope, draft, queryId, geometryId, ratio } from './geometry-fixtures.mjs';

const rejects = change => { const value = envelope(); change(value); assert.throws(() => assertGeometryEnvelope(value, draft, 20000), /invalid_query_response/); };
test('two source scopes and exact geometry strings validate without reconstruction', () => {
  const value = envelope();
  value.geometry.rows[0].ratios.body = ratio('1', '3', '33.33');
  const bytes = JSON.stringify(value);
  assert.doesNotThrow(() => assertGeometryEnvelope(value, draft, 2));
  assert.equal(JSON.stringify(value), bytes);
});
test('identity, method, qualification, policy and fixed keys fail closed', () => {
  for (const change of [
    v => v.query.query_id = 'q', v => v.geometry.geometry_id = 'B'.repeat(64),
    v => v.geometry.query_id = 'c'.repeat(64), v => v.geometry.method_id = 'other',
    v => v.geometry.source_qualification = 'verified', v => v.geometry.qualification = 'signal',
    v => v.geometry.assumption = 'known_units', v => v.geometry.display_policy.rounding = 'up',
    v => v.geometry.display_policy.extra = true, v => v.geometry.extra = true,
    v => v.geometry.rows[0].extra = true, v => delete v.geometry.rows[0].reason,
  ]) rejects(change);
});
test('both scopes enforce order, count, positive unique safe ordinals, source labels and six value types', () => {
  for (const change of [
    v => v.geometry.unlocated = [], v => v.geometry.rows[0].ordinal = 2,
    v => v.query.unlocated[0].ordinal = 1, v => v.query.rows[0].ordinal = 0,
    v => v.query.rows[0].ordinal = Number.MAX_SAFE_INTEGER + 1,
    v => v.query.rows[0].label = '', v => v.query.unlocated[0].label = 'located',
    v => v.query.unlocated[0].values.amount = 1, v => delete v.query.rows[0].values.low,
    v => v.query.counts.selected_rows = 2, v => v.query.selection.cutoff = '2026-01-01',
    v => v.query.selection.snapshot_id = 'other',
  ]) rejects(change);
  assert.throws(() => assertGeometryEnvelope(envelope(), draft, 1));
});
test('computed, zero range and not evaluated states reject inconsistent null combinations', () => {
  const value = envelope(); const g = value.geometry.rows[0];
  Object.assign(g, { direction: 'equal', range: '0', body: '0', upper_shadow: '0', lower_shadow: '0', ratios: { body: null, upper_shadow: null, lower_shadow: null, close_location: null }, ratio_reason: 'zero_range' });
  assert.doesNotThrow(() => assertGeometryEnvelope(value, draft, 2));
  g.body = '1'; assert.throws(() => assertGeometryEnvelope(value, draft, 2));
  Object.assign(g, { status: 'not_evaluated', reason: 'missing_ohlc', direction: null, range: null, body: null, upper_shadow: null, lower_shadow: null, ratio_reason: null });
  assert.doesNotThrow(() => assertGeometryEnvelope(value, draft, 2));
  g.reason = 'unrecognized'; assert.throws(() => assertGeometryEnvelope(value, draft, 2));
  for (const change of [v => v.geometry.rows[0].reason = 'missing_ohlc', v => v.geometry.rows[0].direction = 'unknown', v => v.geometry.rows[0].ratios.body = null, v => v.geometry.rows[0].ratio_reason = 'zero_range']) rejects(change);
});
test('lengths and ratios require canonical bounded strings and percentage displays', () => {
  for (const length of ['-1', '01', '1.0', '0.10', '1e-18', '1'.repeat(21), '0.' + '1'.repeat(19), 1, null]) rejects(v => v.geometry.rows[0].body = length);
  for (const r of [ratio('01'), ratio('-1'), ratio('0', '2', '0.00'), ratio('1', '0'), ratio('1', '01'), ratio('1'.repeat(39)), ratio('1', '1', '100.01'), ratio('1', '1', '01.00'), ratio('1', '1', '33.3'), { ...ratio(), extra: true }]) rejects(v => v.geometry.rows[0].ratios.body = r);
  const value = envelope(); value.geometry.rows[0].body = '99999999999999999999.000000000000000001';
  assert.doesNotThrow(() => assertGeometryEnvelope(value, draft, 2));
});
test('GET replies require the shared geometry validator before publishing a chart', () => {
  const value = { ...envelope(), display: [{ ordinal: 1, direction: 'up', ohlc_drawable: true, precision_lost: false }], navigation: {} };
  assert.doesNotThrow(() => assertReply(value, draft, 2));
  value.geometry.unlocated[0].ordinal = 1;
  assert.throws(() => assertReply(value, draft, 2));
});
async function response(value, header = geometryId) {
  const bytes = typeof value === 'string' ? value : JSON.stringify(value);
  const digest = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(bytes)))].map(b => b.toString(16).padStart(2, '0')).join('');
  return { bytes, response: new Response(bytes, { headers: { 'X-Query-Id': queryId, 'X-Geometry-Id': header, 'X-Content-SHA256': digest } }) };
}
test('derived export validates SHA and complete body, then returns original bytes', async () => {
  const value = envelope(); const r = await response(value);
  const result = await verifiedGeometryExportBlob(r.response, queryId, geometryId, draft, 2);
  assert.equal(await result.blob.text(), r.bytes);
  for (const change of [v => v.geometry.unlocated[0].ordinal = 1, v => v.geometry.geometry_id = 'c'.repeat(64), v => v.query.query_id = 'c'.repeat(64), v => v.extra = true]) {
    const altered = envelope(); change(altered);
    await assert.rejects(verifiedGeometryExportBlob((await response(altered)).response, queryId, geometryId, draft, 2), /invalid_export_response/);
  }
  await assert.rejects(verifiedGeometryExportBlob((await response(value, 'old')).response, queryId, geometryId, draft, 2), /invalid_export_response/);
  await assert.rejects(verifiedGeometryExportBlob((await response('')).response, queryId, geometryId, draft, 2), /invalid_export_response/);
});
