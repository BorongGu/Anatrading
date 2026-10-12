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
 const f=fixture(),draft={...createUniverseDraft(),ids:f.expected.ids,cutoff:f.expected.end,mode:'explanation',explanation:{start:f.expected.start,roles:{}}};
 const html=render(UniverseResearch,{draft,snapshots:f.expected.ids.map(id=>({snapshot_id:id,row_count:62,metadata:{period:'1d',source_code:id.slice(0,6)}})),onImport(){},onOpen(){}});
 assert.equal((html.match(/aria-label="参考组 /g)||[]).length,4);assert.match(html,/解释全部所选成员/);assert.match(html,/每组至少两只/);assert.doesNotMatch(html,/id="universe-lookback"|目标选择|添加条件/);assert.match(html,/当前区间起点/);
});
for (const scenario of ['metadata name', 'unavailable version', 'same name across versions']) {
 test(`SSR reference-group control names preserve displayed stock identity: ${scenario}`, () => {
  const f = fixture();
  const draft = { ...createUniverseDraft(), ids: f.expected.ids, cutoff: f.expected.end, mode: 'explanation',
   explanation: { start: f.expected.start, roles: Object.fromEntries(f.expected.ids.map((id, index) => [id, index < 2 ? 'A' : 'B'])) } };
  let snapshots = f.expected.ids.map((id, index) => ({ snapshot_id: id, row_count: 62,
   metadata: { period: '1d', source_name: '  合成 "样本" & 名称  ', source_code: `  60000${index}.SH  ` } }));
  if (scenario === 'unavailable version') snapshots = snapshots.slice(1);
  if (scenario === 'same name across versions') snapshots = snapshots.map(item => ({ ...item,
   metadata: { ...item.metadata, source_name: '同名合成样本', source_code: '' } }));
  const html = render(UniverseResearch, { draft, snapshots, onImport() {}, onOpen() {} });
  const controls = [...html.matchAll(/<label>([^<]*)<select aria-label="(参考组 [^"]*)"[^>]*>([\s\S]*?)<\/select><\/label>/g)];
  assert.equal(controls.length, f.expected.ids.length);
  assert.equal((html.match(/type="checkbox"/g) ?? []).length, snapshots.length);
  assert.match(html, /已选 4 \/ 50/);
  for (const [index, control] of controls.entries()) {
   const snapshot = snapshots.find(item => item.snapshot_id === f.expected.ids[index]);
   const expectedName = snapshot ? [snapshot.metadata.source_name.trim(), snapshot.metadata.source_code.trim()].filter(Boolean).join(' · ') : '未标注证券';
   const escapedName = renderToStaticMarkup(createElement('span', null, expectedName)).replace(/^<span>|<\/span>$/g, '');
   assert.equal(control[1], escapedName, 'the visible stock label remains unchanged');
   assert.equal(control[2], `参考组 ${escapedName}，版本 ${f.expected.ids[index].slice(0, 8)}`);
   assert.ok(control[3].includes(`<option value="${index < 2 ? 'A' : 'B'}" selected="">`), 'existing role stays selected');
  }
  assert.equal(new Set(controls.map(control => control[2])).size, f.expected.ids.length);
  if (scenario === 'unavailable version') {
   assert.match(html, /1 个已选版本暂不可用/);
   assert.match(html, /disabled="">解释全部所选成员/);
  }
 });
}
test('SSR table keeps all rows, source prices, limits, decomposition and original-record buttons',()=>{
 const f=fixture();f.reply.members[0].model=null;f.reply.members[0].reasons=['factor_rank_unavailable'];f.reply.counts.model_available=3;
 const html=render(TwoGroupResults,{report:f.reply,onOpen(){}});
 assert.equal((html.match(/打开原始记录/g)||[]).length,4);assert.match(html,/无法分开解释/);assert.match(html,/描述排序，未按波动风险标准化/);assert.match(html,/训练目标基线/);assert.match(html,/数值|容差/);assert.match(html,/交易日历/);assert.match(html,/价格变化（对数）/);assert.match(html,/输入顺序/);
});
