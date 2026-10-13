import { Fragment, useEffect, useRef, useState } from 'react';
import { buildReversalReport, parseThresholdBps, reversalSourceFresh } from './close-reversal.ts';
import { researchReason } from './research-model.ts';
import type { ReversalMode, ReversalReport, ReversalSource } from './close-reversal.ts';
const sourceReasons:Record<string,string>={invalid_groups:'存在无效日期记录',duplicate_groups:'存在重复日期',unlocated_rows:'存在无法定位的记录',unreadable_date_rows:'存在无法读取的日期',batch_unlocated_rows:'原批次存在无法定位的记录',source_coverage_unknown:'来源覆盖未核',source_row_count_mismatch:'来源条数与日期序列不一致',no_source_observations:'截止范围没有来源记录',invalid_source_ordinal:'源序号缺失、重复或无效',source_rejected:'来源未通过资格检查'};
const sourceReason=(code:string)=>{if(Object.hasOwn(sourceReasons,code))return sourceReasons[code];const translated=researchReason(code);return typeof translated==='string'&&translated!==code?translated:'来源资格未能确认';};
const modeName=(m:ReversalMode)=>m==='up'?'向上初始化':'向下初始化';
export function CloseReversalRecords({source,isCurrent}:{source:ReversalSource;isCurrent:(source:ReversalSource)=>boolean}) {
 const [open,setOpen]=useState(false),[threshold,setThreshold]=useState('600'),[mode,setMode]=useState<ReversalMode>('up');
 const [report,setReport]=useState<ReversalReport|null>(null),[reportSource,setReportSource]=useState<ReversalSource|null>(null),[loading,setLoading]=useState(false),[issue,setIssue]=useState('');
 const [page,setPage]=useState(0),[selected,setSelected]=useState<number|null>(null);
 const publishedGeneration=useRef<number|null>(null);
 const generation=useRef(0),controller=useRef<AbortController|null>(null),mounted=useRef(true);
 const current=useRef({source,isCurrent,threshold,open,report,mode,page,reportSource});current.current={source,isCurrent,threshold,open,report,mode,page,reportSource};
 function valid(){const c=current.current;return mounted.current&&c.source===source&&c.open&&c.isCurrent(source)&&reversalSourceFresh(source);}
 function clear(){generation.current++;publishedGeneration.current=null;controller.current?.abort();setReport(null);setReportSource(null);setLoading(false);setIssue('');setPage(0);setSelected(null);}
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;generation.current++;controller.current?.abort();};},[]);
 useEffect(()=>{clear();},[source]);
 async function calculate(){if(!valid())return;clear();const run=generation.current,raw=current.current.threshold;controller.current=new AbortController();const signal=controller.current.signal;
  try{parseThresholdBps(raw);setLoading(true);const result=await buildReversalReport(source,raw,{signal});
   if(!valid()||generation.current!==run||current.current.threshold!==raw||signal.aborted)return;publishedGeneration.current=run;setReport(result);setReportSource(source);setLoading(false);
  }catch(error){if(valid()&&generation.current===run&&!signal.aborted){const code=error instanceof Error?error.message:'';setIssue(code==='invalid_threshold'?'请输入1至9999之间的整数基点。':code==='resource_limit'?'完整记录超过2 MiB上限，本次未生成结果。可缩短截止范围后重新研究。':'来源或计算状态已变化，请重新计算。');setLoading(false);}}
 }
 function resultCurrent(){return valid()&&publishedGeneration.current===generation.current&&current.current.report===report&&current.current.reportSource===source&&current.current.mode===mode&&current.current.page===page&&report!==null&&report.parameters.threshold_bps===parseThresholdBps(current.current.threshold);}
 function exportResult(){if(!resultCurrent()||!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=`close-reversal-${report.report_id}.json`;link.click();URL.revokeObjectURL(url);}
 const renderedGeneration=generation.current;
 const available=isCurrent(source),shown=available&&reportSource===source?report:null,events=shown?.modes[mode].events??[],pages=Math.max(1,Math.ceil(events.length/50)),safePage=Math.min(page,pages-1);
 return <section className="research-subsection" aria-label="收盘反转记录">
  <div className="section-heading"><h3>收盘反转记录</h3><button type="button" aria-expanded={open} onClick={()=>{if(!mounted.current||current.current.source!==source||current.current.open!==open||!current.current.isCurrent(source))return;clear();setOpen(!open);}}>{open?'收起收盘反转记录':'展开收盘反转记录'}</button></div>
  {open&&available&&<><p>按保存的收盘字段，记录达到指定幅度的首次反向确认。交易日历与收盘完整性未核；历史当时可得性及复权仍未知。</p>
   <form className="research-controls" onSubmit={event=>{event.preventDefault();void calculate();}}><label>反转幅度（基点）<input type="text" inputMode="numeric" value={threshold} onChange={event=>{clear();setThreshold(event.target.value);}}/><small>100基点 = 1%；默认600，无最优含义</small></label><button disabled={loading}>{loading?'计算中…':'计算收盘反转'}</button>{loading&&<button type="button" onClick={()=>{if(valid()&&generation.current===renderedGeneration)clear();}}>取消计算</button>}</form>
   <p className="subtle">从截止前完整来源首点初始化，两种初始化都计算，均不代表窗口前真实趋势。图表的序号范围不裁剪此计算。</p>{issue&&<p role="alert">{issue}</p>}
   {shown&&<><div className="count-strip"><span>向上初始化：{shown.modes.up.count??'不可计算'} 次</span><span>向下初始化：{shown.modes.down.count??'不可计算'} 次</span></div>
    {shown.status==='unavailable'?<p role="status">完整来源序列无法计算：{Object.entries(shown.source.reasons).map(([r,n])=>`${sourceReason(r)}（${n}）`).join('；')}。没有跳过坏点；原研究报告保留。</p>:<>
     <div className="segmented" aria-label="反转初始化">{(['up','down'] as const).map(value=><button type="button" key={value} aria-pressed={mode===value} onClick={()=>{if(!resultCurrent())return;setMode(value);setPage(0);setSelected(null);}}>{modeName(value)}</button>)}</div>
     <p>当前：{modeName(mode)}。全部事件保留初始化身份；首事件额外提示初始化影响，后续事件也未证明已消除影响。</p>
     <div className="table-scroll"><table><thead><tr><th>极值锚点</th><th>首次确认</th><th>方向</th><th>精确幅度</th><th>确认间隔</th></tr></thead><tbody>{events.slice(safePage*50,(safePage+1)*50).map((event,offset)=>{const position=safePage*50+offset,expanded=selected===position;return <Fragment key={`${shown.report_id}-${mode}-${event.anchor_index}-${event.confirmation_index}`}><tr><td>{event.anchor.date}<br/>{event.anchor_close_exact}</td><td><button type="button" aria-expanded={expanded} onClick={()=>{if(resultCurrent())setSelected(expanded?null:position);}}>{event.confirmation.date}</button><br/>{event.confirmation_close_exact}</td><td>{event.direction==='up'?'向上':'向下'}{event.first_event_initialization_warning?' · 首事件':''}</td><td>{event.magnitude.numerator}/{event.magnitude.denominator}</td><td>{event.confirmation_delay_source_intervals} 个来源区间</td></tr>{expanded&&<tr><td colSpan={5}><p>确认日期 {event.confirmation.date} 才可知此次反转；锚点日期 {event.anchor.date} 当时尚未确认。</p><p>锚点源序号 {event.anchor.ordinal}（位置 {event.anchor_index}）；确认源序号 {event.confirmation.ordinal}（位置 {event.confirmation_index}）。带符号相对变化 {event.signed_relative_change.numerator}/{event.signed_relative_change.denominator}。</p><p>规范收盘原值；原始token未随研究报告提供。来源区间数不代表交易日数。</p></td></tr>}</Fragment>;})}</tbody></table></div>
     {!events.length&&<p>此初始化下没有已确认反转。</p>}
     <nav aria-label="反转事件分页"><button type="button" disabled={safePage===0} onClick={()=>{if(resultCurrent()){setPage(safePage-1);setSelected(null);}}}>上一页</button><span> 第 {safePage+1}/{pages} 页 · 共 {events.length} 条，每页50条 </span><button type="button" disabled={safePage+1===pages} onClick={()=>{if(resultCurrent()){setPage(safePage+1);setSelected(null);}}}>下一页</button></nav>
     <p>未确认末段：{shown.modes[mode].terminal?.mode==='up'?'向上':'向下'}；末极值 {shown.modes[mode].terminal?.extreme.date} / {shown.modes[mode].terminal?.extreme_close_exact}。截至最后来源观察 {shown.modes[mode].terminal?.last_observation.date}，此末段未确认。</p>
    </>}
    <details><summary>来源与计算信息</summary><p>数据版本：{shown.source.identity.snapshot_id}<br/>批次：{shown.source.identity.batch_id}（请求图表来源，研究响应未独立认证）<br/>研究查询：{shown.source.identity.research_query_id}<br/>报告：{shown.report_id}<br/>请求截止：{shown.source.identity.requested_cutoff??'完整来源'}；来源记录 {shown.source.source_rows}</p><p>原始原因：{Object.entries(shown.source.reasons).map(([r,n])=>`${r}: ${n}`).join('；')||'无'}</p><p>方法 {shown.method_id}；规则 {shown.rule_version}；规范收盘字段，原始token不可用。未重新验证完整OHLC，不推断盘内路径、成交收益或未来趋势。</p></details>
    <button type="button" onClick={exportResult}>导出完整反转记录</button>
   </>}
  </>}
 </section>;
}
