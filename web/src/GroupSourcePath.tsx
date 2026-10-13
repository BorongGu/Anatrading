import { useEffect, useRef, useState } from 'react';
import type { DrawdownExpected, DrawdownPoint, DrawdownReport } from './drawdown-episode-model.ts';
import { buildGroupSourcePath, groupPathCanonical, formatGroupPathPercent, groupPathFraction } from './group-source-path-model.ts';
import type { GroupSourcePathResult } from './group-source-path-model.ts';

type OpenSource = (id: string, cutoff: string) => void;
function Fraction({n,d}: {n:string;d:string}) {
  const value=groupPathFraction(n,d);
  return <code>{value.numerator}/{value.denominator}</code>;
}
function Evidence({label,point,id,onOpen}: {label:string;point:DrawdownPoint;id:string;onOpen:OpenSource}) {
  return <li><strong>{label}</strong> {point.date} · 窗口位置 {point.index} · 源序号 <code>{point.ordinal}</code>
    {' · 原收盘价 '}<code>{point.close_exact}</code>{' '}
    <button type="button" className="quiet" aria-label={`打开原版本截至此日：${id}，${point.date}，${label}`} onClick={()=>onOpen(id,point.date)}>打开原版本截至此日</button>
  </li>;
}
export function GroupSourcePathCurve({result}: {result:GroupSourcePathResult}) {
  const {parent,attachment:a}=result;
  return (
        <div className="table-scroll"><table><caption>固定原起点的完整归一化来源价格均值；位置对应原报告端点，未抽样或删点</caption>
          <thead><tr><th>窗口位置</th><th>来源日期</th><th>路径精确值</th><th>共同见证</th></tr></thead>
          <tbody>{a.sums!.map((s,i)=><tr key={i}><td>{i}</td><th>{parent.dates![i]}</th><td><Fraction n={s} d={a.denominator!}/></td>
            <td>{[i===0?'固定原起点':'',i===a.peak_index?'共同峰':'',i===a.trough_index?'共同谷':''].filter(Boolean).join('、') || '—'}</td></tr>)}</tbody>
        </table></div>
  );
}
export function GroupSourcePathCurveDetails({result}: {result:GroupSourcePathResult}) {
  const [open,setOpen]=useState(false);
  return <details onToggle={event=>setOpen(event.currentTarget.open)}>
    <summary>完整来源平均路径：全部 {result.attachment.endpoint_count} 个日期及精确值</summary>
    {open && <GroupSourcePathCurve result={result}/>}
  </details>;
}
export function GroupSourcePathReadout({result,onOpen}: {result:GroupSourcePathResult;onOpen:OpenSource}) {
  const {parent,attachment:a}=result;
  return <section aria-label="组来源平均路径结果" data-parent-content-hash={a.parent_content_hash}>
    <p>原选全部 {a.selected} 个成员 · 截止 {parent.parameters.cutoff} · {parent.parameters.lookback} 个来源区间。</p>
    <p className="inline-note">各股以窗口首日价格为1，再取等权平均，之后不逐期重置权重。保留原起点才能复核共同段。
      仅描述已观察来源收盘；当前成员与最深段属于回顾。全体共同缺日、窗口前峰、柱内极值、复权语义、公司行动覆盖和历史可得性仍未知。
      不提供投资财富、经济收益、因果归因、删股改善、CDaR、优化权重或预测。</p>
    {a.status==='unavailable' ? <>
      <p className="inline-note amber">整组来源平均路径不可计算；曲线、深度和贡献留空。全部成员及具体来源失败保留在原回撤报告中，未计算幸存子组。</p>
      <ul>{parent.members.map(m=><li key={m.snapshot_id}>{m.symbol ?? '身份待核'} · 数据版本 <code>{m.snapshot_id}</code> · 来源{m.source_qualified?'已核':'未通过'} · 自身窗口{m.window_qualified?'已核':'未通过'}</li>)}</ul>
    </> : <>
      <p><strong>固定原起点 {parent.dates![0]}</strong> · 来源平均路径最深回撤 <strong>{formatGroupPathPercent(a.depth!.numerator,a.depth!.denominator)}</strong>
        {' · 精确比例 '}<Fraction n={a.depth!.numerator} d={a.depth!.denominator}/></p>
      {a.status==='no_drawdown' ? <p>完整组路径无正回撤。深度为0，未选择共同峰谷，成员贡献留空。</p> : <>
        <p>唯一共同峰 {parent.dates![a.peak_index!]}（位置 {a.peak_index}）→ 最早最深谷 {parent.dates![a.trough_index!]}（位置 {a.trough_index}）。同深度取最早谷，该谷前同高峰取最后一次。</p>
        <p>所有成员都用此共同峰谷和原起点。正贡献拉低，负贡献抵消，零贡献不变；正项可以大于净回撤。带符号贡献相加等于组回撤，不除以净回撤作贡献占比。</p>
      </>}
      <p>百分数与百分点按半偶规则舍入至4位小数；微小正负值单独标注，精确分数可逐项核对。按钮打开原版本截至该日，不保证直接聚焦源序号。</p>
      {parent.members.map((m,i)=><article key={m.snapshot_id} className="group-path-member">
        <h4>{m.symbol} · 数据版本 <code>{m.snapshot_id}</code></h4>
        {a.contributions && <p>同段贡献 <strong>{formatGroupPathPercent(a.contributions[i],a.sums![a.peak_index!],true)}</strong>
          {' · 精确比例 '}<Fraction n={a.contributions[i]} d={a.sums![a.peak_index!]}/>
          {' · '}{a.contributions[i]==='0'?'不变':a.contributions[i].startsWith('-')?'抵消':'拉低'}</p>}
        <ul><Evidence label="固定原起点" point={m.endpoints![0]} id={m.snapshot_id} onOpen={onOpen}/>
          {a.peak_index!==null && <Evidence label="共同峰" point={m.endpoints![a.peak_index]} id={m.snapshot_id} onOpen={onOpen}/>}
          {a.trough_index!==null && <Evidence label="共同谷" point={m.endpoints![a.trough_index]} id={m.snapshot_id} onOpen={onOpen}/>}
        </ul>
        <details><summary>原批次与查询</summary><p>批次 <code>{m.batch_id}</code> · 查询 <code>{m.query_id}</code></p></details>
      </article>)}
      <GroupSourcePathCurveDetails key={a.attachment_id} result={result}/>
    </>}
    <details><summary>独立附件与完整原报告内容身份</summary>
      <p>附件 <code>{a.attachment_id}</code> · 原分析 <code>{a.parent_analysis_id}</code></p>
      <p>完整原报告内容 SHA256 <code>{a.parent_content_hash}</code> · {a.method_id} · {a.rule_version}</p>
      <p>hash只标识内容，不认证原件真实性。此附件须与完整原报告共同复核。原报告与附件各有独立2MiB限，未证明总内存或响应性能。</p>
    </details>
  </section>;
}
function binding(report:DrawdownReport,expected:DrawdownExpected): string | null {
  try {
    // Also detects a same-object mutation on render, even when analysis_id is unchanged.
    if(new TextEncoder().encode(JSON.stringify(report)).length>2*1024*1024)return null;
    return groupPathCanonical({report,expected});
  } catch {return null;}
}
function Calculation({report,expected,content,onOpen}: {report:DrawdownReport;expected:DrawdownExpected;content:string;onOpen:OpenSource}) {
  const [attempt,setAttempt]=useState(0),generation=useRef(0);
  const [state,setState]=useState<{content:string;result?:GroupSourcePathResult;error?:string}|null>(null);
  useEffect(()=>{
    const controller=new AbortController(),current=++generation.current;
    void buildGroupSourcePath(report,expected,{signal:controller.signal}).then(result=>{
      if(!controller.signal.aborted && generation.current===current)setState({content,result});
    },error=>{
      if(!controller.signal.aborted && generation.current===current)setState({content,error:error instanceof Error?error.message:'group_path_failed'});
    });
    return ()=>{controller.abort();generation.current++;};
  },[report,expected,content,attempt]);
  if(state?.content!==content)return <p role="status">正在核对固定原起点、全组来源与精确共同段…</p>;
  if(state.error)return <div role="alert"><p>组来源路径附件未生成：{state.error}。原回撤结果保留，未输出零回撤结论。</p>
    <button type="button" onClick={()=>{setState(null);setAttempt(a=>a+1);}}>重试组来源路径</button></div>;
  return state.result?<GroupSourcePathReadout result={state.result} onOpen={onOpen}/>:null;
}
export function GroupSourcePath({report,expected,onOpen}: {report:DrawdownReport;expected:DrawdownExpected;onOpen:OpenSource}) {
  const [open,setOpen]=useState(false);
  const content=binding(report,expected);
  return <details onToggle={e=>setOpen(e.currentTarget.open)}>
    <summary>组内平均走势与最大回撤（回顾）</summary>
    <p>各股以窗口首日价格为1，再取等权平均，之后不逐期重置权重。仅使用本次全部已核来源收盘价，保留所有成员的同段拉低与抵消。</p>
    {open && (content===null?<p role="alert">完整原报告或请求内容未通过核对，组来源路径不可计算。</p>:<Calculation report={report} expected={expected} content={content} onOpen={onOpen}/>)}
  </details>;
}
