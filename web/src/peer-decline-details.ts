import { validatePeerSourcePair } from './peer-source-pair.ts';
import type { PeerNeighborReport } from './peer-neighbor-model.ts';

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
  const pair = validatePeerSourcePair(report, peerId);
  if (!pair.available) return pair;
  const { targetPrices, peerPrices, dates } = pair;

  return {
    available: true,
    previous: countWindow(targetPrices, peerPrices, dates, 0),
    current: countWindow(targetPrices, peerPrices, dates, 60),
  };
}
