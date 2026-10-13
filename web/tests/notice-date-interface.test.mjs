import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {buildNoticeDiagnostic,noticeHash} from '../src/notice-date-model.ts';
const fixtures=JSON.parse(execFileSync(fileURLToPath(new URL(process.platform==='win32'?'../../.venv/Scripts/python.exe':'../../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../../tests/notice_date_fixture_bridge.py',import.meta.url))],{encoding:'utf8',maxBuffer:8*1024*1024}));
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {NoticeDateDiagnostic,NoticeDateReadout,NoticeExchangeTable,noticeDatePage}=await server.ssrLoadModule('/src/NoticeDateDiagnostic.tsx');
after(()=>server.close());
const render=(component,props)=>renderToStaticMarkup(createElement(component,props));
const diagnostic=name=>buildNoticeDiagnostic(structuredClone(fixtures[name].reply));
test('051 optional panel is folded with no diagnostic calculation mounted on SSR',()=>{
 const html=render(NoticeDateDiagnostic,{report:fixtures.complete.reply,onOpen(){}});assert.match(html,/已核公告日期核对（回顾）/);assert.doesNotMatch(html,/<details open|<table|有限公告日期核对结果|正在核对/);assert.match(html,/上交所未覆盖/);
});
test('readout displays full denominator, unknown identity, source-claim scope and honest static evidence boundary',async()=>{
 const d=await diagnostic('refused'),html=render(NoticeDateReadout,{diagnostic:d,onOpen(){}});assert.match(html,/原选 2 个成员，交易所声明未核实 1 个/);assert.match(html,/交易所声明已核为SZSE的 1 个成员/);assert.match(html,/未认证证券主数据身份/);assert.match(html,/没有重新读取或认证官方原件/);assert.match(html,/前缀|截至|更早来源日/);for(const m of d.members)assert.ok(html.includes(m.snapshot_id));
 assert.doesNotMatch(html,/交易日完整率|认证供应商漏日|全部股票缺席/);
});
test('empty arrays yield explicit not-evaluated and no zero-difference success',async()=>{
 const html=render(NoticeDateReadout,{diagnostic:await diagnostic('empty'),onOpen(){}});assert.match(html,/没有可比较的成员日期单元，未评估/);assert.doesNotMatch(html,/本次已核公告日期内未发现相应差异/);
});
test('candidate labels preserve single/multiple and fixed source-qualified exchange wording',async()=>{
 const all=await diagnostic('missing_all'),html=render(NoticeDateReadout,{diagnostic:all,onOpen(){}});assert.match(html,/该所声明已核的全部成员无来源日期（候选）/);assert.match(html,/交易所声明已核为SZSE的 2 个成员/);
 const one=structuredClone(fixtures.missing_all.reply);one.members[0].source_qualified=false; // Invalid DTO must not publish.
 await assert.rejects(()=>buildNoticeDiagnostic(one));
});
test('pagination preserves every explicit date with bounded50-row render',async()=>{
 const d=await diagnostic('empty'),ref=structuredClone(d.reference); // Use pure table data for the all85-date rendering budget, no source qualification changes.
 const dates=ref.notices.flatMap(n=>n.reopen_dates.map(date=>({date,planned:'open',evidence:[n.id],present:[],absent:[],unknown:d.members.map(m=>m.snapshot_id),finding:null})));
 const all=Array.from({length:101},(_,i)=>({...dates[i%dates.length],date:`fixture-${i}`}));const result={...d.exchanges[1],dates:all};
 const collected=[];for(let page=0;page<3;page++){collected.push(...noticeDatePage(all,page).rows);const html=render(NoticeExchangeTable,{result,diagnostic:d,page,onPage(){},onOpen(){}});assert.equal((html.match(/<tbody>.*?<\/tbody>/s)[0].match(/<tr>/g)||[]).length,Math.min(50,101-page*50));}
 assert.deepEqual(collected,all);assert.throws(()=>noticeDatePage(all,-1));assert.throws(()=>noticeDatePage(all,3));assert.equal(noticeDatePage([],0).pages,1);
});
function visit(node,fn){if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(n=>visit(n,fn));return;}fn(node);if(typeof node.type==='function')visit(node.type(node.props),fn);else visit(node.props?.children,fn);}
test('source buttons preserve complete snapshot ID and requested cutoff even for absent date',async()=>{
 const d=await diagnostic('missing_all'),result=d.exchanges[1],calls=[],tree=NoticeExchangeTable({result,diagnostic:d,page:0,onPage(){},onOpen:(...args)=>calls.push(args)});
 visit(tree,n=>{if(n.type==='button'&&n.props['aria-label']?.startsWith('打开该版本截至此日'))n.props.onClick();});
 assert.ok(calls.some(([id,date])=>date==='2026-01-05'&&d.members.some(m=>m.snapshot_id===id)));
 assert.ok(calls.every(([id,date])=>id.length===64&&result.dates.some(row=>row.date===date&&(row.present.includes(id)||row.absent.includes(id)))));
});
test('production module never fetches or invokes backend and holds immutable derived facts only',()=>{
 const source=readFileSync(new URL('../src/NoticeDateDiagnostic.tsx',import.meta.url),'utf8')+readFileSync(new URL('../src/notice-date-model.ts',import.meta.url),'utf8');assert.doesNotMatch(source,/fetch\(|\/api\/|localStorage|sessionStorage/);assert.match(source,/active=false/);assert.match(source,/state\?\.report!==report/);
});
