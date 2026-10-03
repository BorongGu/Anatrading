import test from 'node:test';
import assert from 'node:assert/strict';
import { safeCode, explain, checkedFetch, verifiedExportBlob } from '../src/api.ts';

const bytes = '{"amount":"9007199254740993.000000000000000001","missing":null,"zero":"0"}';
async function exportResponse(queryId = 'current', hashOverride) {
  const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(bytes)))].map(x => x.toString(16).padStart(2, '0')).join('');
  return new Response(bytes, { headers: { 'X-Query-Id': queryId, 'X-Content-SHA256': hashOverride ?? hash } });
}
test('export validates identity and bytes without numeric reconstruction', async () => {
  const result = await verifiedExportBlob(await exportResponse(), 'current');
  assert.equal(await result.blob.text(), bytes);
  assert.match(result.digest, /^[a-f0-9]{64}$/);
});
test('mismatched Q or content hash blocks export', async () => {
  await assert.rejects(verifiedExportBlob(await exportResponse('old'), 'current'), /invalid_export_response/);
  await assert.rejects(verifiedExportBlob(await exportResponse('current', '0'.repeat(64)), 'current'), /invalid_export_response/);
});
test('errors retain only a bounded safe code', async () => {
  assert.equal(safeCode(new Error('<private raw payload>')), 'connection_error');
  assert.equal(safeCode(new Error('raw_object_corrupt')), 'raw_object_corrupt');
  const originalFetch = globalThis.fetch;
  let observedOptions;
  globalThis.fetch = async (_url, options) => {
    observedOptions = options;
    return new Response('{"error":"private raw payload"}', { status: 400 });
  };
  try {
    await assert.rejects(checkedFetch('/api/query/x'), error => error.message === 'invalid_response');
    assert.equal(observedOptions.cache, 'no-store');
    assert.equal(observedOptions.credentials, 'same-origin');
  } finally { globalThis.fetch = originalFetch; }
});

test('actual backend failure codes have actionable Chinese reasons', () => {
  for (const [code, expected] of [
    ['raw_object_corrupt', '原件哈希'], ['raw_object_missing', '原件缺失'],
    ['upload_in_progress', '已有文件'], ['invalid_label_cutoff', '截止标签'],
    ['query_row_limit', '20,000'], ['service_busy', '请求队列'],
  ]) assert.ok(explain(new Error(code)).includes(expected), code);
});
