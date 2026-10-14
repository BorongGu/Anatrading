import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../src/App.tsx',import.meta.url),'utf8');
test('query-keyed sibling component roles have stable disjoint namespaces',()=>{
 const roles={SourceChart:'source-chart',SingleResearch:'single-research',GapAnalysis:'gap-analysis',PivotAnalysis:'pivot-analysis',MinuteAggregation:'minute-aggregation',SourceActions:'source-actions'};
 for(const [component,role] of Object.entries(roles))assert.ok(source.includes('<'+component+' key={`'+role+':${q.query_id}`}'),component);
 assert.doesNotMatch(source,/key=\{q\.query_id\}/);
});
