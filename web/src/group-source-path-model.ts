/** 054: one exact source-price kernel, using only a fully validated 050 report. */
import { assertDrawdownEpisodes, drawdownEpisodeRequest, verifyDrawdownIdentity } from './drawdown-episode-model.ts';
import type { DrawdownExpected, DrawdownReport } from './drawdown-episode-model.ts';

/** Full parent JSON includes valid Chinese near-zero labels. No Unicode normalization.
 * The old filter canonicalizer is ASCII-only and remains unchanged for 050 identity.
 */
export function groupPathCanonical(value: unknown): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(groupPathCanonical).join(',')}]`;
  if (value && typeof value === 'object' && Object.getPrototypeOf(value) === Object.prototype) {
    return `{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${groupPathCanonical((value as Record<string, unknown>)[key])}`).join(',')}}`;
  }
  throw new Error('invalid_group_path_json');
}

export const GROUP_PATH_METHOD = 'fixed-start-group-source-path-v1';
export const GROUP_PATH_RULE = 'all-members-earliest-deepest-trough-latest-equal-peak-v1';
export const GROUP_PATH_BATCH = 8;
const RESULT_BITS = 6400, CROSS_BITS = 12800;
const MAX_BYTES = 2*1024*1024, MAX_METADATA_BYTES = 16384;
export interface GroupPathFraction { numerator: string; denominator: string }
export interface GroupSourcePathAttachment {
  method_id: string;
  rule_version: string;
  representation: 'common-denominator-integer-curve-v1';
  attachment_id: string;
  parent_analysis_id: string;
  parent_content_hash: string;
  selected: number;
  endpoint_count: number;
  status: 'drawdown' | 'no_drawdown' | 'unavailable';
  start_index: number | null;
  peak_index: number | null;
  trough_index: number | null;
  denominator: string | null;
  sums: string[] | null;
  contributions: string[] | null;
  depth: GroupPathFraction | null;
}
export interface GroupSourcePathResult { parent: DrawdownReport; attachment: GroupSourcePathAttachment }
export interface GroupSourcePathOptions { signal?: AbortSignal; yieldControl?: () => Promise<void> }
function ensure(value: unknown, code: string): asserts value { if (!value) throw new Error(code); }
function bounded(value: bigint, bits = RESULT_BITS): bigint {
  ensure((value < 0n ? -value : value).toString(2).length <= bits, 'group_path_integer_limit');
  return value;
}
function integer(text: string): bigint {
  ensure(typeof text === 'string' && text.length <= 1928 && /^(?:0|-?[1-9]\d*)$/.test(text), 'invalid_group_path_integer');
  return bounded(BigInt(text));
}
function gcd(a: bigint, b: bigint): bigint {
  a = a < 0n ? -a : a;
  while (b) { const next = a%b; a = b; b = next; }
  return a;
}
function fraction(n: bigint, d: bigint): GroupPathFraction {
  bounded(n); bounded(d); ensure(d > 0n, 'invalid_group_path_integer');
  const divisor = gcd(n,d);
  return { numerator: (n/divisor).toString(), denominator: (d/divisor).toString() };
}
export function groupPathFraction(n: string, d: string): GroupPathFraction { return fraction(integer(n),integer(d)); }
/** Half-even, four percentage decimals. Nonzero signs survive display rounding. */
export function formatGroupPathPercent(n: string, d: string, signed = false): string {
  const numerator = integer(n), denominator = integer(d);
  ensure(denominator > 0n && (signed || numerator >= 0n), 'invalid_group_path_integer');
  const unit = signed ? '个百分点' : '%';
  if (!numerator) return `0.0000${unit}`;
  const magnitude = numerator < 0n ? -numerator : numerator;
  const scaled = bounded(magnitude*1000000n);
  let q = scaled/denominator;
  const r = scaled%denominator;
  if (bounded(2n*r) > denominator || 2n*r === denominator && q%2n === 1n) q++;
  if (!q) return signed ? numerator < 0n ? '负值（绝对值小于0.0001个百分点）' : '正值（小于0.0001个百分点）' : '小于0.0001%';
  const sign = numerator < 0n ? '−' : signed ? '+' : '';
  return `${sign}${q/10000n}.${(q%10000n).toString().padStart(4,'0')}${unit}`;
}
function scaledPrice(value: string): bigint {
  // The original 050 validator already checked canonical DECIMAL(38,18).
  const [whole, part = ''] = value.split('.');
  const a = BigInt(whole)*10n**18n+BigInt(part.padEnd(18,'0'));
  ensure(a > 0n && a < 10n**38n, 'invalid_group_path_price');
  return a;
}
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') {
    for (const child of Object.values(value)) freeze(child);
    Object.freeze(value);
  }
  return value;
}
function abort(signal?: AbortSignal) { if (signal?.aborted) throw new DOMException('Group source path cancelled', 'AbortError'); }
async function hash(value: unknown): Promise<string> {
  const bytes = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(groupPathCanonical(value)));
  return Array.from(new Uint8Array(bytes),b=>b.toString(16).padStart(2,'0')).join('');
}
/** Counts all keys/structure/metadata; only the explicitly bounded numeric payload is removed. */
export function checkGroupPathBudgets(value: unknown): void {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value), 'invalid_group_path_attachment');
  const all = value as Record<string, unknown>;
  const metadata = {...all};
  if (typeof all.denominator === 'string') metadata.denominator = '';
  if (Array.isArray(all.sums)) metadata.sums = [];
  if (Array.isArray(all.contributions)) metadata.contributions = [];
  if (all.depth !== null && typeof all.depth === 'object' && !Array.isArray(all.depth)) {
    metadata.depth = {...all.depth, numerator:'', denominator:''};
  }
  ensure(new TextEncoder().encode(JSON.stringify(metadata)).length <= MAX_METADATA_BYTES, 'group_path_metadata_limit');
  ensure(new TextEncoder().encode(JSON.stringify(value)).length <= MAX_BYTES, 'group_path_result_limit');
}

export async function buildGroupSourcePath(report: DrawdownReport, expected: DrawdownExpected, options: GroupSourcePathOptions = {}): Promise<GroupSourcePathResult> {
  abort(options.signal);
  // Capture both actual request and complete response before any await. No caller mutation.
  const parent = structuredClone(report), request = structuredClone(expected);
  const admitted = drawdownEpisodeRequest(request).expected;
  assertDrawdownEpisodes(parent, admitted);
  freeze(parent); freeze(request);
  const parentCanonical = groupPathCanonical(parent), expectedCanonical = groupPathCanonical(request);
  await verifyDrawdownIdentity(parent); abort(options.signal);
  const parent_content_hash = await hash(parent); abort(options.signal);
  const pause = async () => {
    abort(options.signal);
    await (options.yieldControl ? options.yieldControl() : new Promise<void>(resolve=>setTimeout(resolve,0)));
    abort(options.signal);
  };
  await pause();
  const fields: Omit<GroupSourcePathAttachment, 'attachment_id'> = {
    method_id:GROUP_PATH_METHOD, rule_version:GROUP_PATH_RULE, representation:'common-denominator-integer-curve-v1',
    parent_analysis_id:parent.analysis_id, parent_content_hash, selected:parent.members.length, endpoint_count:0,
    status:'unavailable', start_index:null, peak_index:null, trough_index:null,
    denominator:null, sums:null, contributions:null, depth:null,
  };
  if (parent.comparison_available) {
    const count = parent.members.length, length = parent.dates!.length;
    const prices = parent.members.map(m=>m.endpoints!.map(p=>scaledPrice(p.close_exact)));
    const anchors = prices.map(row=>row[0]);
    let lcm = 1n;
    // Division before multiplication keeps every intermediate within U^k.
    for (const q of anchors) lcm = bounded((lcm/gcd(lcm,q))*q);
    const weights = anchors.map(q=>lcm/q), denominator = bounded(BigInt(count)*lcm);
    const sums: bigint[] = [];
    let runningPeak = 0, peak: number | null = null, trough: number | null = null;
    let bestN = 0n, bestD = 1n;
    for (let t=0;t<length;t++) {
      if (t && t%GROUP_PATH_BATCH === 0) await pause();
      abort(options.signal);
      let sum = 0n;
      for (let i=0;i<count;i++) sum = bounded(sum+bounded(prices[i][t]*weights[i]));
      sums.push(sum);
      if (sum >= sums[runningPeak]) runningPeak = t;
      else {
        const n = sums[runningPeak]-sum, d = sums[runningPeak];
        if (bounded(n*bestD,CROSS_BITS) > bounded(bestN*d,CROSS_BITS)) {
          bestN=n; bestD=d; peak=runningPeak; trough=t;
        }
      }
    }
    ensure(sums[0] === denominator, 'group_path_anchor_mismatch');
    const contributions = peak === null ? null : prices.map((row,i)=>bounded((row[peak!]-row[trough!])*weights[i]));
    if (contributions) ensure(contributions.reduce((a,b)=>bounded(a+b),0n) === bestN, 'group_path_contribution_mismatch');
    Object.assign(fields, {
      endpoint_count:length, status:peak===null?'no_drawdown':'drawdown', start_index:0, peak_index:peak, trough_index:trough,
      denominator:denominator.toString(), sums:sums.map(String), contributions:contributions?.map(String) ?? null,
      depth:fraction(bestN,bestD),
    });
  }
  const attachment = {...fields,attachment_id:await hash(fields)};
  abort(options.signal);
  checkGroupPathBudgets(attachment);
  // Reject original-object mutation during SHA/yields; the retained evidence is the frozen clone.
  ensure(groupPathCanonical(report) === parentCanonical && groupPathCanonical(expected) === expectedCanonical, 'group_path_input_changed');
  return freeze({parent,attachment});
}
