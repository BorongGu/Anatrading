/** Test-only direct peak enumeration, no product scan or DTO as the oracle. */
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const fixtures=JSON.parse(readFileSync(new URL('./drawdown-episode-fixtures.json',import.meta.url),'utf8'));
function reference(points){
 const prices=points.map(p=>{const [a,b='']=p.close_exact.split('.');return BigInt(a)*10n**18n+BigInt(b.padEnd(18,'0'));});
 const episodes=[];
 for(let peak=0;peak<prices.length-1;peak++){
  if(prices.slice(0,peak+1).some(v=>v>prices[peak])||prices[peak+1]>=prices[peak])continue;
  const recovery=prices.findIndex((v,i)=>i>peak&&v>=prices[peak]);
  const end=recovery<0?prices.length-1:recovery;
  const underwater=Array.from({length:end-peak-(recovery<0?0:1)},(_,i)=>peak+1+i);
  const valley=underwater.reduce((a,b)=>prices[b]<prices[a]?b:a);
  episodes.push({peak,valley,recovery:recovery<0?null:recovery,end,n:prices[peak]-prices[valley],d:prices[peak]});
 }
 return episodes;
}
test('API complete endpoints independently enumerate representatives, counts, ties and censoring',()=>{
 for(const f of Object.values(fixtures)){
  if(!f.reply.comparison_available)continue;
  for(const m of f.reply.members){
   const episodes=reference(m.endpoints);
   const deepest=episodes.reduce((a,b)=>!a||b.n*a.d>a.n*b.d?b:a,null);
   const longest=episodes.reduce((a,b)=>!a||b.end-b.peak>a.end-a.peak?b:a,null);
   const open=episodes.find(e=>e.recovery===null)??null;
   assert.equal(m.episode_count,episodes.length);assert.equal(m.open_count,Number(open!==null));
   for(const [field,e] of [['deepest',deepest],['longest_observed',longest],['current_open',open]]){
    const actual=m[field];if(!e){assert.equal(actual,null);continue;}
    assert.deepEqual([actual.peak.index,actual.valley.index,actual.recovery?.index??null,actual.observed_end.index],[e.peak,e.valley,e.recovery,e.end]);
    assert.equal(BigInt(actual.depth_fraction.numerator)*e.d,BigInt(actual.depth_fraction.denominator)*e.n);
   }
  }
 }
});
