// Test-only graphical API adapter. Actual SourceChart React state, effects, DOM,
// model calculations and onChoose closure are retained. No pixel/canvas claims.
export const CandlestickSeries={}, HistogramSeries={}, LineSeries={}, ColorType={Solid:'solid'},CrosshairMode={Normal:0},LineType={WithSteps:0};
export const charts=[];
export function createChartEx(host){const marker=document.createElement('span');marker.dataset.chartAdapter='true';host.append(marker);const chart={removed:false,click:null,addSeries(){return {setData(){},priceScale(){return {applyOptions(){}}}}},panes(){return [{setHeight(){}},{setHeight(){}}]},subscribeCrosshairMove(fn){this.hover=fn},subscribeClick(fn){this.click=fn},timeScale(){return {setVisibleLogicalRange(){},fitContent(){}}},removeSeries(){},remove(){this.removed=true;marker.remove();}};charts.push(chart);return chart;}
export function createSeriesMarkers(){return {setMarkers(){}};}
