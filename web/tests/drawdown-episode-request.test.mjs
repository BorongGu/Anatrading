import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createUniverseDraft,prepareUniverseRequest,loadUniverseRequest} from '../src/universe-request.ts';
import {ResearchRequestController} from '../src/filter-model.ts';
const f=JSON.parse(readFileSync(new URL('./drawdown-episode-fixtures.json',import.meta.url),'utf8')).complete;
const draft=()=>({...createUniverseDraft(),mode:'drawdown_episodes',ids:f.expected.ids,cutoff:f.expected.cutoff,lookback:String(f.expected.lookback)});
test('actual request path rejects repeat submits, cancellation/input/mode changes invalidate late responses',async()=>{
 const previous=globalThis.fetch;
 try{
  for(const action of ['cancel','invalidate','switch_mode']){
   const pending=[];globalThis.fetch=(url,options)=>new Promise(resolve=>pending.push({resolve,url,options}));
   const c=new ResearchRequestController(()=>{}),d=draft();
   const first=c.run(()=>prepareUniverseRequest(d,d.ids),loadUniverseRequest);await new Promise(r=>setImmediate(r));
   assert.equal(await c.run(()=>prepareUniverseRequest(d,d.ids),loadUniverseRequest),false);
   assert.equal(pending.length,1);assert.match(pending[0].url,/drawdown-episodes/);assert.equal(pending[0].options.cache,'no-store');
   if(action==='cancel')c.cancel();else{c.invalidate();if(action==='switch_mode')d.mode='existing';else d.lookback='7';}
   assert.equal(c.state.result,null);assert.equal(pending[0].options.signal.aborted,true);
   pending[0].resolve(Response.json(f.reply));await first;assert.notEqual(c.state.status,'ready');assert.equal(c.state.result,null);
   c.dispose();
  }
 }finally{globalThis.fetch=previous;}
});
test('newest result survives older late response, failed retry clears previous result',async()=>{
 const previous=globalThis.fetch;const pending=[];globalThis.fetch=(url,options)=>new Promise(resolve=>pending.push({resolve,url,options}));
 try{
  const c=new ResearchRequestController(()=>{}),d=draft();
  const first=c.run(()=>prepareUniverseRequest(d,d.ids),loadUniverseRequest);await new Promise(r=>setImmediate(r));c.invalidate();
  const second=c.run(()=>prepareUniverseRequest(d,d.ids),loadUniverseRequest);await new Promise(r=>setImmediate(r));
  pending[1].resolve(Response.json(f.reply));await second;assert.equal(c.state.status,'ready');
  const newest=c.state.result;pending[0].resolve(Response.json({error:'raw_object_corrupt'},{status:409}));await first;assert.equal(c.state.result,newest);
  const third=c.run(()=>prepareUniverseRequest(d,d.ids),loadUniverseRequest);assert.equal(c.state.result,null);await new Promise(r=>setImmediate(r));
  pending[2].resolve(Response.json({...f.reply,analysis_id:'0'.repeat(64)}));await third;assert.equal(c.state.status,'error');assert.equal(c.state.result,null);c.dispose();
 }finally{globalThis.fetch=previous;}
});
