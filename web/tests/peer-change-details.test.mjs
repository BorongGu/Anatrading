import test from 'node:test';
import assert from 'node:assert/strict';
import { validatePeerSourcePair } from '../src/peer-source-pair.ts';
import { peerChangeWindow, changeDisplay } from '../src/peer-change-details.ts';
import { groupPercent } from '../src/group-endpoint-model.ts';
import { declineFixture, setSourcePrices } from './peer-decline-fixtures.mjs';
const rows = (f, offset=0) => { const pair=validatePeerSourcePair(f.report,f.peerId); assert.equal(pair.available,true); return peerChangeWindow(pair,offset); };
test('hand calculation uses target minus peer in percentage points and all 60 rows',()=>{
 const f=declineFixture(); setSourcePrices(f.report,f.targetId,['100','101']); setSourcePrices(f.report,f.peerId,['100','103']);
 const r=rows(f); assert.equal(r.length,60); assert.equal(changeDisplay(r[0].difference,'百分点'),' -2.0000百分点'.trim());
 assert.equal(changeDisplay(r[0].target,'%'),'1.0000%'); assert.equal(changeDisplay(r[0].peer,'%'),'3.0000%');
 assert.equal(r[0].date,f.report.used_dates[1]);
});
test('constant source is available, all ties retained in date order, split has no repeated edge',()=>{
 const f=declineFixture(); assert.deepEqual([...rows(f),...rows(f,60)].map(r=>r.date),f.report.used_dates.slice(1));
 assert.ok(rows(f).every(r=>r.difference.numerator===0n));
});
test('current internal change leaves previous sorted values intact; bad unopened endpoint closes pair',()=>{
 const f=declineFixture(); const before=rows(f); f.report.members.find(m=>m.snapshot_id===f.peerId).endpoints[100].close_exact='101';
 assert.deepEqual(rows(f),before); f.report.members.find(m=>m.snapshot_id===f.peerId).endpoints[120].close_exact='0';
 assert.deepEqual(validatePeerSourcePair(f.report,f.peerId),{available:false,reason:'invalid_source_endpoints'});
});
test('half even signed rounding and nonzero rounded zero retain exact sign',()=>{
 for(const [n,want] of [[1n,'0.0000%（正，显示舍入）'],[-1n,'0.0000%（负，显示舍入）'],[3n,'0.0002%'],[-3n,'-0.0002%']]) assert.equal(changeDisplay({numerator:n,denominator:2000000n},'%'),want);
});
test('old formatter keeps 4096-character fraction domain and text',()=>{
 const d='9'.repeat(4096); assert.equal(groupPercent({numerator:'1',denominator:d}),'0.0000%（正，显示舍入）');
 assert.equal(groupPercent({numerator:d,denominator:d}),'100.0000%'); assert.equal(groupPercent(null),'不可算');
});
// Independent rational oracle uses variable decimal scales and subtracts two
// reduced ratios; it does not use the product-difference production formula.
function gcd(a,b){a=a<0n?-a:a;while(b){[a,b]=[b,a%b];}return a;}
function rat(n,d){const g=gcd(n,d);return [n/g,d/g];}
function decimal(s){const [w,f='']=s.split('.');return rat(BigInt(w+f),10n**BigInt(f.length));}
function minus([a,b],[c,d]){return rat(a*d-c*b,b*d);}
function divide([a,b],[c,d]){return rat(a*d,b*c);}
function oracle(before,after){return divide(minus(decimal(after),decimal(before)),decimal(before));}
test('independent rational oracle: mixed scales, extrema, signed exact ordering, each of 120 edges',()=>{
 const f=declineFixture();const samples=['0.000000000000000001','99999999999999999999.999999999999999999','10','9.123456789012345678','100','100.000000000000000001','0.5'];
 const t=Array.from({length:121},(_,i)=>samples[(i*3)%samples.length]); const p=Array.from({length:121},(_,i)=>samples[(i*5+1)%samples.length]);
 setSourcePrices(f.report,f.targetId,t);setSourcePrices(f.report,f.peerId,p);
 for(const offset of [0,60]){const expected=Array.from({length:60},(_,i)=>{const index=offset+i+1;return {index,x:oracle(t[index-1],t[index]),y:oracle(p[index-1],p[index])};}).map(r=>({...r,z:minus(r.x,r.y)}));
 const abs=n=>n<0n?-n:n; expected.sort((a,b)=>{const diff=abs(a.z[0])*b.z[1]-abs(b.z[0])*a.z[1];return diff>0n?-1:diff<0n?1:a.index-b.index;});
 const actual=rows(f,offset);assert.deepEqual(actual.map(r=>r.index),expected.map(r=>r.index));
 actual.forEach((r,i)=>{for(const [key,ref] of [['target','x'],['peer','y'],['difference','z']])assert.equal(r[key].numerator*expected[i][ref][1],expected[i][ref][0]*r[key].denominator);});}
});
test('opposite signs with equal absolute differences retain date ordering and all maximum ties',()=>{
 const f=declineFixture();setSourcePrices(f.report,f.targetId,['100','101','101']);setSourcePrices(f.report,f.peerId,['100','100','101']);
 const r=rows(f); assert.deepEqual(r.slice(0,2).map(r=>r.index),[1,2]);assert.equal(r.length,60);assert.ok(r[0].difference.numerator>0n);assert.ok(r[1].difference.numerator<0n);
});
test('identical rounded displays do not hide exact ordering',()=>{
 const f=declineFixture();setSourcePrices(f.report,f.targetId,['100','100.000000000000000001','100.000000000000000003']);
 const r=rows(f);assert.deepEqual(r.slice(0,2).map(r=>r.index),[2,1]); assert.equal(changeDisplay(r[0].difference,'百分点'),changeDisplay(r[1].difference,'百分点'));
});
