import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';

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
