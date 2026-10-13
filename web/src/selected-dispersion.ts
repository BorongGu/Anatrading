import type { Query } from './types.ts';

export interface DispersionContext {
  ownerQueryId: string; snapshotId: string; batchId: string; cutoff: string | null;
  ordinalStart: number | null; ordinalEnd: number | null; raw: unknown; contract: unknown; period: unknown; mode: string; sourceQualification: unknown; quarantined: unknown; batchChecks: unknown; sourceCode: unknown; sourceVenue: unknown; sourceAdjustflag: unknown; interpretation: unknown;
}
export function dispersionContext(query: Query): DispersionContext {
  return { ownerQueryId: query.query_id, snapshotId: query.snapshot_id, batchId: query.batch_id,
    cutoff: query.selection.cutoff ?? null, ordinalStart: query.selection.ordinal_start ?? null,
    ordinalEnd: query.selection.ordinal_end ?? null, raw: query.manifest.raw_sha256,
    contract: query.manifest.source_contract_id, period: query.metadata.period, mode: query.selection.mode, sourceQualification: query.manifest.qualification, quarantined: query.metadata.quarantined, batchChecks: query.batch_checks?.filter(check=>check.name==='known_negative_sample').map(check=>check.outcome),
    sourceCode: query.metadata.source_code, sourceVenue: query.metadata.source_venue, sourceAdjustflag: query.metadata.source_adjustflag,
    interpretation: query.metadata.interpretation };
}
export function dispersionContextKey(context: DispersionContext): string { return JSON.stringify(context); }
export interface DispersionInterval { lower: string; upper: string; exact: boolean; display: string | null; display_reason: string | null }
export interface DispersionMember { position: number; date: string; ordinal: number | null; close: string | null; source_reason: string | null }
export interface DispersionRow extends DispersionMember {
  window_start_position: number; window_end_position: number; window_count: number;
  invalid_members: {position: number; date: string; ordinal: number | null; reason: string}[];
  status: 'computed' | 'unavailable'; reason: string | null;
  sum_u: string | null; sum_squares_u: string | null; dispersion_numerator: string | null;
  mean_exact: string | null; variance_exact: string | null;
  sigma: DispersionInterval | null; envelope_lower: DispersionInterval | null; envelope_upper: DispersionInterval | null;
}
export interface SelectedDispersion {
  analysis_id: string; view_method_id: string; method_id: string; adapter_id: string; numeric_policy_id: string;
  identity: { snapshot_id: string; batch_id: string; query_id: string; raw_sha256: string; source_contract_id: string;
    selection: Record<string, unknown>; symbol_identity: Record<string, unknown>; source_qualification: unknown };
  selection: { date_requested: string | null; resolved_date: string | null; policy: 'latest_source_date' | 'exact_source_date' };
  selected: DispersionRow | null; members: DispersionMember[]; status: 'computed' | 'unavailable'; reason: string | null;
  coverage: Record<string, number | boolean>; qualification: string; limitations: string[];
  parameters: {window: 20; current_inclusive: true; variance_divisor: 20; sigma_multiplier: 2};
  units: Record<string, string>; numeric_kind: string; source_numeric_kind: string;
}
function fail(): never { throw new Error('invalid_query_response'); }
const object = (v: unknown): v is Record<string, unknown> => !!v && typeof v === 'object' && !Array.isArray(v);
const text = (v: unknown): v is string => typeof v === 'string' && v.length > 0;
const integer = (v: unknown): v is number => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0;
const decimal = (v: unknown): v is string => typeof v === 'string' && v.length <= 128 && /^-?(?:0|[1-9]\d*)(?:\.\d+)?$/.test(v);
function ordered(left: string, right: string): boolean {
  // Decimal text ordering only; no price/dispersion arithmetic in the client.
  const negativeLeft=left.startsWith('-'), negativeRight=right.startsWith('-');
  if (negativeLeft !== negativeRight) return negativeLeft;
  const [li,lf='']=left.replace('-', '').split('.'), [ri,rf='']=right.replace('-', '').split('.');
  const magnitude=li.length-ri.length || li.localeCompare(ri) || lf.padEnd(40,'0').localeCompare(rf.padEnd(40,'0'));
  return negativeLeft ? magnitude>=0:magnitude<=0;
}
const code = (v: unknown): v is string => typeof v === 'string' && /^[a-z][a-z0-9_]{0,79}$/.test(v);
const day = (v: unknown): v is string => typeof v === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(v)
  && v.slice(0,4) !== '0000' && Number.isFinite(Date.parse(v+'T00:00:00Z')) && new Date(v+'T00:00:00Z').toISOString().slice(0,10) === v;
function finiteJson(value: unknown): void {
  if (typeof value === 'number' && !Number.isFinite(value)) fail();
  if (Array.isArray(value)) value.forEach(finiteJson);
  else if (object(value)) Object.values(value).forEach(finiteJson);
}
function freeze<T>(value: T): T {
  if (value && typeof value === 'object') { Object.values(value).forEach(freeze); Object.freeze(value); }
  return value;
}
function interval(value: unknown): void {
  if (!object(value) || !decimal(value.lower) || !decimal(value.upper) || typeof value.exact !== 'boolean'
    || value.exact !== (value.lower === value.upper) || !ordered(value.lower, value.upper)) fail();
  if (value.display === null) { if (value.display_reason !== 'ambiguous_display_rounding') fail(); }
  else if (typeof value.display !== 'string' || !/^-?(?:0|[1-9]\d*)\.\d{4}$/.test(value.display)
    || value.display === '-0.0000' || value.display_reason !== null) fail();
}
function member(value: unknown): asserts value is DispersionMember {
  if (!object(value) || !integer(value.position) || !day(value.date)
    || !(value.ordinal === null || integer(value.ordinal) && value.ordinal > 0)
    || !(value.close === null || decimal(value.close) && /^-?(?:0|[1-9]\d{0,19})(?:\.\d{1,18})?$/.test(value.close)) || !(value.source_reason === null || code(value.source_reason))) fail();
  if (value.source_reason === null && (value.ordinal === null || value.close === null || value.close === '0' || String(value.close).startsWith('-'))) fail();
  if (value.source_reason === 'duplicate_date' && value.ordinal !== null) fail();
}
export function acceptDispersion(value: unknown, context: DispersionContext, requested: string | null): SelectedDispersion {
  finiteJson(value);
  if (!object(value) || (context.period !== '1d' || context.mode !== 'retrospective') || !/^[a-f0-9]{64}$/.test(String(value.analysis_id))
    || value.view_method_id !== 'selected-source-close-dispersion20-v1'
    || value.method_id !== 'source-close-dispersion20-population-v1' || value.adapter_id !== 'daily-bars-strict-positive-v1'
    || value.numeric_policy_id !== 'integer-moments-isqrt36-v1') fail();
  const id=value.identity, choice=value.selection, p=value.parameters, c=value.coverage;
  if (!object(id) || id.snapshot_id !== context.snapshotId || id.batch_id !== context.batchId || !text(id.query_id)
    || !text(id.raw_sha256) || !text(id.source_contract_id) || !object(id.symbol_identity)
    || !Object.hasOwn(id,'source_qualification') || !object(id.selection)
    || id.selection.snapshot_id !== context.snapshotId || id.selection.mode !== 'retrospective'
    || id.selection.cutoff !== context.cutoff || id.selection.ordinal_start !== null || id.selection.ordinal_end !== null
    || context.raw !== undefined && id.raw_sha256 !== context.raw || context.contract !== undefined && id.source_contract_id !== context.contract) fail();
  if (!object(choice) || choice.date_requested !== requested || choice.policy !== (requested === null ? 'latest_source_date':'exact_source_date')
    || !(choice.resolved_date === null || day(choice.resolved_date)) || requested !== null && !day(requested)) fail();
  if (!object(p) || p.window !== 20 || p.current_inclusive !== true || p.variance_divisor !== 20 || p.sigma_multiplier !== 2
    || value.numeric_kind !== 'exact_integer_moments_with_certified_decimal_enclosures' || value.source_numeric_kind !== 'exact_decimal_text'
    || !object(value.units) || value.units.mean !== 'source_price' || value.units.variance !== 'source_price_squared'
    || value.units.sigma !== 'source_price' || value.units.envelope !== 'source_price'
    || !Array.isArray(value.limitations) || !value.limitations.every(code)
    || !['source_rejected','conditional_source_observations','source_coverage_unknown'].includes(String(value.qualification))) fail();
  const counts=['source_rows','date_groups','valid_groups','invalid_groups','duplicate_groups','unlocated_rows','unreadable_date_rows','batch_unlocated_rows'];
  if (!object(c) || counts.some(k=>!integer(c[k])) || typeof c.coverage_known !== 'boolean') fail();
  const count=c as Record<string,number>;
  if (value.qualification === 'source_rejected' && count.valid_groups !== 0) fail();
  if (count.source_rows > 20000 || count.date_groups > count.source_rows || count.valid_groups + count.invalid_groups !== count.date_groups
    || count.duplicate_groups > count.invalid_groups || count.unlocated_rows > count.source_rows
    || count.unreadable_date_rows > count.unlocated_rows || count.batch_unlocated_rows < count.unlocated_rows
    || c.coverage_known !== (count.unlocated_rows === 0 && count.batch_unlocated_rows === 0)
    || value.qualification !== 'source_rejected' && value.qualification !== (c.coverage_known ? 'conditional_source_observations':'source_coverage_unknown')) fail();
  if (!Array.isArray(value.members) || value.members.length > 20) fail();
  if (value.selected === null) {
    if (choice.resolved_date !== null || value.members.length || value.status !== 'unavailable'
      || value.reason !== (count.date_groups === 0 ? 'no_date_groups':'date_not_present')
      || requested === null && count.date_groups !== 0) fail();
  } else {
    const r=value.selected; member(r);
    const row=r as unknown as Record<string,unknown>;
    if (choice.resolved_date !== r.date || requested !== null && r.date !== requested
      || context.cutoff !== null && r.date > context.cutoff || r.position >= count.date_groups
      || requested === null && r.position !== count.date_groups-1
      || row.window_start_position !== Math.max(0,r.position-19) || row.window_end_position !== r.position
      || row.window_count !== Math.min(r.position+1,20) || value.members.length !== row.window_count) fail();
    const bad: {position:number;date:string;ordinal:number|null;reason:string}[]=[];
    for (const [i,item] of value.members.entries()) {
      member(item);
      if (item.position !== Number(row.window_start_position)+i || i>0 && item.date <= value.members[i-1].date
        || item.date > r.date) fail();
      if (item.source_reason !== null) bad.push({position:item.position,date:item.date,ordinal:item.ordinal,reason:item.source_reason});
    }
    const last=value.members.at(-1);
    if (!last || ['position','date','ordinal','close','source_reason'].some(k=>last[k] !== row[k])) fail();
    const invalid=row.invalid_members;
    if (!Array.isArray(invalid) || invalid.length !== bad.length
      || bad.some((b,i)=>!object(invalid[i]) || Object.entries(b).some(([k,v])=>invalid[i][k]!==v))) fail();
    if (bad.length > count.invalid_groups || value.members.length-bad.length > count.valid_groups
      || value.qualification==='source_rejected' && row.status==='computed') fail();
    const reason=value.members.length <20 ? 'history_insufficient':bad.length ? 'invalid_window':null;
    if (row.reason !== reason || value.reason !== reason || row.status !== (reason === null ? 'computed':'unavailable') || value.status !== row.status) fail();
    for (const k of ['sum_u','sum_squares_u','dispersion_numerator','mean_exact','variance_exact','sigma','envelope_lower','envelope_upper']) {
      if (reason !== null) { if (row[k] !== null) fail(); }
      else if (['sigma','envelope_lower','envelope_upper'].includes(k)) { interval(row[k]); if (k==='sigma' && String((row[k] as DispersionInterval).lower).startsWith('-')) fail(); }
      else if (!decimal(row[k]) || String(row[k]).startsWith('-') || ['sum_u','sum_squares_u','dispersion_numerator'].includes(k) && !/^\d{1,78}$/.test(String(row[k]))) fail();
    }
  }
  return freeze(structuredClone(value)) as unknown as SelectedDispersion;
}

/** Read every response (including errors) with the same byte cap, independent
 * of absent or dishonest Content-Length. No unbounded response.json fallback. */
export async function readDispersionResponse(response: Response): Promise<unknown> {
  const limit=65536;
  if (Number(response.headers.get('content-length')) > limit) { await response.body?.cancel(); throw new Error('dispersion_result_limit'); }
  const reader=response.body?.getReader(); if (!reader) fail();
  const chunks: Uint8Array[]=[]; let length=0;
  try {
    while (true) {
      const part=await reader.read(); if (part.done) break;
      length+=part.value.byteLength;
      if (length>limit) { await reader.cancel(); throw new Error('dispersion_result_limit'); }
      chunks.push(part.value);
    }
  } finally { reader.releaseLock(); }
  const bytes=new Uint8Array(length); let offset=0;
  for(const chunk of chunks) {bytes.set(chunk,offset);offset+=chunk.length;}
  let value: unknown;
  try { value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes)); finiteJson(value); }
  catch { return fail(); }
  if (!response.ok) throw new Error(object(value) && code(value.error) ? value.error:'invalid_query_response');
  return value;
}
export async function requestDispersion(context: DispersionContext, date: string | null, signal: AbortSignal): Promise<SelectedDispersion> {
  if (context.period !== '1d' || context.mode !== 'retrospective') fail();
  const params=new URLSearchParams();
  if (context.cutoff !== null) params.set('cutoff',context.cutoff);
  if (date !== null) { if (!day(date) || context.cutoff !== null && date>context.cutoff) throw new Error('invalid_research_date'); params.set('date',date); }
  const response=await fetch(`/api/research/close-dispersion/${encodeURIComponent(context.snapshotId)}?${params}`,
    {signal,cache:'no-store',credentials:'same-origin'});
  return acceptDispersion(await readDispersionResponse(response),context,date);
}
