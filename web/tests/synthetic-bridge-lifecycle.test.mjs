import test from 'node:test';
import assert from 'node:assert/strict';
import { lstat, readFile, readdir, access } from 'node:fs/promises';
import { join } from 'node:path';
import { withSyntheticBridge } from './synthetic-bridge.mjs';

// These child processes create disposable bytes, never open a real database.
const seed = `
const fs = require('node:fs'), path = require('node:path');
const root = process.argv[1], store = path.join(root, 'store');
// Windows junctions exercise lstat's symbolic-link rejection without requiring
// Developer Mode or the Create symbolic links privilege. Targets are absolute.
const directoryLink = (target, link) => fs.symlinkSync(
  target, link, process.platform === 'win32' ? 'junction' : 'dir');
fs.mkdirSync(store);
fs.mkdirSync(path.join(store, 'staging'));
fs.mkdirSync(path.join(store, 'raw', 'aa'), { recursive: true });
fs.writeFileSync(path.join(store, 'research.duckdb'), 'disposable database bytes');
fs.writeFileSync(path.join(store, '.operation.lock'), 'lock');
fs.writeFileSync(path.join(store, 'raw', 'aa', 'a'.repeat(64)), 'synthetic input');
const reply = { root, lockInode: fs.statSync(path.join(store, '.operation.lock')).ino };
`;
const run = (extra, consume = () => {}) => withSyntheticBridge({
  prefix: 'bridge-lifecycle-test-', command: process.execPath, args: ['-e', seed + extra],
}, consume);
const retained = async error => {
  assert.match(error.message, /synthetic bridge .* root=/);
  assert.equal(await readFile(join(error.root, 'store', 'research.duckdb'), 'utf8'), 'disposable database bytes');
};

test('success releases only new database after asynchronous consumer; lock inode and raw remain', async () => {
  const root = await run('console.log(JSON.stringify(reply));', async reply => {
    await new Promise(resolve => setTimeout(resolve, 20));
    assert.equal(await readFile(join(reply.root, 'store', 'research.duckdb'), 'utf8'), 'disposable database bytes');
    return reply;
  });
  await assert.rejects(access(join(root.root, 'store', 'research.duckdb')), { code: 'ENOENT' });
  assert.equal((await lstat(join(root.root, 'store', '.operation.lock'))).ino, root.lockInode);
  assert.equal(await readFile(join(root.root, 'store', 'raw', 'aa', 'a'.repeat(64)), 'utf8'), 'synthetic input');
  assert.deepEqual((await readdir(join(root.root, 'store'))).sort(), ['.operation.lock', 'raw', 'staging']);
});

test('waits for close, including inherited output pipe, before parsing and consuming', async () => {
  await run(`require('node:child_process').spawn(process.execPath, ['-e',
    'setTimeout(() => console.log(' + JSON.stringify(JSON.stringify(reply)) + '), 100)'],
    { stdio: ['ignore', 'inherit', 'inherit'] }).unref(); process.exit(0);`, reply => assert.ok(reply.root));
});

test('consumer rejection preserves database and original assertion error', async () => {
  const original = new Error('consumer assertion failed');
  let caught; try { await run('console.log(JSON.stringify(reply));', async () => { await Promise.resolve(); throw original; }); } catch (error) { caught = error; }
  assert.equal(caught.cause, original); assert.equal(caught.stage, 'consume'); await retained(caught);
});

for (const [name, extra, stage] of [
  ['child nonzero', "console.log(JSON.stringify(reply)); process.exit(7);", 'child'],
  ['malformed output', "console.log('not json');", 'parse'],
  ['output overflow', "console.log('x'.repeat(200000));", 'child'],
]) test(`${name} preserves database`, async () => {
  let caught;
  try { await withSyntheticBridge({ prefix: 'bridge-lifecycle-test-', command: process.execPath,
    args: ['-e', seed + extra], maxBuffer: 65536 }, () => assert.fail('consumer must not run')); } catch (error) { caught = error; }
  assert.equal(caught.stage, stage); assert.ok(caught.cause); await retained(caught);
});

test('spawn failure reports its new retained root', async () => {
  await assert.rejects(withSyntheticBridge({ prefix: 'bridge-lifecycle-test-', command: '/nonexistent/bridge-command', args: [] }, () => {}), error => {
    assert.equal(error.stage, 'child'); assert.equal(error.cause.code, 'ENOENT'); assert.ok(error.root); return true;
  });
});

for (const [name, mutation] of [
  ['WAL', "fs.writeFileSync(path.join(store, 'research.duckdb.wal'), 'wal')"],
  ['WAL checkpoint', "fs.writeFileSync(path.join(store, 'research.duckdb.wal.checkpoint'), 'keep')"],
  ['WAL recovery', "fs.writeFileSync(path.join(store, 'research.duckdb.wal.recovery'), 'keep')"],
  ['recovery marker', "fs.writeFileSync(path.join(store, '.restore-incomplete'), 'recovery')"],
  ['unexpected root file', "fs.writeFileSync(path.join(root, 'unexpected'), 'keep')"],
  ['staging residue', "fs.writeFileSync(path.join(store, 'staging', 'pending.part'), 'keep')"],
  ['unexpected raw file', "fs.writeFileSync(path.join(store, 'raw', 'aa', 'unexpected'), 'keep')"],
  ['raw symlink', "directoryLink(path.join(store, 'staging'), path.join(store, 'raw', 'aa', 'a'.repeat(63) + 'b'))"],
  ['database hard link', "fs.linkSync(path.join(store, 'research.duckdb'), path.join(store, 'raw', 'aa', 'a'.repeat(63) + 'b'))"],
  ['lock hard link', "fs.linkSync(path.join(store, '.operation.lock'), path.join(store, 'raw', 'aa', 'a'.repeat(63) + 'b'))"],
  ['raw hard link', "fs.linkSync(path.join(store, 'raw', 'aa', 'a'.repeat(64)), path.join(store, 'raw', 'aa', 'a'.repeat(63) + 'b'))"],
]) test(`${name} aborts release and retains database`, async () => {
  let caught; try { await run(mutation + '; console.log(JSON.stringify(reply));'); } catch (error) { caught = error; }
  assert.equal(caught.stage, 'release'); await retained(caught);
});

for (const target of ['research.duckdb', '.operation.lock', 'raw', 'staging']) {
  for (const type of ['symlink', 'wrong type']) test(`${target} ${type} aborts release with shape-valid names`, async () => {
    // Construct the wrong type initially, without deleting/renaming evidence or
    // introducing extra names that would mask the path-type validation.
    let script = seed;
    const path = `path.join(store, '${target}')`;
    const replacement = type === 'symlink'
      ? `directoryLink(path.join(store, '${target === 'raw' ? 'staging' : target === 'staging' ? '.' : 'raw'}'), ${path});`
      : target === 'raw' || target === 'staging'
        ? `fs.writeFileSync(${path}, 'unexpected regular file');`
        : `fs.mkdirSync(${path});`;
    if (target === 'raw') {
      script = script.replace("fs.mkdirSync(path.join(store, 'raw', 'aa'), { recursive: true });",
        replacement).replace("fs.writeFileSync(path.join(store, 'raw', 'aa', 'a'.repeat(64)), 'synthetic input');", '');
    } else if (target === 'staging') {
      script = script.replace("fs.mkdirSync(path.join(store, 'staging'));", replacement);
    } else {
      const contents = target === 'research.duckdb' ? 'disposable database bytes' : 'lock';
      script = script.replace(`fs.writeFileSync(${path}, '${contents}');`, replacement);
    }
    let caught;
    try { await withSyntheticBridge({ prefix: 'bridge-lifecycle-test-', command: process.execPath,
      args: ['-e', script + 'console.log(JSON.stringify(reply));'] }, () => {}); } catch (error) { caught = error; }
    assert.equal(caught.stage, 'release'); assert.match(caught.cause.message, /unexpected (file|directory):/);
    assert.ok(caught.cause.message.endsWith(target));
  });
}
