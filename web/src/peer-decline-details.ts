import { validGroupDate } from './group-endpoint-model.ts';
import type { PeerMember, PeerNeighborReport } from './peer-neighbor-model.ts';

export interface PeerDeclineWindow {
  counts: {
    downDown: number;
    downNonDown: number;
    nonDownDown: number;
    nonDownNonDown: number;
  };
  targetDown: number;
  targetNonDown: number;
  peerDown: number;
  peerNonDown: number;
  targetFlat: number;
  peerFlat: number;
  total: 60;
  jointDownDates: { previousDate: string; date: string }[];
}

export type PeerDeclineDetails = {
  available: true;
  previous: PeerDeclineWindow;
  current: PeerDeclineWindow;
} | {
  available: false;
  reason: 'source_panel_unavailable' | 'invalid_member_identity' | 'invalid_source_endpoints';
};

/** The existing canonical Decimal(38,18) contract, scaled to at most 38 digits. */
function positiveSourcePrice(value: unknown): bigint | null {
  if (typeof value !== 'string' || value.length > 39 ||
    !/^(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(value)) return null;
  const [whole, fraction = ''] = value.split('.');
  const scaled = BigInt(whole + fraction.padEnd(18, '0'));
  return scaled > 0n ? scaled : null;
}

function sourcePrices(member: PeerMember, dates: string[]): bigint[] | null {
  if (!member.source_qualified || !member.panel_complete ||
    member.evaluation !== 'evaluated' || member.reasons.length !== 0 ||
    !member.endpoints || member.endpoints.length !== 121) return null;

  const prices: bigint[] = [];
  const ordinals = new Set<number>();
  for (let index = 0; index < 121; index++) {
    const endpoint = member.endpoints[index];
    if (!endpoint || endpoint.date !== dates[index] || endpoint.reasons.length !== 0 ||
      endpoint.ordinal === null || !Number.isSafeInteger(endpoint.ordinal) ||
      endpoint.ordinal <= 0 || ordinals.has(endpoint.ordinal)) return null;
    const price = positiveSourcePrice(endpoint.close_exact);
    if (price === null) return null;
    ordinals.add(endpoint.ordinal);
    prices.push(price);
  }
  return prices;
}

function countWindow(target: bigint[], peer: bigint[], dates: string[], offset: 0 | 60): PeerDeclineWindow {
  const counts = { downDown: 0, downNonDown: 0, nonDownDown: 0, nonDownNonDown: 0 };
  const jointDownDates: PeerDeclineWindow['jointDownDates'] = [];
  let targetFlat = 0;
  let peerFlat = 0;

  for (let index = offset + 1; index <= offset + 60; index++) {
    const targetDown = target[index] < target[index - 1];
    const peerDown = peer[index] < peer[index - 1];
    if (targetDown && peerDown) {
      counts.downDown++;
      jointDownDates.push({ previousDate: dates[index - 1], date: dates[index] });
    } else if (targetDown) {
      counts.downNonDown++;
    } else if (peerDown) {
      counts.nonDownDown++;
    } else {
      counts.nonDownNonDown++;
    }
    if (target[index] === target[index - 1]) targetFlat++;
    if (peer[index] === peer[index - 1]) peerFlat++;
  }

  return {
    counts,
    targetDown: counts.downDown + counts.downNonDown,
    targetNonDown: counts.nonDownDown + counts.nonDownNonDown,
    peerDown: counts.downDown + counts.nonDownDown,
    peerNonDown: counts.downNonDown + counts.nonDownNonDown,
    targetFlat,
    peerFlat,
    total: 60,
    jointDownDates,
  };
}

/** Derive signs only from the already validated report; never requalify sources or rank. */
export function peerDeclineDetails(report: PeerNeighborReport, peerId: string): PeerDeclineDetails {
  if (!report.source_panel_complete || report.reasons.length !== 0 ||
    report.members.some(member => !member.source_qualified || !member.panel_complete)) {
    return { available: false, reason: 'source_panel_unavailable' };
  }

  const targetId = report.parameters.target_snapshot_id;
  const target = report.members.find(member => member.snapshot_id === targetId);
  const peer = report.members.find(member => member.snapshot_id === peerId);
  if (!target || !peer || targetId === peerId || target.role !== 'target' || peer.role !== 'candidate' ||
    new Set(report.members.map(member => member.snapshot_id)).size !== report.members.length ||
    report.candidates.filter(candidate => candidate.snapshot_id === peerId).length !== 1) {
    return { available: false, reason: 'invalid_member_identity' };
  }

  const dates = report.used_dates;
  if (dates.length !== 121 || dates[120] !== report.parameters.cutoff ||
    !dates.every((date, index) => validGroupDate(date) && (index === 0 || date > dates[index - 1]))) {
    return { available: false, reason: 'invalid_source_endpoints' };
  }
  const targetPrices = sourcePrices(target, dates);
  const peerPrices = sourcePrices(peer, dates);
  if (!targetPrices || !peerPrices) {
    return { available: false, reason: 'invalid_source_endpoints' };
  }

  return {
    available: true,
    previous: countWindow(targetPrices, peerPrices, dates, 0),
    current: countWindow(targetPrices, peerPrices, dates, 60),
  };
}
