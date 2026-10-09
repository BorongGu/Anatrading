import test from 'node:test';
import assert from 'node:assert/strict';
import { minuteReadNotice } from '../src/model.ts';

const query = (end = '20261009150000') => ({
  metadata: { source_end_time: end }, rows: [{ label: '2026-09-30T15:00' }, { label: '2026-09-30T09:31' }],
  unlocated: [],
});

test('saved older minutes show actual range and unmet requested date', () => {
  const text = minuteReadNotice(query());
  assert.match(text, /2026-09-30T09:31～2026-09-30T15:00/);
  assert.match(text, /请求截止日期 2026-10-09/);
  assert.match(text, /可定位记录未出现该日期/);
});

test('target date observed does not claim download, closure or complete coverage', () => {
  const text = minuteReadNotice(query('20260930150000'));
  assert.match(text, /已出现该日期/);
  assert.match(text, /完整性与闭合未核/);
});

test('blank latest request, unlocated labels and empty results remain explicit', () => {
  const q = query('');
  q.unlocated = [{ label: null }];
  assert.match(minuteReadNotice(q), /标签无法定位 1条/);
  assert.match(minuteReadNotice(q), /最新交易日覆盖未核/);
  q.rows = [];
  assert.match(minuteReadNotice(q), /没有可定位分钟标签/);
});

test('records after the requested date remain visible as a range problem', () => {
  assert.match(minuteReadNotice(query('20260928150000')), /包含请求日期之后的标签/);
});
