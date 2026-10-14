import {dispersionContext, dispersionContextKey} from './selected-dispersion.ts';
import type {DispersionContext} from './selected-dispersion.ts';
export const declineContext=dispersionContext, declineContextKey=dispersionContextKey;
export type DeclineContext=DispersionContext;
export interface Rational {numerator:string;denominator:string}
export interface DeclineMember {index:number;date:string;ordinal:string|null;open:string|null;high:string|null;low:string|null;close:string|null;source_reason:string|null}
export interface Point {bar_index:number;date:string;ordinal:string;price_exact:string;slot?:string;path_position?:number}
export interface Bound {value:Rational;witness:{peak:Point;trough:Point;hypothetical?:boolean;path_id?:string}|null}
export interface DeclineReport {
 analysis_id:string; identity:{snapshot_id:string;batch_id:string;query_id:string;raw_sha256:string;source_contract_id:string;selection:Record<string,unknown>;symbol_identity:Record<string,unknown>;source_qualification:unknown};
 window:{requested_start:string;requested_end:string;resolved_start:string|null;resolved_end:string|null;bar_count:number;first_open_initialization:true};
 members:DeclineMember[];invalid_members:{index:number;date:string;ordinal:string|null;reason:string}[];
 status:'computed'|'unavailable';reason:string|null;reasons:string[];missing_endpoints:string[];
 coverage:Record<string,number|boolean>;source_qualification:unknown;source_conflict_counts:Record<string,number>;
 lower:Bound|null;upper:Bound|null;close_only:Bound|null;identified:boolean|null;ambiguity_width:Rational|null;
}
function fail():never {throw new Error('invalid_query_response');}
const object=(v:unknown):v is Record<string,unknown>=>!!v&&typeof v==='object'&&!Array.isArray(v);
const integer=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
const code=(v:unknown):v is string=>typeof v==='string'&&/^[a-z][a-z0-9_]{0,79}$/.test(v);
export const validDay=(v:unknown):v is string=>typeof v==='string'&&/^\d{4}-\d{2}-\d{2}$/.test(v)&&v.slice(0,4)!=='0000'&&Number.isFinite(Date.parse(v+'T00:00:00Z'))&&new Date(v+'T00:00:00Z').toISOString().slice(0,10)===v;
const fields=['open','high','low','close'] as const;
const limitations=['hypothetical_extremizers','window_pre_history_excluded','calendar_and_bar_finality_unverified','adjustment_and_corporate_actions_unverified','historical_availability_unverified','source_values_not_economic_wealth','upper_not_full_real_interval_bound_if_observations_missing','no_prediction_or_execution_claim'];
const paths={lower:'olhc-extremizer-v1',upper:'ohlc-extremizer-v1'};
/** Root depth 0, object keys and values each count one node, matching HTTP. */
export function guardDeclineStructure(value:unknown):void {
 const stack:[unknown,number][]=[[value,0]];let nodes=0;
 while(stack.length){const [item,depth]=stack.pop()!;if(++nodes>65536||depth>64||typeof item==='number'&&!Number.isFinite(item))fail();
  if(typeof item==='string'&&item.length>262144)fail();
  if(Array.isArray(item)){if(nodes+stack.length+item.length>65536)fail();for(const child of item)stack.push([child,depth+1]);}
  else if(object(item)){const entries=Object.entries(item);if(nodes+stack.length+entries.length*2>65536)fail();for(const [key,child]of entries)stack.push([key,depth+1],[child,depth+1]);}
 }
}
function equal(a:unknown,b:unknown):boolean {
 if(a===b)return true;
 if(Array.isArray(a)&&Array.isArray(b))return a.length===b.length&&a.every((v,i)=>equal(v,b[i]));
 if(object(a)&&object(b)){const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(k=>Object.hasOwn(b,k)&&equal(a[k],b[k]));}return false;
}
function freeze<T>(v:T):T {if(v&&typeof v==='object'){Object.values(v).forEach(freeze);Object.freeze(v);}return v;}
function scaled(v:unknown):bigint {
 if(typeof v!=='string'||! /^-?(?:0|[1-9]\d{0,19})(?:\.\d{1,18})?$/.test(v)||v==='-0'||v.includes('.')&&v.endsWith('0'))fail();
 const negative=v.startsWith('-'),[whole,part='']=v.replace('-','').split('.');return (negative?-1n:1n)*BigInt(whole+part.padEnd(18,'0'));
}
function gcd(a:bigint,b:bigint):bigint {while(b){[a,b]=[b,a%b];}return a;}
function rational(v:unknown,digits=38):[bigint,bigint] {
 if(!object(v)||Object.keys(v).length!==2||typeof v.numerator!=='string'||typeof v.denominator!=='string'||! /^(?:0|[1-9]\d*)$/.test(v.numerator)||! /^[1-9]\d*$/.test(v.denominator)||v.numerator.length>digits||v.denominator.length>digits)fail();
 const n=BigInt(v.numerator),d=BigInt(v.denominator);if(n>=d||gcd(n,d)!==1n)fail();return[n,d];
}
export function formatFraction(v:Rational):string {
 const[n,d]=rational(v,76);if(n===0n)return '0%';if(n*1000000n<d)return '小于0.0001%';
 const rounded=(n*1000000n*2n+d)/(2n*d);return `约${rounded/10000n}.${String(rounded%10000n).padStart(4,'0')}%`;
}
const venues:Record<string,string>={SSE:'SH',XSHG:'SH',SZSE:'SZ',XSHE:'SZ',BSE:'BJ',HKEX:'HK',SEHK:'HK',XHKG:'HK',XNAS:'NASDAQ',XNYS:'NYSE'};
const markets:Record<string,string>={SH:'CN_A',SZ:'CN_A',BJ:'CN_A',HK:'HK',NYSE:'US',NASDAQ:'US',AMEX:'US'};
const venue=(v:unknown):string|null=>typeof v==='string'&&v.trim()?venues[v.trim().toUpperCase()]??v.trim().toUpperCase():null;
function claim(v:unknown,place:unknown):[string|null,string|null] {
 let market=venue(place);if(typeof v!=='string'||!v.trim())return[null,market];v=v.trim().toUpperCase();let name=v as string,embedded:string|null=null;
 const parts=name.split('.');if(parts.length>=2&&markets[venue(parts.at(-1))??'']){name=parts.slice(0,-1).join('.');embedded=venue(parts.at(-1));}
 else if(parts.length>=2&&markets[venue(parts[0])??'']){name=parts.slice(1).join('.');embedded=venue(parts[0]);}
 else if(/^(SH|SZ|BJ)[0-9]{6}$/.test(name)){embedded=name.slice(0,2);name=name.slice(2);}
 if(embedded&&market&&embedded!==market)fail();market=embedded??market;
 if(!/^[A-Z0-9][A-Z0-9.-]{0,31}$/.test(name)||['SH','SZ','BJ'].includes(market??'')&&!/^\d{6}$/.test(name))fail();return[name,market];
}
function symbol(context:DeclineContext):Record<string,unknown> {
 const declaration=context.interpretation??{};if(!object(declaration))fail();
 const[sc,sv]=claim(context.sourceCode,context.sourceVenue),[dc,dv]=claim(declaration.instrument,declaration.venue);
 if(sc&&dc&&sc!==dc||sv&&dv&&sv!==dv)fail();const c=sc??dc,v=sv??dv;if(!c||!v||!markets[v])fail();
 const declared=!!(dc||dv&&!sv);return {symbol:`${c}.${v}`,code:c,venue:v,market:markets[v],qualification:sc?(declared?'source_claim_and_declared':'source_claim'):'declared'};
}
export function acceptDeclineBounds(value:unknown,context:DeclineContext,start:string,end:string):DeclineReport {
 guardDeclineStructure(value);
 if(!validDay(start)||!validDay(end)||start>end||context.cutoff!==null&&end>context.cutoff||context.mode!=='retrospective'||context.period!=='1d'||!object(value))fail();
 const v=value;
 if(typeof v.analysis_id!=='string'||! /^[0-9a-f]{64}$/.test(v.analysis_id)||v.view_method_id!=='selected-source-ohlc-decline-bounds-v1'||v.method_id!=='source-ohlc-compatible-max-decline-v1'||v.adapter_id!=='daily-bars-positive-selected-window-strict-coverage-v1'||v.numeric_policy_id!=='scaled18-rational-earliest-extremizer-v1'||v.scope!=='supplied_bars_compatible_paths'||!equal(v.path_ids,paths)||!equal(v.limitations,limitations)||v.source_conflict_policy!=='first_rejection_per_source_row'||v.suppressed_source_predicates!=='not_evaluated_after_first_rejection'||v.calendar_completeness!=='unverified'||v.price_evidence!=='normalized_source_values'||v.raw_token_status!=='not_embedded')fail();
 const id=v.identity,w=v.window,c=v.coverage;
 if(!object(id)||['snapshot_id','batch_id','query_id','source_contract_id'].some(k=>typeof id[k]!=='string'||!id[k]||new TextEncoder().encode(id[k] as string).length>256)||typeof id.snapshot_id!=='string'||! /^[0-9a-f]{64}$/.test(id.snapshot_id)||typeof id.raw_sha256!=='string'||! /^[0-9a-f]{64}$/.test(id.raw_sha256))fail();
 if(!object(id)||id.snapshot_id!==context.snapshotId||id.batch_id!==context.batchId||id.raw_sha256!==context.raw||id.source_contract_id!==context.contract||typeof id.query_id!=='string'||!id.query_id||new TextEncoder().encode(id.query_id).length>256||!equal(id.selection,{mode:'retrospective',cutoff:end,ordinal_start:null,ordinal_end:null})||!equal(id.symbol_identity,symbol(context))||!Object.hasOwn(id,'source_qualification')||!equal(id.source_qualification,context.sourceQualification??null)||!equal(v.source_qualification,id.source_qualification))fail();
 if(!object(w)||w.requested_start!==start||w.requested_end!==end||w.first_open_initialization!==true||!object(c)||!Array.isArray(v.members)||v.members.length>253||w.bar_count!==v.members.length)fail();
 const counts=['source_rows','date_groups','valid_groups','invalid_groups','duplicate_groups','unlocated_rows','unreadable_date_rows','batch_unlocated_rows'];if(counts.some(k=>!integer(c[k])))fail();
 const n=c as Record<string,number>;
 if(n.source_rows>20000||n.date_groups>n.source_rows||n.valid_groups+n.invalid_groups!==n.date_groups||n.duplicate_groups>n.invalid_groups||n.unlocated_rows>n.source_rows||n.unreadable_date_rows>n.unlocated_rows||n.batch_unlocated_rows<n.unlocated_rows||c.coverage_known!==(n.unlocated_rows===0&&n.batch_unlocated_rows===0)||v.members.length>n.date_groups)fail();
 const bad:DeclineReport['invalid_members']=[],seen=new Set<string>();let prior='';
 const memberReasons=['duplicate_date','unlocated_label','missing_ohlc','invalid_price','invalid_ohlc','invalid_source_ordinal','known_negative_source','source_identity_conflict','source_adjustment_conflict','source_adjustment_check_failed'];
 for(const [i,m]of v.members.entries()){
  if(!object(m)||m.index!==i||!validDay(m.date)||m.date<start||m.date>end||m.date<=prior||!(m.ordinal===null||typeof m.ordinal==='string'&&/^(?:0|[1-9]\d{0,18})$/.test(m.ordinal)&&BigInt(m.ordinal)<=9223372036854775807n)||!(m.source_reason===null||memberReasons.includes(String(m.source_reason))))fail();prior=m.date;
  const prices=fields.map(k=>m[k]===null?null:scaled(m[k]));
  const ordinalBad=m.ordinal===null||seen.has(m.ordinal as string);if(m.ordinal!==null)seen.add(m.ordinal as string);
  const[o,h,l,cl]=prices;
  if(m.source_reason===null&&(ordinalBad||prices.some(p=>p===null||p<=0n)||l!>o!||o!>h!||l!>cl!||cl!>h!))fail();
  if(m.source_reason==='invalid_source_ordinal'&&(!ordinalBad||prices.some(p=>p===null||p<=0n)||l!>o!||o!>h!||l!>cl!||cl!>h!))fail();
  if(m.source_reason==='duplicate_date'&&(m.ordinal!==null||prices.some(p=>p!==null)))fail();
  if(m.source_reason!==null)bad.push({index:i,date:m.date,ordinal:m.ordinal as string|null,reason:m.source_reason as string});
 }
 if(!equal(v.invalid_members,bad))fail();
 // Ordinal rejection is added after coverage classification, so bad.length may
 // exceed invalid_groups. Only pre-ordinal rejections use that coverage count.
 if(bad.filter(m=>m.reason!=='invalid_source_ordinal').length>n.invalid_groups||v.members.length-bad.length>n.valid_groups)fail();
 const resolvedStart=v.members[0]?.date===start?start:null,resolvedEnd=v.members.at(-1)?.date===end?end:null;
 const missing=[...new Set([...(resolvedStart?[]:[start]),...(resolvedEnd?[]:[end])])];
 if(w.resolved_start!==resolvedStart||w.resolved_end!==resolvedEnd||!equal(v.missing_endpoints,missing))fail();
 const conflicts=v.source_conflict_counts;if(!object(conflicts))fail();let conflictTotal=0;
 for(const[k,count]of Object.entries(conflicts)){if(!['source_identity_conflict','source_adjustment_conflict','source_adjustment_check_failed'].includes(k)||!integer(count)||count===0)fail();conflictTotal+=count;}if(conflictTotal>n.source_rows)fail();
 const rejected=context.quarantined===true||Array.isArray(context.batchChecks)&&context.batchChecks.includes('fail');if(v.source_rejected!==rejected||rejected&&n.valid_groups!==0)fail();
 const unknown=!c.coverage_known||n.unreadable_date_rows>0;
 const expected=[...(rejected?['known_negative_source']:[]),...Object.keys(conflicts),...(unknown?['source_coverage_unknown']:[]),...(missing.length?['endpoint_not_present']:[]),...(bad.length?['invalid_window',...bad.map(m=>m.reason)]:[])];
 if(!equal(v.reasons,[...new Set(expected)]))fail();
 const reason=rejected?'known_negative_source':Object.keys(conflicts)[0]??(unknown?'source_coverage_unknown':missing.length?'endpoint_not_present':bad.length?'invalid_window':null);
 if(v.reason!==reason||v.status!==(reason?'unavailable':'computed'))fail();
 if(reason){for(const key of ['lower','upper','close_only','identified','ambiguity_width'])if(v[key]!==null)fail();}
 else {
  const members=v.members as unknown as DeclineMember[];
  const validateBound=(key:'lower'|'upper'|'close_only'):[bigint,bigint]=>{
   const b=v[key];if(!object(b))fail();const [num,den]=rational(b.value);const witness=b.witness;
   if(num===0n){if(witness!==null)fail();return[num,den];}if(!object(witness))fail();
   const order=key==='lower'?['open','low','high','close']:['open','high','low','close'];
   if(key!=='close_only'&&(witness.hypothetical!==true||witness.path_id!==paths[key]))fail();
   if(key==='close_only'&&(Object.hasOwn(witness,'hypothetical')||Object.hasOwn(witness,'path_id')))fail();
   const points=['peak','trough'].map(name=>{const p=witness[name];if(!object(p)||!integer(p.bar_index)||p.bar_index>=members.length)fail();const m=members[p.bar_index];
    const slot=key==='close_only'?'close':p.slot;if(typeof slot!=='string'||!fields.includes(slot as typeof fields[number])||p.date!==m.date||p.ordinal!==m.ordinal||p.price_exact!==m[slot as typeof fields[number]])fail();
    if(key==='close_only'&&(Object.hasOwn(p,'slot')||Object.hasOwn(p,'path_position')))fail();
    const pos=key==='close_only'?p.bar_index:4*p.bar_index+order.indexOf(slot);if(key!=='close_only'&&p.path_position!==pos)fail();return{pos,price:scaled(p.price_exact)};});
   const[p,t]=points;if(p.pos>=t.pos||p.price<=t.price||(p.price-t.price)*den!==num*p.price)fail();return[num,den];
  };
  const[ln,ld]=validateBound('lower'),[un,ud]=validateBound('upper'),[cn,cd]=validateBound('close_only'),[wn,wd]=rational(v.ambiguity_width,76);
  if(cn*ld>ln*cd||ln*ud>un*ld||wn*ud*ld!==(un*ld-ln*ud)*wd||v.identified!==(ln*ud===un*ld))fail();
 }
 return freeze(structuredClone(v)) as unknown as DeclineReport;
}
export async function readDeclineResponse(response:Response):Promise<unknown>{
 const limit=262144,header=response.headers.get('content-length');
 if(header!==null&&(header.length>16||!/^\d+$/.test(header)||BigInt(header)>BigInt(limit))){await response.body?.cancel();throw new Error('ohlc_result_limit');}
 const reader=response.body?.getReader();if(!reader)fail();const chunks:Uint8Array[]=[];let length=0;
 try{while(true){const part=await reader.read();if(part.done)break;length+=part.value.byteLength;if(length>limit){await reader.cancel();throw new Error('ohlc_result_limit');}chunks.push(part.value);}}
 catch(error){await reader.cancel().catch(()=>{});throw error;}finally{reader.releaseLock();}
 const bytes=new Uint8Array(length);let offset=0;for(const chunk of chunks){bytes.set(chunk,offset);offset+=chunk.length;}
 let value:unknown;try{value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));guardDeclineStructure(value);}catch{return fail();}
 if(!response.ok)throw new Error(object(value)&&code(value.error)?value.error:'invalid_query_response');return value;
}
export async function requestDeclineBounds(context:DeclineContext,start:string,end:string,signal:AbortSignal):Promise<DeclineReport>{
 if(context.period!=='1d'||context.mode!=='retrospective'||!validDay(start)||!validDay(end)||start>end||context.cutoff!==null&&end>context.cutoff)throw new Error('invalid_research_date');
 const params=new URLSearchParams({start,end});const response=await fetch(`/api/research/ohlc-decline-bounds/${encodeURIComponent(context.snapshotId)}?${params}`,{signal,cache:'no-store',credentials:'same-origin'});
 return acceptDeclineBounds(await readDeclineResponse(response),context,start,end);
}
