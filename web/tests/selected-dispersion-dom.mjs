// Optional real ReactDOM runner with externally installed jsdom, no product dependency.
import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {createServer} from 'vite';
import {createElement,act} from 'react';
const {JSDOM}=await import(process.env.ANATRADING_JSDOM_PATH ? pathToFileURL(process.env.ANATRADING_JSDOM_PATH).href:'jsdom');
const dom=new JSDOM('<!doctype html><div id="root"></div>');
Object.assign(globalThis,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {SelectedCloseDispersion}=await server.ssrLoadModule('/src/SelectedCloseDispersion.tsx');
const root=createRoot(document.getElementById('root'));
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/selected-dispersion.json',import.meta.url)));
const original=globalThis.fetch;
after(async()=>{await act(()=>root.unmount());await server.close();dom.window.close();globalThis.fetch=original;});
const draw=q=>act(()=>root.render(createElement(SelectedCloseDispersion,{query:q})));
const click=text=>act(()=>[...document.querySelectorAll('button')].find(b=>b.textContent===text).click());
const submit=()=>act(()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
let pending=[];
function deferred(){pending=[];globalThis.fetch=(url,options)=>new Promise((resolve,reject)=>pending.push({url,options,resolve,reject}));}
const settle=(item,report)=>act(async()=>item.resolve(new Response(JSON.stringify(report))));
const clear=()=>act(()=>root.render(null));
const rows=()=>document.querySelectorAll('tbody tr').length;

test('independent on-demand window, close/cancel late result and fresh recovery',async()=>{
 const {query,report}=fixture();deferred();await draw(query);assert.equal(pending.length,0);
 await click('打开离散窗口');assert.equal(pending.length,1);await settle(pending[0],report);assert.equal(rows(),20);
 await submit();const canceled=pending.at(-1);await click('取消读取');assert.equal(canceled.options.signal.aborted,true);
 await settle(canceled,report);assert.equal(rows(),0);
 await submit();const closed=pending.at(-1);await click('关闭离散窗口');assert.equal(closed.options.signal.aborted,true);
 await settle(closed,report);assert.equal(rows(),0);assert.equal(document.querySelector('form'),null);
 await click('打开离散窗口');await settle(pending.at(-1),report);assert.equal(rows(),20);
 await clear();
});

test('newest request owns results, invalid response is isolated and recoverable',async()=>{
 const {query,report}=fixture();deferred();await draw(query);await click('打开离散窗口');const a=pending.at(-1);
 await submit();const b=pending.at(-1);assert.equal(a.options.signal.aborted,true);
 await settle(b,report);assert.equal(rows(),20);await settle(a,{...report,identity:{...report.identity,snapshot_id:'wrong'}});assert.equal(rows(),20);
 await submit();await settle(pending.at(-1),{});assert.equal(rows(),0);assert.ok(document.querySelector('[role=alert]'));
 await submit();await settle(pending.at(-1),report);assert.equal(rows(),20);assert.equal(document.querySelector('[role=alert]'),null);
 await clear();
});

for(const [key,change] of Object.entries({owner:q=>q.query_id='changed',snapshot:q=>q.snapshot_id='changed',batch:q=>q.batch_id='changed',cutoff:q=>q.selection.cutoff='2025-01-20',ordinal:q=>q.selection.ordinal_start=3,mode:q=>q.selection.mode='other',period:q=>q.metadata.period='1m',quarantine:q=>q.metadata.quarantined=true,qualification:q=>q.manifest.qualification='changed',negative:q=>q.batch_checks=[{name:'known_negative_sample',outcome:'fail'}],code:q=>q.metadata.source_code='600001',venue:q=>q.metadata.source_venue='SZ',adjustment:q=>q.metadata.source_adjustflag='2',declaration:q=>q.metadata.interpretation={instrument:'600001',venue:'SH'}})) {
 test(`same-ID ${key} mutation invalidates and closes current/pending results`,async()=>{
  const {query,report}=fixture();deferred();await draw(query);await click('打开离散窗口');await settle(pending.at(-1),report);assert.equal(rows(),20);
  await submit();const old=pending.at(-1);change(query);await draw(query);assert.equal(rows(),0);assert.equal(old.options.signal.aborted,true);
  await settle(old,report);assert.equal(rows(),0);assert.equal(document.querySelector('form'),null);await clear();
 });
}

test('unmount and remount never revives a pending generation',async()=>{
 const {query,report}=fixture();deferred();await draw(query);await click('打开离散窗口');const old=pending.at(-1);
 await clear();assert.equal(old.options.signal.aborted,true);await draw(query);await settle(old,report);assert.equal(rows(),0);assert.equal(document.querySelector('form'),null);
 await clear();
});


test('unrelated display metadata does not discard the current accepted report',async()=>{
 const {query,report}=fixture();deferred();await draw(query);await click('打开离散窗口');await settle(pending.at(-1),report);
 query.metadata.source_name='new display name';await draw(query);assert.equal(rows(),20);assert.equal(pending.length,1);await clear();
});

test('date edits clear old result and invalidate pending response before exact resubmission',async()=>{
 const {query,report}=fixture();deferred();await draw(query);await click('打开离散窗口');await settle(pending.at(-1),report);
 await submit();const old=pending.at(-1);
 await act(()=>{
  const input=document.querySelector('input[type=date]');
  Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(input,'2026-01-20');
  input.dispatchEvent(new dom.window.Event('input',{bubbles:true}));input.dispatchEvent(new dom.window.Event('change',{bubbles:true}));
 });
 assert.equal(rows(),0);assert.equal(old.options.signal.aborted,true);
 await settle(old,report);assert.equal(rows(),0);await submit();assert.match(pending.at(-1).url,/date=2026-01-20/);
 const exact=structuredClone(report);exact.selection={date_requested:'2026-01-20',resolved_date:'2026-01-20',policy:'exact_source_date'};
 await settle(pending.at(-1),exact);assert.equal(rows(),20);await clear();
});
