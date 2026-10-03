import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
after(() => server.close());
const { recordStatusMarkers } = await server.ssrLoadModule('/src/SourceChart.tsx');

test('zero plus duplicate uses one visible text label, distinct from missing quantity', () => {
  const marks = recordStatusMarkers([
    [], [], ['数量为零', '重复标签', '质量检查未通过'], ['数量缺失或不可绘制', '重复标签'],
  ]);
  assert.deepEqual(marks.map(({ time, text }) => ({ time, text })), [{ time: 2, text: '0 !' }, { time: 3, text: '∅ !' }]);
  assert.equal(new Set(marks.map(marker => marker.time)).size, marks.length);
  assert.ok(marks.every(marker => marker.position === 'aboveBar'));
});

test('zero-only, nonzero problems and clean records retain distinct status labels', () => {
  const marks = recordStatusMarkers([['数量为零'], ['OHLC 不可绘制'], [], ['质量检查未通过']]);
  assert.deepEqual(marks.map(marker => [marker.time, marker.text]), [[0, '0'], [1, '!'], [3, '!']]);
  assert.equal(marks[0].shape, 'circle');
  assert.equal(marks[1].shape, 'square');
  assert.ok(marks.every(marker => !('price' in marker)));
});
