// Real ReactDOM with optional external jsdom; this is not browser visual QA.
import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import{readFileSync}from'node:fs';
import{pathToFileURL}from'node:url';
import{createServer}from'vite';
import{createElement,act,Profiler}from'react';
const{JSDOM}=await import(process.env.ANATRADING_JSDOM_PATH?pathToFileURL(process.env.ANATRADING_JSDOM_PATH).href:'jsdom');
const dom=new JSDOM('<!doctype html><div id="root"></div>');
Object.assign(globalThis,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
const{createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const{OhlcDeclineBounds}=await server.ssrLoadModule('/src/OhlcDeclineBounds.tsx');
const root=createRoot(document.getElementById('root')),original=globalThis.fetch;
after(async()=>{await act(()=>root.unmount());await server.close();dom.window.close();globalThis.fetch=original;});
const fixture=()=>JSON.parse(readFileSync(new URL('./fixtures/decline-bounds.json',import.meta.url)));
const draw=(q,probe=()=>{})=>act(()=>root.render(createElement(Profiler,{id:'panel',onRender:probe},createElement(OhlcDeclineBounds,{query:q}))));
const click=text=>act(()=>[...document.querySelectorAll('button')].find(b=>b.textContent===text).click());
const submit=()=>act(()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
const input=(i,text)=>act(()=>{const e=document.querySelectorAll('input')[i];Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(e,text);e.dispatchEvent(new dom.window.Event('input',{bubbles:true}));e.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
let pending=[];function deferred(){pending=[];globalThis.fetch=(url,options)=>new Promise((resolve,reject)=>pending.push({url,options,resolve,reject}));}
const settle=(item,report)=>act(async()=>item.resolve(new Response(JSON.stringify(report))));
const clear=()=>act(()=>root.render(null));
const cards=()=>document.querySelectorAll('.metric-grid').length;
async function choose(){await click('选择来源窗口');await input(0,'2026-01-01');await input(1,'2026-01-01');}
test('explicit dates, no automatic fetch, duplicate submit, cancel, close, stale and recovery',async()=>{
 const{query,report}=fixture();deferred();await draw(query);await click('选择来源窗口');assert.equal(pending.length,0);await submit();assert.equal(pending.length,0);
 await input(0,'2026-01-01');await input(1,'2026-01-01');await submit();await submit();assert.equal(pending.length,1);
 const a=pending[0];await click('取消读取');assert.equal(a.options.signal.aborted,true);await submit();const b=pending.at(-1);await settle(b,report);assert.equal(cards(),1);await settle(a,{});assert.equal(cards(),1);
 await input(0,'2025-12-31');assert.equal(cards(),0);await input(0,'2026-01-01');await submit();await settle(pending.at(-1),{});assert.ok(document.querySelector('[role=alert]'));assert.equal(cards(),0);
 await submit();await settle(pending.at(-1),report);assert.equal(cards(),1);await submit();const closed=pending.at(-1);await click('关闭来源窗口');await settle(closed,report);assert.equal(cards(),0);await click('选择来源窗口');assert.equal(cards(),0);await clear();
});
for(const[key,mutate]of Object.entries({owner:q=>q.query_id='other',snapshot:q=>q.snapshot_id='other',batch:q=>q.batch_id='other',raw:q=>q.manifest.raw_sha256='b'.repeat(64),contract:q=>q.manifest.source_contract_id='other',qualification:q=>q.manifest.qualification={changed:true},cutoff:q=>q.selection.cutoff='2026-01-02',ordinal:q=>q.selection.ordinal_start=5,period:q=>q.metadata.period='1m',mode:q=>q.selection.mode='other',quarantine:q=>q.metadata.quarantined=true,negative:q=>q.batch_checks=[{name:'known_negative_sample',outcome:'fail'}],code:q=>q.metadata.source_code='600001',venue:q=>q.metadata.source_venue='SZ',adjustment:q=>q.metadata.source_adjustflag='2',declaration:q=>q.metadata.interpretation={instrument:'600001',venue:'SH'}}))test('first commit hides and resets '+key,async()=>{
 const{query,report}=fixture();deferred();await draw(query);await choose();await submit();await settle(pending.at(-1),report);assert.equal(cards(),1);await submit();const old=pending.at(-1);mutate(query);const commits=[];await draw(query,()=>commits.push({cards:cards(),form:!!document.querySelector('form')}));assert.ok(commits.length);assert.deepEqual(commits[0],{cards:0,form:false});assert.equal(old.options.signal.aborted,true);await settle(old,report);assert.equal(cards(),0);await click('选择来源窗口');assert.deepEqual([...document.querySelectorAll('input')].map(e=>e.value),['','']);await clear();
});
test('unmount rejects old work; display-only name does not reset',async()=>{const{query,report}=fixture();deferred();await draw(query);await choose();await submit();await settle(pending.at(-1),report);query.metadata.source_name='display';await draw(query);assert.equal(cards(),1);await submit();const old=pending.at(-1);await clear();assert.equal(old.options.signal.aborted,true);await draw(query);await settle(old,report);assert.equal(cards(),0);await clear();});
