"""Independent acceptance probes for the bounded source-price filter.

Synthetic data only. The arithmetic/window oracle does not call the production
evaluator, comparator, normalizer or rule canonicalizer. HTTP probes use the
established Store fixtures and preserve its raw-file verification boundary.
"""
import asyncio
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
import math
import random

import pytest

from anatrading.stock_filters import filter_report, parse_rule
from anatrading.store import EvidenceStore
from anatrading.universe_research import universe_report
from test_research_api import client_for, seed


def source(prices, symbol='600011.SH', *, dates=None):
    days = dates or [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(len(prices))]
    sid = hashlib.sha256(symbol.encode()).hexdigest()
    return dict(snapshot_id=sid, query_id='q-' + sid,
                metadata=dict(period='1d', source_code=symbol, source_adjustflag='3'),
                rows=[dict(ordinal=i + 1, label=day, tokens={}, checks=[],
                           values={key: str(price) for key in ('open', 'high', 'low', 'close')})
                      for i, (day, price) in enumerate(zip(days, prices))], unlocated=[])


def condition(field, threshold):
    return dict(field=field, op='lte' if field == 'volatility' else 'gte', threshold=threshold)


def specification(*groups):
    return dict(any_of=[dict(all_of=[condition(field, value) for field, value in group]) for group in groups])


SIX = specification([('momentum', '0.05'), ('volatility', '0.3'), ('max_drawdown', '-0.1')],
                    [('momentum', '0.1'), ('volatility', '0.5'), ('max_drawdown', '-0.3')])


def run(queries, rule=SIX, *, cutoff=None, lookback=2):
    return filter_report(queries, cutoff or queries[0]['rows'][-1]['label'], lookback, rule)


def by_symbol(report):
    return {row['identity']['symbol']: row for row in report['result']['members']}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def historical_golden_inputs():
    rng = random.Random(32419)
    cases = []
    for trial in range(24):
        qs = [source([rng.randrange(1, 100) for _ in range(24)], f'{600011+i}.SH') for i in range(3)]
        if trial % 2 == 0:
            qs[0]['rows'].append(deepcopy(qs[0]['rows'][10]))
        if trial % 3 == 0:
            qs[1]['rows'][18]['values']['high'] = None
        if trial % 5 == 0:
            qs[2]['unlocated'] = [dict(ordinal=99, label=None, tokens={}, values={})]
        if trial % 7 == 0:
            qs[1]['rows'] = qs[1]['rows'][:-1]
        for q in qs:
            rng.shuffle(q['rows'])
        cases.append((qs, '2026-01-24', 2 + trial % 15))
    return cases


def test_old_universe_has_independent_pre_refactor_multicase_golden():
    # Captured from commit 97d483f7 via its original universe_report, never
    # generated from the refactored evaluator. Includes malformed source slots.
    reports = [universe_report(qs, cutoff, n) for qs, cutoff, n in historical_golden_inputs()]
    assert digest(reports) == '97a43f390e74f5cf12176aa784d7ce227bd7438eb67d5f8ec3db1ba56c11f606'


def test_random_exact_facts_and_rule_truth_match_independent_prices_oracle():
    rng = random.Random(96843)
    for trial in range(45):
        n = rng.randrange(2, 30)
        raw = [[rng.randrange(1, 10000) for _ in range(n + 6)] for _ in range(3)]
        qs = [source(prices, f'{600011+i}.SH') for i, prices in enumerate(raw)]
        frozen = deepcopy(qs)
        cutoff = qs[0]['rows'][-2]['label']
        with localcontext() as ctx:
            ctx.prec = 2
            result = run(qs, cutoff=cutoff, lookback=n)
        assert qs == frozen
        conditions = {item['id']: item for item in result['result']['conditions']}
        selected = 0
        for index, prices in enumerate(raw):
            row = by_symbol(result)[f'{600011+index}.SH']
            p = list(map(Fraction, prices[-(n+2):-1]))
            exact = dict(momentum=p[-1] / p[0] - 1,
                         max_drawdown=min(p[j] / max(p[:j+1]) - 1 for j in range(len(p))))
            for field, expected in exact.items():
                value = row['facts'][field]['exact']
                assert Fraction(int(value['numerator']), int(value['denominator'])) == expected
            with localcontext() as ctx:
                ctx.prec = 60
                logs = [Decimal(v.numerator).ln() for v in p]
                changes = [b-a for a, b in zip(logs, logs[1:])]
                mean = sum(changes) / n
                independent_v = (sum((r-mean)**2 for r in changes) / (n-1)).sqrt()
            estimate = row['facts']['volatility']['value']
            assert estimate == pytest.approx(float(independent_v), abs=2e-11, rel=2e-10)
            assert float.fromhex(row['facts']['volatility']['float_hex']) == estimate
            assert float(row['facts']['volatility']['estimate_text']) == estimate
            # V's declared contract compares its computed estimate, not the
            # high-precision mathematical oracle and not rounded display text.
            actual_values = {**exact, 'volatility': Fraction.from_float(estimate)}
            reference = []
            for group in SIX['any_of']:
                reference.append(all((actual_values[a['field']] <= Fraction(a['threshold'])
                                      if a['op'] == 'lte' else
                                      actual_values[a['field']] >= Fraction(a['threshold']))
                                     for a in group['all_of']))
            for atom in row['atoms']:
                definition = conditions[atom['id']]
                value, threshold = actual_values[definition['field']], Fraction(definition['threshold'])
                truth = value <= threshold if definition['op'] == 'lte' else value >= threshold
                assert atom['truth'] == ('true' if truth else 'false')
            assert row['logical_truth'] == ('true' if any(reference) else 'false')
            assert row['selection_state'] == ('selected' if any(reference) else 'excluded')
            assert row['evidence_complete'] and not row['partial_evidence']
            assert len(row['proof_groups']) == sum(reference)
            witness = row['window']['drawdown_witness']
            assert Fraction(witness['trough']['close']) / Fraction(witness['peak']['close']) - 1 == exact['max_drawdown']
            assert witness['peak']['date'] <= witness['trough']['date']
            selected += any(reference)
        assert result['result']['counts']['selection'] == dict(selected=selected, excluded=3-selected, undetermined=0)


@pytest.mark.parametrize('failure', ['future_unlocated_token', 'batch_unlocated', 'quarantine',
                                   'row_adjustment_conflict', 'source_check_failure'])
def test_source_failures_cannot_hide_behind_sufficient_or_branch(failure):
    qs = [source([100, 100, 120]), source([100, 100, 120], '600012.SH')]
    q = qs[0]
    if failure == 'future_unlocated_token':
        q['unlocated'] = [dict(ordinal=99, label=None, tokens=dict(source_date='20990101'), values={})]
    elif failure == 'batch_unlocated':
        q['counts'] = dict(batch_unlocated_rows=1)
    elif failure == 'quarantine':
        q['metadata']['quarantined'] = True
    elif failure == 'row_adjustment_conflict':
        q['rows'][1]['tokens'] = dict(adjustflag='2')
    else:
        q['rows'][1]['checks'] = [dict(name='source_code', outcome='fail', reason='synthetic')]
    out = run(qs, specification([('momentum', '0.1')], [('max_drawdown', '-0.1')]))
    row = by_symbol(out)['600011.SH']
    assert row['selection_state'] == 'undetermined'
    assert row['logical_truth'] == 'unknown'
    assert not row['evidence_complete'] and row['partial_evidence']
    assert all(a['truth'] == 'unknown' and a['reason_refs'] for a in row['atoms'])
    assert row['source_gate'] == ('unknown' if failure in {'future_unlocated_token', 'batch_unlocated'} else 'pass')
    assert all(set(a['reason_refs']) <= {r['id'] for r in row['reasons']} for a in row['atoms'])
    assert by_symbol(out)['600012.SH']['selection_state'] == 'selected'


def test_known_outside_window_failures_and_nonprice_fields_do_not_close_price_facts():
    qs = [source([100]*8), source([100]*8, '600012.SH')]
    qs[0]['rows'][0]['values']['close'] = '0'
    for row in qs[0]['rows']:
        row['values'].update(volume='invalid', amount='NaN')
        row['checks'].append(dict(name='source_volume', outcome='fail'))
    out = run(qs, specification([('momentum', '0')]), lookback=2)
    row = by_symbol(out)['600011.SH']
    assert row['selection_state'] == 'selected' and row['evidence_complete']
    assert row['window']['actual_groups'] == 3
    assert row['window']['first']['date'] == '2026-01-06'
    assert not row['reasons']


def test_missing_cutoff_has_no_fabricated_actual_window_endpoint():
    qs = [source([100, 110]), source([100, 110, 120], '600012.SH')]
    out = run(qs, specification([('momentum', '0')]), cutoff='2026-01-03')
    row = by_symbol(out)['600011.SH']
    assert row['selection_state'] == 'undetermined'
    assert row['window']['cutoff'] == '2026-01-03'
    assert row['window']['actual_groups'] == 0
    assert row['window']['first'] is None and row['window']['last'] is None
    assert row['window']['start_date'] is None and row['window']['end_date'] is None
    # Preserve the legacy universe's requested-end field; only the newly
    # promised actual window endpoint must accurately indicate its absence.
    base = next(r for r in out['result']['universe']['members'] if r['identity']['symbol'] == '600011.SH')
    assert base['end_date'] == '2026-01-03'


def test_all_legal_source_decimal_extremes_remain_unclipped_and_exact():
    low, high = '0.000000000000000001', '99999999999999999999.999999999999999999'
    qs = [source([low, low, high]), source([high, high, low], '600012.SH')]
    rule = specification([('momentum', '10')], [('max_drawdown', '-1')])
    rows = by_symbol(run(qs, rule))
    assert all(r['selection_state'] == 'selected' for r in rows.values())
    assert rows['600011.SH']['facts']['momentum']['value'] > 1e30
    dd = rows['600012.SH']['facts']['max_drawdown']
    assert dd['value'] == -1.0
    assert Fraction(int(dd['exact']['numerator']), int(dd['exact']['denominator'])) > -1
    json.dumps(rows, allow_nan=False)


@pytest.mark.parametrize('bad', [(math.nan, None), (None, None), (0.0, 'numerical_failure')])
def test_inconsistent_internal_facts_fail_whole_request_even_if_field_disabled(monkeypatch, bad):
    import anatrading.universe_research as universe
    monkeypatch.setattr(universe, '_volatility', lambda prices: bad)
    with pytest.raises(RuntimeError, match='filter_internal_fact'):
        run([source([100]*3), source([100]*3, '600012.SH')], specification([('momentum', '0')]))


def test_shared_atom_and_semantically_equivalent_input_have_unique_denominators():
    spec = specification([('momentum', '0'), ('max_drawdown', '-0.20')],
                         [('momentum', '-0.000'), ('volatility', '0.3')])
    qs = [source([100, 110, 120]), source([100]*3, '600012.SH')]
    out = run(qs, spec)
    assert len(out['result']['counts']['atoms']) == 3
    for row in out['result']['members']:
        assert len(row['atoms']) == 3 and len(row['groups']) == 2
        assert len(set(aid for group in row['groups'] for aid in group['atom_ids'])) == 3
    assert all(sum(count.values()) == 2 for count in out['result']['counts']['atoms'].values())
    reversed_spec = deepcopy(spec)
    reversed_spec['any_of'].reverse()
    for group in reversed_spec['any_of']:
        group['all_of'].reverse()
    assert run(list(reversed(qs)), reversed_spec) == out


def test_json_byte_limit_is_utf8_and_precedes_untrusted_json_parsing():
    with pytest.raises(ValueError, match='^filter_rule_limit$'):
        parse_rule('"' + '\u4e2d'*683 + '"')
    with pytest.raises(ValueError, match='^invalid_filter_rule$'):
        parse_rule('{"any_of":[{"all_of":[{"field":"momentum","field":"volatility","op":"gte","threshold":"0"}]}]}')


def test_shared_contracts_are_losslessly_reconstructible_and_not_keyed_only_by_source_id():
    qs = [source([100]*3, f'{600011+i}.SH') for i in range(4)]
    for index, q in enumerate(qs):
        semantics = dict(value='CNY', status='known', reason='documented_meaning_only')
        if index > 0:
            semantics['applicability'] = None if index == 1 else 'unverified'
        q['manifest'] = dict(raw_sha256='f'*64, source_contract_id='same-claimed-source-id',
                             versions=dict(decoder='test-v1'), contract=dict(format_id='synthetic', version='1',
                             source_semantics=dict(scope='all_records', fields=dict(price_unit=semantics))))
    before = deepcopy(qs)
    result = run(qs)['result']
    assert qs == before
    contracts = {item['id']: item for item in result['source_contracts']}
    sources = {item['snapshot_id']: item for item in result['sources']}
    assert len(contracts) == 3  # absent/null/unverified differ despite same source ID.
    assert sources[qs[2]['snapshot_id']]['contract_ref'] == sources[qs[3]['snapshot_id']]['contract_ref']
    assert len({sources[q['snapshot_id']]['id'] for q in qs}) == 4
    for q in qs:
        projected = sources[q['snapshot_id']]
        shared = contracts[projected['contract_ref']]
        assert digest({k:v for k,v in shared.items() if k != 'id'}) == shared['id']
        reconstructed = {k:v for k,v in projected.items() if k not in {'id', 'contract_ref'}}
        reconstructed.update({k:v for k,v in shared.items() if k != 'id'})
        assert digest(reconstructed) == projected['id']
        assert shared['source_contract_id'] == dict(present=True, value='same-claimed-source-id')
        assert shared['semantics']['price_unit']['status'] == dict(present=True, value='known')
    assert run(list(reversed(qs))) == run(qs)


def test_shared_contract_does_not_merge_per_source_capture_metadata_or_identity():
    qs = [source([100]*3), source([100]*3, '600012.SH')]
    for q in qs:
        q['metadata'].update(capture_mode='legacy_reconstruction', transport_evidence='unrecorded')
    original = run(qs)
    changed = deepcopy(qs)
    changed[0]['metadata']['transport_evidence'] = None
    updated = run(changed)
    assert len(original['result']['source_contracts']) == len(updated['result']['source_contracts']) == 1
    assert original['source_metadata_id'] != updated['source_metadata_id']
    assert original['analysis_id'] != updated['analysis_id']
    assert original['rule_id'] == updated['rule_id']
    assert original['base_analysis_id'] == updated['base_analysis_id']
    sources = {s['snapshot_id']:s for s in updated['result']['sources']}
    assert sources[qs[0]['snapshot_id']]['metadata']['transport_evidence'] == dict(present=True, value=None)
    assert sources[qs[1]['snapshot_id']]['metadata']['transport_evidence'] == dict(present=True, value='unrecorded')


def test_compact_condition_and_reason_references_resolve_without_losing_evidence():
    qs = [source([100]*31, f'{600011+i}.SH') for i in range(3)]
    qs[1]['unlocated'] = [dict(ordinal=99, label=None, tokens={}, values={})]
    for row in qs[2]['rows']:
        row['values']['close'] = '0'
    result = run(qs, lookback=30)['result']
    conditions = {item['id']: item for item in result['conditions']}
    sources = {item['id']: item for item in result['sources']}
    contracts = {item['id']: item for item in result['source_contracts']}
    assert list(conditions) == [f'a{i}' for i in range(1, 7)]
    assert result['reason_example_fields'] == ['date', 'ordinal']
    for row in result['members']:
        assert row['source_ref'] in sources
        assert sources[row['source_ref']]['contract_ref'] in contracts
        assert row['window_ref'] == row['window']['id']
        atoms = {a['id']: a for a in row['atoms']}
        reasons = {r['id']: r for r in row['reasons']}
        groups = {g['id']:g for g in row['groups']}
        assert set(atoms) == set(conditions)
        assert list(reasons) == [f'r{i}' for i in range(1, len(reasons)+1)]
        for atom in atoms.values():
            definition = conditions[atom['id']]
            assert atom['fact_ref'] == definition['field']
            fact = row['facts'][atom['fact_ref']]
            assert fact['comparison_type'] == ('float64_estimate' if definition['field']=='volatility' else 'source_fraction')
            assert set(atom['reason_refs']) <= set(reasons)
            assert (atom['truth'] != 'unknown') or atom['reason_refs']
        for group in groups.values():
            assert set(group['atom_ids']) <= set(atoms)
            assert group['false_atoms'] == [aid for aid in group['atom_ids'] if atoms[aid]['truth']=='false']
            assert group['unknown_atoms'] == [aid for aid in group['atom_ids'] if atoms[aid]['truth']=='unknown']
        assert row['proof_groups'] == [gid for gid,g in groups.items() if g['truth']=='true']
        for reason in reasons.values():
            assert all(len(example)==2 for example in reason['examples'])
            if reason['scope'] == 'window_slot':
                assert reason['count'] == len(reason['examples']) + reason['omitted_count']
                assert len(reason['examples']) <= 8
    invalid = next(row for row in result['members'] if row['identity']['symbol']=='600013.SH')
    reason = next(r for r in invalid['reasons'] if r['code']=='invalid_price')
    assert reason['count']==31 and len(reason['examples'])==8 and reason['omitted_count']==23
    assert dict(zip(result['reason_example_fields'], reason['examples'][0])) == dict(date='2026-01-01', ordinal=1)


def api_parameters(ids, rule=SIX):
    return dict(snapshot_ids=','.join(ids), cutoff='2025-01-25', lookback='2',
                rule=json.dumps(rule, separators=(',', ':')))


def test_http_all_duplicate_keys_and_malformed_json_fail_before_source_access(monkeypatch, tmp_path):
    ids = ['a'*64, 'b'*64]
    def forbidden(*args, **kwargs):
        raise AssertionError('request validation reached the Store')
    monkeypatch.setattr(EvidenceStore, 'query_row_count', forbidden)
    monkeypatch.setattr(EvidenceStore, '_research_query', forbidden)
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            params = api_parameters(ids)
            for key in params:
                response = await client.get('/api/research/universe-filter', params=[*params.items(), (key, params[key])])
                assert response.status_code == 400 and response.json() == dict(error='invalid_request')
            for key in params:
                if key == 'lookback':  # Its default is intentionally supported.
                    continue
                response = await client.get('/api/research/universe-filter', params={k:v for k,v in params.items() if k != key})
                assert response.status_code == 400 and response.json() == dict(error='invalid_request')
            for raw in [
                '{"any_of":[{"all_of":[],"all_of":[]}]}',
                '{"any_of":[{"all_of":[{"field":"momentum","\\u0066ield":"momentum","op":"gte","threshold":"0"}]}]}',
                '{"any_of":NaN}', '{"any_of":Infinity}', '{"any_of":-Infinity}',
                '['*1000 + ']'*1000,
            ]:
                response = await client.get('/api/research/universe-filter', params={**params, 'rule':raw})
                assert response.status_code == 400 and response.json() == dict(error='invalid_filter_rule')
                assert response.headers['cache-control'] == 'no-store'
    asyncio.run(scenario())


def test_http_total_row_budget_without_any_individual_overflow(monkeypatch, tmp_path):
    import anatrading.universe_research as universe
    ids = [f'{i:064x}' for i in range(1, 12)]
    seen = []
    def count(self, snapshot_id, cutoff=None):
        seen.append(snapshot_id)
        return 1 if snapshot_id == ids[-1] else 20000
    def forbidden(*args, **kwargs):
        raise AssertionError('total budget failure materialized or calculated a member')
    monkeypatch.setattr(EvidenceStore, 'query_row_count', count)
    monkeypatch.setattr(EvidenceStore, '_research_query', forbidden)
    monkeypatch.setattr(universe, 'daily_bars', forbidden)
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            response = await client.get('/api/research/universe-filter', params=api_parameters(ids))
            assert response.status_code == 400 and response.json() == dict(error='research_row_limit')
    asyncio.run(scenario())
    assert seen == ids


def test_http_exact_rule_byte_budget_and_one_evaluator_for_all_conditions(monkeypatch, tmp_path):
    import anatrading.stock_filters as filters
    import anatrading.universe_research as universe
    ids = seed(tmp_path / 'store', 25)
    calls = dict(evaluator=0, count=0, read=0, raw=0, bars=0)
    # Both pure and prepared HTTP paths use this same numerical core.
    original = universe._evaluate_members
    def evaluated(*args, **kwargs):
        calls['evaluator'] += 1
        return original(*args, **kwargs)
    monkeypatch.setattr(universe, '_evaluate_members', evaluated)
    for attr, key in [('query_row_count', 'count'), ('_research_query', 'read'), ('_verify_raw', 'raw')]:
        old = getattr(EvidenceStore, attr)
        def tracked(self, *args, _old=old, _key=key, **kwargs):
            calls[_key] += 1
            return _old(self, *args, **kwargs)
        monkeypatch.setattr(EvidenceStore, attr, tracked)
    old_bars = universe.daily_bars
    def bars(query):
        calls['bars'] += 1
        return old_bars(query)
    monkeypatch.setattr(universe, 'daily_bars', bars)
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            for key in calls:
                calls[key] = 0
            params = api_parameters(ids)
            params['rule'] += ' ' * (2048 - len(params['rule'].encode('utf-8')))
            response = await client.get('/api/research/universe-filter', params=params)
            assert response.status_code == 200, response.text
            assert calls == dict(evaluator=1, count=3, read=3, raw=3, bars=3)
            before = dict(calls)
            invalid = await client.get('/api/research/universe-filter', params={**params, 'rule':params['rule']+' '})
            assert invalid.status_code == 400 and invalid.json() == dict(error='filter_rule_limit')
            assert calls == before
    asyncio.run(scenario())


def test_http_safe_errors_and_unclassified_failures_are_distinct(monkeypatch, tmp_path):
    import anatrading.stock_filters as filters
    import anatrading.research_api as api
    ids = seed(tmp_path / 'store', 25)
    async def scenario():
        async with client_for(tmp_path / 'store') as client:
            for code in sorted(api._SAFE_ERRORS | filters.FILTER_ERRORS):
                def rejected(*args, _code=code, **kwargs):
                    raise ValueError(_code)
                monkeypatch.setattr(filters, '_assemble_filter', rejected)
                response = await client.get('/api/research/universe-filter', params=api_parameters(ids))
                assert response.status_code == 400 and response.json() == dict(error=code)
            for exception in [ValueError('secret internal values'), RuntimeError('secret internal values'),
                              TypeError('secret internal values'), AssertionError('secret internal values')]:
                def broken(*args, _exception=exception, **kwargs):
                    raise _exception
                monkeypatch.setattr(filters, '_assemble_filter', broken)
                response = await client.get('/api/research/universe-filter', params=api_parameters(ids))
                assert response.status_code == 500 and response.json() == dict(error='internal_error')
                assert 'secret' not in response.text and response.headers['cache-control'] == 'no-store'
    asyncio.run(scenario())


def test_http_reverifies_raw_source_after_prior_success_and_rejects_foreign_origin(tmp_path):
    root = tmp_path / 'store'
    ids = seed(root, 25)
    with EvidenceStore(root) as store:
        query = store.query(ids[0])
        raw = query['manifest']['raw_sha256']
    path = root / 'raw' / raw[:2] / raw
    assert path.is_file()
    original = path.read_bytes()
    async def scenario():
        async with client_for(root) as client:
            params = api_parameters(ids)
            good = await client.get('/api/research/universe-filter', params=params)
            assert good.status_code == 200, good.text
            for headers in [{'Origin':'https://untrusted.invalid'}, {'Host':'untrusted.invalid'}]:
                denied = await client.get('/api/research/universe-filter', params=params, headers=headers)
                assert denied.status_code == 403 and denied.headers['cache-control'] == 'no-store'
            path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
            broken = await client.get('/api/research/universe-filter', params=params)
            assert broken.status_code == 409 and broken.json() == dict(error='raw_object_corrupt')
            assert broken.headers['cache-control'] == 'no-store'
    asyncio.run(scenario())
