import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { calculatePairSignWindows,formatPairSignFraction,checkPairSignBudgets } from '../src/pair-sign-crossproducts.ts';
const fixtures=JSON.parse(readFileSync(new URL('./pair-sign-fixtures.json',import.meta.url)));
const oracle=JSON.parse(readFileSync(new URL('./pair-sign-oracle.json',import.meta.url))).fixtures;
const options={yieldControl:async()=>{}};
function eq(n,d,ref){assert.equal(BigInt(n)*BigInt(ref.d),BigInt(ref.n)*BigInt(d));}
for(const input of fixtures)test(`059 frozen oracle ${input.fixture_id}`,async()=>{
 const ref=oracle.find(x=>x.fixture_id===input.fixture_id);
 if(ref.status==='rejected'){await assert.rejects(calculatePairSignWindows(input,options),/invalid_context/);return;}
 const result=await calculatePairSignWindows(input,options);
 for(const key of ['previous','current']){
  const a=result[key],b=ref.windows[key];
  for(const field of ['start_index','end_index','interval_count','rows','counts','display'])assert.deepEqual(a[field],b[field],`${key}.${field}`);
  for(const term of Object.keys(b.terms))eq(a.terms[term],a.terms.denominator,b.terms[term]);
 }
});
test('059 exact half-even display, exponent boundary and nonzero cancellation',()=>{
 for(const [n,d,out]of [['100005','100000','1.0000e+0'],['100015','100000','1.0002e+0'],['999995','100000','1.0000e+1'],['-1','1'+'0'.repeat(4563),'-1.0000e-4563'],['0','9','0']])assert.equal(formatPairSignFraction(n,d),out);
});
test('059 limits measure UTF-8 metadata and entire attachment separately',()=>{
 assert.throws(()=>checkPairSignBudgets({source_refs:{token:'汉'.repeat(50000)},windows:{previous:null,current:null}}),/resource_limit/);
});
test('059 cancellation returns no partial result',async()=>{
 const signal=AbortSignal.abort();await assert.rejects(calculatePairSignWindows(fixtures[0],{signal}),/cancelled/);
 const controller=new AbortController();let calls=0;
 await assert.rejects(calculatePairSignWindows(fixtures[0],{signal:controller.signal,yieldControl:async()=>{calls++;controller.abort();}}),/cancelled/);assert.equal(calls,1);
});

test('059 frozen-input swap and valid uniform scales preserve exact arithmetic',async()=>{
 for(const input of fixtures.filter(x=>x.fixture_id!=='F07')){
  const base=await calculatePairSignWindows(input,options),swapped=await calculatePairSignWindows({...input,left:input.right,right:input.left},options);
  for(const k of ['previous','current']){for(let i=0;i<60;i++){assert.deepEqual(swapped[k].rows[i].left_change,base[k].rows[i].right_change);assert.deepEqual(swapped[k].rows[i].product,base[k].rows[i].product);}eq(swapped[k].terms.pn,swapped[k].terms.denominator,{n:base[k].terms.np,d:base[k].terms.denominator});}
 }
 for(const input of fixtures.slice(0,4))for(const divisor of [false,true]){
  const copy=structuredClone(input);for(const side of [copy.left,copy.right])for(const p of side.endpoints){const [w,f='']=p.close_exact.split('.');let a=BigInt(w+f.padEnd(18,'0'));a=divisor?a/2n:a*2n;const s=a.toString().padStart(19,'0');p.close_exact=(s.slice(0,-18)+'.'+s.slice(-18)).replace(/0+$/,'').replace(/\.$/,'');p.close_token=p.close_exact;}
  const a=await calculatePairSignWindows(copy,options),b=await calculatePairSignWindows(input,options);for(const k of ['previous','current']){for(const field of ['rows','counts','display'])assert.deepEqual(a[k][field],b[k][field]);for(const term of ['pp','nn','pn','np','centering','centered_cross'])eq(a[k].terms[term],a[k].terms.denominator,{n:b[k].terms[term],d:b[k].terms.denominator});}
 }
});
test('059 source null token retained, cross-category equal IDs allowed, illegal structures rejected',async()=>{
 const good=structuredClone(fixtures[0]);good.left.endpoints[0].close_token=null;good.left.ids.batch=good.right.ids.query;
 await calculatePairSignWindows(good,options);
 for(const change of [x=>x.left.endpoints[4].ordinal=x.left.endpoints[3].ordinal,x=>x.left.endpoints[1].index=5,x=>x.right.ids.snapshot=x.left.ids.snapshot,x=>x.left.endpoints.pop()]){const x=structuredClone(good);change(x);await assert.rejects(calculatePairSignWindows(x,options),/invalid_context/);}
 for(const value of ['0','1.0','-1','100000000000000000000','0.0000000000000000001']){const x=structuredClone(good);x.left.endpoints[0].close_exact=value;await assert.rejects(calculatePairSignWindows(x,options),/invalid_price/);}
});
