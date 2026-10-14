import {useEffect,useRef,useState} from 'react';
import {declineContext,declineContextKey,requestDeclineBounds,formatFraction,validDay} from './decline-bounds.ts';
import type {DeclineContext,DeclineReport,Bound,Rational} from './decline-bounds.ts';
import type {Query} from './types.ts';
const reasons:Record<string,string>={known_negative_source:'来源已隔离',source_identity_conflict:'来源代码冲突',source_adjustment_conflict:'来源复权声明冲突',source_adjustment_check_failed:'来源复权校验失败',source_coverage_unknown:'来源日期覆盖未知',endpoint_not_present:'起止来源日期不存在；未替换为邻近日期',invalid_window:'窗口有失格日期组',duplicate_date:'同一来源日期有重复记录',unlocated_label:'来源标签无法定位',missing_ohlc:'OHLC字段缺失',invalid_price:'价格不符合严格正价要求',invalid_ohlc:'OHLC形态不一致',invalid_source_ordinal:'原序号缺失、越界或重复'};
const reasonText=(r:string|null)=>r===null?'合格来源观察':reasons[r]??r;
function Metric({label,value}:{label:string;value:Rational}){return <div><dt>{label}</dt><dd>{formatFraction(value)}</dd><details><summary>{label}精确分数</summary><p>{value.numerator}/{value.denominator}</p></details></div>;}
function Witness({label,bound,order}:{label:string;bound:Bound;order?:string}){return <details><summary>{label}</summary>{order&&<p>假想兼容次序：{order}。此证明不重建实际市场路径。</p>}{bound.witness?<>{(['peak','trough'] as const).map(k=>{const p=bound.witness![k];return <p key={k}>{order?'假想':''}{k==='peak'?'峰':'谷'}：来源日期 {p.date}，{p.slot??'收盘'}，精确价格 {p.price_exact}，原序号 {p.ordinal}。</p>;})}</>:<p>无正跌幅见证</p>}</details>;}
export function OhlcDeclineBounds({query}:{query:Query}){
 const context=declineContext(query),key=declineContextKey(context);
 // Remount before committing any new parent context: dates, openness and all
 // callbacks belong exclusively to one complete source context.
 return <DeclinePanel key={key} context={context}/>;
}
function DeclinePanel({context}:{context:DeclineContext}){
 const[open,setOpen]=useState(false),[start,setStart]=useState(''),[end,setEnd]=useState('');
 const[state,setState]=useState<{start:string;end:string;generation:number;loading:boolean;report:DeclineReport|null;issue:string}|null>(null);
 const generation=useRef(0),abort=useRef<AbortController|null>(null),isOpen=useRef(false),mounted=useRef(true),dates=useRef({start,end});dates.current={start,end};
 const pending=useRef(false);
 function invalidate(){generation.current++;abort.current?.abort();abort.current=null;pending.current=false;setState(null);}
 useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;isOpen.current=false;generation.current++;abort.current?.abort();};},[]);
 function close(){isOpen.current=false;setOpen(false);invalidate();}
 async function load(){
  if(!mounted.current||!isOpen.current||pending.current)return;
  invalidate();const token=generation.current,controller=new AbortController();abort.current=controller;pending.current=true;
  setState({start,end,generation:token,loading:true,report:null,issue:''});
  const owns=()=>mounted.current&&isOpen.current&&generation.current===token&&dates.current.start===start&&dates.current.end===end&&!controller.signal.aborted;
  try{const report=await requestDeclineBounds(context,start,end,controller.signal);if(owns()){pending.current=false;setState({start,end,generation:token,loading:false,report,issue:''});}}
  catch{if(owns()){pending.current=false;setState({start,end,generation:token,loading:false,report:null,issue:'读取失败，请检查日期或来源后重试。若来源资格已变，请重新读取数据版本。'});}}
 }
 const shown=open&&state?.start===start&&state.end===end&&state.generation===generation.current?state:null,report=shown?.report;
 const supported=context.period==='1d'&&context.mode==='retrospective';
 const valid=supported&&validDay(start)&&validDay(end)&&start<=end&&(context.cutoff===null||end<=context.cutoff);
 return <section className="panel ohlc-decline" aria-label="OHLC 跌幅范围">
  <div className="section-heading"><h2>OHLC 跌幅范围</h2><button type="button" aria-expanded={open} onClick={()=>{if(!mounted.current)return;if(open)close();else{isOpen.current=true;setOpen(true);}}}>{open?'关闭来源窗口':'选择来源窗口'}</button></div>
  {!supported&&<p className="inline-note">仅支持回顾性日线来源</p>}
  {open&&<>
   <form onSubmit={e=>{e.preventDefault();if(valid)void load();}}>
    <label>起始来源日期<input required type="date" value={start} max={end||context.cutoff||undefined} onChange={e=>{dates.current={start:e.target.value,end};setStart(e.target.value);invalidate();}}/></label>
    <label>结束来源日期<input required type="date" value={end} min={start||undefined} max={context.cutoff??undefined} onChange={e=>{dates.current={start,end:e.target.value};setEnd(e.target.value);invalidate();}}/></label>
    <button disabled={!valid||shown?.loading}>计算这个窗口</button>{shown?.loading&&<button type="button" onClick={invalidate}>取消读取</button>}
   </form>
   <p className="inline-note">本次分析截止：{end||'结束来源日期'}。使用该截止内完整来源前缀核验；图形记录序号范围不裁剪研究窗口。</p>
   <p className="subtle">取消仅废弃界面采纳，已开始的只读计算可能继续。</p>
   {shown?.loading&&<p role="status">正在核验来源并计算这个窗口…</p>}{shown?.issue&&<p className="error-banner" role="alert">{shown.issue}</p>}
   {report&&<>
    <p>请求：{report.window.requested_start} 至 {report.window.requested_end}；已定位：{report.window.resolved_start??'无'} 至 {report.window.resolved_end??'无'}；日期组 {report.window.bar_count}。</p>
    <p>来源身份：{report.identity.snapshot_id.slice(0,12)}…</p>
    {report.status==='computed'?<>
     <h3>兼容路径的最大源价跌幅</h3><dl className="metric-grid"><Metric label="下界" value={report.lower!.value}/><Metric label="上界" value={report.upper!.value}/><Metric label="收盘观察参照" value={report.close_only!.value}/><Metric label="次序歧义宽度" value={report.ambiguity_width!}/></dl>
     <p>只观察各日收盘可能漏掉日内及跨柱的跌幅；本窗从首根开盘开始。</p>
     <p>{report.identified?'上下界相等；这个跌幅数值已由供给 OHLC 确定，实际路径仍未确定。':'盘内先后未提供，保留上下界。'}</p>
     <p className="inline-note amber">仅约束已提供柱的兼容路径。若有漏柱，不能作为完整真实区间的上界。交易日历、复权与公司行动、历史可得时点及收盘闭合尚未验证。源价跌幅不等于财富损失或可成交收益；无预测结论。</p>
     <Witness label="假想极值证明 · 下界" bound={report.lower!} order="O→L→H→C"/><Witness label="假想极值证明 · 上界" bound={report.upper!} order="O→H→L→C"/><Witness label="收盘观察峰谷" bound={report.close_only!}/>
    </>:<><p className="inline-note amber">{reasonText(report.reason)}</p><ul>{report.reasons.map(r=><li key={r}>{reasonText(r)}（{r}）</li>)}</ul><h3>全部失格成员</h3><ul>{report.invalid_members.map(m=><li key={m.index}>{m.date}；原序号 {m.ordinal??'无唯一序号'}：{reasonText(m.reason)}（{m.reason}）</li>)}</ul></>}
    <details><summary>来源资格与覆盖</summary><p>来源资格：{JSON.stringify(report.source_qualification)}</p><p>全源首冲突计数：{JSON.stringify(report.source_conflict_counts)}。每行仅计首个拒绝；后续判据未评估。各计数单位不同，不相加。</p><p>来源覆盖：{JSON.stringify(report.coverage)}</p></details>
    <details><summary>全部窗口成员（{report.members.length} / 253）</summary><p>规范精确值；原始 token 未嵌入。重复日期无唯一序号，可用完整查询身份与来源日期回查。</p><div className="table-scroll"><table><thead><tr>{['位置','来源日期','原序号','开盘','最高','最低','收盘','资格'].map(t=><th key={t}>{t}</th>)}</tr></thead><tbody>{report.members.map(m=><tr key={m.index}><td>{m.index}</td><td>{m.date}</td><td>{m.ordinal??'无唯一序号'}</td>{(['open','high','low','close'] as const).map(f=><td key={f}>{m[f]??'无'}</td>)}<td>{reasonText(m.source_reason)}</td></tr>)}</tbody></table></div></details>
    <details><summary>完整来源身份与精确结果</summary><p>结果内容标识 {report.analysis_id}。此标识不证明签名、授权或历史时点可得性。</p><pre>{JSON.stringify(report,null,2)}</pre></details>
   </>}
  </>}
 </section>;
}
