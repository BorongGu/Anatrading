import type {
  ChartOptionsImpl, DataItem, IHorzScaleBehavior, InternalHorzScaleItem, InternalHorzScaleItemKey,
  LocalizationOptions, TickMark, TickMarkWeightValue, TimeMark, TimeScalePoint,
} from 'lightweight-charts';

// Indexes are display coordinates only. Labels are immutable for the lifetime of this chart.
export class SequenceAxis implements IHorzScaleBehavior<number> {
  private chartOptions!: ChartOptionsImpl<number>;
  private readonly labels: string[];
  constructor(labels: string[]) { this.labels = [...labels]; }
  options(): ChartOptionsImpl<number> { return this.chartOptions; }
  setOptions(options: ChartOptionsImpl<number>): void { this.chartOptions = options; }
  preprocessData(_data: DataItem<number> | DataItem<number>[]): void {}
  updateFormatter(options: LocalizationOptions<number>): void {
    if (this.chartOptions) this.chartOptions.localization = options;
  }
  createConverterToInternalObj() { return (item: number) => this.convertHorzItemToInternal(item); }
  convertHorzItemToInternal(item: number): InternalHorzScaleItem { return item as unknown as InternalHorzScaleItem; }
  key(item: InternalHorzScaleItem | number): InternalHorzScaleItemKey { return item as InternalHorzScaleItemKey; }
  cacheKey(item: InternalHorzScaleItem): number { return item as unknown as number; }
  formatHorzItem(item: InternalHorzScaleItem): string { return this.labels[this.cacheKey(item)] ?? ''; }
  formatTickmark(item: TickMark): string { return this.formatHorzItem(item.time); }
  maxTickMarkWeight(marks: TimeMark[]): TickMarkWeightValue {
    return marks.reduce((weight, mark) => Math.max(weight, mark.weight), 0) as TickMarkWeightValue;
  }
  fillWeightsForPoints(points: readonly { -readonly [K in keyof TimeScalePoint]: TimeScalePoint[K] }[], startIndex: number): void {
    for (let i = startIndex; i < points.length; i++) {
      const label = this.formatHorzItem(points[i].time);
      const previous = i > 0 ? this.formatHorzItem(points[i - 1].time) : '';
      points[i].timeWeight = (label.slice(0, 10) !== previous.slice(0, 10) ? 50 : 10) as TickMarkWeightValue;
    }
  }
}
