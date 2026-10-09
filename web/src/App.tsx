import { useCallback, useEffect, useRef, useState } from 'react';
import type { FormEvent } from 'react';
import { checkedFetch, explain, jsonRequest, verifiedExportBlob, verifiedGeometryExportBlob } from './api.ts';
import { assertReply, Generation, minuteReadNotice, queryParameters } from './model.ts';
import { SourceChart } from './SourceChart.tsx';
import { RecordDetails, UnitEvidence } from './RecordDetails.tsx';
import { VolumeAnalysis } from './VolumeAnalysis.tsx';
import { PriceChannel } from './PriceChannel.tsx';
import { VolatilityAnalysis } from './VolatilityAnalysis.tsx';
import { DailyVolume } from './DailyVolume.tsx';
import { PathEfficiency } from './PathEfficiency.tsx';
import { ReferenceData } from './ReferenceData.tsx';
import { DailyCoverage } from './DailyCoverage.tsx';
import { DailyBackground } from './DailyBackground.tsx';
import { MinuteDailyReconciliation } from './MinuteDailyReconciliation.tsx';
import { SourceActions } from './SourceActions.tsx';
import { GapAnalysis } from './GapAnalysis.tsx';
import { PivotAnalysis } from './PivotAnalysis.tsx';
import { MinuteAggregation } from './MinuteAggregation.tsx';
import { fields, fieldNames } from './types.ts';
import type { Attempt, ChannelReport, Config, PivotReport, Query, Reply, Row, SelectionDraft, Snapshot } from './types.ts';

const formatNames: Record<string, string> = { 'tdx-public-text-v1': '通达信 · 已审文本', 'tdx-public-day-v1': '通达信 · 日线 .day', 'baostock-decoded-v0.9.4': 'BaoStock · 已审解码正文', 'tdx-http-market-v1': '通达信 · 分钟接口记录' };
const emptySelection: SelectionDraft = { snapshot: '', cutoff: '', start: '', end: '' };
const declarationNames = { instrument: '证券代码', venue: '市场', asset_type: '品类', volume_unit: '数量单位', amount_unit: '金额单位' };
const statusNames: Record<string, string> = { committed: '已提交', rejected: '已拒绝', failed: '失败', interrupted: '曾中断', running: '进行中', cancelled: '已取消' };
function snapshotName(snapshot: Snapshot): string {
  const m = snapshot.metadata;
  return [m.source_name, m.source_code ?? m.interpretation?.instrument ?? '身份未核实', m.period ?? '周期未知'].filter(Boolean).join(' · ');
}

export default function App() {
  const [config, setConfig] = useState<Config | null>(null);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [selection, setSelection] = useState<SelectionDraft>(emptySelection);
  const selectionRef = useRef(selection);
  const [reply, setReply] = useState<Reply | null>(null);
  const replyRef = useRef<Reply | null>(null);
  const [phase, setPhase] = useState<'idle' | 'dirty' | 'loading' | 'ready' | 'error'>('idle');
  const [issue, setIssue] = useState('');
  const [notice, setNotice] = useState('');
  const [selected, setSelected] = useState<Row | null>(null);
  const [scope, setScope] = useState<'located' | 'unlocated'>('located');
  const [page, setPage] = useState(0);
  const [exporting, setExporting] = useState<string | null>(null);
  const [importing, setImporting] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [format, setFormat] = useState('tdx-public-text-v1');
  const [declarations, setDeclarations] = useState<Record<string, string>>({});
  const [minuteCode, setMinuteCode] = useState('600059');
  const [minuteMarket, setMinuteMarket] = useState('SH');
  const [minuteCount, setMinuteCount] = useState('720');
  const [minuteEnd, setMinuteEnd] = useState('');
  const [readSource, setReadSource] = useState('daily_cache');
  const [snapshotFilter, setSnapshotFilter] = useState('');
  const [backgroundSnapshot, setBackgroundSnapshot] = useState('');
  const [backgroundWindow, setBackgroundWindow] = useState('60');
  const [channelLookback, setChannelLookback] = useState(20);
  const [channelReport, setChannelReport] = useState<ChannelReport | null>(null);
  const [pivotRadius, setPivotRadius] = useState(2);
  const [pivotReport, setPivotReport] = useState<PivotReport | null>(null);
  const [atrPeriod, setAtrPeriod] = useState(14);
  const [dailyVolumeLookback, setDailyVolumeLookback] = useState(20);
  const [efficiencyLookback, setEfficiencyLookback] = useState(10);
  const gate = useRef(new Generation());
  const abort = useRef<AbortController | null>(null);

  const invalidate = useCallback(() => {
    const generation = gate.current.invalidate();
    abort.current?.abort();
    abort.current = null;
    replyRef.current = null;
    setReply(null); setSelected(null); setPage(0); setScope('located'); setExporting(null); setIssue(''); setPhase('dirty');
    return generation;
  }, []);
  const chartError = useCallback(() => { invalidate(); setIssue(explain(new Error('chart_render_failed'))); setPhase('error'); }, [invalidate]);
  const chooseRow = useCallback((row: Row) => {
    const query = replyRef.current?.query;
    if (query && (query.rows.includes(row) || query.unlocated.includes(row))) setSelected(row);
  }, []);

  useEffect(() => {
    let active = true;
    Promise.all([
      jsonRequest<Config>('/api/config'),
      jsonRequest<{ snapshots: Snapshot[] }>('/api/snapshots'),
      jsonRequest<{ attempts: Attempt[] }>('/api/attempts'),
    ]).then(([settings, catalog, ledger]) => {
      if (!active) return;
      if (!settings.csrf_token || !Array.isArray(settings.formats) || settings.mode !== 'retrospective'
        || !Array.isArray(catalog.snapshots) || !Array.isArray(ledger.attempts)) throw new Error('invalid_response');
      setConfig(settings); setSnapshots(catalog.snapshots); setAttempts(ledger.attempts);
      setFormat(settings.formats[0] ?? '');
    }).catch(error => { if (active) { setIssue(explain(error)); setPhase('error'); } });
    return () => { active = false; gate.current.invalidate(); abort.current?.abort(); };
  }, []);

  async function refreshCatalog() {
    try {
      const [catalog, ledger] = await Promise.all([
        jsonRequest<{ snapshots: Snapshot[] }>('/api/snapshots'), jsonRequest<{ attempts: Attempt[] }>('/api/attempts'),
      ]);
      setSnapshots(catalog.snapshots); setAttempts(ledger.attempts);
      return catalog.snapshots;
    } catch (error) { setNotice(explain(error)); return null; }
  }

  function editSelection(patch: Partial<SelectionDraft>) {
    const next = { ...selectionRef.current, ...patch };
    selectionRef.current = next; setSelection(next); invalidate();
  }
  async function loadQuery(next: SelectionDraft, catalog = snapshots) {
    selectionRef.current = next; setSelection(next);
    const generation = invalidate();
    if (!next.snapshot || !config) return;
    try {
      const snapshot = catalog.find(item => item.snapshot_id === next.snapshot);
      if (!snapshot) throw new Error('snapshot_not_found');
      const parameters = queryParameters(next, snapshot.row_count, config.max_query_rows);
      setPhase('loading');
      const controller = new AbortController(); abort.current = controller;
      const result = await jsonRequest<Reply>(`/api/query/${encodeURIComponent(next.snapshot)}?${parameters}`, { signal: controller.signal });
      if (!gate.current.isCurrent(generation)) return;
      assertReply(result, next, config.max_query_rows);
      replyRef.current = result; setReply(result); setPhase('ready');
      return result;
    } catch (error) {
      if (!gate.current.isCurrent(generation)) return;
      invalidate(); setIssue(explain(error)); setPhase('error');
    }
  }

  async function importFile(event: FormEvent) {
    event.preventDefault();
    if (!config || importing) return;
    if (!file) { setNotice(explain(new Error('file_required'))); return; }
    if (file.size > config.max_upload_bytes) { setNotice(explain(new Error('upload_too_large'))); return; }
    if (!config.formats.includes(format)) { setNotice(explain(new Error('unsupported_format'))); return; }
    const generation = invalidate(); setImporting(true); setNotice('导入进行中。关闭页面不会撤销已接受的导入。');
    const parameters = new URLSearchParams({ format_id: format, filename: file.name });
    for (const key of Object.keys(declarationNames)) if (declarations[key]) parameters.set(key, declarations[key]);
    try {
      const result = await jsonRequest<{ attempt: Attempt }>(`/api/import?${parameters}`, {
        method: 'POST', headers: { 'Content-Type': 'application/octet-stream', 'X-Anatrading-Token': config.csrf_token }, body: file,
      });
      const attempt = result.attempt;
      setNotice(`导入${statusNames[attempt.status] ?? attempt.status} · 尝试 ${attempt.attempt_id}${attempt.error_code ? ` · ${attempt.error_code}` : ''}`);
      const catalog = await refreshCatalog();
      if (attempt.status === 'committed' && attempt.snapshot_id && catalog && gate.current.isCurrent(generation)) {
        await loadQuery({ ...emptySelection, snapshot: attempt.snapshot_id }, catalog);
      }
    } catch (error) {
      setNotice(`导入结果待核对。${explain(error)} 请刷新尝试账本确认终态，勿按网络错误判断提交结果。`);
    } finally { setImporting(false); }
  }

  async function readMinuteData(event: FormEvent) {
    event.preventDefault();
    if (!config || importing) return;
    const daily = readSource === 'daily_cache';
    const generation = invalidate(); setImporting(true); setNotice(`正在读取通达信${daily ? '日线缓存' : '分钟数据'}…`);
    const parameters = new URLSearchParams({ symbol: `${minuteCode.trim()}.${minuteMarket}` });
    if (!daily) {
      parameters.set('count', minuteCount);
      if (minuteEnd) parameters.set('end_time', minuteEnd.replaceAll('-', '') + '150000');
    }
    try {
      const result = await jsonRequest<{ attempt: Attempt }>(`/api/${daily ? 'read-tdx-daily-cache' : 'read-tdx-minutes'}?${parameters}`, {
        method: 'POST', headers: { 'X-Anatrading-Token': config.csrf_token },
      });
      const attempt = result.attempt;
      setNotice(`${daily ? '日线缓存' : '分钟数据'}${statusNames[attempt.status] ?? attempt.status}${attempt.error_code ? ` · ${explain(new Error(attempt.error_code))}` : ''}`);
      const catalog = await refreshCatalog();
      if (attempt.status === 'committed' && attempt.snapshot_id && catalog && gate.current.isCurrent(generation)) {
        const received = await loadQuery({ ...emptySelection, snapshot: attempt.snapshot_id }, catalog);
        if (!daily && received && replyRef.current === received) setNotice(minuteReadNotice(received.query));
      }
    } catch (error) {
      setNotice(`${explain(error)} 若连接中断，请刷新尝试账本核对读取结果。`);
    } finally { setImporting(false); }
  }

  async function exportSelection(format: 'json' | 'parquet' | 'geometry') {
    if (!reply || replyRef.current !== reply || !config || exporting || phase !== 'ready') return;
    const generation = gate.current.current();
    const queryId = reply.query.query_id;
    const geometryId = reply.geometry.geometry_id;
    const draft = { ...selectionRef.current };
    setExporting(format);
    try {
      const parameters = queryParameters(draft, reply.query.counts.batch_rows, config.max_query_rows);
      parameters.set('query_id', queryId);
      if (format === 'geometry') parameters.set('geometry_id', geometryId);
      else parameters.set('format', format);
      const route = format === 'geometry' ? 'geometry-export' : 'export';
      const response = await checkedFetch(`/api/${route}/${encodeURIComponent(draft.snapshot)}?${parameters}`, {
        method: 'POST', headers: { 'X-Anatrading-Token': config.csrf_token },
      });
      if (!gate.current.isCurrent(generation)) return;
      const { blob, digest } = format === 'geometry'
        ? await verifiedGeometryExportBlob(response, queryId, geometryId, draft, config.max_query_rows)
        : await verifiedExportBlob(response, queryId);
      if (!gate.current.isCurrent(generation)) return;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a'); link.href = url; link.download = format === 'geometry' ? `anatrading-geometry-${geometryId}.json` : `anatrading-${queryId}.${format}`;
      document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      setNotice(`已发起 ${format === 'geometry' ? 'K线结构 JSON' : format.toUpperCase()} 下载；内容 SHA-256 ${digest}`);
    } catch (error) {
      if (gate.current.isCurrent(generation)) { invalidate(); setIssue(explain(error)); setPhase('error'); }
    } finally { if (gate.current.isCurrent(generation)) setExporting(null); }
  }

  const snapshot = snapshots.find(item => item.snapshot_id === selection.snapshot);
  const matchingSnapshots = snapshots.filter(item => `${snapshotName(item)} ${item.snapshot_id}`.toLowerCase().includes(snapshotFilter.trim().toLowerCase()));
  const visibleSnapshots = matchingSnapshots.slice().reverse().slice(0, 200);
  const q = reply?.query;
  const selectedGeometry = selected && reply ? reply.geometry.rows.find(row => row.ordinal === selected.ordinal)
    ?? reply.geometry.unlocated.find(row => row.ordinal === selected.ordinal) : undefined;
  const tableRows = q ? (scope === 'located' ? q.rows : q.unlocated) : [];
  const pageSize = 50;
  const pageCount = Math.max(1, Math.ceil(tableRows.length / pageSize));

  return <div className="app-shell">
    <header className="topbar"><a className="brand" href="/" aria-label="Anatrading 首页"><span className="brand-mark">A</span><span>Anatrading<small>数据证据工作台</small></span></a>
      <div className="header-status"><span className="local-dot" />本机 · 单快照<span className="badge">历史回顾</span></div></header>
    <div className="workspace">
      <aside className="sidebar">
        <div className="section-heading"><h2>数据快照</h2><button className="quiet" onClick={() => void refreshCatalog()} disabled={!config || importing}>刷新</button></div>
        <p className="subtle">按原件与合同独立保存，切换时重新核验。</p>
        <label>筛选来源<input value={snapshotFilter} onChange={event => setSnapshotFilter(event.target.value)} placeholder="证券代码、名称或快照ID" /></label>
        <p className="subtle">共 {snapshots.length} 份快照；匹配 {matchingSnapshots.length} 份，显示前 {visibleSnapshots.length} 份。</p>
        <label className="field-label" htmlFor="snapshot">选择快照</label>
        <select id="snapshot" value={selection.snapshot} disabled={!config} onChange={event => void loadQuery({ ...emptySelection, snapshot: event.target.value })}>
          <option value="">请选择数据快照</option>
          {snapshot && !visibleSnapshots.includes(snapshot) && <option value={snapshot.snapshot_id}>{snapshotName(snapshot)} · 当前选择</option>}
          {visibleSnapshots.map(item => <option key={item.snapshot_id} value={item.snapshot_id}>{snapshotName(item)} · {item.snapshot_id.slice(0, 8)}</option>)}
        </select>
        <div className="snapshot-list">
          {visibleSnapshots.map(item => <button className={`snapshot-card ${selection.snapshot === item.snapshot_id ? 'active' : ''}`} key={item.snapshot_id}
            onClick={() => void loadQuery({ ...emptySelection, snapshot: item.snapshot_id })}>
            <strong>{snapshotName(item)}</strong><span>{formatNames[item.manifest.contract?.format_id ?? ''] ?? item.manifest.contract?.format_id ?? '来源未注明'}</span>
            <small>{item.row_count.toLocaleString()} 条源记录 · {item.snapshot_id.slice(0, 8)}</small>
          </button>)}
          {!snapshots.length && <div className="sidebar-empty">尚无已提交快照。<br />先导入一份支持的原始文件。</div>}
        </div>
        <details className="import-panel" open><summary>自动读取通达信数据</summary>
          <form onSubmit={readMinuteData}>
            <label>数据来源<select value={readSource} onChange={event => setReadSource(event.target.value)} disabled={!config || importing}>
              <option value="daily_cache">日线 · 原始缓存整数</option><option value="minute_http">1分钟 · 本地行情接口</option>
            </select></label>
            <label>证券代码<input value={minuteCode} onChange={event => setMinuteCode(event.target.value)} pattern="[0-9]{6}" maxLength={6} required disabled={!config || importing} /></label>
            <label>市场<select value={minuteMarket} onChange={event => setMinuteMarket(event.target.value)} disabled={!config || importing}>
              <option value="SH">上海</option><option value="SZ">深圳</option><option value="BJ">北京</option>
            </select></label>
            {readSource === 'minute_http' && <><label>分钟条数<input type="number" min="1" max={config?.max_query_rows ?? 20000} value={minuteCount} onChange={event => setMinuteCount(event.target.value)} required disabled={!config || importing} /></label>
              <label>截止日期（留空取最新）<input type="date" value={minuteEnd} onChange={event => setMinuteEnd(event.target.value)} disabled={!config || importing} /></label></>}
            <p className="subtle">{readSource === 'daily_cache' ? '直接读取客户端已有日线缓存，保留原整数成交量，无需手动导出。缺失缓存会明确报告。' : '先打开并登录通达信。读取1分钟数据，原值独立保存。'}</p>
            <button className="primary" disabled={!config || importing}>{importing ? '处理中…' : '读取并查看K线'}</button>
          </form>
        </details>
        <details className="import-panel" open={!snapshots.length}><summary>导入原始文件</summary>
          <form onSubmit={importFile}>
            <label>文件格式<select value={format} disabled={!config || importing} onChange={event => setFormat(event.target.value)}>
              {(config?.formats ?? Object.keys(formatNames)).map(value => <option value={value} key={value}>{formatNames[value] ?? value}</option>)}
            </select></label>
            <label className="file-picker">选择本地文件<input type="file" disabled={importing || !config} onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
            <p className="subtle">单文件 ≤16 MiB；请选择对应来源格式。文件名仅用于显示。</p>
            <details><summary>可选解释声明 · assumed</summary><div className="declarations">
              {Object.entries(declarationNames).map(([key, name]) => <label key={key}>{name}<input value={declarations[key] ?? ''} disabled={importing} onChange={event => setDeclarations({ ...declarations, [key]: event.target.value })} /></label>)}
            </div><p className="subtle">声明不能验证永久身份或覆盖来源证据。</p></details>
            <button className="primary import-button" disabled={!config || importing || !file}>{importing ? '导入中…' : '核验并导入'}</button>
          </form>
        </details>
        <details className="attempts-panel"><summary>导入尝试账本（{attempts.length}）</summary><button className="quiet" disabled={!config || importing} onClick={() => void refreshCatalog()}>刷新终态</button>
          <p className="subtle">导入中不承诺实时更新。回执丢失后以账本核对。</p>
          <ol className="attempt-list">{attempts.slice().reverse().map(attempt => <li key={attempt.attempt_id}>
            <strong>{statusNames[attempt.status] ?? attempt.status}</strong><span>{attempt.filename ?? attempt.format_id}</span>
            <code>{attempt.attempt_id}</code>{attempt.error_code && <span className="amber">{attempt.error_code}</span>}
          </li>)}</ol>
        </details>
      </aside>

      <main className="main-content">
        <div className="page-heading"><h1>{snapshot ? snapshotName(snapshot) : '从一份原始数据开始'}</h1><span className="badge amber-badge">历史回顾 · 可能包含事后修订</span></div>
        {notice && <div className="notice" role="status"><span>{notice}</span><button aria-label="收起通知" onClick={() => setNotice('')}>×</button></div>}
        {issue && <div className="error-banner" role="alert">{issue}</div>}
        {snapshot && <SnapshotEvidence snapshot={snapshot} />}
        <form className="panel query-toolbar" onSubmit={event => { event.preventDefault(); void loadQuery(selectionRef.current); }}>
          <label className="cutoff-input">源标签截止<input value={selection.cutoff} placeholder="全部源标签；或 2020-12-15T14:08" disabled={!snapshot} onChange={event => editSelection({ cutoff: event.target.value })} /></label>
          <label>源序号起<input inputMode="numeric" value={selection.start} placeholder="不限" disabled={!snapshot} onChange={event => editSelection({ start: event.target.value })} /></label>
          <label>源序号止<input inputMode="numeric" value={selection.end} placeholder="不限" disabled={!snapshot} onChange={event => editSelection({ end: event.target.value })} /></label>
          <button className="primary" disabled={!snapshot || !config || phase === 'loading'}>{phase === 'loading' ? '核验中…' : '应用选择'}</button>
          <div className="navigation-buttons">
            <button type="button" className="quiet" disabled={!reply?.navigation.previous_label} onClick={() => reply?.navigation.previous_label && void loadQuery({ ...selectionRef.current, cutoff: reply.navigation.previous_label })}>← 上一标签</button>
            <button type="button" className="quiet" disabled={!reply?.navigation.next_label} onClick={() => reply?.navigation.next_label && void loadQuery({ ...selectionRef.current, cutoff: reply.navigation.next_label })}>下一标签 →</button>
            <button type="button" className="quiet" disabled={!snapshot || !selection.cutoff} onClick={() => void loadQuery({ ...selectionRef.current, cutoff: '' })}>全部标签</button>
          </div>
        </form>
        {!reply && <section className="panel empty-state" aria-live="polite"><div className="empty-glyph">⌁</div><h2>{phase === 'loading' ? '正在核验原件并读取当前选择' : phase === 'error' ? '当前结果已阻断' : selection.snapshot ? '等待应用当前选择' : '选择快照，开始历史回顾'}</h2>
          <p>{phase === 'loading' ? '旧图、详情与导出已清除。' : '图表、精确字段与导出由同一个查询驱动。超过 20,000 条时请填写源序号窗口。'}</p></section>}
        {reply && q && <>
          <section className="selection-summary" aria-label="当前数据窗口">
            <div><span className="field-label">当前选择 · 可定位</span><strong>{q.counts.selected_rows.toLocaleString()}<small> 条</small></strong></div>
            <div><span className="field-label">当前选择 · 无法定位</span><strong>{q.counts.unlocated_rows.toLocaleString()}<small> 条</small></strong></div>
            <div className="range-summary"><span className="field-label">选择内源标签范围</span><code>{q.rows[0]?.label ?? '空'} → {q.rows.at(-1)?.label ?? '空'}</code><small>缩放仅改变可视区域，不改变选择与导出</small></div>
          </section>
          <SourceChart key={q.query_id} reply={reply} onChoose={chooseRow} onError={chartError} visibleBars={q.metadata.period === '1d' ? 60 : undefined} channel={channelReport?.lookback === channelLookback ? channelReport : null} pivots={pivotReport?.radius === pivotRadius ? pivotReport : null} />
          <section className="panel export-panel"><div><strong>导出当前选择</strong><p>{q.counts.selected_rows} 条定位 ＋ {q.counts.unlocated_rows} 条无法定位 · 保留原字段、质量与版本</p><code title={q.query_id}>Q {q.query_id}</code></div>
            <div className="button-group"><button disabled={!!exporting} onClick={() => void exportSelection('json')}>{exporting === 'json' ? '校验中…' : '下载 JSON'}</button><button disabled={!!exporting} onClick={() => void exportSelection('parquet')}>{exporting === 'parquet' ? '校验中…' : '下载 Parquet'}</button><button disabled={!!exporting} onClick={() => void exportSelection('geometry')}>{exporting === 'geometry' ? '校验中…' : '导出K线结构JSON'}</button></div>
          </section>
          <section className="panel records-panel">
            <div className="section-heading"><h2>精确字段</h2><span className="subtle">字符串原值 · 点击行或使用键盘查看</span></div>
            <div className="tabs" role="tablist" aria-label="记录范围"><button role="tab" aria-selected={scope === 'located'} onClick={() => { setScope('located'); setPage(0); }}>可定位 {q.counts.selected_rows}</button>
              <button role="tab" aria-selected={scope === 'unlocated'} onClick={() => { setScope('unlocated'); setPage(0); }}>无法定位 {q.counts.unlocated_rows}</button></div>
            {scope === 'unlocated' && <p className="inline-note">这些记录受源序号范围过滤，无法归入任何截止标签；仍属于当前查询和导出。</p>}
            <div className="table-scroll"><table><thead><tr><th>源序号 / 标签</th>{fields.map(field => <th key={field}>{fieldNames[field]}</th>)}<th>状态</th></tr></thead>
              <tbody>{tableRows.slice(page * pageSize, (page + 1) * pageSize).map(row => <tr key={row.ordinal} tabIndex={0} aria-selected={selected?.ordinal === row.ordinal} onClick={() => chooseRow(row)}
                onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); chooseRow(row); } }}>
                <th><span>#{row.ordinal}</span><code>{row.label ?? '无法定位'}</code></th>{fields.map(field => <td key={field}><code className={row.values[field] === null ? 'missing' : ''}>{row.values[field] ?? '∅'}</code></td>)}
                <td><span className={row.checks.some(check => check.outcome === 'fail') ? 'check-fail' : 'muted'}>{row.checks.some(check => check.outcome === 'fail') ? '检查未通过' : '查看资格'}</span></td>
              </tr>)}</tbody></table>{!tableRows.length && <p className="table-empty">此范围暂无记录。</p>}</div>
            <div className="pagination"><span>表格每页 {pageSize} 条；完整选择仍为 {tableRows.length} 条</span><div className="button-group"><button className="quiet" disabled={page === 0} onClick={() => setPage(page - 1)}>上一页</button><span>{page + 1} / {pageCount}</span><button className="quiet" disabled={page + 1 >= pageCount} onClick={() => setPage(page + 1)}>下一页</button></div></div>
          </section>
          <section className="panel detail-panel"><div className="section-heading"><h2>固定记录详情</h2>{selected && <button className="quiet" onClick={() => setSelected(null)}>清除</button>}</div>
            {selected ? <RecordDetails row={selected} contract={q.manifest.contract} geometry={selectedGeometry} /> : <p className="subtle">点击图中记录或表格行。原字段作为纯文本保留；二进制金额显示精确解码值及原始位。</p>}</section>
          {q.metadata.period === '1m' && <VolumeAnalysis query={q} selected={selected} />}
          {q.metadata.period === '1d' && <PriceChannel query={q} selected={selected} lookback={channelLookback} onLookbackSelect={setChannelLookback} report={channelReport} onReport={setChannelReport} />}
          {q.metadata.period === '1d' && <VolatilityAnalysis query={q} selected={selected} period={atrPeriod} onPeriodSelect={setAtrPeriod} />}
          {q.metadata.period === '1d' && <DailyVolume query={q} selected={selected} lookback={dailyVolumeLookback} onLookbackSelect={setDailyVolumeLookback} />}
          {q.metadata.period === '1d' && <PathEfficiency query={q} selected={selected} lookback={efficiencyLookback} onLookbackSelect={setEfficiencyLookback} />}
          {(q.metadata.period === '1d' || q.metadata.period === '1m') && <GapAnalysis key={q.query_id} query={q} selected={selected} onChoose={chooseRow} />}
          {(q.metadata.period === '1d' || q.metadata.period === '1m') && <PivotAnalysis key={q.query_id} query={q} selected={selected} onChoose={chooseRow} radius={pivotRadius} onRadiusSelect={setPivotRadius} report={pivotReport} onReport={setPivotReport} />}
          {q.metadata.period === '1m' && <MinuteAggregation key={q.query_id} query={q} selected={selected} onChoose={chooseRow} />}
          {q.metadata.period === '1d' && <SourceActions key={q.query_id} query={q} onChoose={chooseRow} />}
          {q.metadata.period === '1m' && <DailyBackground query={q} selected={selected} snapshots={snapshots} dailySnapshot={backgroundSnapshot} onSelect={setBackgroundSnapshot} window={backgroundWindow} onWindowSelect={setBackgroundWindow} channelLookback={channelLookback} onChannelLookbackSelect={setChannelLookback} atrPeriod={atrPeriod} onAtrPeriodSelect={setAtrPeriod} dailyVolumeLookback={dailyVolumeLookback} onDailyVolumeLookbackSelect={setDailyVolumeLookback} efficiencyLookback={efficiencyLookback} onEfficiencyLookbackSelect={setEfficiencyLookback} />}
          {q.metadata.period === '1m' && <MinuteDailyReconciliation query={q} dailySnapshot={backgroundSnapshot} />}
          <QualityDetails query={q} />
        </>}
        <DailyCoverage onSelect={(snapshot, sourceDate, windows) => {
          if (windows) { setChannelLookback(windows.channel_lookback); setDailyVolumeLookback(windows.volume_lookback); setEfficiencyLookback(windows.efficiency_lookback); }
          void loadQuery({ ...emptySelection, snapshot, cutoff: sourceDate ?? '' });
        }} />
        <ReferenceData config={config} />
        <footer>本地研究工具 · 单快照证据切片<span>图表由 <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView Lightweight Charts™</a> 提供 · <a href="/licenses/lightweight-charts.LICENSE.txt" target="_blank" rel="noreferrer">Apache 2.0</a> · <a href="/licenses/lightweight-charts.NOTICE.txt" target="_blank" rel="noreferrer">NOTICE</a></span></footer>
      </main>
    </div>
  </div>;
}

export function SnapshotEvidence({ snapshot }: { snapshot: Snapshot }) {
  const contract = snapshot.manifest.contract;
  const meta = snapshot.metadata;
  const adjustment = contract?.source_semantics?.fields?.adjustment;
  return <section className="panel evidence-panel">
    <div className="evidence-pills"><span>规范身份 <b>{meta.instrument_id ?? 'unknown'}</b></span><span>复权口径 <b>{adjustment?.value == null ? '未注明' : String(adjustment.value)}</b> · {adjustment?.status ?? 'unknown'}</span><span>闭合 / 可得时点 <b>{contract?.temporal_semantics?.status ?? 'unknown'}</b></span></div>
    <div className="evidence-pills unit-qualifications"><UnitEvidence contract={contract} /></div>
    <p className="inline-note">源数量 / 源金额：单位未核实，规范股数 / 元未赋值。</p>
    {contract?.price_scaling && <p className="inline-note amber">.day 报价：原整数 ÷ 100 · {contract.price_scaling.status ?? 'unknown'}；原整数见记录详情。</p>}
    <details><summary>来源、资格与完整哈希</summary><p className="subtle">仅展示单快照源值；源代码不构成永久身份。单位、柱闭合及历史可得性未验证时，不推断可交易信号。</p><dl className="metadata-list"><dt>来源格式</dt><dd>{contract?.format_id}</dd><dt>快照</dt><dd><code>{snapshot.snapshot_id}</code></dd><dt>原件 SHA-256</dt><dd><code>{snapshot.manifest.raw_sha256}</code></dd><dt>资格</dt><dd>{snapshot.manifest.qualification ?? 'source_evidence_retrospective_only'}</dd></dl>
      <details><summary>完整 manifest / metadata（来源原文）</summary><pre>{JSON.stringify({ manifest: snapshot.manifest, metadata: snapshot.metadata }, null, 2)}</pre></details>
    </details>
  </section>;
}

function QualityDetails({ query }: { query: Query }) {
  return <section className="panel quality-panel"><h2>质量与材料清单</h2>
    <details open><summary>当前选择 · 可定位检查</summary><QualityTable quality={query.quality} /></details>
    <details><summary>当前选择 · 无法定位检查</summary><QualityTable quality={query.unlocated_quality} /></details>
    <details><summary>当前选择 · 源数值算术和</summary><p className="subtle">仅陈述源值算术；未知单位时不解释为规范成交总量或总额。缺值未补零。</p>
      <div className="table-scroll"><table><thead><tr><th>字段</th><th>已知源值之和</th><th>可用 / 不可用记录</th></tr></thead><tbody>{Object.entries(query.totals).map(([field, value]) => <tr key={field}><th>{fieldNames[field as keyof typeof fieldNames] ?? field}</th><td><code>{value.known_sum}</code></td><td>{value.available_rows} / {value.unavailable_rows}</td></tr>)}</tbody></table></div>
    </details>
    <details><summary>全批材料清单 · {query.counts.batch_rows} 条，其中无法定位 {query.counts.batch_unlocated_rows} 条</summary><p className="subtle">全批记录与全局检查不属于截止时点指标。</p>
      <ul className="batch-checks">{query.batch_checks.map((check, i) => <li key={`${check.name}-${i}`}><code>{check.name}</code> · {check.outcome} {check.reason ?? ''} {check.assumption ? `（条件：${check.assumption}）` : ''}</li>)}</ul>
    </details>
  </section>;
}
function QualityTable({ quality }: { quality: Query['quality'] }) {
  return <div className="table-scroll"><table><thead><tr><th>检查</th><th>通过</th><th>未通过</th><th>未评估</th></tr></thead><tbody>{Object.entries(quality).map(([name, value]) => <tr key={name}><th><code>{name}</code></th><td>{value.pass}</td><td className={value.fail ? 'check-fail' : ''}>{value.fail}</td><td>{value.not_evaluated}</td></tr>)}</tbody></table></div>;
}
