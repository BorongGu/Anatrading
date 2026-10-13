import test,{after} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
const fixtures=JSON.parse(readFileSync(new URL('./drawdown-episode-fixtures.json',import.meta.url),'utf8'));
const server=await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});after(()=>server.close());
const {DrawdownEpisodeResults}=await server.ssrLoadModule('/src/DrawdownEpisodeResults.tsx');
const {UniverseResearch,createUniverseDraft}=await server.ssrLoadModule('/src/UniverseResearch.tsx');
const {prepareUniverseRequest}=await server.ssrLoadModule('/src/universe-request.ts');
const render=(c,p)=>renderToStaticMarkup(createElement(c,p));
test('new selector mode keeps source window, hides unrelated filters and routes dedicated request',async()=>{
 const f=fixtures.complete,draft={...createUniverseDraft(),mode:'drawdown_episodes',ids:f.expected.ids,cutoff:f.expected.cutoff,lookback:String(f.expected.lookback)};
 const html=render(UniverseResearch,{draft,snapshots:draft.ids.map(id=>({snapshot_id:id,row_count:9,metadata:{period:'1d'}})),onImport(){},onOpen(){}});
 assert.match(html,/回撤持续与恢复/);assert.match(html,/id="universe-lookback"/);assert.match(html,/核对回撤摘要/);
 assert.doesNotMatch(html,/添加条件|universe-peer-target|universe-group-start/);
 assert.equal((await prepareUniverseRequest(draft,draft.ids)).kind,'drawdown_episodes');
});
for(const [name,f] of Object.entries(fixtures))test(`SSR ${name} preserves members and meaning`,()=>{
 const html=render(DrawdownEpisodeResults,{report:f.reply,name:'人工组',onOpen(){}});
 assert.equal((html.match(/class="drawdown-member"/g)||[]).length,f.reply.counts.selected);
 for(const text of ['最深回撤段','已观察跨度最长段','截止未恢复段','窗口前','来源区间','复权','历史可得性','公司行动'])assert.ok(html.includes(text),text);
 if(name==='complete'||name==='open'){assert.match(html,/20.0000%/);assert.match(html,/1.0000%/);assert.match(html,/完整恢复跨度未知/);assert.match(html,/显示舍入/);}
 else if(!f.reply.comparison_available){assert.match(html,/整组尚不可计算/);assert.doesNotMatch(html,/窗口内无回撤/);}
 assert.doesNotMatch(html,/交易天数|合同|门禁|快照/);
});
test('representative callbacks use that source version and its own observed end',()=>{
 const r=fixtures.complete.reply,calls=[];const tree=DrawdownEpisodeResults({report:r,name:'',onOpen:(...args)=>calls.push(args)});
 function visit(n){if(!n||typeof n!=='object')return;if(Array.isArray(n)){n.forEach(visit);return;}if(n.type==='button')n.props.onClick();if(typeof n.type==='function')visit(n.type(n.props));else visit(n.props?.children);}
 visit(tree);
 assert.deepEqual(calls,r.members.flatMap(m=>[m.deepest,m.longest_observed,m.current_open].filter(Boolean).map(e=>[m.snapshot_id,e.observed_end.date])));
});
