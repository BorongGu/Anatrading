"""Offline capture-only contract; every root and response is synthetic."""
import json
import os

import pytest

from anatrading import public_acquisition as module, public_transport, cli
from anatrading.public_market import canonical_json
from anatrading.store import EvidenceStore
from test_public_acquisition import acquire, response, Crash


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(module, '_SEND_INTERVAL', 0)


@pytest.fixture
def root(tmp_path):
    root = tmp_path / 'synthetic'
    (root / 'public_acquisition' / 'sources').mkdir(parents=True)
    return root


def forbidden(*args, **kwargs):
    raise AssertionError('forbidden Store or transport access')


def guard(monkeypatch):
    import duckdb
    monkeypatch.setattr(duckdb, 'connect', forbidden)
    monkeypatch.setattr(module, 'EvidenceStore', forbidden)
    for name in ('_commit', '_expected', '_receipt', '_revision'):
        monkeypatch.setattr(module, name, forbidden)


def test_capture_and_resume_zero_database(root, monkeypatch):
    guard(monkeypatch)
    result = acquire(root, capture_only=True)
    assert result['status'] == 'captured'
    assert result['execution_mode'] == 'capture_only'
    assert not result['resume_allowed']
    block = result['blocks'][0]
    assert block['capture_sha256'] and block['reused'] is False
    assert all(block[key] is None for key in ('snapshot_id', 'store_attempt_id', 'raw_sha256', 'batch_id', 'target_view'))
    plan = json.loads((root / 'public_acquisition' / result['run_id'] / 'plan.json').read_bytes())
    assert plan['version'] == 'public-market-plan-v2' and plan['execution_mode'] == 'capture_only'
    resumed = module.resume_public(root, result['run_id'], _transport=forbidden)
    assert resumed['status'] == 'captured' and resumed['attempts_used'] == 1
    assert resumed['blocks'] == result['blocks']
    assert {p.name for p in root.iterdir()} == {'.operation.lock', 'public_acquisition'}


@pytest.mark.parametrize('stage', ['reservation_published', 'attempt_requested', 'capture_temporary', 'capture_published', 'capture_recorded'])
def test_capture_crash_recovery(root, monkeypatch, stage):
    guard(monkeypatch)
    def stop(point):
        if point == stage:
            raise Crash
    with pytest.raises(Crash):
        acquire(root, capture_only=True, _checkpoint=stop)
    run = next(p.name for p in (root / 'public_acquisition').iterdir() if len(p.name) == 32)
    calls = []
    def transport(*args, **kwargs):
        calls.append(1)
        return response(*args, **kwargs)
    result = module.resume_public(root, run, _transport=transport)
    assert result['status'] == 'captured'
    assert len(calls) == int(stage in {'reservation_published', 'attempt_requested'})
    assert result['attempts_used'] == 1 + len(calls)
    assert module.resume_public(root, run, _transport=forbidden)['blocks'] == result['blocks']


@pytest.mark.parametrize('missing', ['root', 'public_acquisition', 'sources'])
def test_capture_requires_existing_authority(tmp_path, missing):
    root = tmp_path / 'root'
    if missing != 'root':
        root.mkdir()
    if missing == 'sources':
        (root / 'public_acquisition').mkdir()
    with pytest.raises((module.PublicAcquisitionError, OSError)):
        acquire(root, capture_only=True, _transport=forbidden)
    assert not (root / 'research.duckdb').exists()


@pytest.mark.parametrize('mutation', ['committed', 'receipt', 'reused', 'revision'])
def test_capture_rejects_import_journal(root, monkeypatch, mutation):
    guard(monkeypatch)
    result = acquire(root, capture_only=True)
    path = root / 'public_acquisition' / result['run_id'] / 'journal.json'
    journal = json.loads(path.read_bytes())
    item = journal['attempts'][0]
    if mutation == 'committed':
        item['status'] = journal['blocks'][0]['status'] = 'committed'
    elif mutation == 'receipt':
        item['store_attempt_id'] = 'a' * 32
    elif mutation == 'reused':
        item['reused'] = True
    else:
        item['diagnostics']['revision'] = {}
    path.write_bytes(canonical_json(journal))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, result['run_id'], _transport=forbidden)


def test_capture_obeys_store_lock(root):
    with EvidenceStore(root):
        before = sorted(p.relative_to(root).as_posix() for p in root.rglob('*'))
        with pytest.raises(Exception, match='data_directory_busy'):
            acquire(root, capture_only=True, _transport=forbidden)
        assert sorted(p.relative_to(root).as_posix() for p in root.rglob('*')) == before


@pytest.mark.parametrize('kind', ['symlink', 'hardlink', 'restore'])
def test_capture_rejects_unsafe_lock(root, tmp_path, kind):
    if kind == 'restore':
        (root / '.restore-incomplete').touch()
    else:
        target = tmp_path / 'target'
        target.write_text('sentinel')
        if kind == 'symlink':
            (root / '.operation.lock').symlink_to(target)
        else:
            os.link(target, root / '.operation.lock')
    with pytest.raises(Exception):
        acquire(root, capture_only=True, _transport=forbidden)


def test_capture_mixed_failure_exit(root, monkeypatch, capsys):
    guard(monkeypatch)
    calls = []
    def transport(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise public_transport.PublicTransportError('transport_timeout')
        return response(*args, **kwargs)
    monkeypatch.setattr(public_transport, 'fetch', transport)
    args = ['--root', str(root), 'acquire-public', '--capture-only', '--source', 'tencent', '--symbol', '601577.SH', '--asset-type', 'stock', '--period', '1d', '--start', '2025-01-01', '--end', '2025-02-05']
    assert cli.main(args) == 2
    result = json.loads(capsys.readouterr().out)
    assert result['status'] == 'partial' and result['resume_allowed']


@pytest.mark.parametrize('mutation', ['mode_missing', 'mode_unknown', 'mode_type', 'extra', 'v1_mode'])
def test_capture_plan_is_immutable(root, monkeypatch, mutation):
    guard(monkeypatch)
    result = acquire(root, capture_only=True)
    path = root / 'public_acquisition' / result['run_id'] / 'plan.json'
    plan = json.loads(path.read_bytes())
    if mutation == 'mode_missing':
        del plan['execution_mode']
    elif mutation == 'mode_unknown':
        plan['execution_mode'] = 'import'
    elif mutation == 'mode_type':
        plan['execution_mode'] = True
    elif mutation == 'extra':
        plan['unexpected'] = True
    else:
        plan['version'] = 'public-market-plan-v1'
    del plan['plan_sha256']
    plan['plan_sha256'] = module._hash(canonical_json(plan))
    path.write_bytes(canonical_json(plan))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, result['run_id'], _transport=forbidden)


@pytest.mark.parametrize('status', [401, 403, 429])
def test_capture_source_block_survives_new_run(root, monkeypatch, status):
    guard(monkeypatch)
    def transport(*args, **kwargs):
        raise public_transport.PublicTransportError('transport_headers_invalid', status=status)
    result = acquire(root, capture_only=True, _transport=transport)
    assert result['status'] == 'blocked' and result['attempts_used'] == 1
    again = acquire(root, capture_only=True, _transport=forbidden)
    assert again['status'] == 'blocked' and again['attempts_used'] == 0


def test_capture_budget_reservation_before_send(root, monkeypatch):
    guard(monkeypatch)
    calls = []
    def transport(*args, **kwargs):
        calls.append(1)
        run = next(p for p in (root / 'public_acquisition').iterdir() if len(p.name) == 32)
        assert (run / 'attempts' / f'{len(calls):06d}' / 'reservation.json').is_file()
        assert json.loads((run / 'journal.json').read_bytes())['attempts'][-1]['status'] == 'requested'
        raise public_transport.PublicTransportError('transport_timeout')
    result = acquire(root, capture_only=True, _transport=transport)
    for _ in range(9):
        result = module.resume_public(root, result['run_id'], _transport=transport)
    assert len(calls) == result['attempts_used'] == 10
    result = module.resume_public(root, result['run_id'], _transport=forbidden)
    assert result['error_code'] == 'budget_exhausted'


def test_capture_holds_shared_lock_and_preserves_inode(root):
    from anatrading.store import StoreError
    def transport(*args, **kwargs):
        inode = (root / '.operation.lock').stat().st_ino
        with pytest.raises(StoreError, match='data_directory_busy'):
            EvidenceStore(root)
        with pytest.raises(StoreError, match='data_directory_busy'):
            acquire(root, capture_only=True, _transport=forbidden)
        assert (root / '.operation.lock').stat().st_ino == inode
        return response(*args, **kwargs)
    assert acquire(root, capture_only=True, _transport=transport)['status'] == 'captured'


def test_capture_resume_plan_changed_between_reads(root, monkeypatch):
    result = acquire(root, capture_only=True)
    original = module._read_plan
    count = []
    def changed(directory, run):
        plan = original(directory, run)
        count.append(1)
        if len(count) == 1:
            updated = module._plan(**plan['parameters'], run_id=run, reference='2026-10-12T00:00:00+00:00', capture_only=True)
            (directory.path / 'plan.json').write_bytes(canonical_json(updated))
        return plan
    monkeypatch.setattr(module, '_read_plan', changed)
    guard(monkeypatch)
    with pytest.raises(module.PublicAcquisitionError, match='plan_identity_mismatch'):
        module.resume_public(root, result['run_id'], _transport=forbidden)


def test_capture_root_swapped_before_send(root):
    moved = root.with_name('moved')
    def checkpoint(stage):
        if stage == 'attempt_requested':
            root.rename(moved)
            (root / 'public_acquisition' / 'sources').mkdir(parents=True)
    with pytest.raises(module.PublicAcquisitionError, match='unsafe_path'):
        acquire(root, capture_only=True, _transport=forbidden, _checkpoint=checkpoint)


def test_capture_lock_swapped_before_send(root):
    def checkpoint(stage):
        if stage == 'attempt_requested':
            (root / '.operation.lock').rename(root / '.original-lock')
            (root / '.operation.lock').touch()
    with pytest.raises(module.PublicAcquisitionError, match='unsafe_path'):
        acquire(root, capture_only=True, _transport=forbidden, _checkpoint=checkpoint)


@pytest.mark.parametrize('empty_first', [False, True])
def test_capture_mixed_empty_success(root, monkeypatch, empty_first):
    guard(monkeypatch)
    calls = []
    def transport(request, **kwargs):
        calls.append(1)
        result = response(request, **kwargs)
        if (len(calls) == 1) == empty_first:
            prefix, payload = result['body'].decode().split('=', 1)
            value = json.loads(payload)
            next(iter(value['data'].values()))['day'] = []
            result['body'] = (prefix + '=' + json.dumps(value)).encode()
        return result
    result = acquire(root, capture_only=True, end='2025-02-05', _transport=transport)
    assert result['status'] == 'captured'
    assert {b['status'] for b in result['blocks']} == {'captured', 'empty_result'}
    assert not result['resume_allowed']


def test_capture_cancel_after_record_retains_evidence(root, monkeypatch):
    guard(monkeypatch)
    cancelled = []
    def checkpoint(stage):
        if stage == 'capture_recorded':
            cancelled.append(True)
    result = acquire(root, capture_only=True, end='2025-02-05', _checkpoint=checkpoint, _cancelled=lambda: bool(cancelled))
    assert result['status'] == 'partial'
    assert [b['status'] for b in result['blocks']] == ['captured', 'cancelled']
    assert result['attempts_used'] == 1


@pytest.mark.parametrize('block', [None, [], 'invalid', 1])
def test_capture_malformed_block_is_safe_error(root, monkeypatch, block):
    guard(monkeypatch)
    result = acquire(root, capture_only=True)
    path = root / 'public_acquisition' / result['run_id'] / 'journal.json'
    journal = json.loads(path.read_bytes())
    journal['blocks'] = [block]
    path.write_bytes(canonical_json(journal))
    with pytest.raises(module.PublicAcquisitionError, match='corrupt_journal'):
        module.resume_public(root, result['run_id'], _transport=forbidden)


def test_capture_sources_swapped_before_send(root):
    def checkpoint(stage):
        if stage == 'attempt_requested':
            source = root / 'public_acquisition' / 'sources'
            source.rename(source.with_name('original-sources'))
            source.mkdir()
    with pytest.raises(module.PublicAcquisitionError, match='unsafe_path'):
        acquire(root, capture_only=True, _transport=forbidden, _checkpoint=checkpoint)
