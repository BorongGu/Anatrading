import { useCallback, useEffect, useState } from 'react';
import { explain, jsonRequest } from './api.ts';
import { assertReply } from './model.ts';
import { RecordDetails, UnitEvidence } from './RecordDetails.tsx';
import { SourceChart } from './SourceChart.tsx';
import { PriceChannel } from './PriceChannel.tsx';
import type { DailyBackgroundReport, Query, Row, Snapshot } from './types.ts';

export function DailyBackground({ query, selected, snapshots, dailySnapshot, onSelect, window, onWindowSelect, channelLookback, onChannelLookbackSelect }: {
  query: Query; selected: Row | null; snapshots: Snapshot[]; dailySnapshot: string; onSelect: (value: string) => void;
  window: string; onWindowSelect: (value: string) => void;
  channelLookback: number; onChannelLookbackSelect: (value: number) => void;
}) {
  const [report, setReport] = useState<DailyBackgroundReport | null>(null);
  const [dailyRow, setDailyRow] = useState<Row | null>(null);
  const [issue, setIssue] = useState('');
  const focus = selected ?? query.rows.at(-1);
  const ordinal = focus?.ordinal;
  const label = focus?.label;
  const minuteSnapshot = query.snapshot_id;
  const chooseDailyRow = useCallback((row: Row) => setDailyRow(row), []);
  const chartError = useCallback(() => { setReport(null); setIssue(explain(new Error('chart_render_failed'))); }, []);

  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setDailyRow(null); setIssue('');
    if (!dailySnapshot || !ordinal || !label) return () => controller.abort();
    const parameters = new URLSearchParams({ daily_snapshot: dailySnapshot, ordinal: String(ordinal), window });
    jsonRequest<DailyBackgroundReport>(`/api/daily-background/${minuteSnapshot}?${parameters}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      const daily = result.daily;
      const cutoff = daily?.query?.selection?.cutoff;
      if (result.method_id !== 'prior-source-date-background-v1' || result.qualification !== 'source_date_retrospective_only'
        || result.pairing_status !== 'assumed_text_match' || result.anchor?.snapshot_id !== minuteSnapshot
        || result.anchor.ordinal !== ordinal || result.anchor.label !== label || result.daily_query_id !== daily?.query?.query_id
        || result.requested_rows !== (window === 'all' ? null : Number(window))
        || daily?.query?.metadata?.period !== '1d' || typeof cutoff !== 'string' || cutoff >= label.slice(0, 10)
        || !Array.isArray(daily?.query?.rows) || daily.query.rows.some(row => row.label === null || row.label >= label.slice(0, 10))) throw new Error('invalid_query_response');
      assertReply(daily, { snapshot: dailySnapshot, cutoff,
        start: daily.query.selection.ordinal_start === null ? '' : String(daily.query.selection.ordinal_start),
        end: daily.query.selection.ordinal_end === null ? '' : String(daily.query.selection.ordinal_end) }, 20000);
      setReport(result);
    }).catch(error => { if (!controller.signal.aborted) setIssue(explain(error)); });
    return () => controller.abort();
  }, [minuteSnapshot, dailySnapshot, ordinal, label, window]);

  const current = report?.anchor.snapshot_id === minuteSnapshot && report.anchor.ordinal === ordinal
    && report.anchor.label === label && report.daily.query.snapshot_id === dailySnapshot
    && report.requested_rows === (window === 'all' ? null : Number(window)) ? report : null;
  const daily = current?.daily;
  const shownRow = dailyRow ?? daily?.query.rows.at(-1);
  const geometry = shownRow && daily?.geometry.rows.find(row => row.ordinal === shownRow.ordinal);
  return <section className="panel" aria-label="日线背景与分钟复盘">
    <div className="section-heading"><h2>日线背景 · 分钟复盘联动</h2></div>
    <label>选择用于对照的日线快照<select value={dailySnapshot} onChange={event => onSelect(event.target.value)}>
      <option value="">请选择日线来源</option>
      {snapshots.filter(item => item.metadata.period === '1d').map(item => <option key={item.snapshot_id} value={item.snapshot_id}>
        {item.metadata.source_name ?? item.metadata.source_code ?? item.metadata.interpretation?.instrument ?? '身份未核'} · {item.row_count} 条 · {item.snapshot_id.slice(0, 8)}
      </option>)}
    </select></label>
    <label>背景历史窗口<select value={window} onChange={event => onWindowSelect(event.target.value)}>
      <option value="60">近期60条原记录</option><option value="120">近期120条原记录</option>
      <option value="250">近期250条原记录</option><option value="all">全部此前历史</option>
    </select></label>
    <p className="inline-note amber">前序来源日期回顾；证券声明匹配仅为 assumed。闭合、历史可得时点及跨来源尺度、复权可比性未核。</p>
    <p className="subtle">跟随所选分钟记录，仅展示其来源日期之前的日线；同日完整日线不参与背景。窗口按原记录计数，边界同日期重复记录全部保留；乱序时可能包含额外较早记录。两个图的价格与数量各用自身来源口径。</p>
    {!dailySnapshot ? <p className="subtle">选择日线快照，再点击分钟图或使用标签回放。</p>
      : !label ? <p className="inline-note amber">当前分钟记录无法定位日期，暂无法关联日线背景。</p>
      : issue ? <p className="error-banner">{issue}</p>
      : !daily ? <p className="subtle">正在读取此前日线…</p> : <>
        <p>分钟锚点 <strong>{label}</strong> · 日线源标签截止 <strong>{daily.query.selection.cutoff}</strong></p>
        <p className="subtle">最新前序源日期：{current?.latest_source_date ?? '无'}；与锚点相隔 {current?.calendar_gap_days ?? '∅'} 个自然日。交易日历未知，不能据间隔推断停牌或数据完整。</p>
        <div className="evidence-pills"><UnitEvidence contract={daily.query.manifest.contract} /></div>
        {daily.query.manifest.contract?.price_scaling && <p className="inline-note amber">.day 报价：原整数 ÷ 100 · {daily.query.manifest.contract.price_scaling.status ?? 'unknown'}；原整数见记录详情。</p>}
        {!!current?.context_unlocated_rows && <p className="inline-note amber">日线来源上下文有 {current.context_unlocated_rows} 条日期无法定位，其中 {daily.query.unlocated.length} 条位于本次查询；不归入当前日期背景。</p>}
        <SourceChart reply={daily} onChoose={chooseDailyRow} onError={chartError} visibleBars={60} />
        {shownRow && <RecordDetails row={shownRow} contract={daily.query.manifest.contract} geometry={geometry} />}
        <PriceChannel query={daily.query} selected={dailyRow} lookback={channelLookback} onLookbackSelect={onChannelLookbackSelect} />
        <details><summary>对照来源与完整查询范围</summary>
          <p className="subtle">本次窗口查询可定位日线共 {daily.query.rows.length} 条，图表初始显示其中最近60条，可缩放查看当前窗口全部记录。重复日期与坏字段保留，不自动选取替代记录。日线复权声明：{String(daily.query.manifest.contract?.source_semantics?.fields?.adjustment?.value ?? 'unknown')}。</p>
          <p>日线快照 <code>{daily.query.snapshot_id}</code></p><p>日线查询 <code>{daily.query.query_id}</code></p>
          <p>对照版本 <code>{current?.background_id}</code></p>
        </details>
      </>}
  </section>;
}
