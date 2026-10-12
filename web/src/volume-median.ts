// Local summary of an existing v1 comparison. Never changes server values or identities.
type Median = { status: 'available'; exact_text: string }
  | { status: 'source_unavailable' | 'invalid'; exact_text: null };
type Context = { lookback: unknown; currentDate: unknown; historyDates: unknown; kind: 'daily' | 'regular' | 'cumulative' };
const invalid: Median = Object.freeze({ status: 'invalid', exact_text: null });
const unavailable: Median = Object.freeze({ status: 'source_unavailable', exact_text: null });

function fields(value: unknown, keys: string[]): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function integer(value: unknown, max: bigint): bigint | null {
  if (typeof value !== 'string' || value.length > String(max).length || !/^(0|[1-9]\d*)$/.test(value)) return null;
  const parsed = BigInt(value);
  return parsed <= max ? parsed : null;
}
function fraction(value: unknown, max: bigint, maxDenominator: bigint): [bigint, bigint] | null {
  if (!fields(value, ['numerator', 'denominator', 'display']) || typeof value.display !== 'string'
    || value.display.length > String(max).length + 5 || !/^(0|[1-9]\d*)\.\d{4}$/.test(value.display)) return null;
  const numerator = integer(value.numerator, max), denominator = integer(value.denominator, maxDenominator);
  return numerator !== null && denominator !== null && denominator > 0n ? [numerator, denominator] : null;
}
function date(value: unknown): value is string {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  // Numbers here are bounded calendar fields, never quantities or fractional values.
  const year = Number(value.slice(0, 4)), month = Number(value.slice(5, 7)), day = Number(value.slice(8));
  const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  return year >= 1 && month >= 1 && month <= 12 && day >= 1
    && day <= [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
}

export function historicalVolumeMedian(comparison: unknown, context: Context): Median {
  try {
    const { lookback: n, currentDate, historyDates, kind } = context;
    if (typeof n !== 'number' || !Number.isInteger(n) || n < 2 || n > 252
      || !['daily', 'regular', 'cumulative'].includes(kind)) return invalid;
    const keys = ['current', 'baseline_sum', 'baseline_mean', 'ratio', 'reason', 'members'];
    if (kind === 'daily') keys.push('ordinal', 'history_dates');
    if (!fields(comparison, keys) || !Array.isArray(comparison.members) || comparison.members.length > n
      || !Array.isArray(historyDates) || historyDates.length !== comparison.members.length) return invalid;
    if (kind === 'daily' && (typeof comparison.ordinal !== 'number' || !Number.isSafeInteger(comparison.ordinal)
      || comparison.ordinal < 1 || !Array.isArray(comparison.history_dates)
      || comparison.history_dates.length !== historyDates.length
      || comparison.history_dates.some((day, i) => day !== historyDates[i]))) return invalid;
    const { current, baseline_sum: baselineSum, baseline_mean: baselineMean, ratio, reason, members } = comparison;
    const memberReasons = new Set(kind === 'daily'
      ? ['duplicate_date', 'unlocated_label', 'missing_quantity', 'invalid_quantity']
      : ['missing_slot', 'duplicate_slot', 'missing_quantity', 'invalid_quantity']);
    const currentReasons = new Set([...memberReasons, ...(kind === 'daily' ? ['unsupported_period'] : [])]);
    if (reason !== null && (typeof reason !== 'string'
      || !['history_insufficient', 'zero_baseline', ...currentReasons].includes(reason))) return invalid;
    if (!date(currentDate) && !(currentDate === null && (reason === 'unlocated_label' || reason === 'unsupported_period'))) return invalid;
    const max = 9223372036854775807n * (kind === 'cumulative' ? 240n : 1n), sumMax = max * BigInt(n);
    if (current !== null && integer(current, max) === null) return invalid;
    const values: bigint[] = [], seen = new Set<string>();
    for (const [i, member] of members.entries()) {
      if (!fields(member, ['date', 'value', 'reason']) || !date(member.date) || seen.has(member.date)
        || member.date !== historyDates[i] || (typeof currentDate === 'string' && member.date >= currentDate)) return invalid;
      seen.add(member.date);
      if (member.reason !== null) {
        if (typeof member.reason !== 'string' || !memberReasons.has(member.reason) || member.value !== null) return invalid;
      } else {
        const value = integer(member.value, max);
        if (value === null) return invalid;
        values.push(value);
      }
    }
    if (baselineMean === null) {
      const expectedReason = current === null ? (typeof reason === 'string' && currentReasons.has(reason) ? reason : null)
        : members.length < n ? 'history_insufficient' : members.find(member => member.reason !== null)?.reason;
      return baselineSum === null && ratio === null && typeof reason === 'string' && reason === expectedReason
        ? unavailable : invalid;
    }
    const mean = fraction(baselineMean, sumMax, BigInt(n)), total = integer(baselineSum, sumMax);
    if (members.length !== n || values.length !== n || current === null || !mean || total === null
      || values.reduce((sum, value) => sum + value, 0n) !== total
      || mean[0] * BigInt(n) !== total * mean[1]
      || (total === 0n ? reason !== 'zero_baseline' || ratio !== null : reason !== null || !fraction(ratio, sumMax, sumMax))) return invalid;
    values.sort((a, b) => a < b ? -1 : a > b ? 1 : 0);
    const middle = Math.floor(n / 2);
    const twice = n % 2 ? values[middle] * 2n : values[middle - 1] + values[middle];
    return { status: 'available', exact_text: `${twice / 2n}${twice % 2n ? '.5' : ''}` };
  } catch {
    // Malformed summaries must not break the existing source values / mean / details.
    return invalid;
  }
}
