"""Coverage describes chosen collection outcomes, without filling missing bars."""
import asyncio
import hashlib
import json

import pytest

from anatrading import daily_coverage
from anatrading.tdx_acquisition import AcquireError
from test_formats import day_record
from test_workbench import running


POOL = ['600059.SH', '000001.SZ', '920000.BJ']


def run(root, run_id, outcomes, *, start=0, pool=POOL, state='completed'):
    directory = root / 'acquisition' / 'daily-cache' / run_id
    directory.mkdir(parents=True)
    response = json.dumps(dict(id=1, result=dict(ErrorId='0', Value=pool)))
    (directory / 'catalog.json').write_text(json.dumps(dict(response_utf8=response)))
    (directory / 'progress.json').write_text(json.dumps(dict(status=state,
        pool_sha256=hashlib.sha256(response.encode()).hexdigest(), skipped_prefix=start,
        processed=len(outcomes))))
    (directory / 'outcomes.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in outcomes))


def committed(root, symbol, dates):
    raw = b''.join(day_record(date=value) for value in dates)
    sha = hashlib.sha256(raw).hexdigest()
    path = root / 'raw' / sha[:2] / sha
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    snapshot = hashlib.sha256(symbol.encode()).hexdigest()
    outcome = dict(symbol=symbol, status='committed', snapshot_id=snapshot, raw_sha256=sha)
    catalog = dict(snapshot_id=snapshot, row_count=len(dates), metadata=dict(period='1d'),
        manifest=dict(raw_sha256=sha, interpretation=dict(instrument=symbol, venue=symbol[-2:]),
                      contract=dict(format_id='tdx-public-day-v1')))
    return outcome, catalog


def test_resumed_prefix_joins_without_selecting_newer_snapshots(tmp_path):
    first, snapshot = committed(tmp_path, POOL[0], [20261008, 20260930, 20260930, 20260230])
    second, other = committed(tmp_path, POOL[1], [20260929])
    run(tmp_path, 'a'*32, [first], state='failed')
    run(tmp_path, 'b'*32, [second, dict(symbol=POOL[2], status='missing')], start=1)
    result = daily_coverage.coverage_report(tmp_path, [snapshot, other], ['b'*32, 'a'*32])
    assert result['counts'] == dict(pool=3, processed=3, committed=2, missing=1, failed=0, unprocessed=0, source_rows=5)
    assert result['latest_source_date_counts'] == {'2026-09-29': 1, '2026-10-08': 1}
    row = result['rows'][0]
    assert row['first_record_date'] == '2026-10-08' and row['last_record_date'] is None
    assert row['earliest_source_date'] == '2026-09-30' and row['latest_source_date'] == '2026-10-08'
    assert (row['invalid_date_rows'], row['duplicate_date_rows'], row['descending_steps']) == (1, 1, 1)
    assert row['snapshot_id'] == snapshot['snapshot_id']
    assert result['rows'][2]['latest_source_date'] is None


def test_partial_prefix_keeps_unprocessed_members(tmp_path):
    run(tmp_path, 'a'*32, [dict(symbol=POOL[0], status='missing')], state='interrupted')
    result = daily_coverage.coverage_report(tmp_path, [], ['a'*32])
    assert result['counts']['unprocessed'] == 2
    assert [row['status'] for row in result['rows']] == ['missing', 'unprocessed', 'unprocessed']


def test_native_short_date_is_not_a_readable_format_label(tmp_path):
    outcome,snapshot=committed(tmp_path,POOL[0],[10101])
    run(tmp_path,'a'*32,[outcome])
    row=daily_coverage.coverage_report(tmp_path,[snapshot],['a'*32])['rows'][0]
    assert row['invalid_date_rows']==1 and row['latest_source_date'] is None


def test_relative_data_root_matches_cli_startup(tmp_path, monkeypatch):
    root = tmp_path/'root'
    outcome, snapshot = committed(root, POOL[0], [20261008])
    run(root, 'a'*32, [outcome])
    monkeypatch.chdir(tmp_path)
    assert daily_coverage.collection_runs('root')[0]['run_id'] == 'a'*32
    assert daily_coverage.coverage_report('root', [snapshot], ['a'*32])['counts']['committed'] == 1


@pytest.mark.parametrize('problem', ['overlap', 'changed_pool', 'out_of_order', 'running', 'processed_count'])
def test_incompatible_or_unsettled_logs_are_rejected(tmp_path, problem):
    run(tmp_path, 'a'*32, [dict(symbol=POOL[0], status='missing')])
    if problem == 'overlap': run(tmp_path, 'b'*32, [dict(symbol=POOL[0], status='missing')])
    elif problem == 'changed_pool': run(tmp_path, 'b'*32, [], pool=POOL[::-1])
    elif problem == 'out_of_order': run(tmp_path, 'b'*32, [dict(symbol=POOL[2], status='missing')], start=1)
    elif problem == 'running': run(tmp_path, 'b'*32, [], state='running')
    else:
        run(tmp_path, 'b'*32, [])
        path = tmp_path/'acquisition/daily-cache'/('b'*32)/'progress.json'
        value = json.loads(path.read_text()); value['processed']=1; path.write_text(json.dumps(value))
    with pytest.raises(AcquireError, match='invalid_daily_cache_runs'):
        daily_coverage.coverage_report(tmp_path, [], ['a'*32, 'b'*32])


def test_corrupt_raw_or_conflicting_snapshot_is_not_presented_as_coverage(tmp_path):
    outcome, snapshot = committed(tmp_path, POOL[0], [20261008])
    run(tmp_path, 'a'*32, [outcome])
    snapshot['row_count'] = 2
    with pytest.raises(AcquireError, match='daily_cache_evidence_mismatch'):
        daily_coverage.coverage_report(tmp_path, [snapshot], ['a'*32])
    snapshot['row_count'] = 1
    sha = outcome['raw_sha256']; (tmp_path/'raw'/sha[:2]/sha).write_bytes(day_record(date=20260930))
    with pytest.raises(AcquireError, match='daily_cache_evidence_mismatch'):
        daily_coverage.coverage_report(tmp_path, [snapshot], ['a'*32])


@pytest.mark.parametrize('ids', [[], ['../outside'], ['a'*32, 'a'*32]])
def test_invalid_run_selection(tmp_path, ids):
    with pytest.raises(AcquireError, match='invalid_daily_cache_runs'):
        daily_coverage.coverage_report(tmp_path, [], ids)


def test_http_coverage_uses_local_owner_and_rejects_ambiguous_parameters(tmp_path):
    root = tmp_path/'root'
    run(root, 'a'*32, [dict(symbol=POOL[0], status='missing')])
    async def scenario():
        async with running(root) as (_, client, auth):
            listing = (await client.get('/api/daily-cache-runs')).json()['runs']
            assert listing[0]['run_id'] == 'a'*32
            reply = await client.get('/api/daily-cache-coverage', params=dict(run_ids='a'*32))
            assert reply.status_code == 200 and reply.json()['coverage']['counts']['missing'] == 1
            bad = await client.get('/api/daily-cache-coverage?run_ids='+('a'*32)+'&run_ids='+('a'*32))
            assert bad.status_code == 400
    asyncio.run(scenario())
