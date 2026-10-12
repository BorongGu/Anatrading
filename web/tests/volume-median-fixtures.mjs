// Entirely synthetic. Expected medians in tests are hand-calculated, never computed here.
export function volumeFixture(values = ['100', '100', '100', '100', '10000'], kind = 'regular', current = '200') {
  const dates = values.map((_, i) => new Date(Date.UTC(2024, 0, i + 1)).toISOString().slice(0, 10));
  const sum = values.reduce((s, value) => s + BigInt(value), 0n), n = BigInt(values.length);
  const fraction = (a, b) => {
    const gcd = (x, y) => y ? gcd(y, x % y) : x;
    const d = gcd(a, b); let rounded = a * 10000n / b; const remainder = a * 10000n % b;
    if (remainder * 2n > b || (remainder * 2n === b && rounded % 2n)) rounded++;
    return { numerator: String(a / d), denominator: String(b / d), display: `${rounded / 10000n}.${String(rounded % 10000n).padStart(4, '0')}` };
  };
  const comparison = { current, baseline_sum: String(sum), baseline_mean: fraction(sum, n),
    ratio: sum ? fraction(BigInt(current) * n, sum) : null, reason: sum ? null : 'zero_baseline',
    members: dates.map((date, i) => ({ date, value: values[i], reason: null })) };
  if (kind === 'daily') Object.assign(comparison, { ordinal: 10, history_dates: dates });
  return { comparison, lookback: values.length, currentDate: '2025-01-01', historyDates: dates, kind };
}
