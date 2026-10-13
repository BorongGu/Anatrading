import test, { after } from 'node:test';
import assert from 'node:assert/strict';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createServer } from 'vite';
import { acceptEventPath, captureEventPath } from '../src/single-event-path.ts';
import { assertResearchReply } from '../src/research-model.ts';
import { fixture, context } from './single-event-path-fixtures.mjs';
const server = await createServer({server:{middlewareMode:true,hmr:false,ws:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}});
after(()=>server.close());
const {SingleEventPath}=await server.ssrLoadModule('/src/SingleEventPath.tsx');
function render(name, partition='descriptive') {
 const f=fixture(name);assertResearchReply(f.reply,f.expected);
 const projection=captureEventPath(acceptEventPath(f.reply,context(f.query),f.expected),f.eventPosition);
 return renderToStaticMarkup(createElement(SingleEventPath,{projection,partition,onClose(){}}));
}
test('all six exact positions show original identities without new arithmetic',()=>{
 const html=render('P1A');for(const value of ['事件日与后5个来源日期组','研究查询 Q','原贪心去重 selected','原分段 partition','原标签 label_status','原评价 evaluation_status','5步不代表5个交易日','全部日期基线另有规则','当前 descriptive','本表转述原响应']) assert.ok(html.includes(value),value);
 assert.equal((html.match(/<tr>/g)||[]).length,7);assert.doesNotMatch(html,/%|MFE|MAE/);
 for(const id of ['a','c','d'])assert.ok(html.includes(id.repeat(64)));
});
test('immature unknown slots differ from retained null, zero and negatives',()=>{
 assert.match(render('P3'),/已有 4\/6/);assert.equal((render('P3').match(/原评价截止下尚无此来源槽/g)||[]).length,2);
 assert.match(render('P4_END_NULL'),/∅（本槽未保留可解析收盘）/);
 assert.match(render('P4_END_ZERO'),/>0<\/td>/);assert.match(render('P4_NEGATIVE'),/-0\.000000000000000001/);
 assert.match(render('P4_DUP'),/无唯一源序号/);
});
test('null versus explicit request cutoff and estimator failure preserve original label',()=>{
 assert.match(render('NULL_CUTOFF'),/请求未限截止/);
 assert.match(render('EXPLICIT_GAP_CUTOFF'),/原评价截止 D：2026-01-20/);
 const kalman=render('KALMAN_ONLY_FAILURE');assert.match(kalman,/label_status：valid/);assert.match(kalman,/当前 descriptive/);
});
test('split explanation changes only current membership',()=>{
 assert.match(render('P5_OTHER_PART','test'),/本条不计入该分段/);assert.match(render('P5_OTHER_PART','train'),/计入当前 train/);
 assert.match(render('P5_INVALID_PURGE','train'),/purged/);
});
