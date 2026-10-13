import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { gunzipSync } from 'node:zlib';
import { test } from 'node:test';
import { CAP, precompress } from '../scripts/precompress.mjs';

const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
async function fixture(t) {
  const root = await mkdtemp(join(tmpdir(), 'anatrading-static-'));
  t.after(() => rm(root, { recursive: true, force: true }));
  await mkdir(join(root, 'assets'));
  return root;
}

test('packaging produces deterministic bound representations and complete sorted manifest', async (t) => {
  const root = await fixture(t);
  const sources = new Map([
    ['assets/z-12345678.js', Buffer.from('const synthetic = 1;\n'.repeat(100))],
    ['assets/a-12345678.css', Buffer.from('.synthetic{color:red}\n'.repeat(100))],
  ]);
  for (const [name, value] of sources) await writeFile(join(root, name), value);
  await writeFile(join(root, 'index.html'), '<title>unencoded</title>');
  const summary = await precompress(root);
  const first = await readFile(join(root, '.static-encodings.json'));
  const manifest = JSON.parse(first);
  assert.equal(summary.assets, 2);
  assert.deepEqual(manifest.assets.map(x => x.identity_path), [...sources.keys()].sort());
  const encoded = [];
  for (const entry of manifest.assets) {
    const source = sources.get(entry.identity_path);
    const gzip = await readFile(join(root, entry.gzip_path));
    encoded.push(gzip);
    assert.deepEqual(gunzipSync(gzip), source);
    assert.equal(entry.identity_sha256, hash(source));
    assert.equal(entry.gzip_sha256, hash(gzip));
    assert.equal(entry.identity_bytes, source.length);
    assert.equal(entry.gzip_bytes, gzip.length);
    assert.equal(entry.cap, CAP);
    assert.ok(gzip.length < source.length);
  }
  await precompress(root);
  assert.deepEqual(await readFile(join(root, '.static-encodings.json')), first);
  for (const [i, entry] of manifest.assets.entries()) assert.deepEqual(await readFile(join(root, entry.gzip_path)), encoded[i]);
});

test('oversized generated source fails packaging rather than silently omitting asset', async (t) => {
  const root = await fixture(t);
  await writeFile(join(root, 'assets/large-12345678.js'), Buffer.alloc(CAP + 1));
  await assert.rejects(precompress(root), /invalid_generated_asset_size_or_type/);
  await assert.rejects(readFile(join(root, '.static-encodings.json')), { code: 'ENOENT' });
});

test('nonhashed generated JS and nonregular target fail packaging', async (t) => {
  const root = await fixture(t);
  await writeFile(join(root, 'assets/plain.js'), 'synthetic');
  await assert.rejects(precompress(root), /invalid_generated_asset_name/);
  await rm(join(root, 'assets/plain.js'));
  await mkdir(join(root, 'assets/nonregular-12345678.js'));
  await assert.rejects(precompress(root), /invalid_generated_asset_size_or_type/);
});

test('build rejects symlink parents, outputs and manifest without writing through them', async (t) => {
  const { symlink } = await import('node:fs/promises');
  for (const kind of ['assets', '.encoded', '.encoded/assets', '.encoded/assets/a-12345678.js.gz', '.static-encodings.json']) {
    const root = await fixture(t);
    const outside = await fixture(t);
    await writeFile(join(root, 'assets/a-12345678.js'), 'synthetic');
    await writeFile(join(outside, 'sentinel'), 'unchanged');
    if (kind === 'assets') await rm(join(root, 'assets'), { recursive: true });
    if (kind.startsWith('.encoded/')) await mkdir(join(root, '.encoded'), { recursive: true });
    if (kind.includes('.js.gz')) await mkdir(join(root, '.encoded/assets'));
    const isFile = kind.includes('.js.gz') || kind.endsWith('.json');
    await symlink(isFile ? join(outside, 'sentinel') : outside, join(root, kind), isFile ? 'file' : 'dir');
    await assert.rejects(precompress(root), /invalid_build_(directory|output)/);
    assert.equal(await readFile(join(outside, 'sentinel'), 'utf8'), 'unchanged');
  }
});
