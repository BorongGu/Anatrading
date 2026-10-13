import { useEffect, useRef, useState } from 'react';
import { explain } from './api.ts';
import { dispersionContext, dispersionContextKey, requestDispersion } from './selected-dispersion.ts';
import type { DispersionInterval, SelectedDispersion } from './selected-dispersion.ts';
import type { Query } from './types.ts';

const reasons: Record<string,string> = {
  history_insufficient:'不足20个来源日期组', invalid_window:'窗口含失格来源日期组',
  no_date_groups:'当前截止内没有可读来源日期组', date_not_present:'当前截止内没有这个来源日期；未替换为邻近日期',
  duplicate_date:'同日重复来源', unlocated_label:'原标签无效；日期从原字段恢复',
  invalid_price:'价格不符合严格正价要求', invalid_ohlc:'OHLC形态不一致', missing_ohlc:'OHLC字段缺失',
  known_negative_source:'来源已隔离', source_identity_conflict:'来源代码冲突', source_adjustment_conflict:'复权声明冲突',
  source_adjustment_check_failed:'复权校验失败',
};
const reasonText=(reason: string | null)=>reason === null ? '合格来源观察':reasons[reason] ?? reason;
function Interval({label,value}: {label:string;value:DispersionInterval}) {
  return <div><dt>{label}</dt><dd>{value.display ?? '显示舍入未定'}</dd>
    <details><summary>{label}精确端点</summary><p>下端 {value.lower}；上端 {value.upper}</p>
      <p>{value.exact ? '端点完全相等':'数值闭包络'}；显示舍入 {value.display_reason ?? '已证明一致'}</p></details></div>;
}
export function SelectedCloseDispersion({query}: {query:Query}) {
  const context=dispersionContext(query), contextKey=dispersionContextKey(context);
  const current=useRef(contextKey); current.current=contextKey;
  const [open,setOpen]=useState(false), [date,setDate]=useState('');
  const selectedDate=useRef(date); selectedDate.current=date;
  const [state,setState]=useState<{key:string;date:string;generation:number;report:SelectedDispersion|null;issue:string;loading:boolean}|null>(null);
  const generation=useRef(0), abort=useRef<AbortController|null>(null), isOpen=useRef(false);
  function invalidate() { generation.current++; abort.current?.abort(); abort.current=null; setState(null); }
  function close() { isOpen.current=false; setOpen(false); invalidate(); }
  async function load() {
    if (current.current !== contextKey || !isOpen.current) return;
    invalidate(); const token=generation.current, controller=new AbortController(); abort.current=controller;
    const requested=date;
    setState({key:contextKey,date:requested,generation:token,report:null,issue:'',loading:true});
    const owns=()=>isOpen.current && generation.current===token && current.current===contextKey && selectedDate.current===requested && !controller.signal.aborted;
    try {
      const report=await requestDispersion(context,requested || null,controller.signal);
      if(owns()) setState({key:contextKey,date:requested,generation:token,report,issue:'',loading:false});
    } catch(error) {
      if(owns()) setState({key:contextKey,date:requested,generation:token,report:null,issue:explain(error),loading:false});
    }
  }
  useEffect(()=>{ invalidate(); isOpen.current=false; setOpen(false); setDate(''); return ()=>{generation.current++;abort.current?.abort();}; },[contextKey]);
  // The render guard hides a prior context immediately, before effect cleanup.
  const shown=open && state?.key===contextKey && state.date===date && state.generation===generation.current ? state:null;
  const report=shown?.report, row=report?.selected;
  return <section className="panel selected-dispersion" aria-label="精确收盘离散">
    <div className="section-heading"><h2>精确收盘离散 · 单日期</h2><button type="button" aria-expanded={open} onClick={()=>{
      if(open) close(); else {isOpen.current=true;setOpen(true);void load();}
    }}>{open ? '关闭离散窗口':'打开离散窗口'}</button></div>
    <p className="subtle">固定当前及此前19个来源日期组；总体方差、均值±2σ。数值界不代表概率区间，无预测或交易收益结论。</p>
    {open && <>
      <form onSubmit={event=>{event.preventDefault();void load();}}>
        <label>来源日期（留空为最近来源日期）<input type="date" value={date} max={context.cutoff ?? undefined}
          onChange={event=>{selectedDate.current=event.target.value;setDate(event.target.value);invalidate();}} /></label>
        <button disabled={shown?.loading}>读取单日期</button>
        {shown?.loading && <button type="button" onClick={invalidate}>取消读取</button>}
      </form>
      <p className="inline-note">查询截止不变：{context.cutoff ?? '全部来源历史'}。计算使用截止内完整前缀，图形源序号裁剪不裁剪研究。默认取最近来源日期组，包含失格组。</p>
      {shown?.loading && <p role="status">正在核验来源并读取一个窗口…</p>}
      {shown?.issue && <p className="error-banner" role="alert">{shown.issue}</p>}
      {!shown && <p className="subtle">请读取当前选择。取消仅停止采用返回结果，已开始的只读计算可能继续完成。</p>}
      {report && <>
        <p>请求：{report.selection.date_requested ?? '最近来源日期'}；实际日期：{report.selection.resolved_date ?? '无'}。</p>
        {report.reason && <p className="inline-note amber">{reasonText(report.reason)}</p>}
        {row?.status==='computed' && <dl className="metric-grid">
          <div><dt>均值（精确）</dt><dd>{row.mean_exact}</dd></div>
          <div><dt>总体方差（精确，源价平方）</dt><dd>{row.variance_exact}</dd></div>
          <Interval label="σ" value={row.sigma!}/><Interval label="均值−2σ" value={row.envelope_lower!}/><Interval label="均值+2σ" value={row.envelope_upper!}/>
        </dl>}
        <p className="subtle">显示为0.0000不代表数学上为零。均值、σ及上下界单位均为来源价格。复权、公司行动、历史可得性、收盘闭合及完整交易日历尚未验证。</p>
        <p>来源资格：{report.qualification}；日期组 {String(report.coverage.date_groups)}，失格 {String(report.coverage.invalid_groups)}，无定位行 {String(report.coverage.unlocated_rows)}，完全不可读日期 {String(report.coverage.unreadable_date_rows)}。
          {report.coverage.coverage_known ? '来源定位计数已知；交易日历仍未核。':'来源覆盖未知。'}</p>
        {report.members.length>0 && <details open><summary>全部窗口成员（{report.members.length} / 20）</summary>
          <div className="table-scroll"><table><thead><tr><th>来源位置</th><th>日期</th><th>原序号</th><th>收盘原精确值</th><th>来源资格</th></tr></thead>
            <tbody>{report.members.map(member=><tr key={member.position}><td>{member.position}</td><td>{member.date}</td><td>{member.ordinal ?? '无唯一序号'}</td><td>{member.close ?? '无'}</td><td>{reasonText(member.source_reason)}</td></tr>)}</tbody></table></div>
        </details>}
        <details><summary>来源身份与完整精确结果</summary>
          <p>完整前缀查询 {report.identity.query_id}；窗口身份 {report.analysis_id}</p>
          <pre>{JSON.stringify(report,null,2)}</pre>
        </details>
      </>}
    </>}
  </section>;
}
