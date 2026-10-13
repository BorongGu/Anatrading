"""Bounded single-date projection, preserving the offline full report."""
from copy import deepcopy
import json
import pytest
import anatrading.close_dispersion as module
from test_close_dispersion import query


def test_selected_matches_every_legacy_row_without_full_report(monkeypatch):
    q = query(['1', '2'] * 32)
    q['rows'][25]['values']['low'] = '100'
    full = module.dispersion_report(q)
    before = deepcopy(q)
    monkeypatch.setattr(module, 'dispersion_report', lambda *_: pytest.fail('full report called'))
    original = module.exact_window
    calls = []
    monkeypatch.setattr(module, 'exact_window', lambda values: (calls.append(1), original(values))[1])
    for row in full['series']:
        calls.clear()
        result = module.selected_dispersion_report(q, row['date'])
        assert result['selected'] == row
        assert result['status'] == row['status'] and result['reason'] == row['reason']
        assert len(calls) == int(row['status'] == 'computed')
        assert result['members'] == [{k: member[k] for k in ('position','date','ordinal','close','source_reason')}
                                      for member in full['series'][row['window_start_position']:row['position']+1]]
        assert {k:v for k,v in result.items() if k in full} == {k:v for k,v in full.items() if k != 'series'}
    assert q == before


def test_latest_includes_invalid_duplicate_and_recovered_date():
    q = query(['1'] * 20)
    q['rows'][-1]['values']['close'] = '0'
    assert module.selected_dispersion_report(q)['selected']['source_reason'] == 'invalid_price'
    q['rows'].append(deepcopy(q['rows'][-1]))
    assert module.selected_dispersion_report(q)['selected']['source_reason'] == 'duplicate_date'
    q['unlocated'] = [dict(ordinal=22, label=None, tokens=dict(date='2030-01-01'), values={})]
    result = module.selected_dispersion_report(q)
    assert result['selection'] == dict(date_requested=None, resolved_date='2030-01-01', policy='latest_source_date')
    assert result['selected']['source_reason'] == 'unlocated_label'


@pytest.mark.parametrize('day', ['2020-01-01', '2030-01-01'])
def test_exact_missing_never_falls_back(day):
    result = module.selected_dispersion_report(query(['1'] * 20), day)
    assert result['status'] == 'unavailable' and result['reason'] == 'date_not_present'
    assert result['selected'] is None and result['members'] == []
    assert result['selection']['resolved_date'] is None


def test_empty_and_all_undated():
    q = query([])
    for unlocated in ([], [dict(ordinal=1,label=None,tokens={},values={})]):
        q['unlocated'] = unlocated
        result = module.selected_dispersion_report(q)
        assert result['reason'] == 'no_date_groups' and result['selected'] is None
        assert result['coverage']['unlocated_rows'] == len(unlocated)


@pytest.mark.parametrize('day', ['2025-02-30','20250101','2025-01-01T00:00:00',True,''])
def test_selected_date_strict(day):
    with pytest.raises(ValueError): module.selected_dispersion_report(query(['1'] * 20), day)


def test_prefix_local_values_but_current_coverage_and_quarantine():
    q = query(['1'] * 30)
    target = q['rows'][19]['label']
    q['selection']['cutoff'] = target
    q['rows'] = q['rows'][:20]
    first = module.selected_dispersion_report(q, target)
    q['unlocated'] = [dict(ordinal=31,label=None,tokens=dict(date='2030-01-01'),values={})]
    later = module.selected_dispersion_report(q, target)
    assert first['selected'] == later['selected'] and first['members'] == later['members']
    assert first['coverage'] != later['coverage']
    q['metadata']['quarantined'] = True
    rejected = module.selected_dispersion_report(q, target)
    assert rejected['qualification'] == 'source_rejected'
    assert rejected['selected']['reason'] == 'invalid_window'
    assert len(rejected['selected']['invalid_members']) == 20


def test_response_bytes_exact_boundary_unicode_and_no_truncation():
    from anatrading.research_api import _dispersion_bytes
    class Error(ValueError): pass
    assert len(_dispersion_bytes({'x':'x' * 65528}, Error)) == 65536
    with pytest.raises(Error, match='dispersion_result_limit'):
        _dispersion_bytes({'x':'x' * 65529}, Error)
    with pytest.raises(Error, match='dispersion_result_limit'):
        _dispersion_bytes({'qualification':'中' * 22000}, Error)
    assert json.loads(_dispersion_bytes({'x':'中'}, Error)) == {'x':'中'}
