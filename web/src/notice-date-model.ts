/** 053: bounded explicit-notice comparison of the validated 051 date DTO only.
 * No Store reads, price calculation, inferred sessions or original report edits.
 */
import bundledReference from './notice-reference-v1.json' with { type: 'json' };
import { assertGroupPairs, verifyGroupPairIdentity } from './group-pair-model.ts';
import type { GroupPairReport } from './group-pair-model.ts';
import { validGroupDate } from './group-endpoint-model.ts';

export const NOTICE_REFERENCE_HASH = 'f3ad5c46bde683f3d713259e2aa35166f7469296956d7cc82538734c60a90264';
export const NOTICE_METHOD = 'group-pairs-explicit-notice-diagnostic-v1';
const RULE = 'qualified-source-claims-complete-date-groups-v1';
const MAX_REFERENCE_BYTES = 128 * 1024, MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024;
const exchanges = ['SSE','SZSE'] as const;
export type NoticeExchange = typeof exchanges[number];
export interface NoticeSource {
  id: string; exchange: NoticeExchange; document_id: string; url: string;
  publication_date: string; original_sha256: string;
  closed_ranges: [string,string][]; closed_dates: string[]; reopen_dates: string[];
}
export interface NoticeReference {
  schema: 'explicit-notice-reference-v1'; version: string; scope: [string,string]; timezone: 'Asia/Shanghai';
  mode: 'retrospective'; exception_coverage: 'unknown'; historical_availability: 'unknown';
  accepted_facts_sha256: string; reviewed_on: string; notices: NoticeSource[];
}
export interface NoticeMember {
  snapshot_id: string; batch_id: string; query_id: string; symbol: string | null;
  exchange: NoticeExchange | null; present: string[]; absence_span: [string,string] | null;
  source_span: [string,string] | null; unknown_reasons: string[];
}
export interface NoticeDate {
  date: string; planned: 'open' | 'closed' | 'conflict'; evidence: string[];
  present: string[]; absent: string[]; unknown: string[];
  finding: 'closed_present' | 'all_absent' | 'some_absent' | null;
}
export interface NoticeExchangeResult {
  exchange: NoticeExchange; members: string[]; dates: NoticeDate[];
  covered_dates: number; open_dates: number; closed_dates: number; conflict_dates: number; uncovered_dates: number;
  present: number; absent: number; unknown: number;
}
export interface NoticeComparison {
  selected: number; window: [string,string] | null; members: NoticeMember[]; unknown_members: string[];
  exchanges: NoticeExchangeResult[]; status: 'no_overlap' | 'not_evaluated' | 'evaluated'; differences: number;
}
export interface NoticeDiagnostic extends NoticeComparison {
  method_id: string; rule_version: string; attachment_id: string; parent_analysis_id: string;
  reference_hash: string; reference: NoticeReference; mode: 'retrospective'; historical_availability: 'unknown';
}
function ensure(value: unknown, code = 'invalid_notice_reference'): asserts value {
  if (!value) throw new Error(code);
}
function keys(value: unknown, names: string[]) {
  ensure(value !== null && typeof value === 'object' && !Array.isArray(value));
  ensure(Object.keys(value).length === names.length && names.every(k => Object.hasOwn(value,k)));
}
const hex = (v: unknown): v is string => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const text = (v: unknown, max: number): v is string => typeof v === 'string' && v.length > 0 && v.length <= max;
const day = (v: unknown): v is string => typeof v === 'string' && v.length === 10 && validGroupDate(v);
// UTC integer days enumerate already-validated date labels; no local timezone conversion.
const ordinal = (d: string) => Date.parse(`${d}T00:00:00Z`) / 86400000;
const spanSize = (start: string, end: string) => ordinal(end) - ordinal(start) + 1;
function days(start: string,end: string): string[] {
  return Array.from({length:spanSize(start,end)},(_,i)=>new Date((ordinal(start)+i)*86400000).toISOString().slice(0,10));
}
/** Sorted keys, exact Unicode values, finite JSON only. Inputs are bounded before use. */
export function noticeCanonical(value: unknown): string {
  if (value === null || typeof value === 'boolean' || typeof value === 'string' || typeof value === 'number' && Number.isFinite(value)) return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(noticeCanonical).join(',')}]`;
  if (value && typeof value === 'object') return `{${Object.keys(value).sort().map(k=>`${JSON.stringify(k)}:${noticeCanonical((value as Record<string,unknown>)[k])}`).join(',')}}`;
  throw new Error('invalid_notice_identity');
}
export async function noticeHash(value: unknown): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256',new TextEncoder().encode(noticeCanonical(value)));
  return Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');
}
export function assertNoticeReference(value: unknown): asserts value is NoticeReference {
  const r = value as NoticeReference;
  keys(r,['schema','version','scope','timezone','mode','exception_coverage','historical_availability','accepted_facts_sha256','reviewed_on','notices']);
  ensure(r.schema === 'explicit-notice-reference-v1' && text(r.version,128) && /^[a-z0-9-]+$/.test(r.version));
  ensure(r.timezone === 'Asia/Shanghai' && r.mode === 'retrospective' && r.exception_coverage === 'unknown' && r.historical_availability === 'unknown');
  ensure(hex(r.accepted_facts_sha256) && day(r.reviewed_on));
  ensure(Array.isArray(r.scope) && r.scope.length === 2 && r.scope.every(day) && r.scope[0] <= r.scope[1] && spanSize(...r.scope) <= 800);
  ensure(Array.isArray(r.notices) && r.notices.length <= 16);
  const ids = new Set<string>(); let facts = 0;
  for (const n of r.notices) {
    keys(n,['id','exchange','document_id','url','publication_date','original_sha256','closed_ranges','closed_dates','reopen_dates']);
    ensure(text(n.id,128) && /^[a-z0-9-]+$/.test(n.id) && !ids.has(n.id)); ids.add(n.id);
    ensure(exchanges.includes(n.exchange) && text(n.document_id,128) && hex(n.original_sha256) && day(n.publication_date));
    ensure(text(n.url,2048));
    let url: URL; try { url = new URL(n.url); } catch { throw new Error('invalid_notice_reference'); }
    ensure(url.protocol === 'https:' && !url.username && !url.password && !url.port &&
      url.hostname === (n.exchange === 'SSE' ? 'www.sse.com.cn' : 'www.szse.cn'));
    ensure(Array.isArray(n.closed_ranges) && Array.isArray(n.closed_dates) && Array.isArray(n.reopen_dates));
    facts += n.closed_ranges.length + n.closed_dates.length + n.reopen_dates.length;
    ensure(facts <= 128);
    const within = (d: unknown): d is string => day(d) && d >= r.scope[0] && d <= r.scope[1];
    for (const range of n.closed_ranges) ensure(Array.isArray(range) && range.length === 2 && range.every(within) && range[0] <= range[1] && spanSize(...range) <= 31);
    for (const list of [n.closed_dates,n.reopen_dates]) ensure(list.every(within) && new Set(list).size === list.length);
  }
  ensure(new TextEncoder().encode(JSON.stringify(r)).length <= MAX_REFERENCE_BYTES,'notice_reference_limit');
}
export async function verifyNoticeReference(value: unknown, expectedHash = NOTICE_REFERENCE_HASH) {
  assertNoticeReference(value);
  ensure(hex(expectedHash) && await noticeHash(value) === expectedHash,'notice_reference_integrity');
}
/** Internal adapter: only call on a 051 DTO accepted by assertGroupPairs. */
export function adaptNoticeMembers(report: GroupPairReport): NoticeMember[] {
  return [...report.members].sort((a,b)=>a.snapshot_id.localeCompare(b.snapshot_id)).map(m=>{
    const counts = m.anomalies?.counts ?? {};
    const counted = (code: string) => Object.hasOwn(counts,code) && Number.isSafeInteger(counts[code]) && counts[code] > 0;
    const has = (code: string) => m.reasons.includes(code) || counted(code);
    const qualified = m.source_qualified && m.evaluation === 'evaluated' && !has('global_source_conflict') &&
      m.symbol !== null && /^[0-9]{6}\.(SH|SZ)$/.test(m.symbol);
    const exchange: NoticeExchange | null = qualified ? m.symbol!.endsWith('.SH') ? 'SSE' : 'SZSE' : null;
    const problems: string[] = exchange === null ? ['exchange_claim_unverified'] : [];
    const blocked = ['local_source_conflict','source_date_range','unclassified_source_failure'].filter(has);
    problems.push(...blocked);
    const usable = exchange !== null && blocked.length === 0;
    const uncertainEndpoint = (reasons: string[]) => reasons.includes('unlocated_endpoint') || reasons.includes('missing_endpoint');
    const present = usable ? (m.endpoints ?? []).filter(p=>m.date_array.includes(p.date) && !uncertainEndpoint(p.reasons)).map(p=>p.date) : [];
    const uncertainDates = ['endpoint_integrity_unknown','unlocated_label','label'].filter(has);
    problems.push(...uncertainDates);
    if ((m.endpoints ?? []).some(p=>uncertainEndpoint(p.reasons))) problems.push('endpoint_date_unverified');
    if (!m.date_array.length) problems.push('date_array_empty');
    if (m.date_array.at(-1) !== report.parameters.cutoff) problems.push('cutoff_not_enumerated');
    const source_span: [string,string] | null = m.date_array.length ? [m.date_array[0],m.date_array.at(-1)!] : null;
    const absence_span: [string,string] | null = usable && problems.length === 0 ? [m.date_array[0],report.parameters.cutoff] : null;
    return { snapshot_id:m.snapshot_id,batch_id:m.batch_id,query_id:m.query_id,symbol:m.symbol,exchange,present,absence_span,source_span,unknown_reasons:[...new Set(problems)].sort() };
  });
}
/** Pure bounded matcher. The public UI entry below verifies the report and pinned manifest first. */
export function matchNoticeDates(report: GroupPairReport, reference: NoticeReference): NoticeComparison {
  assertNoticeReference(reference);
  ensure(report.members.length >= 2 && report.members.length <= 50 && report.members.every(m=>m.date_array.length<=121),'notice_member_limit');
  const members = adaptNoticeMembers(report), firsts = report.members.flatMap(m=>m.date_array.length?[m.date_array[0]]:[]).sort();
  const start = [firsts[0] ?? reference.scope[0],reference.scope[0]].sort().at(-1)!;
  const end = [report.parameters.cutoff,reference.scope[1]].sort()[0];
  const window: [string,string] | null = start <= end ? [start,end] : null;
  const windowDays = window ? spanSize(...window) : 0;
  const output: NoticeExchangeResult[] = [];
  let totalCells = 0, totalStates = 0, comparable = 0, differences = 0;
  for (const exchange of exchanges) {
    const selected = members.filter(m=>m.exchange===exchange);
    const schedule = new Map<string,{states:Set<'open'|'closed'>;evidence:Set<string>}>();
    const add = (d: string,state:'open'|'closed',id:string) => {
      if (!window || d < window[0] || d > window[1]) return;
      const item = schedule.get(d) ?? {states:new Set<'open'|'closed'>(),evidence:new Set<string>()};
      item.states.add(state);item.evidence.add(id);schedule.set(d,item);
    };
    for (const n of reference.notices.filter(n=>n.exchange===exchange)) {
      for (const range of n.closed_ranges) for (const d of days(...range)) add(d,'closed',n.id);
      for (const d of n.closed_dates) add(d,'closed',n.id);
      for (const d of n.reopen_dates) add(d,'open',n.id);
    }
    totalCells += schedule.size;totalStates += schedule.size*selected.length;
    ensure(totalCells<=1600 && totalStates<=40000,'notice_result_limit');
    let open_dates=0,closed_dates=0,conflict_dates=0,present=0,absent=0,unknown=0;
    const dates: NoticeDate[] = [];
    for (const [d,item] of [...schedule].sort(([a],[b])=>a.localeCompare(b))) {
      const planned = item.states.size===2 ? 'conflict' : item.states.has('open') ? 'open' : 'closed';
      if (planned==='open') open_dates++; else if (planned==='closed') closed_dates++; else conflict_dates++;
      if (!selected.length) continue; // Retain evidence coverage, never compare the empty member set.
      const row: NoticeDate = {date:d,planned,evidence:[...item.evidence].sort(),present:[],absent:[],unknown:[],finding:null};
      for (const m of selected) {
        const state = planned==='conflict' ? 'unknown' : m.present.includes(d) ? 'present' :
          m.absence_span && d>=m.absence_span[0] && d<=m.absence_span[1] ? 'absent' : 'unknown';
        row[state].push(m.snapshot_id);
      }
      if (planned!=='conflict') { present+=row.present.length;absent+=row.absent.length;unknown+=row.unknown.length;comparable+=row.present.length+row.absent.length; }
      if (planned==='closed' && row.present.length) row.finding='closed_present';
      if (planned==='open' && row.absent.length) row.finding=row.absent.length===selected.length?'all_absent':'some_absent';
      if (row.finding) differences++;
      dates.push(row);
    }
    output.push({exchange,members:selected.map(m=>m.snapshot_id),dates,covered_dates:schedule.size,open_dates,closed_dates,conflict_dates,uncovered_dates:windowDays-schedule.size,present,absent,unknown});
  }
  return {selected:members.length,window,members,unknown_members:members.filter(m=>m.exchange===null).map(m=>m.snapshot_id),exchanges:output,status:!window?'no_overlap':comparable?'evaluated':'not_evaluated',differences};
}
export async function buildNoticeDiagnostic(report: GroupPairReport, reference: unknown = bundledReference, expectedHash = NOTICE_REFERENCE_HASH): Promise<NoticeDiagnostic> {
  // Freeze this calculation before any asynchronous SHA work; never mutate the parent DTO.
  const r = structuredClone(report), ref = structuredClone(reference);
  assertGroupPairs(r,{ids:r.members.map(m=>m.snapshot_id),cutoff:r.parameters.cutoff});
  assertNoticeReference(ref);
  await Promise.all([verifyGroupPairIdentity(r),verifyNoticeReference(ref,expectedHash)]);
  const comparison = matchNoticeDates(r,ref);
  const sourceProjection = r.members.map(m=>({symbol:m.symbol,snapshot_id:m.snapshot_id,batch_id:m.batch_id,query_id:m.query_id,
    source_qualified:m.source_qualified,evaluation:m.evaluation,date_array:m.date_array,reasons:m.reasons,
    counts:m.anomalies?.counts ?? null,endpoints:m.endpoints?.map(p=>({date:p.date,reasons:p.reasons})) ?? null}));
  const identity = {method_id:NOTICE_METHOD,rule_version:RULE,parent_analysis_id:r.analysis_id,parent_method:r.method_id,
    parent_rule:r.rule_version,parent_source_rule:r.source_rule_version,parameters:r.parameters,sources:sourceProjection,
    window:comparison.window,members:comparison.members,reference_version:ref.version,reference_hash:expectedHash};
  const result: NoticeDiagnostic = {...comparison,method_id:NOTICE_METHOD,rule_version:RULE,attachment_id:await noticeHash(identity),
    parent_analysis_id:r.analysis_id,reference_hash:expectedHash,reference:ref,mode:'retrospective',historical_availability:'unknown'};
  ensure(new TextEncoder().encode(JSON.stringify(result)).length<=MAX_ATTACHMENT_BYTES,'notice_result_limit');
  return result;
}
