import {createHash} from 'node:crypto';
import {canonicalJson} from '../src/filter-model.ts';
export function fixture() {
  const ids = ['a', 'b', 'c', 'd'].map(s => s.repeat(64));
  const dates = Array.from({ length: 62 }, (_, i) => new Date(Date.UTC(2026, 0, i+1)).toISOString().slice(0, 10));
  const expected = { ids, groups: { A: ids.slice(0, 2), B: ids.slice(2) }, start: dates[60], end: dates[61] };
  const endpoint = (date, i) => ({date, ordinal: i+1, close_token: '100', close_exact: '100', reasons: []});
  const reply = {
    method_id: 'two-group-frozen-source-v1', rule_version: 'decimal80-qr2-reference-v1', analysis_id: 'f'.repeat(64),
    parameters: { groups: expected.groups, current_start: expected.start, current_end: expected.end, rules: { training_intervals: 60, decimal_precision: 80, rounding: 'ROUND_HALF_EVEN', sd_min: 1e-12, rank_min: 1e-10, rank_gray: 1e-12, tolerance_absolute: 1e-10, tolerance_relative: 1e-8, exclusion: 'each_target_from_own_group_train_and_current', unit: 'source_log_change' } },
    scope: Object.fromEntries(Object.entries({asset_type:'stock', share_class:'A_share', price_currency:'CNY', daily_label_basis:'CN_exchange_date'}).map(([k,v]) => [k, {value:v,evidence_status:'assumed'}])),
    events: [], training_dates: dates.slice(0,61), members: ids.map((id,i)=>({symbol:`60000${i}.SH`,snapshot_id:id,query_id:String(i+1).repeat(64),group:i<2?'A':'B',
      endpoints:{start:endpoint(expected.start,60),end:endpoint(expected.end,61)},training_endpoints:dates.map(endpoint),raw_change:.1,source_complete:true,reasons:[],
      model:{baseline:.01,contributions:[.02,.03],explained:.06,residual:.04,gamma:[.02,.03],factor_mean:[0,0],factor_sd:[.1,.1],current_factor:[.1,.1],current_z:[1,1],rank_ratio:.4,tolerance:1.1e-9,within_resolution:false},
      anomalies:{total:0,counts:{},examples:[],truncated:false}})),counts:{selected:4,source_complete:4,model_available:4},status:'complete',reasons:[],
    limitations:{trading_calendar:'unknown',historical_availability:'unverified',membership:'current_members_retrospective',source_semantics:'unverified',adjustment:'request_declared_semantics_unverified',corporate_action_coverage:'unknown',economic_return_qualified:false,predictive_advantage:'not_evaluated',residuals:'mutually_dependent_not_noise_or_probability',risk_standardized:false}
  };
  const numeric = Object.fromEntries(Object.entries(reply.parameters.rules).map(([k,v]) => [k, v === 1e-8 ? '1e-08' : String(v)]));
  reply.analysis_id = createHash('sha256').update(canonicalJson({method_id:reply.method_id,rule_version:reply.rule_version,parameters:{groups:reply.parameters.groups,current_start:expected.start,current_end:expected.end},numerical_protocol:numeric,sources:reply.members.map(m=>({symbol:m.symbol,snapshot_id:m.snapshot_id,query_id:m.query_id})),scope:reply.scope,events:reply.events})).digest('hex');
  return {expected,reply};
}
