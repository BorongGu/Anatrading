import { useEffect, useRef, useState } from 'react';
import { buildPairSignAttachment, formatPairSignFraction, pairSignContextBinding } from './pair-sign-crossproducts.ts';
import type { PairSignAttachment, PairSignSelection } from './pair-sign-crossproducts.ts';
import type { GroupPairExpected, GroupPairReport } from './group-pair-model.ts';
import { groupPairReason } from './group-pair-model.ts';
const labels={pp:'同涨原乘积和',nn:'同跌原乘积和',pn:'左涨右跌原乘积和',np:'左跌右涨原乘积和',centering:'均值中心化校正',centered_cross:'中心化交叉乘积总和'};
const signs:Record<string,string>={n:'跌',z:'不变',p:'涨'};
type Props={report:GroupPairReport;expected:GroupPairExpected;pair:PairSignSelection;onOpen:(id:string,date:string)=>void};
function Calculation({report,expected,pair,onOpen,isOpen}:Props & {isOpen:()=>boolean}){
 const [state,setState]=useState<{report:GroupPairReport;expected:GroupPairExpected;left:string;right:string;generation:number;binding:string|null;attachment?:PairSignAttachment;error?:string}|null>(null);
 const binding=()=>pairSignContextBinding(report,expected,pair);
 const text=binding();
 const current=useRef({report,expected,left:pair.left_snapshot_id,right:pair.right_snapshot_id,generation:0,binding:text});
 if(current.current.report!==report||current.current.expected!==expected||current.current.left!==pair.left_snapshot_id||current.current.right!==pair.right_snapshot_id||current.current.binding!==text)current.current={report,expected,left:pair.left_snapshot_id,right:pair.right_snapshot_id,generation:current.current.generation+1,binding:text};
 const generation=current.current.generation;
 const live=useRef(true);
 useEffect(()=>{
  live.current=true;const controller=new AbortController(),context=current.current;
  const valid=()=>live.current&&isOpen()&&!controller.signal.aborted&&current.current.generation===context.generation&&context.binding!==null&&binding()===context.binding&&current.current.report===context.report&&current.current.expected===context.expected&&current.current.left===context.left&&current.current.right===context.right;
  setState(null);
  if(context.binding===null)return()=>{live.current=false;controller.abort();};
  void buildPairSignAttachment(report,expected,pair,{signal:controller.signal}).then(({attachment})=>{if(valid())setState({...context,attachment});}).catch(error=>{if(valid())setState({...context,error:error instanceof Error?error.message:'invalid_context'});});
  return()=>{live.current=false;controller.abort();};
 },[report,expected,pair.left_snapshot_id,pair.right_snapshot_id,generation]);
 const valid=()=>live.current&&isOpen()&&state?.generation===current.current.generation&&state?.binding!==null&&state?.binding===binding()&&state?.report===current.current.report&&state?.expected===current.current.expected&&state?.left===current.current.left&&state?.right===current.current.right;
 const attachment=valid()?state?.attachment:undefined;
 const download=()=>{if(!valid()||!attachment)return;const url=URL.createObjectURL(new Blob([JSON.stringify(attachment)],{type:'application/json'}));try{const a=document.createElement('a');a.href=url;a.download='涨跌分项共变核查.json';a.click();}finally{URL.revokeObjectURL(url);}};
 const open=(id:string,date:string)=>{if(valid()&&attachment)onOpen(id,date);};
 if(text===null)return <p role="status">分项核查未完成：来源上下文已失效或超过资源限制。</p>;
 if(!attachment)return <p role="status">{valid()&&state?.error?'分项核查未完成：来源上下文、数值或资源限制未通过。':'正在核查选中对的精确变化…'}</p>;
 return <>
  <p>同涨、同跌及异向部分和使用原变化乘积。减去均值校正后才得到中心化交叉乘积总和；此处未除59。显示为5位有效数字，无百分比或年化。</p>
  <p className="inline-note amber">来源价格回顾；公司行动与历史当时可得性未知。不能据此归因、推断尾部依赖、预测、组合收益或避险能力；实际人效未验证。</p>
  <button type="button" onClick={download}>导出本次分项核查</button>
  {attachment.status==='unavailable'?<p>完整来源面板未齐，分项不可算；保留双方来源原因，不挑选幸存成员。</p>:(['previous','current'] as const).map(key=>{
   const w=attachment.windows[key]!;return <section key={key}>
    <h5>{key==='previous'?'前60区间':'当前60区间'}</h5>
    <p>原相关：{w.parent_correlation_state.correlation?.display??groupPairReason(w.parent_correlation_state.reason!)}。常量变化的原乘积和仍可定义，相关资格保持原状。</p>
    <ul>{Object.entries(labels).map(([term,label])=><li key={term}>{label}：{w.display[term as keyof typeof labels]}<details><summary>精确分数</summary><p style={{overflowWrap:'anywhere'}}>{w.terms[term as keyof typeof labels]} / {w.terms.denominator}</p></details></li>)}</ul>
    <p>九格计数（合计60）：{Object.entries(w.counts).map(([cell,count])=>`${signs[cell[0]]}/${signs[cell[1]]} ${count}`).join('；')}。零项表示本窗未观察到对应变化。</p>
    <details><summary>逐来源区间：两列变化与原乘积（60行）</summary><div className="table-scroll"><table><thead><tr><th>来源区间</th><th>左源序号／变化</th><th>右源序号／变化</th><th>符号／乘积</th></tr></thead><tbody>{w.rows.map(row=>{
     const i=row.right_index,l=attachment.source_refs.left.endpoints!,r=attachment.source_refs.right.endpoints!;
     const cell=(f:{n:string;d:string})=><>{formatPairSignFraction(f.n,f.d)}<details><summary>精确分数</summary>{f.n} / {f.d}</details></>;
     return <tr key={i}><td>{l[i-1].date} → {l[i].date}<div><button type="button" onClick={()=>open(attachment.pair.left_snapshot_id,l[i].date)}>打开左方区间终点</button><button type="button" onClick={()=>open(attachment.pair.right_snapshot_id,r[i].date)}>打开右方区间终点</button></div></td><td>{l[i-1].ordinal} → {l[i].ordinal}<br/>{cell(row.left_change)}</td><td>{r[i-1].ordinal} → {r[i].ordinal}<br/>{cell(row.right_change)}</td><td>{signs[row.sign_cell[0]]}/{signs[row.sign_cell[1]]}<br/>{cell(row.product)}</td></tr>;
    })}</tbody></table></div></details>
   </section>;
  })}
  <details><summary>附件身份</summary><p>{attachment.parent_content_hash}</p><p>完整父报告哈希只绑定本次内容，不认证来源真实性。原日期、序号、精确价格与原文保留在双方来源及附件。</p></details>
 </>;
}
export function PairSignDetails(props:Props){
 const [open,setOpen]=useState(false),epoch=useRef(0),opened=useRef(false);
 const token=epoch.current;
 return <details onToggle={event=>{if(opened.current!==event.currentTarget.open)epoch.current++;opened.current=event.currentTarget.open;setOpen(event.currentTarget.open);}}><summary>涨跌分项共变核查</summary>{open&&<Calculation {...props} isOpen={()=>opened.current&&epoch.current===token}/>}</details>;
}
