import { useEffect, useMemo, useRef, useState } from 'react';
import { CandlestickSeries, ColorType, CrosshairMode, HistogramSeries, LineSeries, createChartEx, createSeriesMarkers } from 'lightweight-charts';
import type { IChartApiBase, MouseEventParams, SeriesMarker } from 'lightweight-charts';
import { buildPlot } from './model.ts';
import { SequenceAxis } from './sequence-axis.ts';
import { RecordDetails } from './RecordDetails.tsx';
import type { Reply, Row } from './types.ts';

export function recordStatusMarkers(status: string[][]): SeriesMarker<number>[] {
  return status.flatMap((notes, time) => {
    if (!notes.length) return [];
    const zero = notes.includes('数量为零');
    const missing = notes.includes('数量缺失或不可绘制');
    const problem = notes.some(note => note !== '数量为零');
    return [{ time, position: 'aboveBar', shape: zero ? 'circle' : 'square', size: 0.6,
      color: problem ? '#a16619' : '#526278', text: zero ? (problem ? '0 !' : '0') : missing ? '∅ !' : '!' }];
  });
}

export function SourceChart({ reply, onChoose, onError }: { reply: Reply; onChoose: (row: Row) => void; onError: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApiBase<number> | null>(null);
  const [hover, setHover] = useState<number | null>(null);
  const plot = useMemo(() => buildPlot(reply.query.rows, reply.display), [reply]);
  useEffect(() => {
    if (!host.current || !reply.query.rows.length) return;
    let chart: IChartApiBase<number> | null = null;
    try {
      chart = createChartEx(host.current, new SequenceAxis(plot.labels), {
        autoSize: true,
        layout: { background: { type: ColorType.Solid, color: '#ffffff' }, textColor: '#657184', fontSize: 11, attributionLogo: true },
        grid: { vertLines: { color: '#f1f3f7' }, horzLines: { color: '#edf0f5' } },
        rightPriceScale: { borderColor: '#e3e8ef', scaleMargins: { top: 0.1, bottom: 0.08 } },
        timeScale: { borderColor: '#e3e8ef', ignoreWhitespaceIndices: false, enableConflation: false,
          precomputeConflationOnInit: false, tickMarkMaxCharacterLength: 20, minBarSpacing: 0.01 },
        crosshair: { mode: CrosshairMode.Normal, horzLine: { labelVisible: false } },
        localization: { locale: 'zh-CN' },
      });
      chartRef.current = chart;
      const candles = chart.addSeries(CandlestickSeries, { lastValueVisible: false, priceLineVisible: false,
        priceFormat: { type: 'price', precision: 4, minMove: 0.0001 } }, 0);
      const volume = chart.addSeries(HistogramSeries, { lastValueVisible: false, priceLineVisible: false,
        priceFormat: { type: 'volume' } }, 1);
      candles.setData(plot.candles);
      volume.setData(plot.volumes);
      chart.panes()[1].setHeight(125);
      // One status label per record avoids independent plugins overlapping. The hidden
      // scale keeps labels near the lower baseline; its constant is not source quantity.
      const annotations = chart.addSeries(LineSeries, { priceScaleId: 'record-status', lineVisible: false,
        pointMarkersVisible: false, lastValueVisible: false, priceLineVisible: false, crosshairMarkerVisible: false }, 1);
      annotations.priceScale().applyOptions({ visible: false, scaleMargins: { top: 0.86, bottom: 0.08 } });
      annotations.setData(plot.labels.map((_, time) => ({ time, value: 0 })));
      // inBar puts text below its shape; aboveBar keeps it inside this short pane.
      createSeriesMarkers(annotations, recordStatusMarkers(plot.status), { autoScale: false, zOrder: 'top' });
      const rowFor = (event: MouseEventParams<number>) => {
        const index = event.time;
        return index !== undefined && Number.isInteger(index) && index >= 0 && index < reply.query.rows.length ? index : null;
      };
      chart.subscribeCrosshairMove(event => setHover(event.point ? rowFor(event) : null));
      chart.subscribeClick(event => { const index = rowFor(event); if (index !== null) onChoose(reply.query.rows[index]); });
      chart.timeScale().fitContent();
    } catch {
      chart?.remove();
      chartRef.current = null;
      onError();
      return;
    }
    return () => { chart?.remove(); chartRef.current = null; };
  }, [reply, plot, onChoose, onError]);

  return <section className="panel chart-panel" aria-label="源 OHLC 与源数量图">
    <div className="section-heading"><div><h2>源 OHLC <span className="muted">/ 源数量</span></h2><p>源记录序列 · 等距不代表时间间隔 · 坐标为近似显示</p></div>
      <button className="quiet" onClick={() => chartRef.current?.timeScale().fitContent()} disabled={!reply.query.rows.length}>恢复视图</button></div>
    <div className="chart-legend"><span><i className="red-dot" />收 &gt; 开</span><span><i className="green-dot" />收 &lt; 开</span><span>灰色：相等 / 未知 · 方向取精确比较</span><span className="amber">状态行：0 数量为零 · ∅ 数量缺失 · ! 问题提示（位置不表示数量）</span></div>
    {reply.query.rows.length ? <div ref={host} className="chart-host" onMouseLeave={() => setHover(null)} /> : <div className="empty-chart">当前截止范围没有可定位记录。无法定位记录仍单独列出。</div>}
    <div className="chart-tooltip" aria-label="十字线精确值">
      {hover !== null && reply.query.rows[hover] ? <><div className="tooltip-title">十字线 · 精确解码字符串<span>{plot.status[hover].join(' · ')}</span></div><RecordDetails row={reply.query.rows[hover]} contract={reply.query.manifest.contract} compact /></>
        : <p className="muted">移动十字线查看精确值；点击记录可固定详情。单位与柱定义保持源资格，不推断真实成交方向。</p>}
    </div>
  </section>;
}
