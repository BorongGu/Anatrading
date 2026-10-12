// Test-only scope. No caller-supplied root and no recursive deletion: failures keep
// their evidence; successful consumers release only their freshly created DB.
import { execFile } from 'node:child_process';
import { mkdir, mkdtemp, realpath, lstat, readdir, unlink } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

async function directory(path) {
  const stat = await lstat(path);
  if (!stat.isDirectory() || stat.isSymbolicLink()) throw new Error(`unexpected directory: ${path}`);
  return stat;
}
async function file(path) {
  const stat = await lstat(path);
  if (!stat.isFile() || stat.isSymbolicLink() || stat.nlink !== 1) throw new Error(`unexpected file: ${path}`);
}
async function entries(path, expected) {
  await directory(path);
  const names = (await readdir(path)).sort();
  if (JSON.stringify(names) !== JSON.stringify([...expected].sort())) throw new Error(`unexpected entries: ${path}`);
}
async function releaseDatabase(root, identity) {
  const current = await directory(root);
  if (current.dev !== identity.dev || current.ino !== identity.ino) throw new Error('test root identity changed');
  await entries(root, ['store']);
  const store = join(root, 'store');
  await entries(store, ['research.duckdb', '.operation.lock', 'raw', 'staging']);
  await file(join(store, 'research.duckdb'));
  await file(join(store, '.operation.lock'));
  await entries(join(store, 'staging'), []);
  const raw = join(store, 'raw');
  await directory(raw);
  const shards = await readdir(raw);
  if (!shards.length) throw new Error('missing synthetic raw input');
  for (const shard of shards) {
    if (!/^[0-9a-f]{2}$/.test(shard)) throw new Error('unexpected raw shard');
    const path = join(raw, shard); await directory(path);
    const hashes = await readdir(path);
    if (!hashes.length) throw new Error('empty raw shard');
    for (const hash of hashes) {
      if (!/^[0-9a-f]{64}$/.test(hash) || !hash.startsWith(shard)) throw new Error('unexpected raw filename');
      await file(join(path, hash));
    }
  }
  // The trusted synthetic child has closed and the consumer has finished. Keep
  // the lock inode, raw inputs and directories. Unexpected artifacts abort above.
  await unlink(join(store, 'research.duckdb'));
}

export async function withSyntheticBridge({ prefix, command, args, cwd, maxBuffer = 8 * 1024 * 1024 }, consume) {
  let root, stage = 'create';
  try {
    if (!/^[a-z0-9-]+-$/.test(prefix)) throw new Error('invalid test prefix');
    const temporary = process.env.ANATRADING_TEST_TMPDIR ?? tmpdir();
    await mkdir(temporary, { recursive: true });
    root = await mkdtemp(join(await realpath(temporary), prefix));
    const identity = await directory(root);
    stage = 'child';
    const stdout = await new Promise((resolve, reject) => {
      let result;
      const child = execFile(command, [...args, root], { cwd, maxBuffer,
        env: { ...process.env, TMPDIR: root, TEMP: root, TMP: root } },
      (error, stdout) => { result = { error, stdout }; });
      // execFile's callback collects errors/output on close. Waiting explicitly
      // also covers inherited stdio handles still open after the process exits.
      child.once('close', () => {
        if (!result) reject(new Error('child closed without a result'));
        else if (result.error) reject(result.error);
        else resolve(result.stdout);
      });
    });
    stage = 'parse';
    const reply = JSON.parse(stdout);
    stage = 'consume';
    const result = await consume(reply, root);
    stage = 'release';
    await releaseDatabase(root, identity);
    return result;
  } catch (cause) {
    const error = new Error(`synthetic bridge ${stage} failed; retained root=${root ?? '(not created)'}`, { cause });
    error.stage = stage; error.root = root;
    throw error;
  }
}
