/** Build-only, deterministic within the installed Node/zlib version. */
import { createHash } from 'node:crypto';
import { lstat, mkdir, readFile, readdir, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { gzipSync, gunzipSync } from 'node:zlib';
import { pathToFileURL } from 'node:url';

export const CAP = 2_097_152;
const hash = (bytes) => createHash('sha256').update(bytes).digest('hex');
const assetName = /^[A-Za-z0-9_-]+-[A-Za-z0-9_-]{8,}\.(js|css)$/;

async function directoryOnly(path, create = false) {
  if (create) await mkdir(path, { recursive: true });
  if (!(await lstat(path)).isDirectory()) throw new Error('invalid_build_directory');
}

async function outputOnly(path) {
  try {
    if (!(await lstat(path)).isFile()) throw new Error('invalid_build_output');
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
}

export async function precompress(directory) {
  const root = resolve(directory);
  await directoryOnly(root);
  await directoryOnly(join(root, 'assets'));
  const entries = (await readdir(join(root, 'assets'))).filter(name => /\.(js|css)$/.test(name)).sort();
  if (entries.length > 1024) throw new Error('too_many_generated_assets');
  if (new Set(entries.map(name => name.toLowerCase())).size !== entries.length) {
    throw new Error('generated_asset_case_collision');
  }
  await directoryOnly(join(root, '.encoded'), true);
  await directoryOnly(join(root, '.encoded/assets'), true);
  await outputOnly(join(root, '.static-encodings.json'));
  const assets = [];
  for (const name of entries) {
    if (!assetName.test(name)) throw new Error('invalid_generated_asset_name');
    const identity_path = `assets/${name}`;
    const source = join(root, identity_path);
    const info = await lstat(source);
    if (!info.isFile() || info.size > CAP) throw new Error('invalid_generated_asset_size_or_type');
    const identity = await readFile(source);
    if (identity.length > CAP) throw new Error('generated_asset_size_cap');
    const encoded = gzipSync(identity, { level: 9, mtime: 0 });
    if (encoded.length > CAP || !gunzipSync(encoded).equals(identity)) throw new Error('invalid_gzip_output');
    const gzip_path = `.encoded/${identity_path}.gz`;
    await outputOnly(join(root, gzip_path));
    await writeFile(join(root, gzip_path), encoded);
    assets.push({ identity_path, gzip_path, identity_sha256: hash(identity), gzip_sha256: hash(encoded),
      identity_bytes: identity.length, gzip_bytes: encoded.length,
      media_type: name.endsWith('.js') ? 'text/javascript' : 'text/css', cap: CAP });
  }
  const manifest = JSON.stringify({ schema_version: 1, assets }, null, 2) + '\n';
  if (Buffer.byteLength(manifest) > 1_048_576) throw new Error('manifest_size_cap');
  await writeFile(join(root, '.static-encodings.json'), manifest);
  return { assets: assets.length, identity_bytes: assets.reduce((n, x) => n + x.identity_bytes, 0),
    gzip_bytes: assets.reduce((n, x) => n + x.gzip_bytes, 0) };
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  console.log(JSON.stringify(await precompress(process.argv[2] ?? 'dist')));
}
