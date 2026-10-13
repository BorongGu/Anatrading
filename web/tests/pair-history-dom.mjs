// Optional integration runner, using an already installed jsdom without adding
// a product dependency. ANATRADING_JSDOM_PATH points to its lib/api.js.
import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
import { createServer } from 'vite';
import { createElement, act } from 'react';
import { fixture as parentFixture, snapshots, ids, cutoff } from './pair-history-fixtures.mjs';
const { JSDOM } = await import(process.env.ANATRADING_JSDOM_PATH ? pathToFileURL(process.env.ANATRADING_JSDOM_PATH).href : 'jsdom');
const dom = new JSDOM('<!doctype html><div id="root"></div>');
Object.assign(globalThis, { window: dom.window, document: dom.window.document, HTMLElement: dom.window.HTMLElement, IS_REACT_ACT_ENVIRONMENT: true });
const { createRoot } = await import('react-dom/client');
const server = await createServer({ server: { middlewareMode: true, hmr: false, ws: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
const { PairHistory } = await server.ssrLoadModule('/src/PairHistory.tsx');
const { CrossResearch } = await server.ssrLoadModule('/src/CrossResearch.tsx');
const root = createRoot(document.getElementById('root'));
after(async () => { await act(() => root.unmount()); await server.close(); dom.window.close(); });
const date = i => new Date(Date.UTC(2025, 0, i + 1)).toISOString().slice(0, 10);
function fixture(n = 101) { return { method_id:'pair',analysis_id:'same',inputs:[{snapshot_id:'A',query_id:'a'},{snapshot_id:'B',query_id:'b'}],parameters:{cutoff:'2026-01-01',lookback:5},result:{series:Array.from({length:n},(_,i)=>({date:date(i),returns_start_date:i?date(Math.max(0,i-5)):null,returns_end_date:i?date(i):null,n_returns:Math.min(i,5),return_correlation:i<5?null:1,return_beta:i<5?null:2,correlation_reason:i<5?'history_insufficient':null,return_beta_reason:i<5?'history_insufficient':null,coverage_reason:null,reason:null}))}}; }
const render = report => act(() => root.render(createElement(PairHistory, {report,lookback:5})));
const rows = () => [...document.querySelectorAll('tbody tr')];
const click = text => act(() => [...document.querySelectorAll('button')].find(b=>b.textContent===text).click());
const toggle = async open => { await act(async()=>{const d=document.querySelector('details');d.open=open;d.dispatchEvent(new dom.window.Event('toggle'));}); };

test('real ReactDOM preserves all pages, reasons and current report across repeated/interrupted display', async () => {
 const report=fixture();report.result.series[100].return_correlation=null;report.result.series[100].return_beta=0;report.result.series[100].correlation_reason='return_variance_too_small';report.result.series[100].coverage_reason='unequal_source_coverage';report.result.series[100].reason='duplicate_date';
 await render(report);assert.equal(document.querySelector('details').open,false);assert.equal(rows().length,50);assert.equal(rows()[0].cells[0].textContent,date(100));
 assert.match(rows()[0].cells[3].textContent,/—.*方差/);assert.equal(rows()[0].cells[4].textContent,'0.000');assert.match(rows()[0].cells[5].textContent,/覆盖：.*记录：/);
 const seen=[];await toggle(true);seen.push(...rows().map(r=>r.cells[0].textContent));await click('下一页');seen.push(...rows().map(r=>r.cells[0].textContent));await toggle(false);await toggle(true);assert.equal(rows()[0].cells[0].textContent,date(50));await click('下一页');seen.push(...rows().map(r=>r.cells[0].textContent));assert.deepEqual(seen,report.result.series.map(r=>r.date).reverse());assert.equal(rows().length,1);assert.match(rows()[0].cells[1].textContent,/— → —/);assert.equal(rows()[0].cells[2].textContent,'0 / 5');assert.equal(document.querySelectorAll('button')[1].disabled,true);
 await click('下一页');assert.equal(rows().length,1);await render({...report});assert.equal(rows()[0].cells[0].textContent,date(100));await render(report);await click('下一页');
 report.result.series[50].return_beta=-4;await render(report);assert.equal(rows()[0].cells[4].textContent,'-4.000');report.inputs[0].query_id='changed';await render(report);assert.equal(rows()[0].cells[0].textContent,date(100));
 await click('下一页');report.result.series.length=1;await render(report);assert.equal(rows().length,1);assert.equal(document.querySelectorAll('button')[0].disabled,true);report.result.series=fixture().result.series;await render(report);assert.equal(rows()[0].cells[0].textContent,date(100));
 await act(()=>root.render(null));assert.equal(document.querySelector('details'),null);await render(report);assert.equal(document.querySelector('details').open,false);assert.equal(rows()[0].cells[0].textContent,date(100));
 await render(fixture(0));assert.match(document.body.textContent,/截止范围没有共同日期记录/);assert.equal(rows().length,0);assert.equal(document.querySelectorAll('button').length,0);
});

for (const loss of ['removed', 'period']) test(`parent catalog ${loss} interrupts requests and never revives old history`, async () => {
 await act(()=>root.render(null));
 let source=structuredClone(snapshots);const pending=[];
 const previousFetch=globalThis.fetch;
 globalThis.fetch=(url,options)=>new Promise((resolve,reject)=>pending.push({url,options,resolve,reject}));
 const draw=()=>act(()=>root.render(createElement(CrossResearch,{kind:'pair',snapshots:source,onImport(){},onOpen(){}})));
 const submit=()=>act(()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
 const settle=(r,reject=false)=>act(async()=>{if(reject)r.reject(new Error('late synthetic failure'));else r.resolve({ok:true,json:async()=>parentFixture()});});
 const lose=()=>{if(loss==='removed')source=source.filter(s=>s.snapshot_id!==ids[0]);else source[0].metadata.period='1m';};
 try {
  await draw();await act(()=>{const input=document.querySelector('input[type=date]');Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(input,cutoff);input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));input.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
  await submit();assert.equal(pending.length,1);await settle(pending[0]);assert.ok(document.querySelector('.pair-history'));
  lose();await draw();assert.equal(document.querySelector('.pair-history'),null);assert.match(document.body.textContent,/所选数据版本已不可用/);await submit();assert.equal(pending.length,1);
  source=structuredClone(snapshots);await draw();assert.equal(document.querySelector('.pair-history'),null);
  await submit();const old=pending.at(-1);lose();await draw();assert.equal(old.options.signal.aborted,true);
  source=structuredClone(snapshots);await draw();await submit();const fresh=pending.at(-1);await settle(fresh);const current=document.querySelector('.pair-history');assert.ok(current);await settle(old,true);assert.equal(document.querySelector('.pair-history'),current);assert.equal(document.querySelector('[role=alert]'),null);
  await submit();const unmounted=pending.at(-1);await act(()=>root.render(null));assert.equal(unmounted.options.signal.aborted,true);await settle(unmounted);assert.equal(document.querySelector('.pair-history'),null);
 } finally {globalThis.fetch=previousFetch;}
});
