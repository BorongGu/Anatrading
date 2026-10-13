"""Frozen P/R/I/A diagnostics matrix: synthetic streams and no socket calls."""
import errno
import hashlib
import io
import json
import socket
import ssl

import pytest

from anatrading import public_http_worker as worker, public_transport as transport
from anatrading import public_acquisition as acquisition
from test_public_transport import REQUEST, URL, response
from test_public_acquisition import acquire, response as market_response

PHASES = ('dns', 'connect', 'tls', 'http', 'read', 'unknown')


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No actual connection permitted')
    monkeypatch.setattr(worker.socket, 'create_connection', forbidden)
    monkeypatch.setattr(acquisition, '_SEND_INTERVAL', 0)


def raised(error):
    def fail(*args, **kwargs):
        raise error
    return fail


@pytest.mark.parametrize('error,phase,code', [
    (socket.gaierror('PRIVATE'), 'dns', 'transport_network_error'),
    (ConnectionRefusedError('PRIVATE'), 'connect', 'transport_network_error'),
    (PermissionError('PRIVATE'), 'unknown', 'transport_network_error'),
    (OSError('PRIVATE'), 'unknown', 'transport_network_error'),
    (OSError(errno.ENETUNREACH, 'PRIVATE'), 'unknown', 'transport_network_error'),
    (TimeoutError('PRIVATE'), 'unknown', 'transport_timeout'),
])
def test_p1_connect_narrow_boundary(monkeypatch, error, phase, code):
    monkeypatch.setattr(worker.socket, 'create_connection', raised(error))
    with pytest.raises(worker._TransportFailure) as caught:
        worker._request(REQUEST)
    assert caught.value.code == code
    assert getattr(caught.value, 'phase', 'unknown') == phase
    assert 'PRIVATE' not in json.dumps(caught.value.record())


class Connection:
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def sendall(self, wire): pass
    def makefile(self, *args, **kwargs): return io.BytesIO(response())


def setup_connection(monkeypatch, connection=None):
    connection = connection or Connection()
    monkeypatch.setattr(worker.socket, 'create_connection', lambda *a, **kw: connection)
    class Context:
        def wrap_socket(self, *args, **kwargs): return connection
    context = Context()
    monkeypatch.setattr(worker.ssl, 'create_default_context', lambda: context)
    return connection, context


@pytest.mark.parametrize('error,code', [(ssl.SSLCertVerificationError('PRIVATE'), 'transport_tls_invalid'),
    (ssl.SSLError('PRIVATE'), 'transport_tls_invalid'), (OSError('PRIVATE'), 'transport_network_error'),
    (TimeoutError('PRIVATE'), 'transport_timeout'), (socket.gaierror('PRIVATE'), 'transport_network_error')])
@pytest.mark.parametrize('stage,phase', [('wrap_socket', 'tls'), ('sendall', 'http'), ('makefile', 'http')])
def test_p2_p4_operation_boundaries(monkeypatch, error, code, stage, phase):
    connection, context = setup_connection(monkeypatch)
    monkeypatch.setattr(context if stage == 'wrap_socket' else connection, stage, raised(error))
    with pytest.raises(worker._TransportFailure) as caught:
        worker._request(REQUEST)
    assert caught.value.code == code
    assert caught.value.phase == phase


@pytest.mark.parametrize('stage', ['context', 'socket_exit', 'stream_close'])
def test_p3_close_never_inherits_phase(monkeypatch, stage):
    connection, context = setup_connection(monkeypatch)
    if stage == 'context':
        monkeypatch.setattr(worker.ssl, 'create_default_context', raised(OSError('PRIVATE')))
        # Initialization remains outside original request catch.
        with pytest.raises(OSError): worker._request(REQUEST)
        return
    if stage == 'socket_exit':
        monkeypatch.setattr(Connection, '__exit__', raised(OSError('PRIVATE')))
    else:
        class Stream(io.BytesIO):
            def __exit__(self, *args): raise OSError('PRIVATE')
        monkeypatch.setattr(connection, 'makefile', lambda *a, **kw: Stream(response()))
    with pytest.raises(worker._TransportFailure) as caught: worker._request(REQUEST)
    assert caught.value.code == 'transport_network_error'
    assert getattr(caught.value, 'phase', 'unknown') == 'unknown'


@pytest.mark.parametrize('error,code', [(OSError('PRIVATE'), 'transport_network_error'),
    (ssl.SSLError('PRIVATE'), 'transport_network_error'), (TimeoutError('PRIVATE'), 'transport_timeout'),
    (EOFError('PRIVATE'), 'transport_network_error')])
@pytest.mark.parametrize('stage,phase', [('status', 'http'), ('headers', 'http'), ('body', 'read')])
def test_p4_p5_read_faults_preserve_metadata(error, code, stage, phase):
    class Stream(io.BytesIO):
        def readline(self, size=-1):
            if stage == 'status' or stage == 'headers' and self.tell() > 0: raise error
            return super().readline(size)
        def read(self, size=-1): raise error
    with pytest.raises(worker._TransportFailure) as caught:
        worker._read_response(Stream(response()), URL)
    record = caught.value.record()
    assert record['code'] == code and record['phase'] == phase
    assert record.get('status') == (None if stage == 'status' else 200)
    assert record['byte_count'] == 0 and record['body_sha256'] == hashlib.sha256(b'').hexdigest()
    assert record['complete'] is False and 'PRIVATE' not in json.dumps(record)


@pytest.mark.parametrize('wire,code,count', [
    (response(b'abc')[:-1], 'transport_truncated', 2),
    (response(b'abc') + b'x', 'transport_framing_invalid', 3),
    (response(b'x\r\n', b'Transfer-Encoding: chunked\r\n', framing=False), 'transport_framing_invalid', 0),
    (response(b'1\r\naBAD\r\n', b'Transfer-Encoding: chunked\r\n', framing=False), 'transport_framing_invalid', 1),
    (response(b'1\r\na\r\n0\r\nBad Name: secret\r\n\r\n', b'Transfer-Encoding: chunked\r\n', framing=False), 'transport_headers_invalid', 1),
    (response(b'', framing=False).replace(b'\r\n\r\n', b'\r\nContent-Length: 1048577\r\n\r\n'), 'transport_body_too_large', 0),
    (response(b'captcha'), 'transport_restricted', 7),
])
def test_p5_p6_entity_phase(wire, code, count):
    with pytest.raises(worker._TransportFailure) as caught: worker._read_response(io.BytesIO(wire), URL)
    record = caught.value.record()
    assert (record['phase'], record['code'], record['byte_count']) == ('read', code, count)
    assert record['complete'] is (code == 'transport_restricted')


@pytest.mark.parametrize('status,code', [(500, 'transport_http_transient'), (302, 'transport_http_redirect'), (404, 'transport_http_status')])
def test_p6_http_classifications(status, code):
    with pytest.raises(worker._TransportFailure) as caught:
        worker._read_response(io.BytesIO(response(status=str(status).encode())), URL)
    assert caught.value.code == code and caught.value.phase == 'http' and caught.value.status == status


def test_p6_interim_and_success_shape():
    result = worker._read_response(io.BytesIO(b'HTTP/1.1 100 Continue\r\n\r\n' + response()), URL)
    assert 'phase' not in result and result['body'] == b'hello'
    with pytest.raises(worker._TransportFailure) as caught:
        worker._read_response(io.BytesIO(b'HTTP/1.1 100 Continue\r\nContent-Length: 0\r\n\r\n' + response()), URL)
    assert caught.value.phase == 'http' and caught.value.status == 100


@pytest.mark.parametrize('status', [401, 403, 429])
@pytest.mark.parametrize('header,code', [(b'Bad Name: PRIVATE\r\n', 'transport_headers_invalid'),
    (b'Content-Length: 5\r\n', 'transport_headers_invalid'),
    (b'Transfer-Encoding: chunked\r\n', 'transport_framing_invalid'),
    (b'Content-Encoding: gzip\r\n', 'transport_encoding_unsupported'), (None, 'transport_timeout')])
def test_r1_trusted_status_blocks_before_classification(tmp_path, status, header, code):
    raw = response(status=str(status).encode(), headers=header or b'')
    class Stream(io.BytesIO):
        def readline(self, size=-1):
            if header is None and self.tell() > 0: raise TimeoutError('PRIVATE')
            return super().readline(size)
    with pytest.raises(worker._TransportFailure) as caught: worker._read_response(Stream(raw), URL)
    record = caught.value.record()
    assert record['phase'] == 'http' and record['status'] == status and record['code'] == code
    def fail(*args, **kwargs): transport._decode_output(json.dumps({'error': record}), REQUEST)
    result = acquire(tmp_path / 'store', _transport=fail)
    assert result['status'] == 'blocked' and result['error_code'] == code and not result['resume_allowed']
    assert (tmp_path / 'store/public_acquisition/sources/tencent.json').exists()
    assert result['transport_diagnostics'][0]['phase'] == 'http'


@pytest.mark.parametrize('status', [401, 403, 429])
@pytest.mark.parametrize('fragment', ['"phase":"PRIVATE"', '"phase":null', '"phase":123',
    '"phase":"http","phase":"read"', '"phase":"http","secret":"PRIVATE"'])
def test_r2_invalid_ipc_does_not_salvage_status(tmp_path, status, fragment):
    payload = '{"error":{"code":"transport_timeout","status":' + str(status) + ',' + fragment + '}}'
    def fail(*a, **kw): transport._decode_output(payload, REQUEST)
    result = acquire(tmp_path / 'store', _transport=fail)
    assert result['status'] == 'failed_terminal' and not result['resume_allowed']
    assert result['error_code'] == 'transport_protocol_invalid'
    assert result['transport_diagnostics'][0]['phase'] == 'unknown'
    assert not list((tmp_path / 'store/public_acquisition/sources').iterdir())
    assert 'PRIVATE' not in json.dumps(result)


@pytest.mark.parametrize('phase', PHASES)
def test_i1_valid_roundtrip(phase):
    with pytest.raises(transport.PublicTransportError) as caught:
        transport._decode_output(json.dumps({'error': worker._TransportFailure('transport_timeout', phase=phase).record()}), REQUEST)
    assert caught.value.phase == phase and str(caught.value) == 'transport_timeout'


@pytest.mark.parametrize('phase', [True, [], {}, 'x'*10000, None, 3])
def test_i2_phase_strict_type(phase):
    with pytest.raises(transport.PublicTransportError) as caught:
        transport._decode_output(json.dumps({'error': dict(code='transport_timeout', phase=phase, status=403)}), REQUEST)
    assert caught.value.__dict__ == {'code': 'transport_protocol_invalid'}


def test_i1_old_missing_attribute():
    with pytest.raises(transport.PublicTransportError) as caught:
        transport._decode_output('{"error":{"code":"transport_timeout"}}', REQUEST)
    assert caught.value.__dict__ == {'code': 'transport_timeout'}


@pytest.mark.parametrize('phase', ['PRIVATE', [], {}, 5, True])
def test_a1_local_invalid_phase_is_safe(tmp_path, phase):
    error = transport.PublicTransportError('transport_timeout', phase=phase, status=403)
    assert error.phase == 'unknown'
    # Also defend against subsequently mutated injected local exceptions.
    error.phase = phase
    result = acquire(tmp_path / 'store', _transport=raised(error))
    diagnostic = result['transport_diagnostics']
    assert diagnostic == [dict(run_id=result['run_id'], attempt_number=1,
        block_id=result['blocks'][0]['block_id'], code='transport_timeout', phase='unknown')]
    assert result['status'] == 'blocked'
    journal = json.loads((tmp_path / 'store/public_acquisition' / result['run_id'] / 'journal.json').read_bytes())
    assert set(journal['attempts'][0]['transport']) == {'status', 'byte_count', 'body_sha256', 'complete'}
    assert 'phase' not in json.dumps(journal)
    assert acquisition.resume_public(tmp_path / 'store', result['run_id'], _transport=raised(AssertionError()))['transport_diagnostics'] == []


def test_a2_independent_lists_resume_real_attempts_budget(tmp_path):
    root = tmp_path / 'store'
    failure = raised(transport.PublicTransportError('transport_timeout', phase='read'))
    result = acquire(root, _transport=failure)
    for number in range(1, 11):
        if number > 1: result = acquisition.resume_public(root, result['run_id'], _transport=failure)
        assert result['attempts_used'] == number
        assert len(result['transport_diagnostics']) == 1 <= 10
        assert result['transport_diagnostics'][0]['attempt_number'] == number
    result = acquisition.resume_public(root, result['run_id'], _transport=raised(AssertionError()))
    assert result['transport_diagnostics'] == [] and result['error_code'] == 'budget_exhausted'
    assert acquire(tmp_path / 'other')['transport_diagnostics'] == []


def test_a1_partial_failure_and_success_resume(tmp_path):
    calls = []
    def partial(request, **kwargs):
        calls.append(1)
        if len(calls) == 2: raise transport.PublicTransportError('transport_timeout')
        return market_response(request, **kwargs)
    root = tmp_path / 'store'
    result = acquire(root, end='2025-02-10', _transport=partial)
    assert result['status'] == 'partial'
    assert result['transport_diagnostics'] == [dict(run_id=result['run_id'], attempt_number=2,
        block_id=result['blocks'][1]['block_id'], code='transport_timeout', phase='unknown')]
    resumed = acquisition.resume_public(root, result['run_id'], _transport=market_response)
    assert resumed['status'] == 'committed' and resumed['transport_diagnostics'] == []
    assert acquisition.resume_public(root, result['run_id'], _transport=raised(AssertionError()))['transport_diagnostics'] == []


@pytest.mark.parametrize('payload', [
    '{"error":{"code":"transport_timeout"},"error":{"code":"transport_timeout"}}',
    '{"error":{"code":"transport_timeout","code":"transport_timeout"}}',
    '{"error":{"code":"transport_timeout","phase":NaN}}',
    'true', '[]', '{}',
])
def test_i2_duplicate_and_nonfinite_protocol(payload):
    with pytest.raises(transport.PublicTransportError) as caught: transport._decode_output(payload, REQUEST)
    assert caught.value.__dict__ == {'code': 'transport_protocol_invalid'}


def test_i2_success_cannot_smuggle_phase():
    import base64
    result = worker._read_response(io.BytesIO(response()), URL)
    result['body_base64'] = base64.b64encode(result.pop('body')).decode()
    result['phase'] = 'PRIVATE'
    with pytest.raises(transport.PublicTransportError) as caught:
        transport._decode_output(json.dumps({'result': result}), REQUEST)
    assert caught.value.__dict__ == {'code': 'transport_protocol_invalid'}


@pytest.mark.parametrize('phase', [None, 'PRIVATE', [], {}, True])
def test_worker_record_never_emits_invalid_phase(phase):
    assert worker._TransportFailure('transport_timeout', phase=phase, secret='PRIVATE').record() == {'code': 'transport_timeout'}


@pytest.mark.parametrize('program,code', [
    ('import sys;sys.exit(1)', 'transport_worker_failed'),
    ('print(\'{"error":\')', 'transport_protocol_invalid'),
    ('import sys;sys.stdout.write("x"*(2*1024*1024+1))', 'transport_ipc_too_large'),
    ('import sys;sys.stderr.write("x"*4097)', 'transport_ipc_too_large'),
    ('import time;time.sleep(60)', 'transport_timeout'),
])
def test_i3_parent_failures_unknown_and_reaped(tmp_path, monkeypatch, program, code):
    from test_public_transport import script, track_children, fetch_after
    script(tmp_path, monkeypatch, program)
    children = track_children(monkeypatch)
    with pytest.raises(transport.PublicTransportError) as caught: fetch_after(.3)
    assert caught.value.code == code and getattr(caught.value, 'phase', 'unknown') == 'unknown'
    assert all(child.poll() is not None for child, _, _ in children)


def test_i3_spawn_pipe_and_cancel_unknown(monkeypatch):
    import queue
    import threading
    import time
    monkeypatch.setattr(transport.subprocess, 'Popen', raised(OSError('PRIVATE')))
    for deadline, cancelled, code in [(time.monotonic()-1, lambda: False, 'transport_timeout'),
        (time.monotonic()+3, lambda: True, 'transport_cancelled'),
        (time.monotonic()+3, lambda: False, 'transport_spawn_failed')]:
        with pytest.raises(transport.PublicTransportError) as caught:
            transport.fetch(REQUEST, deadline=deadline, cancelled=cancelled)
        assert caught.value.__dict__ == {'code': code}
    class Stream:
        def fileno(self): raise OSError('PRIVATE')
    messages = queue.Queue()
    transport._read_pipe(Stream(), 'stdout', 100, messages, threading.Event())
    assert messages.get() == ('error', 'transport_protocol_invalid')
