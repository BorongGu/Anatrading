import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { assertGroupPairs,verifyGroupPairIdentity,groupPairRequest,groupPairReason } from '../src/group-pair-model.ts';
import { createUniverseDraft,prepareUniverseRequest,loadUniverseRequest } from '../src/universe-request.ts';
import { ResearchRequestController,canonicalJson } from '../src/filter-model.ts';
const fixtures=JSON.parse(execFileSync(fileURLToPath(new URL('../../.venv/bin/python',import.meta.url)),[fileURLToPath(new URL('../../tests/group_pair_fixture_bridge.py',import.meta.url))],{encoding:'utf8',maxBuffer:4*1024*1024}));
const f=(name='complete')=>structuredClone(fixtures[name]);
const draftFor=f=>({...createUniverseDraft(),mode:'group_pairs',ids:f.expected.ids,cutoff:f.expected.cutoff,peerTarget:'ignored',lookback:'ignored',filter:{enabled:true,groups:[]}});
const tick=()=>new Promise(resolve=>setImmediate(resolve));
// Vite middleware transforms SSR modules only; no listening port, service or browser.
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
const {GroupPairResults,GroupPairPage,GroupPairSource,groupPairPage}=await server.ssrLoadModule('/src/GroupPairResults.tsx');
const {UniverseResearch}=await server.ssrLoadModule('/src/UniverseResearch.tsx');
const render=(component,props)=>renderToStaticMarkup(createElement(component,props));
after(()=>server.close());
for(const name of Object.keys(fixtures))test(`051 actual Python ${name} strict DTO and SHA`,async()=>{const x=f(name);assertGroupPairs(x.reply,x.expected);await verifyGroupPairIdentity(x.reply);});
const changes={
 extra_key:r=>r.target='x', rule:r=>r.parameters.rules.transform='log', scope:r=>r.scope.price_currency.value='USD',limitation:r=>r.limitations.trading_calendar='known',
 cutoff:r=>r.parameters.cutoff='2026-01-01',member:r=>r.members.pop(), order:r=>r.members.reverse(), query:r=>r.members[0].query_id=r.members[1].query_id,
 batch:r=>r.members[0].batch_id=r.members[1].batch_id, symbol:r=>r.members[0].symbol=r.members[1].symbol,
 missing_pair:r=>r.pairs.pop(), duplicate_pair:r=>r.pairs[1]=r.pairs[0], reverse_pair:r=>[r.pairs[0].left_snapshot_id,r.pairs[0].right_snapshot_id]=[r.pairs[0].right_snapshot_id,r.pairs[0].left_snapshot_id],
 sign:r=>r.pairs[0].current.correlation.sign='negative', display:r=>r.pairs[0].current.correlation.display='NaN', estimate:r=>r.pairs[0].current.correlation.estimate='2E+0',
 tiny:r=>r.pairs[0].current.correlation.estimate='1E-10001', oversized_digits:r=>r.pairs[0].current.correlation.estimate='1.'+'9'.repeat(100)+'E-1',
 boundary:r=>r.pairs[0].current.correlation.exact_boundary='zero', null:r=>r.pairs[0].current.correlation=null,
 constants:r=>r.members[0].constant.current=true, pair_constants:r=>r.pairs[0].current.constant_members=[r.members[0].snapshot_id],
 endpoint:r=>r.members[0].endpoints.pop(), ordinal:r=>r.members[0].endpoints[1].ordinal=r.members[0].endpoints[0].ordinal,
 date:r=>r.members[0].date_array[30]=r.members[0].date_array[29], grid:r=>r.used_dates.pop(), reasons:r=>r.grid_reasons=['member_grid_unavailable'],
 window:r=>r.windows.current.available--, total:r=>r.counts.pairs--, status:r=>r.status='unavailable', anomaly:r=>r.members[0].anomalies.total++,
 panel:r=>r.source_panel_complete=false, events:r=>r.events=[{}], budget:r=>r.members[0].endpoints[0].close_token='x'.repeat(2*1024*1024),
};
for(const [name,change]of Object.entries(changes))test(`051 rejects DTO tamper ${name}`,()=>{const x=f();change(x.reply);assert.throws(()=>assertGroupPairs(x.reply,x.expected));});
test('051 constant claims checked against prices even with internally consistent cells',()=>{
 const x=f();for(const m of x.reply.members)m.constant.current=true;
 for(const p of x.reply.pairs)p.current={correlation:null,reason:'constant_source_change',constant_members:[p.left_snapshot_id,p.right_snapshot_id]};
 x.reply.windows.current.available=0;x.reply.windows.current.unavailable=x.reply.pairs.length;x.reply.status='partial';
 assert.throws(()=>assertGroupPairs(x.reply,x.expected));
});
test('051 all failure pair cells and constant member list are exact',()=>{
 for(const name of ['refused','missing','price','empty','cutoff','duplicate','unknown']){const x=f(name);x.reply.pairs[0].current.constant_members=[x.reply.members[0].snapshot_id];assert.throws(()=>assertGroupPairs(x.reply,x.expected));}
 const x=f('partial'),p=x.reply.pairs.find(p=>p.current.reason==='constant_source_change');p.current.constant_members=[];assert.throws(()=>assertGroupPairs(x.reply,x.expected));
});
test('051 exact tiny sign never Number underflows; non-boundary can display as one',()=>{
 const x=f();x.reply.pairs[0].current.correlation={estimate:'-1E-4566',display:'0.0000',sign:'negative',exact_boundary:'none'};assertGroupPairs(x.reply,x.expected);
 x.reply.pairs[0].current.correlation={estimate:'1E+0',display:'1.0000',sign:'positive',exact_boundary:'none'};assertGroupPairs(x.reply,x.expected);
});
test('051 hash rejects changed identity but is explicitly not a signature or Pearson oracle',async()=>{
 const x=f();x.reply.analysis_id='0'.repeat(64);await assert.rejects(()=>verifyGroupPairIdentity(x.reply));
 const y=f();y.reply.members[0].query_id='f'.repeat(64);assertGroupPairs(y.reply,y.expected);await assert.rejects(()=>verifyGroupPairIdentity(y.reply));
 const r=y.reply,identity={method_id:r.method_id,rule_version:r.rule_version,source_rule_version:r.source_rule_version,parameters:r.parameters,sources:r.members.map(({symbol,snapshot_id,batch_id,query_id,date_array})=>({symbol,snapshot_id,batch_id,query_id,date_array})),used_dates:r.used_dates,scope:r.scope,limitations:r.limitations,events:r.events};
 r.analysis_id=Buffer.from(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(canonicalJson(identity)))).toString('hex');await verifyGroupPairIdentity(r);
});
test('051 request copies all IDs and one explicit submission makes exactly one GET',async()=>{
 const x=f(),draft=draftFor(x),calls=[],original=globalThis.fetch;
 globalThis.fetch=async(url,options)=>{calls.push([url,options]);return Response.json(x.reply);};
 try{const controller=new ResearchRequestController(()=>{});await controller.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);
 assert.equal(controller.state.status,'ready');assert.equal(controller.state.result.kind,'group_pairs');assert.equal(calls.length,1);
 assert.match(calls[0][0],/^\/api\/research\/group-pairs\?/);assert.doesNotMatch(calls[0][0],/target|lookback|events|start_date/);
 assert.equal(calls[0][1].cache,'no-store');controller.dispose();
 }finally{globalThis.fetch=original;}
 const expected=x.expected,request=groupPairRequest(expected);expected.ids.reverse();assert.deepEqual(request.expected.ids,[...expected.ids].sort());
 assert.equal(createUniverseDraft().mode,'existing');
});
test('051 cancel, invalidate, dispose and late fetch/hash cannot publish obsolete report',async()=>{
 const x=f(),draft=draftFor(x),original=globalThis.fetch;
 try{for(const action of ['cancel','invalidate','dispose']){
   let finish;globalThis.fetch=()=>new Promise(resolve=>finish=resolve);const c=new ResearchRequestController(()=>{});
   const task=c.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);await tick();c[action]();finish(Response.json(x.reply));await task;assert.equal(c.state.result,null);c.dispose();
 }
 const oldDigest=crypto.subtle.digest.bind(crypto.subtle);let finish;globalThis.fetch=async()=>Response.json(x.reply);
 crypto.subtle.digest=(...args)=>new Promise(resolve=>finish=async()=>resolve(await oldDigest(...args)));
 try{const c=new ResearchRequestController(()=>{}),task=c.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);await tick();c.invalidate();await finish();await task;assert.equal(c.state.result,null);c.dispose();}finally{crypto.subtle.digest=oldDigest;}
 }finally{globalThis.fetch=original;}
});
test('051 SSR explicit targetless entry and default unchanged with no automatic request',()=>{
 const x=f(),draft=draftFor(x),html=render(UniverseResearch,{draft,snapshots:x.expected.ids.map(id=>({snapshot_id:id,row_count:121,metadata:{period:'1d',source_code:id.slice(0,6)}})),onImport(){},onOpen(){}});
 assert.match(html,/无目标/);assert.match(html,/核对完整成对双窗/);assert.doesNotMatch(html,/id="universe-peer-target"|id="universe-lookback"|id="universe-group-start"/);
});
test('051 SSR both tables initially folded and only selected source pair can mount',()=>{
 for(const name of Object.keys(fixtures)){const r=f(name).reply,html=render(GroupPairResults,{report:r,name:'合成',onOpen(){}});
 assert.match(html,/全成对双窗相关/);assert.doesNotMatch(html,/<details open|<table|选中对来源回查/);
 for(const m of r.members)assert.ok(html.includes(m.snapshot_id));
 assert.match(html,/不自动聚焦源序号/);assert.match(html,/前端不独立认证原件/);
 }
});
test('051 pagination retains all 1225 pairs, constants and failures, 50 per page',()=>{
 for(const name of ['maximum','partial','missing']){const r=f(name).reply,all=[];
 for(let page=0;page<Math.ceil(r.pairs.length/50);page++){
 const result=groupPairPage(r,page);all.push(...result.pairs);
 const html=render(GroupPairPage,{report:r,window:'current',page,onPage(){},onSelect(){}});
 assert.equal((html.match(/回查双方/g)||[]).length,result.pairs.length);assert.ok(result.pairs.length<=50);
 }
 assert.deepEqual(all,r.pairs);assert.throws(()=>groupPairPage(r,-1));assert.throws(()=>groupPairPage(r,Math.ceil(r.pairs.length/50)));
 }
});
function visit(node,callback){if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(n=>visit(n,callback));return;}callback(node);visit(node.props?.children,callback);}
test('051 both sides arbitrary dates and boundary handlers preserve IDs and date labels',()=>{
 for(const name of ['complete','missing']){const r=f(name).reply,calls=[];
 for(const member of r.members){const tree=GroupPairSource({member,commonDates:r.used_dates,onOpen:(...args)=>calls.push(args)});visit(tree,n=>{if(n.type==='button')n.props.onClick();});}
 const expected=new Set(r.members.flatMap(m=>(m.endpoints??[]).map(p=>`${m.snapshot_id}/${p.date}`)));
 assert.ok(calls.every(([id,day])=>expected.has(`${id}/${day}`)));
 assert.equal(calls.length,r.members.reduce((n,m)=>n+(m.endpoints?.length??0)+(r.used_dates.length?3:0),0));
 }
});
test('051 page selection buttons select a single exact pair without requests',()=>{
 const r=f('maximum').reply,selected=[],pages=[],tree=GroupPairPage({report:r,window:'previous',page:1,onPage:p=>pages.push(p),onSelect:p=>selected.push(p)});
 visit(tree,n=>{if(n.type==='button')n.props.onClick();});assert.deepEqual(pages,[0,2]);assert.deepEqual(selected,r.pairs.slice(50,100));
 const source=readFileSync(new URL('../src/GroupPairResults.tsx',import.meta.url),'utf8');assert.match(source,/useState<GroupPair \| null>\(null\)/);assert.match(source,/setSelected\(null\)/);assert.doesNotMatch(source,/fetch\(/);
});


test('051 Python Unicode failure DTO uses full UTF-8 budget and ASCII-only identity',async()=>{
 const x=f('unicode_failure');assertGroupPairs(x.reply,x.expected);await verifyGroupPairIdentity(x.reply);
 assert.equal(new TextEncoder().encode(JSON.stringify(x.reply)).byteLength,x.serialized_bytes);
 const m=x.reply.members.find(m=>m.symbol==='600001.SH');
 assert.equal(m.endpoints[10].close_token,'停牌');assert.equal([...m.endpoints[13].close_token].length,128);
 assert.equal(x.reply.status,'unavailable');assert.equal(x.reply.members.length,3);assert.equal(x.reply.pairs.length,3);
 for(const code of ['未知核验','constructor','__proto__','toString']) assert.equal(groupPairReason(code),`来源限制：${code}`);
 const reordered=Object.fromEntries(Object.entries(x.reply).reverse());assertGroupPairs(reordered,x.expected);
 assert.equal(new TextEncoder().encode(JSON.stringify(reordered)).byteLength,x.serialized_bytes);
});
test('051 Unicode source failures render original tokens, all members and unavailable pairs',()=>{
 const x=f('unicode_failure');assertGroupPairs(x.reply,x.expected);
 const html=render(GroupPairResults,{report:x.reply,name:'Unicode合成',onOpen(){}});
 assert.match(html,/原组 3/);assert.match(html,/全部相关关闭/);for(const m of x.reply.members)assert.ok(html.includes(m.snapshot_id));
 const member=x.reply.members.find(m=>m.symbol==='600001.SH');
 const source=render(GroupPairSource,{member,commonDates:x.reply.used_dates,onOpen(){}});
 assert.match(source,/原文 停牌/);assert.match(source,/来源限制：未知核验/);assert.match(source,/来源限制：constructor/);assert.match(source,/来源限制：__proto__/);
 assert.ok(source.includes('🛑'.repeat(128)));assert.doesNotMatch(source,/native code|function Object/);
 for(const window of ['previous','current']){const table=render(GroupPairPage,{report:x.reply,window,page:0,onPage(){},onSelect(){}});assert.equal((table.match(/回查双方/g)||[]).length,3);assert.match(table,/不可算/);}
});

test('051 Unicode byte budget rejects multi-byte overflow below the UTF-16 text count',()=>{
 const x=f('unicode_failure'),m=x.reply.members.find(m=>m.symbol==='600001.SH');
 const code='未知'.repeat(180000);
 m.anomalies.counts[code]=m.anomalies.counts['未知核验'];delete m.anomalies.counts['未知核验'];
 const example=m.anomalies.examples.find(e=>e.codes.includes('未知核验'));
 example.codes[example.codes.indexOf('未知核验')]=code;
 const text=JSON.stringify(x.reply);
 assert.ok(text.length<2*1024*1024);assert.ok(new TextEncoder().encode(text).byteLength>2*1024*1024);
 assert.throws(()=>assertGroupPairs(x.reply,x.expected),/invalid_group_pair_response/);
});

test('051 SSR discloses complete-source post-cutoff qualification boundary',()=>{
 const html=render(GroupPairResults,{report:f().reply,name:'合成',onOpen(){}});
 assert.ok(html.includes('价格计算只使用截止日及以前的窗口；所选完整数据版本在截止日后出现身份、复权或结构反证，也会关闭本次相关计算。历史当时可得性未核实。'));
});
