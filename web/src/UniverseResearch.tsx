import { TwoGroupResults } from './TwoGroupResults.tsx';
import { explanationReasons } from './two-group-model.ts';
import { useEffect, useRef, useState } from 'react';
import { isDailySnapshot, snapshotName } from './research-model.ts';
import { explainFilter, FilterInputError, ResearchRequestController } from './filter-model.ts';
import type { ResearchRequestState, SelectionState } from './filter-types.ts';
import type { Snapshot } from './types.ts';
import { UniverseResults } from './UniverseResults.tsx';
import { createUniverseDraft, prepareUniverseRequest, loadUniverseRequest, universeErrorTarget } from './universe-request.ts';
import type { UniverseDraft, UniverseRequestSpec as Spec, UniverseRequestResult as Result } from './universe-request.ts';
export { createUniverseDraft } from './universe-request.ts';
export type { UniverseDraft } from './universe-request.ts';
import { FilterEditor, FilterResults } from './UniverseFilter.tsx';

const initialRequest: ResearchRequestState<Spec, Result> = { status: 'idle', result: null, error: null, spec: null };
export function UniverseResearch({ snapshots, onImport, onOpen, draft: controlledDraft, onDraftChange }: {
  snapshots: Snapshot[]; onImport: () => void; onOpen: (id: string, cutoff: string) => void;
  draft?: UniverseDraft; onDraftChange?: (next: UniverseDraft) => void;
}) {
  const [localDraft, setLocalDraft] = useState(createUniverseDraft);
  const draft = controlledDraft ?? localDraft;
  const [search, setSearch] = useState('');
  const [view, setView] = useState<'all' | SelectionState>('all');
  const [requestState, setRequestState] = useState<ResearchRequestState<Spec, Result>>(initialRequest);
  const control = useRef<ResearchRequestController<Spec, Result> | null>(null);
  function controller() {
    if (!control.current) control.current = new ResearchRequestController<Spec, Result>(setRequestState);
    return control.current;
  }
  function edit(patch: Partial<UniverseDraft>, semantic = true) {
    if (semantic) { controller().invalidate(); setView('all'); }
    const next = { ...draft, ...patch };
    if (patch.ids) next.explanation = { ...next.explanation, roles: Object.fromEntries(Object.entries(next.explanation.roles).filter(([id]) => patch.ids!.includes(id))) };
    if (onDraftChange) onDraftChange(next); else setLocalDraft(next);
  }
  useEffect(() => {
    controller();
    const pageHide = () => control.current?.invalidate();
    const pageShow = (event: PageTransitionEvent) => { if (event.persisted) control.current?.invalidate(); };
    window.addEventListener('pagehide', pageHide); window.addEventListener('pageshow', pageShow);
    return () => {
      window.removeEventListener('pagehide', pageHide); window.removeEventListener('pageshow', pageShow);
      control.current?.dispose(); control.current = null;
    };
  }, []);
  const daily = snapshots.filter(isDailySnapshot);
  const unavailable = draft.ids.filter(id => !daily.some(snapshot => snapshot.snapshot_id === id));
  const unavailableKey = unavailable.join(',');
  useEffect(() => { if (unavailableKey) control.current?.invalidate(); }, [unavailableKey]);
  useEffect(() => {
    if (requestState.status === 'cancelled') { document.getElementById('universe-run')?.focus(); return; }
    if (requestState.status !== 'error') return;
    document.getElementById(universeErrorTarget(requestState.error))?.focus();
  }, [requestState.status, requestState.error]);
  async function load() {
    setView('all');
    await controller().run(() => prepareUniverseRequest(draft, daily.map(snapshot => snapshot.snapshot_id)), loadUniverseRequest);
  }
  const filtered = daily.filter(item => snapshotName(item).toLowerCase().includes(search.trim().toLowerCase()));
  const busy = requestState.status === 'loading';
  const errorTarget = requestState.status === 'error' ? universeErrorTarget(requestState.error) : '';
  const report = requestState.result;
  const labels = requestState.spec?.kind === 'filter' ? requestState.spec.request.expected.groupLabels : [];
  let status = '';
  if (busy) status = '正在核验来源并计算，较早的结果已清除。';
  else if (requestState.status === 'cancelled') status = '已停止等待，可修改条件后重新运行。服务端已接受的只读核验可能仍在完成。';
  else if (report?.kind === 'filter') {
    const c = report.report.result.counts;
    status = `已完成，共 ${c.selected_members} 只；入选 ${c.selection.selected}、排除 ${c.selection.excluded}、待核 ${c.selection.undetermined}，其中 ${c.evidence.partial} 只仍有条件待核。`;
  } else if (report) status = '多股研究已完成。';
  return <>
    <div className="workspace-intro"><span className="eyebrow">横截面研究</span><h1>多股研究</h1><p>从明确的所选成员出发，查看价格条件、实际窗口与入选原因。</p></div>
    {daily.length < 2 && !draft.ids.length ? <section className="panel workflow-empty"><div className="empty-step">01</div><h2>先准备至少两份日线行情</h2><p>每只证券选一个数据版本，再指定共同截止日期。</p><button className="primary" onClick={onImport}>导入日线数据</button></section> : <>
      <section className="panel research-setup filter-universe-setup"><div className="section-heading"><h2>选择研究范围</h2><span className="subtle">日线 · 同一截止日期</span></div>
        <form onSubmit={event => { event.preventDefault(); void load(); }}>
          <div className="universe-selection-heading"><label>搜索代码或名称<input value={search} onChange={event => setSearch(event.target.value)} placeholder="证券代码或来源名称" /></label><div><strong>已选 {draft.ids.length} / 50</strong><button type="button" className="quiet" disabled={!draft.ids.length} onClick={() => edit({ ids: [] })}>清空</button></div></div>
          <div className="universe-picker">{filtered.map(item => <label className={`dataset-choice${draft.ids.includes(item.snapshot_id) ? ' selected' : ''}`} key={item.snapshot_id}><input type="checkbox" checked={draft.ids.includes(item.snapshot_id)} disabled={!draft.ids.includes(item.snapshot_id) && draft.ids.length >= 50} onChange={event => edit({ ids: event.target.checked ? [...draft.ids, item.snapshot_id] : draft.ids.filter(id => id !== item.snapshot_id) })} /><span><strong>{snapshotName(item)}</strong><small>{item.row_count.toLocaleString()} 条记录 · {item.snapshot_id.slice(0, 8)}</small></span></label>)}</div>
          {!filtered.length && <p className="subtle">没有匹配的日线数据。搜索不会更改已选成员。</p>}
          {!!draft.ids.length && <details className="selected-versions"><summary>查看已选 {draft.ids.length} 个版本</summary><ul>{draft.ids.map(id => {
            const snapshot = daily.find(item => item.snapshot_id === id);
            return <li key={id}><span>{snapshot ? snapshotName(snapshot) : '版本暂不可用'} <code>{id}</code></span><button type="button" className="quiet" aria-label={`移除版本 ${id.slice(0, 8)}`} onClick={() => edit({ ids: draft.ids.filter(value => value !== id) })}>移除</button></li>;
          })}</ul></details>}
          {!!unavailable.length && <p className="inline-note amber" role="status">{unavailable.length} 个已选版本暂不可用，请核对数据管理或明确移除后再运行；成员没有自动删除。</p>}
          <label>研究方式<select value={draft.explanation.enabled ? 'explanation' : 'existing'} onChange={event => edit({ explanation: { ...draft.explanation, enabled: event.target.value === 'explanation' } })}><option value="existing">原始分项与条件</option><option value="explanation">个股与参考组</option></select></label>
          {draft.explanation.enabled && <fieldset><legend>明确参考组（每组至少两只）</legend><p>逐只解释全部成员；每次从同伴均值中剔除该只股票。范围假设为A股、CNY、中国日线源日期；不认证行业或复权语义。仅支持腾讯日线既有格式。</p>{draft.ids.map(id => <label key={id}>{snapshotName(daily.find(item => item.snapshot_id === id) ?? { snapshot_id: id, metadata: {} } as Snapshot)}<select aria-label={`参考组 ${id.slice(0, 8)}`} value={draft.explanation.roles[id] ?? ''} onChange={event => edit({ explanation: { ...draft.explanation, roles: { ...draft.explanation.roles, [id]: event.target.value as 'A' | 'B' | '' } } })}><option value="">请明确分组</option><option value="A">参考组A</option><option value="B">参考组B</option></select></label>)}<label>当前区间起点<input type="date" required value={draft.explanation.start} onChange={event => edit({ explanation: { ...draft.explanation, start: event.target.value } })} /></label><p>前序固定60个所选源区间，截至当前起点；当前终点使用下方统一截止日期。任一点缺失会关闭全部模型，不补齐或前移。</p></fieldset>}
          <div className="research-controls cross-controls"><label>统一截止日期<input id="universe-cutoff" type="date" required value={draft.cutoff} aria-invalid={errorTarget === 'universe-cutoff' || undefined} aria-describedby={errorTarget === 'universe-cutoff' ? 'universe-error-summary' : undefined} onChange={event => edit({ cutoff: event.target.value })} /></label>
            {!draft.explanation.enabled && <label>观察窗口<input id="universe-lookback" type="number" min="2" max="252" step="1" required value={draft.lookback} aria-invalid={errorTarget === 'universe-lookback' || undefined} aria-describedby={errorTarget === 'universe-lookback' ? 'universe-lookback-hint universe-error-summary' : 'universe-lookback-hint'} onChange={event => edit({ lookback: event.target.value })} /><small id="universe-lookback-hint">来源区间；每股实际起点可能不同</small></label>}
            <label>集合名称（可选）<input value={draft.groupName} maxLength={80} onChange={event => edit({ groupName: event.target.value }, false)} placeholder="如：我的自选样本" /></label></div>
          {!draft.explanation.enabled && <FilterEditor draft={draft.filter} onChange={filter => edit({ filter })} inputError={requestState.error instanceof FilterInputError ? requestState.error : undefined} />}
          {requestState.status === 'error' && <p className="error-banner" role="alert" id="universe-error-summary" tabIndex={-1}>{draft.explanation.enabled && requestState.error instanceof Error && explanationReasons[requestState.error.message] || explainFilter(requestState.error)}</p>}
          <div className="button-group filter-run"><button id="universe-run" className="primary" disabled={busy || draft.ids.length < (draft.explanation.enabled ? 4 : 2) || !!unavailable.length}>{busy ? '核验并计算中…' : requestState.status === 'error' ? '按当前输入重试' : draft.explanation.enabled ? '解释全部所选成员' : draft.filter.enabled ? '按条件研究' : '研究所选股票'}</button>
            {busy && <button type="button" onClick={() => controller().cancel()}>取消等待</button>}</div>
        </form>
        <p className="inline-note">缺少截止当日记录时保留待核，不回退日期。重复证券版本由服务端拒绝。集合名称只用于显示，不认证行业归属。</p>
      </section>
      <p className="research-request-status" role="status" aria-live="polite">{status}</p>
      {!report && !busy && requestState.status !== 'error' && <div className="workflow-hint"><span>接下来</span><p>{draft.ids.length ? '输入已保留，重新运行可核验当前数据版本。刷新页面不会保存这些草稿。' : '勾选 2–50 只股票，指定截止日期；可直接查看原始分项，也可添加有限条件。'}</p></div>}
      {report?.kind === 'explanation' && <TwoGroupResults key={report.report.analysis_id} report={report.report} onOpen={onOpen} />}
      {report?.kind === 'filter' && <FilterResults key={report.report.analysis_id} report={report.report} groupLabels={labels} name={draft.groupName} onOpen={onOpen} view={view} onViewChange={setView} />}
      {report?.kind === 'universe' && <UniverseResults report={report.report} cutoff={report.report.parameters.cutoff as string} lookback={report.report.parameters.lookback as number} name={draft.groupName} onOpen={onOpen} />}
    </>}
  </>;
}
