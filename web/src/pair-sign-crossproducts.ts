/** 059: bounded descriptive arithmetic; no reads and no second correlation estimate. */
import { assertGroupPairs, groupPairRequest, verifyGroupPairIdentity } from './group-pair-model.ts';
import type { GroupPairReport, GroupPairExpected, GroupPairCell, GroupPairMember } from './group-pair-model.ts';
import { groupPathCanonical } from './group-source-path-model.ts';
import { validGroupDate } from './group-endpoint-model.ts';
export interface PairSignOptions { signal?: AbortSignal; yieldControl?: () => Promise<void> }
export interface PairSignFraction { n: string; d: string }
export interface PairSignEndpoint { index: number; date: string; ordinal: number; close_exact: string; close_token: string|null }
interface Side { ids: {snapshot:string;batch:string;query:string}; endpoints: PairSignEndpoint[] }
export interface PairSignInput { cutoff:string; common_dates:string[]; left:Side; right:Side }
export interface PairSignSelection { left_snapshot_id:string; right_snapshot_id:string }
const cells=['nn','nz','np','zn','zz','zp','pn','pz','pp'] as const;
const terms=['pp','nn','pn','np','centering','centered_cross'] as const;
type Term=typeof terms[number];
export interface PairSignWindow { start_index:number; end_index:number; interval_count:60; rows:{right_index:number;left_change:PairSignFraction;right_change:PairSignFraction;sign_cell:string;product:PairSignFraction}[]; counts:Record<string,number>; terms:Record<Term|'denominator',string>; display:Record<Term,string> }
export interface PairSignAttachment {
 method_id:'pair-sign-crossproducts-v1'; rule_version:'source-simple-60x2-zero-threshold-v1'; parent_analysis_id:string; parent_content_hash:string;
 pair:PairSignSelection; cutoff:string; status:'complete'|'unavailable'; reason:null|'source_panel_unavailable';
 source_refs:{left:GroupPairMember;right:GroupPairMember};
 windows:Record<'previous'|'current',(PairSignWindow & {parent_correlation_state:GroupPairCell})|null>;
 limitations:{flags:string[];parent_reasons:string[];parent_grid_reasons:string[];parent_limitations:GroupPairReport['limitations']};
}
function ensure(v:unknown,code='invalid_context'):asserts v {if(!v)throw new Error(code);}
function bounded(v:bigint,bits=16000){ensure((v<0n?-v:v).toString(2).length<=bits,'numeric_limit');return v;}
function gcd(a:bigint,b:bigint):bigint {a=a<0n?-a:a;while(b){const r=a%b;a=b;b=r;}return a;}
function fraction(n:bigint,d:bigint):PairSignFraction {bounded(n);bounded(d);const g=gcd(n,d);return {n:(n/g).toString(),d:(d/g).toString()};}
function integer(s:string){ensure(typeof s==='string'&&s.length<=4820&&/^(?:0|-?[1-9]\d*)$/.test(s),'numeric_limit');return bounded(BigInt(s));}
export function formatPairSignFraction(n:string,d:string):string {
 let a=integer(n);const b=integer(d);ensure(b>0n,'numeric_limit');if(a===0n)return '0';const sign=a<0n?'-':'';a=a<0n?-a:a;
 let e=a.toString().length-b.toString().length;
 if(e>=0 ? a<bounded(b*10n**BigInt(e),32000) : bounded(a*10n**BigInt(-e),32000)<b)e--;
 const power=4-e,top=power>=0?bounded(a*10n**BigInt(power),32000):a, bottom=power<0?bounded(b*10n**BigInt(-power),32000):b;
 let q=top/bottom;const r=top%bottom,twice=bounded(2n*r,32000);if(twice>bottom||twice===bottom&&q%2n===1n)q++;
 if(q===100000n){q=10000n;e++;}const digits=q.toString();const result=`${sign}${digits[0]}.${digits.slice(1)}e${e>=0?'+':''}${e}`;ensure(result.length<=32,'numeric_limit');return result;
}
function price(v:unknown){ensure(typeof v==='string'&&v.length<=39&&/^(?:0|[1-9]\d{0,19})(?:\.\d{0,17}[1-9])?$/.test(v),'invalid_price');const [a,b='']=v.split('.');const n=BigInt(a+b.padEnd(18,'0'));ensure(n>0n&&n<10n**38n,'invalid_price');return n;}
function abort(options:PairSignOptions){ensure(!options.signal?.aborted,'cancelled');}
async function pause(options:PairSignOptions){abort(options);await(options.yieldControl?options.yieldControl():new Promise<void>(r=>setTimeout(r,0)));abort(options);}
function freeze<T>(v:T):T {if(v&&typeof v==='object'){Object.values(v).forEach(freeze);Object.freeze(v);}return v;}
function bytes(v:unknown){try{return new TextEncoder().encode(JSON.stringify(v)).length;}catch{throw new Error('invalid_context');}}
/** Retain every structural key and all original source text; strip only calculated numeric strings. */
export function checkPairSignBudgets(value:unknown):void {
 ensure(bytes(value)<=512*1024,'resource_limit');
 const metadata=structuredClone(value) as {windows?:Record<string,PairSignWindow|null>};
 for(const w of Object.values(metadata.windows??{})){if(!w)continue;for(const row of w.rows??[]){for(const f of [row.left_change,row.right_change,row.product]){f.n='';f.d='';}}for(const key of Object.keys(w.terms??{}))w.terms[key as Term]='';for(const key of Object.keys(w.display??{}))w.display[key as Term]='';}
 ensure(bytes(metadata)<=128*1024,'resource_limit');
}
function validate(input:PairSignInput):[bigint[],bigint[]] {
 ensure(input&&validGroupDate(input.cutoff)&&Array.isArray(input.common_dates)&&input.common_dates.length===121);
 ensure(input.common_dates.every((d,i)=>validGroupDate(d)&&(i===0||d>input.common_dates[i-1]))&&input.common_dates[120]===input.cutoff);
 const ids={snapshot:new Set<string>(),batch:new Set<string>(),query:new Set<string>()};
 return [input.left,input.right].map(side=>{
  ensure(side&&side.ids&&Object.values(side.ids).length===3&&['snapshot','batch','query'].every(k=>/^[a-f0-9]{64}$/.test(side.ids[k as keyof Side['ids']])));
  for(const key of ['snapshot','batch','query'] as const){const id=side.ids[key];ensure(!ids[key].has(id));ids[key].add(id);}
  ensure(Array.isArray(side.endpoints)&&side.endpoints.length===121);const ordinals=new Set<number>();
  return side.endpoints.map((p,i)=>{ensure(p&&p.index===i&&p.date===input.common_dates[i]&&Number.isSafeInteger(p.ordinal)&&p.ordinal>0&&!ordinals.has(p.ordinal)&&(p.close_token===null||typeof p.close_token==='string'));ordinals.add(p.ordinal);return price(p.close_exact);});
 }) as [bigint[],bigint[]];
}
export async function calculatePairSignWindows(input:PairSignInput,options:PairSignOptions={}):Promise<Record<'previous'|'current',PairSignWindow>> {
 abort(options);ensure(bytes(input)<=128*1024,'resource_limit');const captured=freeze(structuredClone(input));const [left,right]=validate(captured);
 const result={} as Record<'previous'|'current',PairSignWindow>;
 for(const [key,start]of [['previous',0],['current',60]] as const){
  let lx=1n,ly=1n;for(let t=start;t<start+60;t++){lx=bounded(lx/gcd(lx,left[t])*left[t]);ly=bounded(ly/gcd(ly,right[t])*right[t]);if((t-start+1)%8===0)await pause(options);}
  const denominator=bounded(60n*bounded(lx*ly)), sums={pp:0n,nn:0n,pn:0n,np:0n};let sx=0n,sy=0n;
  const rows:PairSignWindow['rows']=[],counts=Object.fromEntries(cells.map(c=>[c,0]));
  for(let t=start+1;t<=start+60;t++){
   const dx=left[t]-left[t-1],dy=right[t]-right[t-1],vx=bounded(dx*(lx/left[t-1])),vy=bounded(dy*(ly/right[t-1]));
   sx=bounded(sx+vx);sy=bounded(sy+vy);const sign=(n:bigint)=>n<0n?'n':n>0n?'p':'z',cell=sign(dx)+sign(dy);counts[cell]++;
   if(!cell.includes('z')){const v=bounded(vx*vy);sums[cell as keyof typeof sums]=bounded(sums[cell as keyof typeof sums]+(v<0n?-v:v));}
   rows.push({right_index:t,left_change:fraction(dx,left[t-1]),right_change:fraction(dy,right[t-1]),sign_cell:cell,product:fraction(dx*dy,left[t-1]*right[t-1])});
   if((t-start)%8===0)await pause(options);
  }
  const pp=bounded(60n*sums.pp),nn=bounded(60n*sums.nn),pn=bounded(60n*sums.pn),np=bounded(60n*sums.np),centering=bounded(sx*sy),centered_cross=bounded(pp+nn-pn-np-centering);
  const values={pp,nn,pn,np,centering,centered_cross};
  result[key]={start_index:start,end_index:start+60,interval_count:60,rows,counts,terms:{denominator:denominator.toString(),...Object.fromEntries(terms.map(k=>[k,values[k].toString()]))} as PairSignWindow['terms'],display:Object.fromEntries(terms.map(k=>[k,formatPairSignFraction(values[k].toString(),denominator.toString())])) as PairSignWindow['display']};
 }
 abort(options);ensure(groupPathCanonical(input)===groupPathCanonical(captured),'cancelled');checkPairSignBudgets({windows:result});return freeze(result);
}
export async function pairSignParentHash(parent:unknown):Promise<string>{const digest=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(groupPathCanonical(parent)));return Array.from(new Uint8Array(digest),v=>v.toString(16).padStart(2,'0')).join('');}
export async function buildPairSignAttachment(report:GroupPairReport,expected:GroupPairExpected,pair:PairSignSelection,options:PairSignOptions={}) {
 abort(options);ensure(bytes(report)<=2*1024*1024,'resource_limit');
 const parent=freeze(structuredClone(report)),request=freeze(structuredClone(expected)),selection=freeze({left_snapshot_id:pair.left_snapshot_id,right_snapshot_id:pair.right_snapshot_id});
 try{assertGroupPairs(parent,groupPairRequest(request).expected);}catch{throw new Error('invalid_context');}
 ensure(selection.left_snapshot_id!==selection.right_snapshot_id);
 const left=parent.members.find(m=>m.snapshot_id===selection.left_snapshot_id),right=parent.members.find(m=>m.snapshot_id===selection.right_snapshot_id);
 const selected=parent.pairs.find(p=>[p.left_snapshot_id,p.right_snapshot_id].includes(selection.left_snapshot_id)&&[p.left_snapshot_id,p.right_snapshot_id].includes(selection.right_snapshot_id));ensure(left&&right&&selected);
 try{await verifyGroupPairIdentity(parent);}catch{throw new Error('invalid_context');}abort(options);
 const parent_content_hash=await pairSignParentHash(parent);abort(options);
 const ref=(m:GroupPairMember)=>({...m,endpoints:m.endpoints?.map((p,index)=>({...p,index}))??null});
 const attachment:PairSignAttachment={method_id:'pair-sign-crossproducts-v1',rule_version:'source-simple-60x2-zero-threshold-v1',parent_analysis_id:parent.analysis_id,parent_content_hash,pair:selection,cutoff:request.cutoff,status:'unavailable',reason:'source_panel_unavailable',source_refs:{left:ref(left),right:ref(right)},windows:{previous:null,current:null},limitations:{flags:['retrospective_source_prices','no_causal_attribution','no_tail_dependence','no_forecast','no_portfolio_return','unknown_corporate_actions/PIT','human_efficiency_not_evaluated'],parent_reasons:parent.reasons,parent_grid_reasons:parent.grid_reasons,parent_limitations:parent.limitations}};
 checkPairSignBudgets(attachment);
 if(parent.source_panel_complete){
  const side=(m:GroupPairMember):Side=>({ids:{snapshot:m.snapshot_id,batch:m.batch_id,query:m.query_id},endpoints:m.endpoints!.map((p,index)=>({index,date:p.date,ordinal:p.ordinal!,close_exact:p.close_exact!,close_token:p.close_token}))});
  const windows=await calculatePairSignWindows({cutoff:request.cutoff,common_dates:parent.used_dates,left:side(left),right:side(right)},options);
  attachment.status='complete';attachment.reason=null;for(const key of ['previous','current'] as const)attachment.windows[key]={...windows[key],parent_correlation_state:selected[key]};
 }
 abort(options);ensure(groupPathCanonical(report)===groupPathCanonical(parent)&&groupPathCanonical(expected)===groupPathCanonical(request)&&groupPathCanonical({left_snapshot_id:pair.left_snapshot_id,right_snapshot_id:pair.right_snapshot_id})===groupPathCanonical(selection),'cancelled');checkPairSignBudgets(attachment);return freeze({parent,attachment});
}

/** Event-time invalidation only: malformed or expanded live DTOs cannot revive an old action. */
export function pairSignContextBinding(report:GroupPairReport,expected?:GroupPairExpected,pair?:PairSignSelection):string|null {
 try {if(bytes(report)>2*1024*1024||expected&&bytes(expected)>8192)return null;return groupPathCanonical({report,expected:expected??null,pair:pair?{left_snapshot_id:pair.left_snapshot_id,right_snapshot_id:pair.right_snapshot_id}:null});}catch{return null;}
}
