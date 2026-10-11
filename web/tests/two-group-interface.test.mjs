import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {fixture} from './two-group-fixtures.mjs';
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});after(()=>server.close());
const {UniverseResearch,createUniverseDraft}=await server.ssrLoadModule('/src/UniverseResearch.tsx');
const {TwoGroupResults}=await server.ssrLoadModule('/src/TwoGroupResults.tsx');
const render=(c,p)=>renderToStaticMarkup(createElement(c,p));
test('SSR explicit roles are expanded and no target selector or legacy required window exists',()=>{
 const f=fixture(),draft={...createUniverseDraft(),ids:f.expected.ids,cutoff:f.expected.end,explanation:{enabled:true,start:f.expected.start,roles:{}}};
 const html=render(UniverseResearch,{draft,snapshots:f.expected.ids.map(id=>({snapshot_id:id,row_count:62,metadata:{period:'1d',source_code:id.slice(0,6)}})),onImport(){},onOpen(){}});
 assert.equal((html.match(/aria-label="参考组 /g)||[]).length,4);assert.match(html,/解释全部所选成员/);assert.match(html,/每组至少两只/);assert.doesNotMatch(html,/id="universe-lookback"|目标选择|添加条件/);assert.match(html,/当前区间起点/);
});
test('SSR table keeps all rows, source prices, limits, decomposition and original-record buttons',()=>{
 const f=fixture();f.reply.members[0].model=null;f.reply.members[0].reasons=['factor_rank_unavailable'];f.reply.counts.model_available=3;
 const html=render(TwoGroupResults,{report:f.reply,onOpen(){}});
 assert.equal((html.match(/打开原始记录/g)||[]).length,4);assert.match(html,/无法分开解释/);assert.match(html,/描述排序，未按波动风险标准化/);assert.match(html,/训练目标基线/);assert.match(html,/数值|容差/);assert.match(html,/交易日历/);assert.match(html,/价格变化（对数）/);assert.match(html,/输入顺序/);
});
