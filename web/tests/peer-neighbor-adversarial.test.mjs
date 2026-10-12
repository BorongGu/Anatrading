import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {assertPeerNeighbors,peerDisplay} from '../src/peer-neighbor-model.ts';
const input=JSON.parse(readFileSync(new URL('./peer-neighbor-fixtures.json',import.meta.url),'utf8')).partial;
const fixture=()=>structuredClone(input.reply);
const expected=input.expected;
test('rejects reversed positive and zero rank groups',()=>{
 const r=fixture(),valid=r.candidates.filter(c=>c.current.correlation),positive=valid.filter(c=>c.current.correlation.sign==='positive'),zeros=valid.filter(c=>c.current.correlation.sign==='zero');
 assert.equal(positive.length,1);assert.equal(zeros.length,2);
 zeros.forEach(c=>{c.current.rank=1;c.current.tie_size=2;});positive[0].current.rank=3;
 r.windows.current.order=[...zeros.map(c=>c.snapshot_id).sort(),positive[0].snapshot_id,...r.windows.current.order.slice(3)];
 assert.throws(()=>assertPeerNeighbors(r,expected),/invalid_peer_neighbor_response/);
});
test('rejects splitting mathematical exact-zero tie into different ranks',()=>{
 const r=fixture(),zeros=r.candidates.filter(c=>c.current.correlation?.exact_boundary==='zero').sort((a,b)=>a.snapshot_id.localeCompare(b.snapshot_id));
 zeros.forEach((c,i)=>{c.current.rank=2+i;c.current.tie_size=1;});assert.throws(()=>assertPeerNeighbors(r,expected),/invalid_peer_neighbor_response/);
});
test('rejects source complete alongside explicitly reported global identity contradiction',()=>{
 const r=fixture(),m=r.members.find(m=>m.role==='candidate');m.anomalies={total:1,counts:{global_source_conflict:1},examples:[{date:'2025-01-01',ordinal:999,scope:'outside_interval',codes:['global_source_conflict']}],truncated:false};
 assert.throws(()=>assertPeerNeighbors(r,expected),/invalid_peer_neighbor_response/);
});
for(const code of ['未知核验','__proto__','constructor'])test(`preserves bounded unknown source check label ${code}`,()=>{
 const r=fixture(),m=r.members.find(m=>m.role==='candidate');m.anomalies={total:1,counts:{[code]:1,unclassified_source_failure:1},examples:[{date:'2025-01-01',ordinal:999,scope:'outside_interval',codes:[code,'unclassified_source_failure']}],truncated:false};
 assertPeerNeighbors(r,expected);
});
test('rejects qualified source identity that cannot be an A-share normalized symbol',()=>{const r=fixture();r.members[0].symbol='not a normalized symbol';assert.throws(()=>assertPeerNeighbors(r,expected),/invalid_peer_neighbor_response/);});
test('rejects zero delta when supplied exact endpoints are rho zero and plus one',()=>{
 const r=fixture(),c=r.candidates.find(c=>c.previous.correlation?.exact_boundary==='zero'&&c.current.correlation?.exact_boundary==='positive_one');assert.ok(c);c.difference={estimate:'0',display:'0.0000',direction:'increased'};
 assert.throws(()=>assertPeerNeighbors(r,expected),/invalid_peer_neighbor_response/);
});
test('rejects noncanonical scientific exponent spellings',()=>{for(const number of ['5E-00001','5E-01','1E-0','1E+00'])assert.throws(()=>peerDisplay(number),/invalid_peer_neighbor_response/);});

test('rounded plus-one estimate cannot outrank a declared exact plus-one',()=>{
 const r=fixture(),peers=r.candidates.filter(c=>c.current.correlation),perfect=peers.find(c=>c.current.correlation.exact_boundary==='positive_one'),near=peers.filter(c=>c!==perfect);
 for(const c of near){c.current={correlation:{estimate:'1E+0',display:'1.0000',sign:'positive',exact_boundary:'none'},rank:1,tie_size:2,reason:null};c.difference={estimate:'0',display:'0.0000',direction:'decreased'};}
 perfect.current.rank=3;r.windows.current.order=[...near.map(c=>c.snapshot_id).sort(),perfect.snapshot_id,...r.windows.current.order.slice(3)];
 assert.throws(()=>assertPeerNeighbors(r,expected),/invalid_peer_neighbor_response/);
});
test('moving from declared exact plus-one to non-extreme rounded one must decrease',()=>{
 const r=fixture(),peers=r.candidates.filter(c=>c.current.correlation),near=peers.filter(c=>c.current.correlation.exact_boundary==='zero');
 for(const c of near){c.current.correlation={estimate:'1E+0',display:'1.0000',sign:'positive',exact_boundary:'none'};c.difference={estimate:'0',display:'0.0000',direction:'equal'};}
 assert.throws(()=>assertPeerNeighbors(r,expected),/invalid_peer_neighbor_response/);
});
