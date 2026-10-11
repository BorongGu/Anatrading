"""Synthetic, network-free crash and admission tests for public acquisition."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from anatrading import public_acquisition as module
from anatrading.store import EvidenceStore


NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)


def response(request, *, deadline, cancelled):
    source, _, start, end, count, _ = request['parameters']['param'].split(',')
    row = [start, '10', '10.5', '11', '9', '123.45', {}, '0', '12.345', '0', '0']
    body = (request['parameters']['_var'] + '=' + json.dumps(
        {'code': 0, 'msg': '', 'data': {source: {'day': [row]}}}, separators=(',', ':'))).encode()
    return dict(status=200, response_url=request['url'],
                response_headers=[['Content-Type', 'text/html; charset=UTF-8']], body=body,
                byte_count=len(body), body_sha256=hashlib.sha256(body).hexdigest(), complete=True)


def acquire(root, **kwargs):
    defaults = dict(source='tencent', symbol='601577.SH', asset_type='stock', period='1d',
                    start='2025-01-01', end='2025-01-03', _transport=response, _now=NOW)
    defaults.update(kwargs)
    return module.acquire_public(root, **defaults)


@pytest.fixture(autouse=True)
def no_wait(monkeypatch):
    monkeypatch.setattr(module, '_SEND_INTERVAL', 0)


@pytest.mark.parametrize('changes', [
    {'asset_type': None}, {'asset_type': 'index'}, {'symbol': '601577'},
    {'symbol': '601577.BJ'}, {'source': 'other'}, {'period': '1m'},
    {'count': 64}, {'start': '2025-1-1'}, {'end': '2999-01-01'},
    {'start': '2025-01-04'}, {'start': '2020-01-01'},
])
def test_invalid_plan_never_creates_root_or_sends(tmp_path, changes):
    root = tmp_path / 'unused'
    with pytest.raises(module.PublicAcquisitionError):
        acquire(root, **changes)
    assert not root.exists()


def test_basic_commit_and_resume_do_not_resend(tmp_path):
    root = tmp_path / 'root'
    result = acquire(root)
    assert result['status'] == 'committed' and result['coverage'] == 'unverified'
    assert result['attempts_used'] == 1
    sid = result['blocks'][0]['snapshot_id']
    def forbidden(*args, **kwargs):
        raise AssertionError('resume re-sent a committed block')
    resumed = module.resume_public(root, result['run_id'], _transport=forbidden)
    assert resumed['status'] == 'committed' and resumed['attempts_used'] == 1
    assert resumed['blocks'][0]['snapshot_id'] == sid
    with EvidenceStore(root) as store:
        query = store.query(sid)
        assert query['rows'][0]['tokens']['volume'] == '123.45'
        assert query['rows'][0]['values']['volume'] is None


class Crash(BaseException):
    pass


@pytest.mark.parametrize('stage', ['reservation_published', 'attempt_requested', 'capture_temporary',
                                   'capture_published', 'capture_recorded', 'store_commit_verified'])
def test_crash_recovery_keeps_budget_and_adopts_capture(tmp_path, stage):
    root = tmp_path / 'root'
    def stop(point):
        if point == stage:
            raise Crash
    with pytest.raises(Crash):
        acquire(root, _checkpoint=stop)
    run = next(p.name for p in (root / 'public_acquisition').iterdir() if len(p.name) == 32)
    calls = []
    def tracked(*args, **kwargs):
        calls.append(1)
        return response(*args, **kwargs)
    result = module.resume_public(root, run, _transport=tracked)
    assert result['status'] == 'committed'
    before_capture = stage in {'reservation_published', 'attempt_requested'}
    assert len(calls) == int(before_capture)
    assert result['attempts_used'] == 1 + int(before_capture)


def test_symlink_root_is_rejected_before_store_or_transport(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'link'
    root.symlink_to(outside, target_is_directory=True)
    with pytest.raises(module.PublicAcquisitionError, match='unsafe_path'):
        acquire(root)
    assert list(outside.iterdir()) == []


def test_corrupt_or_missing_reservation_stops_resume(tmp_path):
    root = tmp_path / 'root'
    result = acquire(root)
    reservation = root / 'public_acquisition' / result['run_id'] / 'attempts' / '000001' / 'reservation.json'
    reservation.unlink()
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, result['run_id'], _transport=response)


def test_duplicate_journal_keys_are_not_accepted(tmp_path):
    root = tmp_path / 'root'
    result = acquire(root)
    path = root / 'public_acquisition' / result['run_id'] / 'journal.json'
    path.write_bytes(b'{"version":1,"version":1}')
    with pytest.raises(module.PublicAcquisitionError, match='corrupt_journal'):
        module.resume_public(root, result['run_id'], _transport=response)


def test_empty_capture_is_retained_without_snapshot(tmp_path):
    def empty(request, **kwargs):
        result = response(request, **kwargs)
        source = request['parameters']['param'].split(',')[0]
        result['body'] = (request['parameters']['_var'] + '=' + json.dumps(
            {'code': 0, 'msg': '', 'data': {source: {'day': []}}}, separators=(',', ':'))).encode()
        return result
    root = tmp_path / 'store'
    result = acquire(root, _transport=empty)
    assert result['status'] == 'empty_result' and result['resume_allowed'] is False
    capture = root / 'public_acquisition' / result['run_id'] / 'attempts' / '000001' / 'capture.json'
    assert capture.is_file()
    with EvidenceStore(root) as store:
        assert store.list_snapshots() == []
    assert module.resume_public(root, result['run_id'], _transport=response)['status'] == 'empty_result'


def test_later_block_failure_is_partial_and_resumes_only_pending_block(tmp_path):
    from anatrading.public_transport import PublicTransportError
    root = tmp_path / 'store'
    calls = []
    def second_fails(request, **kwargs):
        calls.append(request)
        if len(calls) == 2:
            raise PublicTransportError('transport_timeout')
        return response(request, **kwargs)
    first = acquire(root, end='2025-02-10', _transport=second_fails)
    assert first['status'] == 'partial' and first['resume_allowed'] is True
    assert first['attempts_used'] == 2 and first['blocks'][0]['snapshot_id']
    def retry(request, **kwargs):
        assert request == calls[1]
        return response(request, **kwargs)
    finished = module.resume_public(root, first['run_id'], _transport=retry)
    assert finished['status'] == 'committed' and finished['attempts_used'] == 3
    assert finished['blocks'][0]['snapshot_id'] == first['blocks'][0]['snapshot_id']


@pytest.mark.parametrize('changed,expected', [('price', 1), ('quantity', 1), ('qt', 0)])
def test_new_observation_records_exact_market_or_ancillary_revision(tmp_path, changed, expected):
    root = tmp_path / 'store'
    first = acquire(root)
    def revised(request, **kwargs):
        result = response(request, **kwargs)
        prefix, raw = result['body'].split(b'=', 1)
        payload = json.loads(raw)
        source = request['parameters']['param'].split(',')[0]
        if changed == 'price':
            payload['data'][source]['day'][0][2] = '10.500000000000000001'
        elif changed == 'quantity':
            payload['data'][source]['day'][0][5] = '123.450000000000000001'
        else:
            payload['data'][source]['qt'] = {'uninterpreted': 'changed'}
        result['body'] = prefix + b'=' + json.dumps(payload, separators=(',', ':')).encode()
        return result
    second = acquire(root, _transport=revised)
    assert second['status'] == 'committed'
    assert first['blocks'][0]['snapshot_id'] != second['blocks'][0]['snapshot_id']
    revision = second['blocks'][0]['diagnostics']['revision']
    assert revision['previous_snapshot_id'] == first['blocks'][0]['snapshot_id']
    assert revision['changed_market_rows'] == expected
    assert revision['body_changed_without_market_rows'] is (changed == 'qt')
    assert module.resume_public(root, second['run_id'], _transport=response)['blocks'][0]['diagnostics'] == second['blocks'][0]['diagnostics']


def test_sina_future_label_is_frozen_log_diagnostic_only(tmp_path):
    def minute(request, **kwargs):
        body = ("/*<script>location.href='//sina.com';</script>*/\n=(" + json.dumps([
            dict(day='2026-10-12 09:31:00', open='10', high='11', low='9', close='10', volume='12.3', amount='100')
        ], separators=(',', ':')) + ');').encode('gbk')
        return dict(status=200, response_url=request['url'],
                    response_headers=[['Content-Type', 'application/javascript; charset=GBK']], body=body)
    root = tmp_path / 'store'
    result = module.acquire_public(root, source='sina', symbol='601577.SH', asset_type='stock', period='1m',
                                   _transport=minute, _now=NOW)
    assert result['status'] == 'committed'
    assert result['blocks'][0]['diagnostics']['future_label_count'] == 1
    resumed = module.resume_public(root, result['run_id'], _transport=minute)
    assert resumed['blocks'][0]['diagnostics'] == result['blocks'][0]['diagnostics']
    with EvidenceStore(root) as store:
        query = store.query(result['blocks'][0]['snapshot_id'])
        assert query['metadata']['acquisition_clock'] == 'unavailable'
        assert query['metadata']['response_identity'] == 'absent'


def test_failed_transport_logs_only_bounded_metadata(tmp_path):
    from anatrading.public_transport import PublicTransportError
    def failure(*args, **kwargs):
        raise PublicTransportError('transport_truncated', status=200, byte_count=17,
                                   body_sha256='a'*64, complete=False)
    root = tmp_path / 'store'
    result = acquire(root, _transport=failure)
    journal = json.loads((root / 'public_acquisition' / result['run_id'] / 'journal.json').read_bytes())
    assert journal['attempts'][0]['transport'] == dict(status=200, byte_count=17, body_sha256='a'*64, complete=False)
    assert not list((root / 'public_acquisition' / result['run_id']).rglob('capture.json'))


def test_missing_root_resume_does_not_create_empty_store(tmp_path):
    root = tmp_path / 'missing'
    with pytest.raises(module.PublicAcquisitionError):
        module.resume_public(root, 'a'*32, _transport=response)
    assert not root.exists()


@pytest.mark.parametrize('stage', ['source_block_temporary', 'source_block_published'])
def test_durable_source_restriction_survives_journal_ack_loss(tmp_path, stage):
    from anatrading.public_transport import PublicTransportError
    root = tmp_path / 'store'
    def restricted(*args, **kwargs):
        raise PublicTransportError('transport_http_blocked', status=429, retry_after=1000000)
    def stop(point):
        if point == stage:
            raise Crash
    with pytest.raises(Crash):
        acquire(root, _transport=restricted, _checkpoint=stop)
    def forbidden(*args, **kwargs):
        raise AssertionError('durable restriction was bypassed after crash')
    result = acquire(root, _transport=forbidden)
    assert result['status'] == 'blocked' and result['attempts_used'] == 0


@pytest.mark.parametrize('stage', ['capture_temporary', 'capture_published'])
def test_legacy_capture_cannot_replace_network_capture_on_resume(tmp_path, stage):
    from test_public_market_legacy import legacy_capture
    root = tmp_path / 'store'
    def stop(point):
        if point == stage:
            raise Crash
    with pytest.raises(Crash):
        acquire(root, _checkpoint=stop)
    run = next(p for p in (root / 'public_acquisition').iterdir() if len(p.name) == 32)
    slot = run / 'attempts' / '000001'
    capture = next(p for p in slot.iterdir() if 'capture.json' in p.name)
    capture.write_bytes(legacy_capture(capture.read_bytes()))
    def forbidden(*args, **kwargs):
        raise AssertionError('legacy capture caused another network request')
    with pytest.raises(module.PublicAcquisitionError, match='legacy_capture_not_network_evidence'):
        module.resume_public(root, run.name, _transport=forbidden)
    assert capture.exists()
    with EvidenceStore(root) as store:
        assert store.list_snapshots() == []
