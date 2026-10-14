// Frozen before implementation: narrow source contract, actual DOM tested separately.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../src/SingleResearch.tsx',import.meta.url),'utf8');
test('full ledger has native bounded navigation and exact no-event state',()=>{
 for(const text of ['最近一页','较新一页','较早一页','最早一页','当前研究范围没有突破事件。','每页最多100个事件；上方统计使用完整研究范围。'])assert.ok(source.includes(text),text);
 assert.doesNotMatch(source,/rows\.slice\(-100\)/);
});
test('page identity includes full context and independent synchronous active view',()=>{
 assert.match(source,/activeView\.current !== view/);
 assert.match(source,/reversalContextMatches\(view\.context, currentReversalContext\.current\)/);
 assert.match(source,/view\.generation/);
});
