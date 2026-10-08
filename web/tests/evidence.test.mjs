import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { entry, sourceRow } from './geometry-fixtures.mjs';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { SnapshotEvidence } = await server.ssrLoadModule('/src/App.tsx');
const { RecordDetails } = await server.ssrLoadModule('/src/RecordDetails.tsx');
// Synthetic contracts use the exact nested shape emitted by formats._source_semantics.
const snapshot = (fields, extra = {}) => ({ snapshot_id: 'synthetic', metadata: { instrument_id: null }, manifest: { contract: {
  source_semantics: { scope: 'all_records', fields }, standard_units: { status: 'unknown' },
  temporal_semantics: { status: 'unknown' }, ...extra,
} } });
const text = value => renderToStaticMarkup(createElement(SnapshotEvidence, { snapshot: value })).replace(/<[^>]+>/g, '');

test('Bao documented meaning, applicability and normalized units stay separate', () => {
  const result = text(snapshot({
    volume_unit: { value: 'shares', status: 'known', applicability: 'unverified' },
    amount_unit: { value: 'CNY', status: 'known', applicability: 'unverified' },
    adjustment: { value: '3', status: 'assumed' },
  }));
  assert.match(result, /数量定义\s*shares\s*· known/);
  assert.match(result, /金额定义\s*CNY\s*· known/);
  assert.match(result, /样本适用性\s*unverified/);
  assert.match(result, /规范单位\s*unknown/);
  assert.match(result, /复权口径\s*3\s*· assumed/);
});

test('day adjustment is unknown even when a metadata claim happens to exist', () => {
  const value = snapshot({
    volume_unit: { value: null, status: 'unknown' }, amount_unit: { value: null, status: 'unknown' },
    adjustment: { value: null, status: 'unknown' },
  }, { price_scaling: { value: 'raw_uint32/100', status: 'assumed' } });
  value.metadata.source_adjustment = 'irrelevant metadata claim';
  const result = text(value);
  assert.match(result, /复权口径\s*未注明\s*· unknown/);
  assert.doesNotMatch(result, /复权口径\s*未注明\s*· assumed/);
  assert.match(result, /原整数 ÷ 100/);
  assert.match(result, /单位未核实/);
});

test('absent source semantics retains explicit unknown values', () => {
  const result = text({ snapshot_id: 'synthetic', metadata: {}, manifest: {} });
  assert.match(result, /数量定义\s*未注明\s*· unknown/);
  assert.match(result, /金额定义\s*未注明\s*· unknown/);
  assert.match(result, /复权口径\s*未注明\s*· unknown/);
});

test('compact tooltip and fixed details show the same query contract qualifications', () => {
  const contract = snapshot({
    price_unit: { value: 'CNY', status: 'known', applicability: 'unverified' },
    volume_unit: { value: 'shares', status: 'known', applicability: 'unverified' },
    amount_unit: { value: 'CNY', status: 'known', applicability: 'unverified' },
  }).manifest.contract;
  const row = { ordinal: 1, label: '2021-01-04', locator: 'synthetic:1', tokens: {}, checks: [],
    values: { open: '1', high: '1', low: '1', close: '1', volume: '9007199254740993', amount: '2' } };
  for (const compact of [true, false]) {
    const result = renderToStaticMarkup(createElement(RecordDetails, { row, contract, compact })).replace(/<[^>]+>/g, '');
    assert.match(result, /价格定义\s*CNY\s*· known/);
    assert.match(result, /数量定义\s*shares\s*· known/);
    assert.match(result, /金额定义\s*CNY\s*· known/);
    assert.match(result, /样本适用性\s*unverified/);
    assert.match(result, /规范单位\s*unknown/);
    assert.ok(result.includes('9007199254740993'));
  }
});

test('fixed geometry details show backend strings, approximation and fractions; compact stays short', () => {
  const geometry = entry(1);
  geometry.body = '99999999999999999999.000000000000000001';
  geometry.ratios.body = { numerator: '1', denominator: '3', percent_display: '33.33' };
  const props = { row: sourceRow(1), geometry };
  const result = renderToStaticMarkup(createElement(RecordDetails, props)).replace(/<[^>]+>/g, '');
  assert.match(result, /单根源结构，未检验预测效力/);
  assert.ok(result.includes(geometry.body));
  assert.match(result, /≈33\.33%/);
  assert.match(result, /1\/3/);
  assert.match(result, /同根 OHLC 价格尺度相同/);
  assert.match(result, /规范单位\s*unknown/);
  const compact = renderToStaticMarkup(createElement(RecordDetails, { ...props, compact: true }));
  assert.doesNotMatch(compact, /单根源结构|33\.33%|权威分数/);
});
test('geometry states expose zero-range reason, invalid reason and unlocated limitation', () => {
  const geometry = entry(1);
  Object.assign(geometry, { direction: 'equal', range: '0', body: '0', upper_shadow: '0', lower_shadow: '0', ratios: { body: null, upper_shadow: null, lower_shadow: null, close_location: null }, ratio_reason: 'zero_range' });
  const render = () => renderToStaticMarkup(createElement(RecordDetails, { row: sourceRow(1, null), geometry })).replace(/<[^>]+>/g, '');
  assert.match(render(), /零区间.*比例未定义/);
  assert.match(render(), /无法定位.*时点指标/);
  Object.assign(geometry, { status: 'not_evaluated', reason: 'invalid_ohlc', direction: null, range: null, body: null, upper_shadow: null, lower_shadow: null, ratio_reason: null });
  assert.match(render(), /OHLC 边界不一致/);
  assert.doesNotMatch(render(), /≈0\.00%/);
});
