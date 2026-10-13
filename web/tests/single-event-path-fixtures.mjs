import { readFileSync } from 'node:fs';
const data = JSON.parse(readFileSync(new URL('./single-event-path-fixtures.json', import.meta.url)));
export const names = Object.keys(data.cases);
export function fixture(name = 'P1A') {
  const result = structuredClone(data.base);
  for (const [path, value] of data.cases[name]) {
    let node = result; for (const key of path.slice(0, -1)) node = node[key];
    node[path.at(-1)] = structuredClone(value);
  }
  return result;
}
export const context = query => ({ ownerQueryId: query.query_id, snapshotId: query.snapshot_id, cutoff: query.selection.cutoff ?? null, ordinalStart: query.selection.ordinal_start ?? null, ordinalEnd: query.selection.ordinal_end ?? null });
