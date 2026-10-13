/** 060. Exact descriptive arithmetic on an accepted retrospective source prefix. */
import type { ResearchExpected } from './research-model.ts';
import type { ResearchEnvelope, SingleResult } from './research-types.ts';
import type { EventPathContext } from './single-event-path.ts';
import { validGroupDate } from './group-endpoint-model.ts';
import { groupPathCanonical } from './group-source-path-model.ts';
export type ReversalMode = 'up' | 'down';
export interface ReversalPoint { index: number; date: string; ordinal: string; close_exact: string; close_token: null; token_status: 'unavailable_in_parent_report' }
export interface ReversalOptions { signal?: AbortSignal; yieldControl?: () => Promise<void> }
export interface ReversalContext extends EventPathContext { batchId: string }
export interface ReversalEvent {
 initial_mode: ReversalMode; direction: ReversalMode; anchor_index: number; confirmation_index: number;
 anchor_close_exact: string; confirmation_close_exact: string; anchor: ReversalPoint; confirmation: ReversalPoint;
 signed_relative_change: {numerator:string;denominator:string}; magnitude: {numerator:string;denominator:string};
 confirmation_delay_source_intervals: number; first_event_initialization_warning: boolean;
}
export interface ReversalTerminal { mode: ReversalMode; extreme_index:number; extreme_close_exact:string; last_observation_index:number; confirmed:false; extreme:ReversalPoint; last_observation:ReversalPoint }
export interface ReversalModeResult { initial_mode:ReversalMode; count:number|null; events:ReversalEvent[]|null; terminal:ReversalTerminal|null }
export interface ReversalSource {
 readonly token:object; readonly report:ResearchEnvelope<SingleResult>; readonly context:Readonly<ReversalContext>;
 readonly signature: string;
 readonly evidence: { identity:{snapshot_id:string;batch_id:string;owner_query_id:string;research_query_id:string;parent_analysis_id:string;requested_cutoff:string|null};
  coverage:Record<string,unknown>; rejected_observations:readonly {index:number;date:string;ordinal:number|null;close:string|null;reason:string|null;status:string}[]; qualification:string; limitations:readonly string[];
  points:readonly ReversalPoint[]; reasons:Readonly<Record<string,number>>; source_rows:number };
}
export interface ReversalReport {
 method_id:'close-reversal-records-v1';rule_version:'exact-close-bps-earliest-tie-both-initial-v1'; report_id:string;
 mode:'retrospective'; status:'complete'|'unavailable'; source:ReversalSource['evidence'];
 parameters:{threshold_bps:number;initial_modes:readonly ['up','down'];initialization:'full_source_prefix';tie_policy:'earliest_equal_extreme'};
 modes:Record<ReversalMode,ReversalModeResult>; limitations:readonly string[];
}
const MAX_POINTS=20000, MAX_BYTES=2*1024*1024;
function ensure(value:unknown,code='invalid_context'):asserts value {if(!value)throw new Error(code);}
const identifier=(v:unknown):v is string=>typeof v==='string'&&/^[a-f0-9]{64}$/.test(v);
const integer=(v:unknown):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0;
function freeze<T>(v:T):T {if(v&&typeof v==='object'){Object.values(v).forEach(freeze);Object.freeze(v);}return v;}
export function parseThresholdBps(v:unknown):number {
 ensure(typeof v==='number'&&Number.isInteger(v)||typeof v==='string'&&/^[1-9]\d{0,3}$/.test(v),'invalid_threshold');
 const n=Number(v);ensure(n>=1&&n<=9999,'invalid_threshold');return n;
}
function price(v:unknown):bigint {
 ensure(typeof v==='string'&&v.length<=39&&/^(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(v),'invalid_price');
 const [whole,part='']=v.split('.'), n=BigInt(whole+part.padEnd(18,'0'));ensure(n>0n&&n<10n**38n,'invalid_price');return n;
}
function fraction(n:bigint,d:bigint){let a=n<0n?-n:n,b=d;while(b){const r=a%b;a=b;b=r;}return {numerator:(n/a).toString(),denominator:(d/a).toString()};}
function abort(o:ReversalOptions){ensure(!o.signal?.aborted,'cancelled');}
async function pause(o:ReversalOptions){abort(o);await(o.yieldControl?o.yieldControl():new Promise<void>(resolve=>setTimeout(resolve,0)));abort(o);}
function checkPoints(points:readonly ReversalPoint[]):bigint[] {
 ensure(Array.isArray(points)&&points.length>0&&points.length<=MAX_POINTS,'resource_limit');const ordinals=new Set<string>();let previous='';
 return points.map((p,i)=>{ensure(p.index===i&&validGroupDate(p.date)&&p.date>previous&&typeof p.ordinal==='string'&&/^[1-9]\d{0,15}$/.test(p.ordinal)&&Number.isSafeInteger(Number(p.ordinal))&&!ordinals.has(p.ordinal)&&p.close_token===null&&p.token_status==='unavailable_in_parent_report');previous=p.date;ordinals.add(p.ordinal);return price(p.close_exact);});
}
export async function scanCloseReversals(input:readonly ReversalPoint[],thresholdBps:unknown,options:ReversalOptions={}):Promise<Record<ReversalMode,ReversalModeResult & {count:number;events:ReversalEvent[];terminal:ReversalTerminal}>> {
 abort(options);const bps=BigInt(parseThresholdBps(thresholdBps));ensure(Array.isArray(input)&&input.length<=MAX_POINTS,'resource_limit');
 const points=freeze(input.map(p=>({...p}))), values=checkPoints(points);
 const result={} as Record<ReversalMode,ReversalModeResult & {count:number;events:ReversalEvent[];terminal:ReversalTerminal}>;
 for(const initial_mode of ['up','down'] as const){let mode:ReversalMode=initial_mode,extreme=0;const events:ReversalEvent[]=[];
  for(let i=1;i<points.length;i++){
   const value=values[i],anchorValue=values[extreme];
   if(mode==='up'?value>anchorValue:value<anchorValue)extreme=i;
   else {const change=value-anchorValue,magnitude=change<0n?-change:change;
    if(magnitude*10000n>=anchorValue*bps){const direction:ReversalMode=mode==='up'?'down':'up';
     events.push({initial_mode,direction,anchor_index:extreme,confirmation_index:i,anchor_close_exact:points[extreme].close_exact,confirmation_close_exact:points[i].close_exact,
      signed_relative_change:fraction(change,anchorValue),magnitude:fraction(magnitude,anchorValue),confirmation_delay_source_intervals:i-extreme,first_event_initialization_warning:events.length===0,anchor:points[extreme],confirmation:points[i]});mode=direction;extreme=i;
    }
   }
   if(i%256===0)await pause(options);
  }
  result[initial_mode]={initial_mode,count:events.length,events,terminal:{mode,extreme_index:extreme,extreme_close_exact:points[extreme].close_exact,last_observation_index:points.length-1,confirmed:false,extreme:points[extreme],last_observation:points[points.length-1]}};
 }
 abort(options);return freeze(result);
}
export function reversalContextMatches(a:ReversalContext,b:ReversalContext):boolean {return a.ownerQueryId===b.ownerQueryId&&a.snapshotId===b.snapshotId&&a.batchId===b.batchId&&a.cutoff===b.cutoff&&a.ordinalStart===b.ordinalStart&&a.ordinalEnd===b.ordinalEnd;}
/** Called once after the existing complete parent DTO acceptance, never during render. */
export function captureReversalSource(report:ResearchEnvelope<SingleResult>,context:ReversalContext,expected:ResearchExpected):ReversalSource {
 const r=report.result,c=r.coverage,p=report.parameters;
 ensure(expected.kind==='single'&&report.method_id==='daily-causal-research-v1'&&report.mode==='retrospective'&&identifier(report.analysis_id)&&identifier(context.batchId)&&identifier(context.ownerQueryId)&&identifier(context.snapshotId)
  &&report.inputs.length===1&&report.inputs[0].snapshot_id===context.snapshotId&&identifier(report.inputs[0].query_id)&&expected.snapshotIds.length===1&&expected.snapshotIds[0]===context.snapshotId
  &&p.cutoff===context.cutoff&&p.cutoff===expected.parameters.cutoff&&p.horizon===expected.parameters.horizon&&p.lookback===expected.parameters.lookback&&p.test_start===expected.parameters.test_start
  &&(context.cutoff===null||validGroupDate(context.cutoff))&&r.parameters.initialization==='full_source_prefix'&&r.parameters.period==='1d');
 ensure(Array.isArray(r.series)&&r.series.length<=MAX_POINTS&&Array.isArray(report.limitations)&&['retrospective_source_version','calendar_and_bar_closure_unverified','historical_availability_unverified','adjustment_basis_unverified'].every(x=>report.limitations.includes(x)));
 const countKeys=['source_rows','date_groups','valid_groups','invalid_groups','duplicate_groups','unlocated_rows','unreadable_date_rows','batch_unlocated_rows'] as const;
 ensure(c&&countKeys.every(k=>integer(c[k]))&&typeof c.coverage_known==='boolean'&&c.date_groups===r.series.length&&Number(c.valid_groups)+Number(c.invalid_groups)===c.date_groups);
 ensure(Number(c.source_rows)<=MAX_POINTS&&Number(c.source_rows)>=r.series.length,'resource_limit');
 const reasonCounts=new Map<string,number>();const add=(key:string,n=1)=>{reasonCounts.set(key,(reasonCounts.get(key)??0)+n);};
 for(const k of ['invalid_groups','duplicate_groups','unlocated_rows','unreadable_date_rows','batch_unlocated_rows'])if(Number(c[k])>0)add(k,Number(c[k]));
 if(Number(c.source_rows)!==r.series.length)add('source_row_count_mismatch');
 if(!c.coverage_known)add('source_coverage_unknown');if(r.qualification!=='conditional_source_observations')add(r.qualification);
 if(!r.series.length)add('no_source_observations');
 const points:ReversalPoint[]=[];let previous='';const ordinals=new Set<number>();
 for(const [index,row]of r.series.entries()){
  ensure(validGroupDate(row.date)&&row.date>previous&&(context.cutoff===null||row.date<=context.cutoff));previous=row.date;
  if(row.reason!==null&&row.reason!=='numerical_failure')add(row.reason);
  if(row.ordinal===null||!integer(row.ordinal)||row.ordinal<1||ordinals.has(row.ordinal)){add('invalid_source_ordinal');continue;}ordinals.add(row.ordinal);
  try{price(row.close);}catch{add('invalid_price');continue;}
  points.push({index,date:row.date,ordinal:String(row.ordinal),close_exact:row.close!,close_token:null,token_status:'unavailable_in_parent_report'});
 }
 const reasons=Object.fromEntries(reasonCounts);
 // Invalid observations remain represented by their original coverage and reasons;
 // no shortened point sequence is eligible for the recurrence.
 const evidence=freeze({identity:{snapshot_id:context.snapshotId,batch_id:context.batchId,owner_query_id:context.ownerQueryId,research_query_id:report.inputs[0].query_id,parent_analysis_id:report.analysis_id,requested_cutoff:context.cutoff},coverage:{...c},rejected_observations:Object.keys(reasons).length?r.series.map((row,index)=>({index,date:row.date,ordinal:row.ordinal,close:row.close,reason:row.reason,status:row.status})):[],qualification:r.qualification,limitations:[...report.limitations],points:points as readonly ReversalPoint[],reasons,source_rows:Number(c.source_rows)});
 return Object.freeze({token:Object.freeze({}),report,signature:sourceSignature(report),context:Object.freeze({...context}),evidence});
}
function sourceSignature(report:ResearchEnvelope<SingleResult>):string {
 ensure(Array.isArray(report.result.series)&&report.result.series.length<=MAX_POINTS,'resource_limit');
 return groupPathCanonical({method_id:report.method_id,analysis_id:report.analysis_id,mode:report.mode,inputs:report.inputs,parameters:report.parameters,limitations:report.limitations,
  coverage:report.result.coverage,qualification:report.result.qualification,model:report.result.parameters,series:report.result.series.map(({date,ordinal,close,reason,status})=>({date,ordinal,close,reason,status}))});
}
/** Event/async boundary only. Never called by the render availability guard. */
export function reversalSourceFresh(source:ReversalSource):boolean {try{return sourceSignature(source.report)===source.signature;}catch{return false;}}
export function checkReversalBudget(value:unknown):void {ensure(new TextEncoder().encode(JSON.stringify(value)).length<=MAX_BYTES,'resource_limit');}
export async function buildReversalReport(source:ReversalSource,thresholdBps:unknown,options:ReversalOptions={}):Promise<ReversalReport> {
 abort(options);ensure(reversalSourceFresh(source),'cancelled');const bps=parseThresholdBps(thresholdBps),unavailable=Object.keys(source.evidence.reasons).length>0;
 const modes:Record<ReversalMode,ReversalModeResult>=unavailable?{up:{initial_mode:'up',count:null,events:null,terminal:null},down:{initial_mode:'down',count:null,events:null,terminal:null}}:await scanCloseReversals(source.evidence.points,bps,options);
 const result:ReversalReport={method_id:'close-reversal-records-v1',rule_version:'exact-close-bps-earliest-tie-both-initial-v1',report_id:'',mode:'retrospective',status:unavailable?'unavailable':'complete',source:source.evidence,
  parameters:{threshold_bps:bps,initial_modes:['up','down'],initialization:'full_source_prefix',tie_policy:'earliest_equal_extreme'},modes,
  limitations:[...source.evidence.limitations,'canonical_close_only_raw_token_unavailable','batch_identity_from_owner_query_not_certified_by_parent_response','no_intrabar_path','no_forecast_or_trading_return','initialization_dependent','no_tradingview_ohlc_equivalence']};
 checkReversalBudget({...result,report_id:'0'.repeat(64)});
 const {report_id:_,...identity}=result;const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(groupPathCanonical(identity)));abort(options);
 ensure(reversalSourceFresh(source),'cancelled');result.report_id=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');checkReversalBudget(result);return freeze(result);
}
