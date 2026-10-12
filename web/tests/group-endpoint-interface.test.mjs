import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
const fixtures=JSON.parse(readFileSync(new URL('./group-endpoint-fixtures.json',import.meta.url),'utf8'));
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});after(()=>server.close());
const {UniverseResearch,createUniverseDraft}=await server.ssrLoadModule('/src/UniverseResearch.tsx');
const {GroupEndpointResults}=await server.ssrLoadModule('/src/GroupEndpointResults.tsx');
const render=(c,p)=>renderToStaticMarkup(createElement(c,p));
test('SSR new mode reuses selection and requires common endpoints without old window or roles',()=>{
 const f=fixtures.complete,draft={...createUniverseDraft(),mode:'group_endpoints',ids:f.expected.ids,cutoff:f.expected.end,groupStart:f.expected.start};
 const html=render(UniverseResearch,{draft,snapshots:f.expected.ids.map(id=>({snapshot_id:id,row_count:2,metadata:{period:'1d',source_code:id.slice(0,6)}})),onImport(){},onOpen(){}});
 assert.match(html,/共同起点日期/);assert.match(html,/核对共同端点单组/);assert.match(html,/4–50/);assert.match(html,/腾讯日线/);
 assert.doesNotMatch(html,/id="universe-lookback"|aria-label="参考组 |添加条件/);assert.equal((html.match(/type="checkbox"/g)||[]).length,5);
});
for(const name of ['complete','partial','rejected','near_zero'])test(`SSR ${name} keeps all source rows and exact limitations`,()=>{
 const r=fixtures[name].reply,html=render(GroupEndpointResults,{report:r,name:'人工组',onOpen(){}});
 assert.equal((html.match(/打开此版本至起点日期/g)||[]).length,r.counts.selected);assert.equal((html.match(/打开此版本至终点日期/g)||[]).length,r.counts.selected);
 assert.match(html,/原组/);assert.match(html,/精确正／零／负/);assert.match(html,/Type7/);assert.match(html,/未提供事件附件/);assert.match(html,/不自动聚焦源序号/);
 if(name==='partial')assert.match(html,/完整组均值、中位数、Q1、Q3均留空/);
 if(name==='rejected')assert.match(html,/端点和异常尚未检查/);
 if(name==='near_zero')assert.match(html,/显示舍入/);
});
test('pure result component binds both prefix buttons to the submitted source version and exact dates',()=>{
 const r=fixtures.complete.reply,calls=[];const tree=GroupEndpointResults({report:r,name:'',onOpen:(...args)=>calls.push(args)});
 function visit(node){if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(visit);return;}if(node.type==='button')node.props.onClick();visit(node.props?.children);}
 visit(tree);assert.deepEqual(calls,r.members.flatMap(m=>[[m.snapshot_id,r.parameters.start_date],[m.snapshot_id,r.parameters.end_date]]));
});
test('SSR display name changes while the report identity and every member remain the same',()=>{
 const r=fixtures.complete.reply,before=JSON.stringify(r);
 const first=render(GroupEndpointResults,{report:r,name:'原显示名',onOpen(){}}),second=render(GroupEndpointResults,{report:r,name:'新显示名',onOpen(){}});
 assert.match(first,/原显示名/);assert.match(second,/新显示名/);assert.equal(JSON.stringify(r),before);
 assert.ok(second.includes(r.analysis_id));assert.equal((second.match(/打开此版本至终点日期/g)||[]).length,r.counts.selected);
});
