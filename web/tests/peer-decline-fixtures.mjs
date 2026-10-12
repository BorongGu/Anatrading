import { readFileSync } from 'node:fs';

// Reuse only the established synthetic report envelope, never a Store or capture.
const envelope = JSON.parse(readFileSync(
  new URL('./peer-neighbor-fixtures.json', import.meta.url), 'utf8',
)).complete.reply;

export function setSourcePrices(report, id, prices) {
  const member = report.members.find(item => item.snapshot_id === id);
  member.endpoints.forEach((endpoint, index) => {
    const price = prices[index] ?? prices.at(-1);
    endpoint.close_exact = price;
    endpoint.close_token = price;
  });
}

export function declineFixture() {
  const report = structuredClone(envelope);
  for (const member of report.members) setSourcePrices(report, member.snapshot_id, ['100']);
  for (const candidate of report.candidates) {
    for (const window of ['previous', 'current']) {
      candidate[window] = {
        correlation: null, rank: null, tie_size: null, reason: 'target_constant_source_change',
      };
    }
    candidate.difference = null;
  }
  for (const window of ['previous', 'current']) {
    report.windows[window].available = 0;
    report.windows[window].target_reason = 'target_constant_source_change';
    report.windows[window].order = report.candidates.map(candidate => candidate.snapshot_id).sort();
  }
  report.status = 'unavailable';
  return {
    report,
    targetId: report.parameters.target_snapshot_id,
    peerId: report.candidates[0].snapshot_id,
  };
}

export const fourStepPrices = {
  target: ['100', '97', '96.03', '96.9903', '99.900009'],
  a: ['100', '103', '101.97', '104.0094', '106.089588'],
  b: ['100', '102', '104.04', '102.9996', '106.089588'],
};
