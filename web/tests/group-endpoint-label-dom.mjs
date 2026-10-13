// Optional ReactDOM synthetic-flow check. No browser or product dependency added.
import test, {after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
import {createServer} from 'vite';
import {createElement, act, useState} from 'react';
const {JSDOM}=await import(process.env.ANATRADING_JSDOM_PATH ? pathToFileURL(process.env.ANATRADING_JSDOM_PATH).href : 'jsdom');
const dom=new JSDOM('<!doctype html><div id="root"></div>');
Object.assign(globalThis,{window:dom.window,document:dom.window.document,HTMLElement:dom.window.HTMLElement,IS_REACT_ACT_ENVIRONMENT:true});
const {createRoot}=await import('react-dom/client');
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {UniverseResearch,createUniverseDraft}=await server.ssrLoadModule('/src/UniverseResearch.tsx');
const root=createRoot(document.getElementById('root'));
const fixtures=JSON.parse(readFileSync(new URL('./group-endpoint-fixtures.json',import.meta.url)));
const originalFetch=globalThis.fetch;
after(async()=>{await act(()=>root.unmount());await server.close();dom.window.close();globalThis.fetch=originalFetch;});

for(const key of ['complete','partial'])test(`${key}: renamed mode submits old parameters and retains status, member selection and exact callbacks`,async()=>{
 const f=fixtures[key],calls=[],pending=[];let current;
 const initial={...createUniverseDraft(),mode:'existing',ids:[...f.expected.ids].reverse(),cutoff:f.expected.end,groupStart:f.expected.start,groupName:'人工组'};
 const snapshots=f.expected.ids.map(id=>({snapshot_id:id,row_count:2,metadata:{period:'1d',source_code:id.slice(0,6)}}));
 function Harness(){const [draft,setDraft]=useState(initial);current=draft;return createElement(UniverseResearch,{snapshots,draft,onDraftChange:setDraft,onImport(){},onOpen:(...args)=>calls.push(args)});}
 globalThis.fetch=(url,options)=>new Promise(resolve=>pending.push({url,options,resolve}));
 await act(()=>root.render(createElement(Harness)));
 const select=[...document.querySelectorAll('select')].find(s=>[...s.options].some(o=>o.value==='group_endpoints'));
 assert.equal([...select.options].find(o=>o.value==='group_endpoints').textContent,'区间收盘变化对比');
 await act(()=>{select.value='group_endpoints';select.dispatchEvent(new dom.window.Event('change',{bubbles:true}));});
 assert.deepEqual(current,{...initial,mode:'group_endpoints'});
 assert.equal(document.querySelector('legend').textContent,'统一起止日期 · 源收盘变化');
 assert.equal(document.getElementById('universe-run').textContent,'比较区间收盘变化');
 assert.equal(document.querySelectorAll('input[type=checkbox]:checked').length,initial.ids.length);
 const submit=()=>act(()=>document.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true})));
 await submit();assert.equal(pending.length,1);
 const url=new URL(pending[0].url,'http://localhost');
 assert.equal(url.pathname,'/api/research/group-endpoints');
 assert.deepEqual([...url.searchParams], [['snapshot_ids',[...f.expected.ids].sort().join(',')],['start_date',f.expected.start],['end_date',f.expected.end]]);
 await act(async()=>pending[0].resolve(new Response(JSON.stringify(f.reply))));
 // Identity verification includes async WebCrypto; wait for its actual terminal UI state.
 for(let i=0;i<100 && document.getElementById('universe-run').disabled;i++)await act(()=>new Promise(resolve=>setTimeout(resolve,10)));
 assert.equal(document.getElementById('universe-run').disabled,false);
 assert.equal(document.querySelector('[role=alert]'),null);
 assert.ok([...document.querySelectorAll('h2')].some(h=>h.textContent==='区间收盘变化对比 · 人工组'));
 const c=f.reply.counts;
 assert.equal(document.querySelector('.research-request-status').textContent,`区间收盘变化核验完成：原组 ${c.selected}、有效 ${c.valid}、不可算 ${c.missing}。`);
 assert.match(document.body.textContent,/源收盘变化 = 终点收盘 \/ 起点收盘 − 1/);
 assert.match(document.body.textContent,/复权、历史当时可得性、交易日历和收盘闭合均未核实/);
 if(key==='partial')assert.match(document.body.textContent,/完整组均值、中位数、Q1、Q3均留空/);
 await act(()=>[...document.querySelectorAll('button')].filter(b=>/打开此版本至[起终]点日期/.test(b.textContent)).forEach(b=>b.click()));
 assert.deepEqual(calls,f.reply.members.flatMap(m=>[[m.snapshot_id,f.expected.start],[m.snapshot_id,f.expected.end]]));
 // A repeated request clears the old result; cancellation never revives it.
 await submit();assert.equal(pending.length,2);
 assert.ok(![...document.querySelectorAll('h2')].some(h=>h.textContent==='区间收盘变化对比 · 人工组'));
 await act(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='取消等待').click());
 assert.equal(pending[1].options.signal.aborted,true);
 await act(async()=>pending[1].resolve(new Response(JSON.stringify(f.reply))));
 assert.match(document.querySelector('.research-request-status').textContent,/已停止等待/);
 assert.deepEqual(current,{...initial,mode:'group_endpoints'});
 await act(()=>root.render(null));
});
