/** One explicit group, exact source ratios. No source qualification is added here. */
import { jsonRequest } from './api.ts';
import { canonicalJson } from './filter-model.ts';
import type { SourceEndpoint } from './two-group-model.ts';
export const GROUP_METHOD = 'explicit-group-source-endpoints-v1';
export const GROUP_RULE = 'peer-eligibility-complete-group-type7-v1';
const SOURCE_RULE = 'peer-relative-eligibility-v1';
export interface ExactRatio { numerator: string; denominator: string; unit: 'ratio' }
export interface GroupEndpointMember {
  symbol: string | null; snapshot_id: string; batch_id: string; query_id: string;
  evaluation: 'evaluated' | 'not_evaluated';
  endpoints: { start: SourceEndpoint; end: SourceEndpoint } | null;
  source_change: ExactRatio | null; reasons: string[];
  anomalies: { total: number; counts: Record<string, number>; examples: { ordinal: number; scope: string; codes: string[] }[]; truncated: boolean } | null;
}
export interface GroupEndpointReport {
  method_id: string; rule_version: string; source_rule_version: string; analysis_id: string;
  parameters: { start_date: string; end_date: string };
  scope: Record<string, { value: string; evidence_status: 'assumed' }>; events: unknown[];
  members: GroupEndpointMember[]; counts: { selected: number; valid: number; missing: number };
  coverage: ExactRatio; sign_counts: Record<'positive' | 'zero' | 'negative', number>;
  sign_proportions: Record<'positive' | 'zero' | 'negative', ExactRatio | null>;
  summary: Record<'mean' | 'median' | 'q1' | 'q3', ExactRatio | null>;
  summary_reason: 'incomplete_group' | null; status: 'complete' | 'partial' | 'unavailable';
  diagnostic_only: boolean; limitations: Record<string, string | boolean>;
}
export interface GroupEndpointExpected { ids: string[]; start: string; end: string }
type Rational = { n: bigint; d: bigint };
const sourceReasons = ['known_negative_source','source_identity_conflict','source_adjustment_conflict','source_structure_failed','unsupported_source_check','scope_conflict','unsupported_source','unsupported_period'];
const endpointReasons = ['duplicate_endpoint','unlocated_endpoint','missing_endpoint','missing_ohlc','invalid_price','invalid_ohlc','endpoint_price_check_failed'];
const memberReasons = ['local_source_conflict','unclassified_source_failure','endpoint_integrity_unknown',...endpointReasons,'corporate_action_unresolved','halted_endpoint_source_value'];
const diagnostics = ['corporate_action_unresolved','halted_endpoint_source_value'];
const signs = ['positive','zero','negative'] as const;
const summaries = ['mean','median','q1','q3'] as const;
const scope = Object.fromEntries(Object.entries({ asset_type:'stock',share_class:'A_share',price_currency:'CNY',daily_label_basis:'CN_exchange_date' }).map(([key,value])=>[key,{value,evidence_status:'assumed'}]));
const limitations = { economic_return_qualified:false,total_return_qualified:false,historical_availability:'unverified',closure:'unknown',trading_calendar:'unknown',corporate_action_coverage:'unknown',adjustment:'request_declared_semantics_unverified',source_integrity:'trusted_store_boundary',membership:'current_members_retrospective',source_semantics:'unverified',statistical_or_trading_advantage:'not_evaluated' };
function ensure(v: unknown): asserts v { if (!v) throw new Error('invalid_group_endpoint_response'); }
function keys(v: unknown, expected: string[]) {
  ensure(v !== null && typeof v === 'object' && !Array.isArray(v));
  ensure(Object.keys(v).length === expected.length && expected.every(key=>Object.hasOwn(v,key)));
}
const hash = (v: unknown) => typeof v === 'string' && /^[a-f0-9]{64}$/.test(v);
const integer = (v: unknown, max=20000) => typeof v === 'number' && Number.isSafeInteger(v) && v >= 0 && v <= max;
function sourceSymbol(v: unknown, evaluated: boolean): v is string {
  if (typeof v !== 'string') return false;
  const match = /^([A-Z0-9][A-Z0-9.-]{0,31})\.(SH|SZ|BJ|HK|NYSE|NASDAQ|AMEX)$/.exec(v);
  return !!match && (!['SH','SZ','BJ'].includes(match[2]) || /^\d{6}$/.test(match[1]))
    && (!evaluated || ['SH','SZ'].includes(match[2]));
}
function codes(v: unknown, allowed?: string[]): asserts v is string[] {
  ensure(Array.isArray(v) && v.every(c=>typeof c === 'string' && c.length > 0 && (!allowed || allowed.includes(c))) && new Set(v).size === v.length);
}
export function validGroupDate(v: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(v)) return false;
  const [y,m,d]=v.split('-').map(Number), leap=y%4===0&&(y%100!==0||y%400===0);
  return y>0&&m>=1&&m<=12&&d>=1&&d<=[31,leap?29:28,31,30,31,30,31,31,30,31,30,31][m-1];
}
function rational(n: bigint, d=1n): Rational {
  ensure(d > 0n);
  let a=n<0n?-n:n,b=d;
  while(b){const r=a%b;a=b;b=r;}
  return {n:n/a,d:d/a};
}
const add = (a: Rational,b: Rational) => rational(a.n*b.d+b.n*a.d,a.d*b.d);
const scale = (a: Rational,n: bigint,d=1n) => rational(a.n*n,a.d*d);
const compare = (a: Rational,b: Rational) => { const v=a.n*b.d-b.n*a.d;return v<0n?-1:v>0n?1:0; };
function exact(v: unknown, expected: Rational): asserts v is ExactRatio {
  keys(v,['numerator','denominator','unit']); const r=v as ExactRatio;
  ensure(r.unit === 'ratio' && typeof r.numerator === 'string' && r.numerator.length <= 4096 && /^(0|-?[1-9][0-9]*)$/.test(r.numerator));
  ensure(typeof r.denominator === 'string' && r.denominator.length <= 4096 && /^[1-9][0-9]*$/.test(r.denominator));
  // Compare canonical strings. Never accumulate arbitrary response-sized BigInts.
  ensure(r.numerator === expected.n.toString() && r.denominator === expected.d.toString());
}
function price(v: unknown): bigint {
  ensure(typeof v === 'string' && v.length <= 40 && /^-?(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(v) && v !== '-0');
  const negative=v.startsWith('-'), [whole,part='']=(negative?v.slice(1):v).split('.');
  const n=BigInt(whole)*10n**18n+BigInt(part.padEnd(18,'0'));
  return negative?-n:n;
}
function endpoint(p: SourceEndpoint, day: string) {
  keys(p,['date','ordinal','close_token','close_exact','reasons']);
  ensure(p.date === day && (p.ordinal === null || integer(p.ordinal,Number.MAX_SAFE_INTEGER) && p.ordinal > 0));
  ensure(p.close_token === null || typeof p.close_token === 'string' && p.close_token.length <= 128);
  if(p.close_exact !== null)price(p.close_exact);
  codes(p.reasons,endpointReasons);
}
function quantile(values: Rational[], quarter: bigint) {
  const position=BigInt(values.length-1)*quarter,index=Number(position/4n),weight=position%4n;
  return weight===0n?values[index]:add(scale(values[index],4n-weight,4n),scale(values[index+1],weight,4n));
}
export function assertGroupEndpoints(value: unknown, expected: GroupEndpointExpected): asserts value is GroupEndpointReport {
  const r=value as GroupEndpointReport;
  keys(r,['method_id','rule_version','source_rule_version','analysis_id','parameters','scope','events','members','counts','coverage','sign_counts','sign_proportions','summary','summary_reason','status','diagnostic_only','limitations']);
  ensure(r.method_id===GROUP_METHOD&&r.rule_version===GROUP_RULE&&r.source_rule_version===SOURCE_RULE&&hash(r.analysis_id));
  keys(r.parameters,['start_date','end_date']);ensure(r.parameters.start_date===expected.start&&r.parameters.end_date===expected.end);
  ensure(canonicalJson(r.scope)===canonicalJson(scope)&&canonicalJson(r.limitations)===canonicalJson(limitations));
  ensure(Array.isArray(r.events)&&r.events.length===0); // This HTTP route does not accept event attachments.
  ensure(Array.isArray(r.members)&&r.members.length===expected.ids.length&&r.members.length>=4&&r.members.length<=50);
  const symbols=new Set<string>(), queryIds=new Set<string>(), changes:Rational[]=[];
  const sortedIds=[...expected.ids].sort();
  for(let i=0;i<r.members.length;i++){
    const m=r.members[i]; keys(m,['symbol','snapshot_id','batch_id','query_id','evaluation','endpoints','source_change','reasons','anomalies']);
    ensure(m.snapshot_id===sortedIds[i]&&hash(m.snapshot_id)&&hash(m.batch_id)&&hash(m.query_id)&&!queryIds.has(m.query_id));queryIds.add(m.query_id);
    ensure(m.symbol===null||sourceSymbol(m.symbol,m.evaluation==='evaluated')&&!symbols.has(m.symbol));
    if(m.symbol!==null)symbols.add(m.symbol);
    if(m.evaluation==='not_evaluated'){
      codes(m.reasons,sourceReasons);ensure(m.reasons.length===1&&m.endpoints===null&&m.anomalies===null&&m.source_change===null);
      if(m.reasons[0]==='source_identity_conflict')ensure(m.symbol===null);
      continue;
    }
    ensure(m.evaluation==='evaluated'&&m.symbol!==null);codes(m.reasons,memberReasons);
    keys(m.endpoints,['start','end']);const ep=m.endpoints!;endpoint(ep.start,expected.start);endpoint(ep.end,expected.end);
    ensure(ep.start.ordinal===null||ep.end.ordinal===null||ep.start.ordinal!==ep.end.ordinal);
    ensure([...ep.start.reasons,...ep.end.reasons].every(c=>m.reasons.includes(c)));
    const available=ep.start.ordinal!==null&&ep.end.ordinal!==null&&ep.start.close_exact!==null&&ep.end.close_exact!==null&&ep.start.reasons.length===0&&ep.end.reasons.length===0&&!m.reasons.some(c=>!diagnostics.includes(c));
    ensure((m.source_change!==null)===available);
    if(m.source_change!==null){
      const a=price(ep.start.close_exact),b=price(ep.end.close_exact);ensure(a>0n&&b>0n);
      const derived=rational(b-a,a);exact(m.source_change,derived);changes.push(derived);
    } else ensure(m.reasons.length>0);
    keys(m.anomalies,['total','counts','examples','truncated']);const anomalies=m.anomalies!;
    ensure(integer(anomalies.total)&&Array.isArray(anomalies.examples)&&anomalies.examples.length===Math.min(anomalies.total,20)&&anomalies.truncated===(anomalies.total>20));
    ensure(anomalies.counts!==null&&typeof anomalies.counts==='object'&&!Array.isArray(anomalies.counts));
    ensure(Object.entries(anomalies.counts).every(([c,n])=>c.length>0&&integer(n,anomalies.total)&&n>0));
    ensure((Object.keys(anomalies.counts).length===0)===(anomalies.total===0));
    const ordinals=new Set<number>(), exampleCounts:Record<string,number>=Object.create(null);let previous=0;
    for(const item of anomalies.examples){
      keys(item,['ordinal','scope','codes']);ensure(integer(item.ordinal,Number.MAX_SAFE_INTEGER)&&item.ordinal>previous&&!ordinals.has(item.ordinal));previous=item.ordinal;ordinals.add(item.ordinal);
      ensure(['unknown','inside_interval','outside_interval'].includes(item.scope));codes(item.codes);ensure(item.codes.length>0&&item.codes.every(c=>anomalies.counts[c]>0));
      for(const code of item.codes)exampleCounts[code]=(exampleCounts[code]??0)+1;
      if(item.scope==='unknown')ensure(item.codes.includes('endpoint_integrity_unknown')&&m.reasons.includes('endpoint_integrity_unknown'));
      if(item.scope!=='outside_interval')ensure(item.codes.filter(c=>['local_source_conflict','unclassified_source_failure'].includes(c)).every(c=>m.reasons.includes(c)));
    }
    ensure(Object.entries(exampleCounts).every(([code,count])=>anomalies.counts[code]>=count));
    if(!anomalies.truncated)ensure(Object.keys(exampleCounts).length===Object.keys(anomalies.counts).length&&Object.entries(exampleCounts).every(([code,count])=>Object.hasOwn(anomalies.counts,code)&&anomalies.counts[code]===count));
  }
  const n=r.members.length,k=changes.length;keys(r.counts,['selected','valid','missing']);
  ensure(r.counts.selected===n&&r.counts.valid===k&&r.counts.missing===n-k);exact(r.coverage,rational(BigInt(k),BigInt(n)));
  keys(r.sign_counts,[...signs]);keys(r.sign_proportions,[...signs]);
  for(const sign of signs){const count=changes.filter(v=>sign==='positive'?v.n>0n:sign==='negative'?v.n<0n:v.n===0n).length;
    ensure(r.sign_counts[sign]===count);if(k)exact(r.sign_proportions[sign],rational(BigInt(count),BigInt(k)));else ensure(r.sign_proportions[sign]===null);}
  keys(r.summary,[...summaries]);
  if(k===n){const ordered=[...changes].sort(compare),sum=ordered.reduce(add,rational(0n));
    exact(r.summary.mean,scale(sum,1n,BigInt(n)));exact(r.summary.median,quantile(ordered,2n));exact(r.summary.q1,quantile(ordered,1n));exact(r.summary.q3,quantile(ordered,3n));
  }else ensure(summaries.every(key=>r.summary[key]===null));
  ensure(r.summary_reason===(k===n?null:'incomplete_group')&&r.status===(k===n?'complete':k?'partial':'unavailable'));
  ensure(r.diagnostic_only===r.members.some(m=>m.reasons.some(c=>diagnostics.includes(c))));
}
export async function verifyGroupEndpointIdentity(report: GroupEndpointReport) {
  const identity={method_id:report.method_id,rule_version:report.rule_version,source_rule_version:report.source_rule_version,parameters:report.parameters,
    sources:report.members.map(m=>({symbol:m.symbol,snapshot_id:m.snapshot_id,batch_id:m.batch_id,query_id:m.query_id})),scope:report.scope,events:report.events};
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonicalJson(identity)));
  ensure(Array.from(new Uint8Array(bytes),v=>v.toString(16).padStart(2,'0')).join('')===report.analysis_id);
}
export function groupEndpointRequest(expected: GroupEndpointExpected) {
  if(expected.ids.length<4||expected.ids.length>50||!expected.ids.every(hash)||new Set(expected.ids).size!==expected.ids.length)throw new Error('research_member_limit');
  if(!validGroupDate(expected.start)||!validGroupDate(expected.end)||expected.start>=expected.end)throw new Error('invalid_dates');
  const copy={...expected,ids:[...expected.ids].sort()};
  const params=new URLSearchParams({snapshot_ids:copy.ids.join(','),start_date:copy.start,end_date:copy.end});
  return {path:`/api/research/group-endpoints?${params}`,expected:copy};
}
export async function fetchGroupEndpoints(request: ReturnType<typeof groupEndpointRequest>, signal: AbortSignal) {
  const report=await jsonRequest<unknown>(request.path,{signal});assertGroupEndpoints(report,request.expected);await verifyGroupEndpointIdentity(report);return report;
}
export function groupPercent(value: ExactRatio | null): string {
  if(value===null)return '不可算';
  // Values reach rendering only after the bounded exact response validator.
  const n=BigInt(value.numerator),d=BigInt(value.denominator),absolute=n<0n?-n:n;
  const scaled=absolute*1_000_000n;let rounded=scaled/d;const remainder=scaled%d;
  if(remainder*2n>d||remainder*2n===d&&rounded%2n===1n)rounded++;
  const text=`${rounded/10000n}.${(rounded%10000n).toString().padStart(4,'0')}%`;
  return `${n<0n&&rounded!==0n?'-':''}${text}${n!==0n&&rounded===0n?`（${n>0n?'正':'负'}，显示舍入）`:''}`;
}
export const groupSign = (value: ExactRatio | null) => value===null?'不可算':value.numerator==='0'?'零':value.numerator.startsWith('-')?'负':'正';
const groupReasons: Record<string,string> = {
  missing_endpoint:'共同日期缺少记录',duplicate_endpoint:'共同日期存在重复记录',unlocated_endpoint:'共同日期的标签不合格',missing_ohlc:'端点缺少完整开高低收',invalid_price:'端点价格无效或不为正数',invalid_ohlc:'端点开高低收关系不成立',endpoint_price_check_failed:'端点价格核验未通过或原文与精确值不一致',
  endpoint_integrity_unknown:'存在无法定位日期，端点完整性未知',local_source_conflict:'区间存在身份、调整或结构冲突',unclassified_source_failure:'区间存在未分类的来源核验失败',
  unsupported_source:'当前仅支持已核对格式的腾讯日线',unsupported_period:'来源周期不属于本入口的日线范围',known_negative_source:'已知负样本不进入来源算术',source_identity_conflict:'来源证券身份存在冲突',source_adjustment_conflict:'来源复权声明存在冲突',source_structure_failed:'来源整体结构核验失败',unsupported_source_check:'来源含未支持的整体核验失败',scope_conflict:'来源与A股、CNY或中国日线日期范围冲突',
  corporate_action_unresolved:'存在未解决的公司行动，仅保留来源诊断',halted_endpoint_source_value:'端点有已知停牌，仅保留来源诊断',
  invalid_dates:'共同起点须是有效日期，且早于终点',group_result_limit:'结果超过2 MiB预算，请减少成员',group_fraction_limit:'精确分数超过本入口预算',research_member_limit:'本入口需要4–50个不同数据版本',duplicate_member:'同一证券只可选择一个数据版本',invalid_group_endpoint_response:'响应与共同日期、成员或精确算术约定不符，结果已清空',
  research_row_limit:'完整来源超过每股20,000条或合计200,000条预算；修改日期不会缩减读取',universe_row_limit:'完整来源合计超过200,000条预算',
};
export const groupReason = (code: string) => Object.hasOwn(groupReasons,code) ? groupReasons[code] : `来源限制：${code}`;
