import { exactPercent } from './exact-percent.ts';
import type { PeerSourcePair } from './peer-source-pair.ts';

export interface ChangeRatio { numerator: bigint; denominator: bigint }
export interface PeerChangeRow {
  previousDate: string; date: string; index: number;
  target: ChangeRatio; peer: ChangeRatio; difference: ChangeRatio;
}
const absolute = (n: bigint) => n < 0n ? -n : n;
export const changeDisplay = (value: ChangeRatio, unit: '%' | '百分点') =>
  exactPercent(value.numerator, value.denominator, unit);
export function changeSign(value: ChangeRatio): string {
  if (value.numerator === 0n) return '精确为零';
  return `${value.numerator > 0n ? '正' : '负'}${absolute(value.numerator) * 2_000_000n <= value.denominator ? '，显示未分辨' : ''}`;
}
/** One 60-edge window only. Positive validated prices are <10^38; products <10^76. */
export function peerChangeWindow(pair: Extract<PeerSourcePair, { available: true }>, offset: 0 | 60): PeerChangeRow[] {
  const rows: PeerChangeRow[] = [];
  for (let index = offset + 1; index <= offset + 60; index++) {
    const a = pair.targetPrices[index - 1], b = pair.targetPrices[index];
    const c = pair.peerPrices[index - 1], d = pair.peerPrices[index];
    rows.push({ previousDate: pair.dates[index - 1], date: pair.dates[index], index,
      target: { numerator: b - a, denominator: a },
      peer: { numerator: d - c, denominator: c },
      difference: { numerator: b * c - d * a, denominator: a * c },
    });
  }
  return rows.sort((a, b) => {
    const left = absolute(a.difference.numerator) * b.difference.denominator;
    const right = absolute(b.difference.numerator) * a.difference.denominator;
    return left > right ? -1 : left < right ? 1 : a.date < b.date ? -1 : a.date > b.date ? 1 : 0;
  });
}
