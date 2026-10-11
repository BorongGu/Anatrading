// Synthetic frontend contracts only. These fixtures are not market or numeric-oracle evidence.
import { PATH_RULES, PATH_METHOD_ID, buildHistoricalPathRequest, PATH_METHODS } from '../src/historical-path-model.ts';
export const shown = n => n.toExponential(11).replace(/e([+-])(\d)$/, 'e$10$2');
export function historicalPathFixture(count = 84, invalid = []) {
  const groups = Array.from({ length: count }, (_, i) => new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10));
  const start = count - 21, total = Math.max(0, start - 20), valid = Array.from({ length: total }, (_, i) => i).filter(i => !invalid.includes(i));
  const select = indices => {
    const chosen = [];
    for (const i of indices) { if (chosen.every(j => Math.abs(i - j) > 20)) chosen.push(i); if (chosen.length === 3) break; }
    return chosen;
  };
  const selections = { path: select(valid), endpoint: select(valid), recent: select([...valid].reverse()) };
  const window = (index, query = false) => ({ start_index: index, end_index: index + 20, start_date: groups[index], end_date: groups[index + 20], calendar_days: 20,
    ordinals: Array.from({ length: 21 }, (_, j) => index + j + 1), prices: Array.from({ length: 21 }, (_, j) => `${query ? 100 + j : 100}.000000000000000000`),
    relative_path: Array.from({ length: 21 }, (_, j) => shown(query ? j / 100 : 0)), endpoint_change: shown(query ? .2 : 0),
    max_drawdown: { value: shown(0), peak_step: 0, trough_step: 0 }, distance: shown(query ? 0 : .01435), endpoint_distance: shown(query ? 0 : .2),
    max_point_difference: { value: shown(query ? 0 : .2), step: query ? 0 : 20 }, differences: Array.from({ length: 21 }, (_, j) => shown(query ? 0 : j / 100)) });
  const ledger = Array.from({ length: total }, (_, i) => {
    const failed = invalid.includes(i);
    const states = PATH_METHODS.map(method => {
      if (failed) return null;
      const rank = selections[method].indexOf(i), overlap = selections[method].find(j => Math.abs(i - j) <= 20);
      return rank >= 0 ? [rank + 1, null] : [null, overlap ?? null];
    });
    return [i, failed ? 'invalid_price' : null, failed ? null : shown(.01435), failed ? null : shown(.2), ...states, failed ? i : null];
  });
  const counts = Object.fromEntries(PATH_METHODS.map((method, index) => [method, { total, valid: valid.length, invalid: total - valid.length, selected: selections[method].length,
    overlap_excluded: ledger.filter(r => r[index + 4]?.[1] !== null && r[index + 4] !== null).length,
    remaining: ledger.filter(r => r[index + 4] !== null && r[index + 4][0] === null && r[index + 4][1] === null).length }]));
  const result = { identity: { symbol: '600000.SH', code: '600000', venue: 'SH', market: 'CN_A', qualification: 'source_claim' }, cutoff: groups.at(-1),
    qualification: 'conditional_source_close_paths', unknowns: ['adjustment', 'corporate_actions', 'calendar', 'coverage', 'bar_closure', 'known_at'],
    selection_rule: 'three_greedy_nonoverlapping_windows_not_global_optimum', ranking_rule: 'exact_distance_then_earlier_start',
    difference_direction: 'query_minus_candidate', display_policy: 'rounded_display_exact_ranking',
    parameters: { ...PATH_RULES }, groups, query: window(start, true), windows: [...new Set(Object.values(selections).flat())].map(i => window(i)), selections, counts,
    ledger_columns: ['start_index', 'reason', 'distance', 'endpoint_distance', 'path', 'endpoint', 'recent', 'first_invalid_index'], ledger };
  const reply = { method_id: PATH_METHOD_ID, analysis_id: 'd'.repeat(64), mode: 'retrospective', inputs: [{ snapshot_id: 'a'.repeat(64), query_id: 'b'.repeat(64) }],
    parameters: { cutoff: result.cutoff, model: { ...PATH_RULES } }, limitations: ['retrospective_source_version', 'adjustment_basis_unverified', 'historical_availability_unverified',
      'calendar_and_bar_closure_unverified'], result };
  return { reply, request: buildHistoricalPathRequest(reply.inputs[0].snapshot_id, result.cutoff) };
}

/** Fresh synthetic EvidenceStore → actual ASGI HTTP route; no socket or browser. */
export async function actualHistoricalPathFixture() {
  const { execFile } = await import('node:child_process');
  const { promisify } = await import('node:util');
  const { mkdir, mkdtemp } = await import('node:fs/promises');
  const { fileURLToPath } = await import('node:url');
  const { resolve, join } = await import('node:path');
  const repo = resolve(fileURLToPath(new URL('../..', import.meta.url)));
  const { tmpdir } = await import('node:os');
  const temporary = process.env.ANATRADING_TEST_TMPDIR ?? tmpdir(); await mkdir(temporary, { recursive: true });
  const root = await mkdtemp(join(temporary, '041-ui-bridge-'));
  const python = join(repo, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const script = `
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / 'tests'))
from test_historical_path_api import seed, client_for, path
root = Path(sys.argv[1]) / 'store'
sid = seed(root, 100)[0]
async def run():
    async with client_for(root) as client:
        response = await client.get(path(sid), params={'cutoff': '2025-04-10'})
        assert response.status_code == 200, response.text
        print(response.text)
asyncio.run(run())
`;
  const { stdout } = await promisify(execFile)(python, ['-c', script, root], { cwd: repo, maxBuffer: 8 * 1024 * 1024, env: { ...process.env, TMPDIR: root } });
  const reply = JSON.parse(stdout);
  return { reply, request: buildHistoricalPathRequest(reply.inputs[0].snapshot_id, reply.parameters.cutoff) };
}
