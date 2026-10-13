// Saved after the original JavaScript runs. Saving this file is not a rerun.
// Original code used a `text` output helper; this adapter emits JSONL.
const text = value => console.log(JSON.stringify(value));

// FIRST ORIGINAL RUN: after the primary float protocol freeze.
function stats(a){let n=BigInt(a.length),S=a.reduce((x,y)=>x+y,0n),Q=a.reduce((x,y)=>x+y*y,0n);return {n:String(n),sum:String(S),mean:`${S}/${n}`,variance:`${n*Q-S*S}/${n*n}`}}
const basics={
alternating:Array.from({length:20},(_,i)=>BigInt(99+2*(i%2))),
sparse:[99n,101n,...Array(18).fill(100n)],
linear:Array.from({length:20},(_,i)=>BigInt(100+i)),
constant:Array(20).fill(100n),
decimal_collision_scaled1e18:Array.from({length:20},(_,i)=>1000000000000000000n+BigInt(i%2))
};for (let [name,a] of Object.entries(basics))text({name,...stats(a)});
text({collision_float_values:[Number("1"),Number("1.000000000000000001")],collision_float_equal:Number("1")===Number("1.000000000000000001"),collision_exact_sigma:"0.0000000000000000005",within_source_decimal38_18:true});

// SECOND ORIGINAL RUN: separately frozen reviewer-boundary-extension-v1.
const max=10n**38n-1n, k=10n**18n;
const fixtures={
constant_min:Array(20).fill(1n),constant_max:Array(20).fill(max),
alternating_min:Array.from({length:20},(_,i)=>1n+BigInt(i%2)),
alternating_max:Array.from({length:20},(_,i)=>max-1n+BigInt(i%2)),
max_outlier:[...Array(19).fill(1n),max],
positive_negative_lower:[...Array(19).fill(k),100n*k]};
for(let [name,a] of Object.entries(fixtures)){
let S=a.reduce((x,y)=>x+y,0n),Q=a.reduce((x,y)=>x+y*y,0n),D=20n*Q-S*S, pair=0n;
for(let i=0;i<20;i++)for(let j=i+1;j<20;j++)pair+=(a[i]-a[j])**2n;
text({name,exact_pair_oracle_matches:D===pair,D:String(D),bits:D.toString(2).length,variance:`${D}/${400n*k*k}`,zero_iff_constant:(D===0n)==a.every(x=>x===a[0]),lower_negative:S*S<4n*D});
}
text({source_validation:[-1n,0n,1n,max,max+1n].map(x=>({lattice:String(x),valid:x>0&&x<=max}))});
const s=Array(60).fill(100n);s[25]=null;
let invalid=[],warmup=[],good=[];
for(let i=0;i<s.length;i++){if(i<19)warmup.push(i);else if(s.slice(i-19,i+1).some(x=>x===null))invalid.push(i);else good.push(i)}
text({warmup,invalid,first_recovered:good.find(x=>x>25),computed_count:good.length});
