import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {explain} from '../src/api.ts';
import {peerReason,explainPeerNeighborError} from '../src/peer-neighbor-model.ts';
import {explainFilter,ResearchRequestController} from '../src/filter-model.ts';
import {explainGroupEndpointError,groupReason} from '../src/group-endpoint-model.ts';
import {explanationReasons} from '../src/two-group-model.ts';
import {createUniverseDraft,prepareUniverseRequest,loadUniverseRequest} from '../src/universe-request.ts';
const source=readFileSync(new URL('../src/UniverseResearch.tsx',import.meta.url),'utf8');
const expression=source.match(/id="universe-error-summary" tabIndex=\{-1\}>\{([^\n]+)\}<\/p>/)?.[1];assert.ok(expression);
const evaluate=new Function('draft','requestState','explainPeerNeighborError','groupReason','explainGroupEndpointError','explanationReasons','explainFilter',`return (${expression});`);
const banner=error=>evaluate({mode:'peer_neighbors'},{status:'error',error},explainPeerNeighborError,groupReason,explainGroupEndpointError,explanationReasons,explainFilter);
const codes=['raw_object_missing','raw_object_corrupt','snapshot_not_found','service_busy','connection_error','service_closing','storage_io_error','internal_error'];
for(const code of codes)test(`peer request banner retains shared recovery: ${code}`,()=>{const e=new Error(code);assert.equal(banner(e),explain(e));assert.doesNotMatch(banner(e),/来源限制/);});
test('unknown and prototype request codes keep safe shared fallback; member labels stay plain',()=>{
 for(const error of [new Error('constructor'),new Error('__proto__'),new Error('toString'),new Error('unknown_safe_code'),new Error('<private>'),new Error('/private/path'),new TypeError('Failed to fetch'),null,{message:'raw_object_missing'}]){assert.equal(banner(error),explainFilter(error));assert.doesNotMatch(banner(error),/native code|private|来源限制/);}
 for(const code of ['constructor','__proto__','toString','未知核验'])assert.equal(peerReason(code),`来源限制：${code}`);
 for(const code of ['invalid_target','peer_neighbor_integer_limit','peer_neighbor_result_limit','invalid_peer_neighbor_response'])assert.equal(banner(new Error(code)),`${peerReason(code)}（${code}）`);
});
test('actual peer loader error, clean retry and source drafts preserve recovery through controller',async()=>{
 const f=JSON.parse(readFileSync(new URL('./peer-neighbor-fixtures.json',import.meta.url),'utf8')).complete;
 const draft={...createUniverseDraft(),mode:'peer_neighbors',ids:f.expected.ids,peerTarget:f.expected.target,cutoff:f.expected.cutoff},saved=structuredClone(draft),old=globalThis.fetch;
 let failure=null;globalThis.fetch=async()=>{if(failure==='connection_error')throw new TypeError('Failed to fetch');return failure?Response.json({error:failure},{status:409}):Response.json(f.reply);};
 const c=new ResearchRequestController(()=>{}),run=()=>c.run(()=>prepareUniverseRequest(draft,draft.ids),loadUniverseRequest);
 try{await run();for(const code of codes.slice(0,5)){failure=code;await run();assert.equal(c.state.status,'error');assert.equal(c.state.result,null);assert.equal(banner(c.state.error),explain(new Error(code)));assert.deepEqual(draft,saved);failure=null;await run();assert.equal(c.state.status,'ready');}}finally{c.dispose();globalThis.fetch=old;}
});
