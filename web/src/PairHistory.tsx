import { useState } from 'react';
import { pairHistoryIdentity, pairHistoryPage } from './pair-history.ts';
import { formatEstimate, researchReason } from './research-model.ts';
import type { PairResult, ResearchEnvelope } from './research-types.ts';

export function PairHistory({ report, lookback }: { report: ResearchEnvelope<PairResult>; lookback: number }) {
  const identity = pairHistoryIdentity(report, lookback);
  const [position, setPosition] = useState({ report, identity, page: 0 });
  const sameReport = position.report === report && position.identity === identity;
  const current = pairHistoryPage(report.result.series, sameReport ? position.page : 0);
  // Reset synchronously on report replacement, even if analysis_id is unchanged.
  // Also commit a clamped position so a later growing series cannot revive an old page.
  if (!sameReport || position.page !== current.page) setPosition({ report, identity, page: current.page });
  return <details className="calculation-note pair-history">
    <summary>历史相关与 β（{current.total}）</summary>
    <p className="subtle">共同日期先对齐再计算对数变化，当前区间参与。相邻行窗口重叠，记录间隔未必一天。β 为 A 对 B，不限于 −1 到 1；相关不等于协整、均值回归或预测。</p>
    {current.total === 0 ? <p>截止范围没有共同日期记录。</p> : <>
      <div className="pagination" aria-label="历史相关与 β 分页">
        <button type="button" disabled={current.page === 0} onClick={() => setPosition(value => ({ report, identity, page: (value.report === report && value.identity === identity ? value.page : 0) - 1 }))}>上一页</button>
        <span aria-live="polite">第 {current.page + 1}/{current.pages} 页，共 {current.total} 条共同日期记录 · 最新到最早</span>
        <button type="button" disabled={current.page === current.pages - 1} onClick={() => setPosition(value => ({ report, identity, page: (value.report === report && value.identity === identity ? value.page : 0) + 1 }))}>下一页</button>
      </div>
      <div className="table-scroll"><table><thead><tr><th scope="col">共同记录日期</th><th scope="col">相关窗口</th><th scope="col">有效共同区间</th><th scope="col">区间相关</th><th scope="col">区间 β（A 对 B）</th><th scope="col">覆盖与记录状态</th></tr></thead>
        <tbody>{current.rows.map(row => <tr key={row.date}>
          <th scope="row">{row.date}</th><td>{row.returns_start_date ?? '—'} → {row.returns_end_date ?? '—'}</td><td>{row.n_returns} / {lookback}</td>
          <td>{formatEstimate(row.return_correlation)}{row.correlation_reason && <div className="subtle">{researchReason(row.correlation_reason)}</div>}</td>
          <td>{formatEstimate(row.return_beta)}{row.return_beta_reason && <div className="subtle">{researchReason(row.return_beta_reason)}</div>}</td>
          <td>{row.coverage_reason && <div className="inline-note amber">覆盖：{researchReason(row.coverage_reason)}</div>}{row.reason && <div className="inline-note amber">记录：{researchReason(row.reason)}</div>}{!row.coverage_reason && !row.reason ? '—' : null}</td>
        </tr>)}</tbody></table></div>
    </>}
  </details>;
}
