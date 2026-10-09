import { useEffect, useState } from 'react';
import { explain, jsonRequest } from './api.ts';
import type { Query, ReconciliationReport, ReconciliationValues } from './types.ts';

const reasons: Record<string, string> = {
  date_membership_unknown: '存在日期不可读记录，归属未知', unlocated_clock: '分钟时钟无法定位',
  duplicate_clock: '分钟时钟重复', missing_date: '缺少同日日线', duplicate_date: '同日日线重复',
  unlocated_date: '日线标签无法定位', missing_field: '源字段缺失', invalid_field: '源字段无效',
};

function Values({ title, value }: { title: string; value: ReconciliationValues }) {
  return <tr><th>{title}</th><td><code>{value.selected_minute_sum ?? '∅'}</code>
    {value.minute_reason && <p className="amber">{reasons[value.minute_reason] ?? value.minute_reason}</p>}</td>
    <td><code>{value.daily_source_value ?? '∅'}</code>
      {value.daily_reason && <p className="amber">{reasons[value.daily_reason] ?? value.daily_reason}</p>}</td>
    <td><code>{value.difference ?? '∅'}</code></td></tr>;
}

export function MinuteDailyReconciliation({ query, dailySnapshot }: { query: Query; dailySnapshot: string }) {
  const [multiplier, setMultiplier] = useState('');
  const [report, setReport] = useState<ReconciliationReport | null>(null);
  const [issue, setIssue] = useState('');
  useEffect(() => {
    const controller = new AbortController();
    setReport(null); setIssue('');
    if (!dailySnapshot) return () => controller.abort();
    const parameters = new URLSearchParams({ daily_snapshot: dailySnapshot, query_id: query.query_id, mode: query.selection.mode });
    for (const key of ['cutoff', 'ordinal_start', 'ordinal_end'] as const) {
      if (query.selection[key] !== null) parameters.set(key, String(query.selection[key]));
    }
    if (multiplier) parameters.set('amount_multiplier', multiplier);
    jsonRequest<ReconciliationReport>(`/api/minute-daily-reconciliation/${query.snapshot_id}?${parameters}`, { signal: controller.signal }).then(result => {
      if (controller.signal.aborted) return;
      if (result.method_id !== 'selected-minute-daily-source-reconciliation-v1' || result.qualification !== 'retrospective_source_arithmetic'
        || result.minute_query_id !== query.query_id || result.minute_snapshot_id !== query.snapshot_id
        || result.daily_snapshot_id !== dailySnapshot || result.pairing_status !== 'assumed_text_match'
        || result.amount_multiplier !== (multiplier ? Number(multiplier) : null)
        || result.template_id !== 'observed-600059-240-clocks-v1' || !Array.isArray(result.days)
        || !Array.isArray(result.unreadable_minute_date_ordinals) || !Array.isArray(result.unreadable_daily_date_ordinals)) throw new Error('invalid_query_response');
      setReport(result);
    }).catch(error => { if (!controller.signal.aborted) setIssue(explain(error)); });
    return () => controller.abort();
  }, [query, dailySnapshot, multiplier]);
  const current = report?.minute_query_id === query.query_id && report.daily_snapshot_id === dailySnapshot
    && report.amount_multiplier === (multiplier ? Number(multiplier) : null) ? report : null;
  return <section className="panel" aria-label="分钟与同日日线对账">
    <div className="section-heading"><h2>分钟与同日日线 · 源值对账</h2></div>
    <p className="subtle">沿用上方日线来源，按当前查询中的分钟记录累计。日线使用同日完整源记录，仅用于事后核查；截止时刻与序号窗口均保留，部分分钟不会补齐。</p>
    <label>金额差的假设倍率<select value={multiplier} onChange={event => setMultiplier(event.target.value)}>
      <option value="">未选择：仅看两个源值</option><option value="1">分钟源金额之和 × 1</option>
      <option value="10000">分钟源金额之和 × 10000</option>
    </select></label>
    <p className="inline-note amber">差值 = 分钟源值之和 × 倍率 − 同日日线源值。数量暂按相同尺度比较；金额倍率由你声明。单位与成交覆盖未核，差值不代表数据错误，也不构成 VWAP 资格。</p>
    {!dailySnapshot ? <p className="subtle">先在上方选择日线来源。</p> : issue ? <p className="error-banner">{issue}</p>
      : !current ? <p className="subtle">正在核对源记录…</p> : <>
        {(current.unreadable_minute_date_ordinals.length > 0 || current.unreadable_daily_date_ordinals.length > 0) && <p className="amber">
          日期归属未知：分钟源序号 {current.unreadable_minute_date_ordinals.join('、') || '无'}；日线源序号 {current.unreadable_daily_date_ordinals.join('、') || '无'}。相应累计或日值不可用。
        </p>}
        {!current.days.length && <p className="subtle">当前查询没有日期可读的分钟记录。</p>}
        {current.days.map(day => <div key={day.source_date}>
          <h3>{day.source_date} · 所选 {day.selected_count} 条分钟源记录</h3>
          <p className="subtle">观察模板覆盖 {day.coverage.observed_template_slots}/{day.coverage.template_slots}；模板达到240槽仍不能确认全天成交覆盖。重复或无法定位分钟会阻止当日累计。</p>
          <div className="table-scroll"><table><thead><tr><th>字段</th><th>所选分钟源值之和</th><th>同日日线源值</th><th>假设倍率下源值差</th></tr></thead>
            <tbody><Values title="源数量（倍率1）" value={day.quantity} /><Values title={`源金额（倍率${multiplier || '未选'}）`} value={day.amount} /></tbody></table></div>
          <details><summary>覆盖与记录定位</summary>
            <p>分钟源序号：{day.minute_ordinals.join('、')}；同日日线源序号：{day.daily_ordinals.join('、') || '无'}。</p>
            <p>模板缺少时钟：{day.coverage.missing_clocks.join('、') || '无'}。</p>
            <p>模板外时钟（唯一可定位记录仍计入）：{day.coverage.extra_clocks.join('、') || '无'}。</p>
            <p>重复时钟：{day.coverage.duplicate_clocks.join('、') || '无'}；时钟无法定位源序号：{day.coverage.unlocated_clock_ordinals.join('、') || '无'}。</p>
          </details>
        </div>)}
        <details><summary>对账身份</summary><p>分钟查询 <code>{current.minute_query_id}</code></p>
          <p>完整日线查询 <code>{current.daily_query_id}</code></p><p>对账版本 <code>{current.reconciliation_id}</code></p></details>
      </>}
  </section>;
}
