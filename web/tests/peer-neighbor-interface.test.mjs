import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
const fixtures=JSON.parse(readFileSync(new URL('./peer-neighbor-fixtures.json',import.meta.url),'utf8'));
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});after(()=>server.close());
const {UniverseResearch,createUniverseDraft}=await server.ssrLoadModule('/src/UniverseResearch.tsx');
const {PeerNeighborResults}=await server.ssrLoadModule('/src/PeerNeighborResults.tsx');
const render=(c,p)=>renderToStaticMarkup(createElement(c,p));
test('SSR peer mode reuses existing selection with explicit empty target and fixed windows',()=>{
 const f=fixtures.complete,draft={...createUniverseDraft(),mode:'peer_neighbors',ids:f.expected.ids,cutoff:f.expected.cutoff};
 const html=render(UniverseResearch,{draft,snapshots:f.expected.ids.map(id=>({snapshot_id:id,row_count:121,metadata:{period:'1d',source_code:id.slice(0,6)}})),onImport(){},onOpen(){}});
 assert.match(html,/id="universe-peer-target"/);assert.match(html,/请明确选择目标/);assert.match(html,/核对全部双窗候选/);assert.match(html,/2–50/);
 assert.doesNotMatch(html,/id="universe-lookback"|aria-label="参考组 |id="universe-group-start"|添加条件/);
 assert.equal((html.match(/type="checkbox"/g)||[]).length,4);
});
for(const name of Object.keys(fixtures))test(`SSR ${name} preserves target, all candidates, exact meaning and raw endpoints`,()=>{
 const r=fixtures[name].reply,html=render(PeerNeighborResults,{report:r,name:'明确自选组',onOpen(){}});
 assert.match(html,/原组/);assert.match(html,/与既有双股对数变化相关口径不同/);assert.match(html,/不自动聚焦源序号/);assert.match(html,/未来稳定/);assert.match(html,/实际省时与判断改善未验/);
 for(const m of r.members)assert.ok(html.includes(m.snapshot_id));
 if(name==='complete'||name==='partial'){assert.equal((html.match(/打开共享边界/g)||[]).length,r.members.length);assert.match(html,/精确并列/);}
 if(name==='partial')assert.match(html,/常量/);
 if(name==='source_bad')assert.match(html,/来源资格拒绝/);
 if(name.startsWith('anchor'))assert.match(html,/端点尚未评估/);
 if(name==='anchor_unknown')assert.match(html,/全局身份/);
});
test('all boundary and selected date handlers preserve exact snapshot and date',()=>{
 const r=fixtures.complete.reply,calls=[],tree=PeerNeighborResults({report:r,name:'',onOpen:(...args)=>calls.push(args)});
 function visit(node){if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(visit);return;}if(node.type==='button')node.props.onClick();visit(node.props?.children);}
 visit(tree);assert.equal(calls.length,r.members.length*124);
 const expected=new Set(r.members.flatMap(m=>r.used_dates.map(day=>`${m.snapshot_id}/${day}`)));assert.ok(calls.every(([id,day])=>expected.has(`${id}/${day}`)));
});
test('existing controller lifecycle remains wired and target removal clears rather than choosing replacement',()=>{
 const source=readFileSync(new URL('../src/UniverseResearch.tsx',import.meta.url),'utf8');
 assert.match(source,/patch\.ids && !patch\.ids\.includes\(next\.peerTarget\)/);assert.match(source,/next\.peerTarget = ''/);
 assert.match(source,/pagehide/);assert.match(source,/pageshow/);assert.match(source,/control\.current\?\.dispose\(\)/);assert.match(source,/edit\(\{ peerTarget: event\.target\.value \}\)/);
});
