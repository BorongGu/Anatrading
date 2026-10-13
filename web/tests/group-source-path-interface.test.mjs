import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fixtures} from './group-source-path-fixtures.mjs';
import {buildGroupSourcePath} from '../src/group-source-path-model.ts';
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});after(()=>server.close());
const {GroupSourcePath,GroupSourcePathReadout,GroupSourcePathCurve,GroupSourcePathCurveDetails}=await server.ssrLoadModule('/src/GroupSourcePath.tsx');
const {DrawdownEpisodeResults}=await server.ssrLoadModule('/src/DrawdownEpisodeResults.tsx');
const render=(c,p)=>renderToStaticMarkup(createElement(c,p));
const build=f=>buildGroupSourcePath(f.reply,f.expected,{yieldControl:async()=>{}});
test('054 is default folded and mounted only with actual request context',()=>{
 const f=fixtures.T2,html=render(GroupSourcePath,{report:f.reply,expected:f.expected,onOpen(){}});
 assert.match(html,/组来源平均路径与共同最深段/);assert.doesNotMatch(html,/<details open|<table|组来源平均路径结果|正在核对/);
 const original=render(DrawdownEpisodeResults,{report:f.reply,name:'',onOpen(){}});assert.match(original,/缺少本次已核请求，附件不可计算/);
 const integrated=render(DrawdownEpisodeResults,{report:f.reply,expected:f.expected,name:'',onOpen(){}});assert.match(integrated,/固定原起点等权/);assert.match(integrated,/最深回撤段/);
});
test('one common witness keeps every signed member, original start and complete curve',async()=>{
 const result=await build(fixtures.T2),html=render(GroupSourcePathReadout,{result,onOpen(){}});
 for(const label of ['固定原起点','唯一共同峰','最早最深谷','拉低','抵消','+14.2857个百分点','−4.7619个百分点','全部 3 个日期','2/21','1/7','-1/21','公司行动','历史可得性','窗口前峰','投资财富','因果归因','删股改善','不保证直接聚焦源序号'])assert.ok(html.includes(label),label);
 assert.equal((html.match(/class="group-path-member"/g)||[]).length,2);
 for(const m of result.parent.members){for(const value of [m.snapshot_id,m.batch_id,m.query_id,...m.endpoints.map(p=>p.ordinal)])assert.ok(html.includes(value));}
});
function visit(n,callback){if(!n||typeof n!=='object')return;if(Array.isArray(n)){n.forEach(x=>visit(x,callback));return;}callback(n);if(typeof n.type==='function' && n.type!==GroupSourcePathCurveDetails)visit(n.type(n.props),callback);else visit(n.props?.children,callback);}
test('all three evidence buttons preserve original full IDs and original endpoint dates',async()=>{
 const result=await build(fixtures.T2),calls=[];
 visit(GroupSourcePathReadout({result,onOpen:(...args)=>calls.push(args)}),n=>{if(n.type==='button')n.props.onClick();});
 assert.deepEqual(calls,result.parent.members.flatMap(m=>[0,result.attachment.peak_index,result.attachment.trough_index].map(i=>[m.snapshot_id,m.endpoints[i].date])));
});
test('zero, unavailable and tiny signed offsets have distinct language',async()=>{
 const zero=render(GroupSourcePathReadout,{result:await build(fixtures.T1),onOpen(){}}),bad=render(GroupSourcePathReadout,{result:await build(fixtures.failure_refused),onOpen(){}});
 assert.match(zero,/完整组路径无正回撤/);assert.match(zero,/0.0000%/);assert.match(zero,/贡献留空/);
 assert.match(bad,/整组来源平均路径不可计算/);assert.doesNotMatch(bad,/0.0000%|完整组路径无正回撤|<table/);
 const tiny=render(GroupSourcePathReadout,{result:await build(fixtures.tiny_offset),onOpen(){}});assert.match(tiny,/负值（绝对值小于0.0001个百分点）/);assert.match(tiny,/抵消/);
});
test('maximum product size exposes all253 curve dates and all50 signed members without truncation',async()=>{
 const result=await build(fixtures.full_bound),html=render(GroupSourcePathReadout,{result,onOpen(){}});
 assert.equal((html.match(/class="group-path-member"/g)||[]).length,50);
 assert.doesNotMatch(html,/<tbody>/);
 const curve=render(GroupSourcePathCurve,{result});
 const body=curve.match(/<tbody>([\s\S]*?)<\/tbody>/)[1];assert.equal((body.match(/<tr>/g)||[]).length,253);
 for(const day of result.parent.dates)assert.ok(body.includes(day));assert.match(curve,/未抽样或删点/);
});
test('attachment is local only, actual expected flows from request controller, legacy kernel unchanged',()=>{
 const sources=readFileSync(new URL('../src/GroupSourcePath.tsx',import.meta.url),'utf8')+readFileSync(new URL('../src/group-source-path-model.ts',import.meta.url),'utf8');
 assert.doesNotMatch(sources,/fetch\(|\/api\/|localStorage|sessionStorage|Number\(.*sums/);
 const integration=readFileSync(new URL('../src/UniverseResearch.tsx',import.meta.url),'utf8');assert.match(integration,/expected=\{requestState\.spec\?\.kind === 'drawdown_episodes' \? requestState\.spec\.request\.expected : undefined\}/);
});
