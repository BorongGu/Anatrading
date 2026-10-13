import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { declineFixture, setSourcePrices } from './peer-decline-fixtures.mjs';
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
after(()=>server.close());
const ui=await server.ssrLoadModule('/src/PeerChangeDetails.tsx');
const {validatePeerSourcePair}=await server.ssrLoadModule('/src/peer-source-pair.ts');
const render=(type,props)=>renderToStaticMarkup(createElement(type,props));
function nodes(n,p,out=[]){if(!n||typeof n!=='object')return out;if(Array.isArray(n)){n.forEach(x=>nodes(x,p,out));return out;}if(p(n))out.push(n);nodes(n.props?.children,p,out);return out;}
test('closed entry reads no source props and renders no rows',()=>{
 const report=new Proxy({},{get(){throw new Error('eager source access');}});
 const html=render(ui.PeerChangeDetails,{report,peerId:'peer',onOpen(){}});
 assert.match(html,/变化差异/); assert.doesNotMatch(html,/<tr|精确计算/);
});
test('content validates pair but closed windows have no change rows',()=>{
 const f=declineFixture(); const html=render(ui.PeerChangeContent,{report:f.report,peerId:f.peerId,onOpen(){}});
 assert.match(html,/前60区间/); assert.match(html,/当前60区间/); assert.doesNotMatch(html,/<tr|精确计算/);
});
test('pure window renders all rows, expressions, source texts and exact original-version callbacks without fetch',()=>{
 const f=declineFixture(); setSourcePrices(f.report,f.targetId,['100','101']); setSourcePrices(f.report,f.peerId,['100','103']);
 const calls=[];const old=globalThis.fetch; globalThis.fetch=()=>{throw new Error('unexpected request');};
 try { const props={report:f.report,peerId:f.peerId,pair:validatePeerSourcePair(f.report,f.peerId),offset:0,onOpen:(...args)=>calls.push(args)};
 const tree=ui.PeerChangeRows(props); const html=renderToStaticMarkup(tree); assert.equal((html.match(/<summary>精确计算<\/summary>/g)||[]).length,60); assert.match(html,/-2.0000百分点/); assert.match(html,/100 → 101/);
 const buttons=nodes(tree,n=>n.type==='button');assert.equal(buttons.length,120);buttons.forEach(b=>b.props.onClick());
 assert.deepEqual(calls.slice(0,2),[[f.targetId,f.report.used_dates[1]],[f.peerId,f.report.used_dates[1]]]);
 const f2=structuredClone(f);setSourcePrices(f2.report,f2.targetId,['100','105']);const html2=render(ui.PeerChangeRows,{...props,report:f2.report,pair:validatePeerSourcePair(f2.report,f2.peerId)});assert.match(html2,/2.0000百分点/);assert.notEqual(html,html2);
 } finally {globalThis.fetch=old;}
});
test('toggle ignores nested events and uses current open value, including repeated and closing events',()=>{
 const seen=[]; const current={open:true};ui.syncDetailsOpen({target:{},currentTarget:current},v=>seen.push(v));
 ui.syncDetailsOpen({target:current,currentTarget:current},v=>seen.push(v));ui.syncDetailsOpen({target:current,currentTarget:current},v=>seen.push(v)); current.open=false;ui.syncDetailsOpen({target:current,currentTarget:current},v=>seen.push(v));assert.deepEqual(seen,[true,true,false]);
});
test('entry keys distinguish report and peer identities; callback replacement uses current props',async()=>{
 const {PeerNeighborResults}=await server.ssrLoadModule('/src/PeerNeighborResults.tsx');
 const f=declineFixture(); const entries=report=>nodes(PeerNeighborResults({report,name:'',onOpen(){}}),n=>n.type===ui.PeerChangeDetails);
 const first=entries(f.report);assert.equal(first.length,f.report.candidates.length);assert.equal(new Set(first.map(n=>n.key)).size,first.length);
 const updated=structuredClone(f.report);updated.analysis_id='f'.repeat(64);assert.ok(entries(updated).every((n,i)=>n.key!==first[i].key));
 const calls=[]; const current=structuredClone(f.report);setSourcePrices(current,f.targetId,['100','105']);
 const tree=ui.PeerChangeRows({report:current,peerId:f.peerId,pair:validatePeerSourcePair(current,f.peerId),offset:60,onOpen:(...args)=>calls.push(args)});
 nodes(tree,n=>n.type==='button').forEach(n=>n.props.onClick());assert.equal(calls.length,120);assert.deepEqual(calls[0],[f.targetId,current.used_dates[61]]);assert.deepEqual(calls.at(-1),[f.peerId,current.used_dates[120]]);
});
test('invalid source content has no windows, partial rows, or zero substitutes',()=>{
 const f=declineFixture(); f.report.members.find(m=>m.snapshot_id===f.peerId).endpoints[120].close_exact='0';
 const html=render(ui.PeerChangeContent,{report:f.report,peerId:f.peerId,onOpen(){}});assert.match(html,/121个同日精确端点未通过核对/);assert.doesNotMatch(html,/<table|<details|0.0000/);
});
