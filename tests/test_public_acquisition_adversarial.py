"""Independent offline recovery/budget tests; never contact a public vendor."""
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from anatrading import public_acquisition as module
from anatrading.public_market import build_request, canonical_json
from anatrading.public_transport import PublicTransportError
from anatrading.store import EvidenceStore
from test_public_acquisition import Crash, response
from test_public_market_formats import tx_capture


NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def remove_real_request_spacing(monkeypatch):
    monkeypatch.setattr(module, '_SEND_INTERVAL', 0)


def acquire(root, **kwargs):
    defaults = dict(source='tencent', symbol='601577.SH', asset_type='stock', period='1d',
                    start='2025-01-01', end='2025-01-03', _transport=response, _now=NOW)
    defaults.update(kwargs)
    return module.acquire_public(root, **defaults)


def transient(*args, **kwargs):
    raise PublicTransportError('transport_network_error')


def forbidden(*args, **kwargs):
    raise AssertionError('An invalid, committed or captured run must not send')


def run_dir(root, run_id=None):
    base = root / 'public_acquisition'
    if run_id is None:
        run_id = next(path.name for path in base.iterdir() if len(path.name) == 32)
    return base / run_id


def rewrite_journal(directory, change):
    path = directory / 'journal.json'
    value = json.loads(path.read_bytes())
    change(value)
    path.write_bytes(canonical_json(value))


@pytest.mark.parametrize('claimed', ['committed', 'empty_result', 'captured'])
def test_block_cannot_promote_failed_attempt_using_only_journal_status(tmp_path, claimed):
    root = tmp_path / 'root'
    result = acquire(root, _transport=transient)
    directory = run_dir(root, result['run_id'])
    rewrite_journal(directory, lambda j: j['blocks'][0].update(status=claimed))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, result['run_id'], _transport=forbidden)


def test_unverified_committed_block_cannot_drop_latest_attempt_pointer(tmp_path):
    root = tmp_path / 'root'
    result = acquire(root, _transport=transient)
    rewrite_journal(run_dir(root, result['run_id']),
                    lambda j: j['blocks'][0].update(status='committed', latest_attempt=None, error_code=None))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, result['run_id'], _transport=forbidden)


@pytest.mark.parametrize('bad', ['PRIVATE_MARKER\nHeader: SECRET', {'secret': 'PRIVATE_MARKER'}, 7, True])
def test_persisted_block_error_is_not_an_arbitrary_output_channel(tmp_path, bad):
    root = tmp_path / 'root'
    result = acquire(root, _transport=transient)
    rewrite_journal(run_dir(root, result['run_id']), lambda j: j['blocks'][0].update(error_code=bad))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, result['run_id'], _transport=forbidden)


def test_complete_foreign_temporary_capture_stops_instead_of_refetching(tmp_path):
    root = tmp_path / 'root'
    def stop(stage):
        if stage == 'capture_temporary':
            raise Crash
    with pytest.raises(Crash):
        acquire(root, _checkpoint=stop)
    directory = run_dir(root)
    temporary = next((directory / 'attempts' / '000001').glob('.capture.json.*.part'))
    # This is a complete, valid, canonical capture for another security, not
    # partial bytes left by an interrupted write.
    foreign = build_request('tencent', '600111.SH', '1d', start='2025-01-01', end='2025-01-03', count=64)
    temporary.write_bytes(tx_capture(request=foreign))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, directory.name, _transport=forbidden)


@pytest.mark.parametrize('status', [401, 403, 429])
@pytest.mark.parametrize('code', ['transport_headers_invalid', 'transport_encoding_unsupported'])
def test_explicit_source_restriction_survives_other_protocol_errors(tmp_path, status, code):
    root = tmp_path / 'root'
    def restricted(*args, **kwargs):
        raise PublicTransportError(code, status=status)
    result = acquire(root, _transport=restricted)
    assert result['status'] == 'blocked'
    assert result['resume_allowed'] is False
    assert (root / 'public_acquisition' / 'sources' / 'tencent.json').is_file()
    # A new run is also bound by the remembered source restriction.
    again = acquire(root, _transport=forbidden)
    assert again['status'] == 'blocked' and again['attempts_used'] == 0


def test_request_budget_is_cumulative_across_all_explicit_resumes(tmp_path):
    root = tmp_path / 'root'
    sends = []
    def failed(*args, **kwargs):
        sends.append(1)
        raise PublicTransportError('transport_timeout')
    result = acquire(root, _transport=failed)
    for expected in range(2, 11):
        result = module.resume_public(root, result['run_id'], _transport=failed)
        assert result['attempts_used'] == expected
        assert result['attempts_remaining'] == 10 - expected
    result = module.resume_public(root, result['run_id'], _transport=forbidden)
    assert result['status'] == 'failed_terminal' and result['error_code'] == 'budget_exhausted'
    assert result['attempts_used'] == len(sends) == 10
    assert result['resume_allowed'] is False
    assert len(list((run_dir(root, result['run_id']) / 'attempts').iterdir())) == 10


def test_captured_request_binding_cannot_be_replaced_by_valid_other_symbol(tmp_path):
    root = tmp_path / 'root'
    def stop(stage):
        if stage == 'capture_recorded':
            raise Crash
    with pytest.raises(Crash):
        acquire(root, _checkpoint=stop)
    directory = run_dir(root)
    foreign = build_request('tencent', '600111.SH', '1d', start='2025-01-01', end='2025-01-03', count=64)
    (directory / 'attempts' / '000001' / 'capture.json').write_bytes(tx_capture(request=foreign))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, directory.name, _transport=forbidden)


def test_source_raw_corruption_blocks_committed_resume_before_network(tmp_path):
    root = tmp_path / 'root'
    result = acquire(root)
    sha = result['blocks'][0]['raw_sha256']
    (root / 'raw' / sha[:2] / sha).write_bytes(b'corrupt')
    with pytest.raises(Exception, match='raw_object_corrupt'):
        module.resume_public(root, result['run_id'], _transport=forbidden)


def test_committed_ack_loss_reuses_one_snapshot_and_no_more_network(tmp_path):
    root = tmp_path / 'root'
    def stop(stage):
        if stage == 'store_commit_verified':
            raise Crash
    with pytest.raises(Crash):
        acquire(root, _checkpoint=stop)
    directory = run_dir(root)
    with EvidenceStore(root) as store:
        before = store.list_snapshots()
        assert len(before) == 1
    result = module.resume_public(root, directory.name, _transport=forbidden)
    assert result['status'] == 'committed' and result['attempts_used'] == 1
    with EvidenceStore(root) as store:
        assert store.list_snapshots() == before


def test_second_writer_fails_before_reservation_or_send(tmp_path):
    root = tmp_path / 'root'
    with EvidenceStore(root):
        with pytest.raises(Exception, match='data_directory_busy'):
            acquire(root, _transport=forbidden)
    assert not (root / 'public_acquisition').exists()


def test_resume_rejects_symlink_capture_even_when_target_has_valid_bytes(tmp_path):
    root = tmp_path / 'root'
    result = acquire(root)
    path = run_dir(root, result['run_id']) / 'attempts' / '000001' / 'capture.json'
    outside = tmp_path / 'outside.json'
    path.rename(outside)
    path.symlink_to(outside)
    with pytest.raises(module.PublicAcquisitionError, match='unsafe_path'):
        module.resume_public(root, result['run_id'], _transport=forbidden)


@pytest.mark.parametrize('stage', [
    'store.attempt_started', 'store.raw_published', 'store.transaction_open',
    'store.before_commit', 'store.after_commit',
])
def test_real_process_exit_across_store_commit_boundary_does_not_redownload(tmp_path, stage):
    """os._exit cannot be swallowed by the Store's exception recovery path."""
    import subprocess
    import sys
    root = tmp_path / 'root'
    tests = str(Path(__file__).resolve().parent)
    script = f'''
import os, sys
sys.path.insert(0, {tests!r})
from test_public_acquisition import acquire

def exit_at(actual):
    if actual == {stage!r}:
        os._exit(73)

acquire({str(root)!r}, _checkpoint=exit_at)
raise RuntimeError("crash checkpoint was not reached")
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, timeout=15)
    assert result.returncode == 73, result.stderr
    directory = run_dir(root)
    result = module.resume_public(root, directory.name, _transport=forbidden)
    assert result['status'] == 'committed'
    assert result['attempts_used'] == 1
    with EvidenceStore(root) as store:
        assert len(store.list_snapshots()) == 1
        query = store.query(result['blocks'][0]['snapshot_id'])
        assert len(query['rows']) == 1
        assert query['rows'][0]['tokens']['volume'] == '123.45'


def test_fsync_failure_prevents_all_network_sends(tmp_path, monkeypatch):
    def broken_sync(descriptor):
        raise OSError('simulated disk failure')
    monkeypatch.setattr(module.os, 'fsync', broken_sync)
    with pytest.raises(module.PublicAcquisitionError, match='durability_unavailable'):
        acquire(tmp_path / 'root', _transport=forbidden)


@pytest.mark.parametrize('damage', ['gap', 'journal_rewind', 'reservation_request', 'reservation_number'])
def test_reservation_history_cannot_reset_or_redirect_send_budget(tmp_path, damage):
    root = tmp_path / 'root'
    result = acquire(root, _transport=transient)
    directory = run_dir(root, result['run_id'])
    slot = directory / 'attempts' / '000001'
    if damage == 'gap':
        slot.rename(slot.with_name('000002'))
    elif damage == 'journal_rewind':
        rewrite_journal(directory, lambda j: j.update(attempts=[], blocks=[dict(
            block_id=j['blocks'][0]['block_id'], status='committed', error_code=None, latest_attempt=None)]))
    else:
        path = slot / 'reservation.json'
        value = json.loads(path.read_bytes())
        value['request_sha256' if damage == 'reservation_request' else 'attempt_number'] = ('0' * 64 if damage == 'reservation_request' else 0)
        path.write_bytes(canonical_json(value))
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, result['run_id'], _transport=forbidden)


@pytest.mark.parametrize('retry', [604800, 604801, 1000000, 999999999, '2050-01-01T00:00:00Z'])
def test_source_retry_metadata_written_by_transport_can_be_read_on_resume(tmp_path, retry):
    root = tmp_path / 'root'
    def restricted(*args, **kwargs):
        raise PublicTransportError('transport_http_blocked', status=429, retry_after=retry)
    first = acquire(root, _transport=restricted)
    assert first['status'] == 'blocked'
    again = module.resume_public(root, first['run_id'], _transport=forbidden)
    assert again['status'] == 'blocked' and again['attempts_used'] == 1
    assert again['resume_allowed'] is False


@pytest.mark.parametrize('stage,expected', [('capture_recorded', 'cancelled'),
                                            ('store.transaction_open', 'committed')])
def test_cancellation_respects_store_publication_boundary(tmp_path, stage, expected):
    root = tmp_path / 'root'
    requested = [False]
    def checkpoint(actual):
        if actual == stage:
            requested[0] = True
    result = acquire(root, _checkpoint=checkpoint, _cancelled=lambda: requested[0])
    assert result['status'] == expected
    assert result['attempts_used'] == 1
    again = module.resume_public(root, result['run_id'], _transport=forbidden)
    assert again['status'] == expected and again['attempts_used'] == 1
    with EvidenceStore(root) as store:
        assert len(store.list_snapshots()) == int(expected == 'committed')


def test_explicit_requested_view_preserves_full_source_and_query_identity(tmp_path):
    from test_public_market_formats import tx_row
    import base64
    def earlier_context(request, **kwargs):
        data = response(request, **kwargs)
        capture = tx_capture([tx_row('2024-12-31'), tx_row('2025-01-01'), tx_row('2025-01-03')],
                             request=request, symbol='sh601577')
        data['body'] = base64.b64decode(json.loads(capture)['body_base64'])
        return data
    root = tmp_path / 'root'
    result = acquire(root, _transport=earlier_context)
    block = result['blocks'][0]
    view = block['target_view']
    assert (view['view_start'], view['view_end'], view['retained_rows'], view['excluded_rows']) == ('2025-01-01', '2025-01-03', 2, 1)
    assert [row['ordinal'] for row in view['rows']] == [2, 3]
    with EvidenceStore(root) as store:
        query = store.query(block['snapshot_id'])
        assert len(query['rows']) == 3
        assert query['query_id'] == view['source_query_id']
        assert query['manifest']['raw_sha256'] == view['source_raw_sha256']
        assert [row['label'] for row in query['rows']] == ['2024-12-31', '2025-01-01', '2025-01-03']


@pytest.mark.parametrize('stage', ['capture_temporary', 'capture_published', 'capture_recorded', 'store_commit_verified'])
def test_legacy_reconstruction_cannot_enter_network_resume_path(tmp_path, stage):
    import hashlib
    from test_public_market_legacy import legacy_capture
    root = tmp_path / 'root'
    def stop(actual):
        if actual == stage:
            raise Crash
    with pytest.raises(Crash):
        acquire(root, _checkpoint=stop)
    directory = run_dir(root)
    slot = directory / 'attempts' / '000001'
    path = next(slot.glob('.capture.json.*.part')) if stage == 'capture_temporary' else slot / 'capture.json'
    replacement = legacy_capture(path.read_bytes())
    path.write_bytes(replacement)
    # Even consistently recomputed local capture hashes do not make a legacy
    # reconstruction into an observed network response.
    if stage in {'capture_recorded', 'store_commit_verified'}:
        rewrite_journal(directory, lambda j: j['attempts'][0].update(capture_sha256=hashlib.sha256(replacement).hexdigest()))
    with pytest.raises(module.PublicAcquisitionError, match='legacy_capture_not_network_evidence'):
        module.resume_public(root, directory.name, _transport=forbidden)
    with EvidenceStore(root) as store:
        snapshots = store.list_snapshots()
        assert len(snapshots) == int(stage == 'store_commit_verified')
        for snapshot in snapshots:
            assert 'provenance' not in store.query(snapshot['snapshot_id'])['metadata']


def test_network_binding_explicitly_rejects_valid_legacy_for_same_request(tmp_path):
    from test_public_market_legacy import legacy_capture
    plan = module._plan('tencent', '601577.SH', 'stock', '1d', '2025-01-01', '2025-01-03', reference=NOW.isoformat())
    block = plan['blocks'][0]
    strict = tx_capture(request=block['request'], symbol='sh601577')
    with pytest.raises(module.PublicAcquisitionError, match='legacy_capture_not_network_evidence'):
        module._binding(legacy_capture(strict), block)
