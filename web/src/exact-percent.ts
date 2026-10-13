/** Display an already validated integer ratio; caller owns its input bounds. */
export function exactPercent(numerator: bigint, denominator: bigint, unit: '%' | '百分点'): string {
  const absolute = numerator < 0n ? -numerator : numerator;
  const scaled = absolute * 1_000_000n;
  let rounded = scaled / denominator;
  const remainder = scaled % denominator;
  if (remainder * 2n > denominator ||
    (remainder * 2n === denominator && rounded % 2n === 1n)) rounded++;
  const fraction = (rounded % 10_000n).toString().padStart(4, '0');
  const text = `${rounded / 10_000n}.${fraction}${unit}`;
  const sign = numerator < 0n && rounded !== 0n ? '-' : '';
  const roundedZero = numerator !== 0n && rounded === 0n
    ? `（${numerator > 0n ? '正' : '负'}，显示舍入）` : '';
  return `${sign}${text}${roundedZero}`;
}
