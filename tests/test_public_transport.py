"""Synthetic HTTP and real isolated-process fault injection; no public network."""
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from anatrading import public_http_worker as worker
from anatrading import public_transport as transport


URL = "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?_var=kline_day2024&param=sh600111%2Cday%2C2024-01-01%2C2024-01-02%2C64%2C&r=0.8205512681390605"
REQUEST = {"method": "GET", "url": URL, "parameters": {"_var": "kline_day2024", "param": "sh600111,day,2024-01-01,2024-01-02,64,", "r": "0.8205512681390605"}, "headers": {"Accept": "*/*", "Accept-Encoding": "identity"}}


def response(body=b"hello", headers=b"", *, status=b"200 OK", framing=True):
    length = b"Content-Length: " + str(len(body)).encode() + b"\r\n" if framing else b""
    return b"HTTP/1.1 " + status + b"\r\nContent-Type: text/html; charset=UTF-8\r\n" + length + headers + b"\r\n" + body


def parse(raw):
    return worker._read_response(io.BytesIO(raw), URL)


def script(tmp_path, monkeypatch, code):
    path = tmp_path / "injected_worker.py"
    path.write_text(code, encoding="utf-8")
    monkeypatch.setattr(transport, "_WORKER_SCRIPT", path)
    return path


def track_children(monkeypatch):
    children = []
    actual = subprocess.Popen
    def start(*args, **kwargs):
        proc = actual(*args, **kwargs)
        children.append((proc, args, kwargs))
        return proc
    monkeypatch.setattr(transport.subprocess, "Popen", start)
    return children


def fetch_after(seconds=.4, *, cancelled=lambda: False):
    return transport.fetch(REQUEST, deadline=time.monotonic() + seconds, cancelled=cancelled)


def test_complete_entity_exact_bytes_and_only_capture_headers():
    result = parse(response(b"\x00\xffraw", b"X-Secret: never-return\r\nSet-Cookie: secret\r\n"))
    assert result == {"status": 200, "response_url": URL,
                      "response_headers": [["content-type", "text/html; charset=UTF-8"]],
                      "body": b"\x00\xffraw", "byte_count": 5,
                      "body_sha256": hashlib.sha256(b"\x00\xffraw").hexdigest(), "complete": True}


@pytest.mark.parametrize(("header", "code"), [
    (b"Content-Type: application/json\r\n", "transport_headers_invalid"),
    (b"Content-Encoding: identity\r\nContent-Encoding: identity\r\n", "transport_headers_invalid"),
    (b"Content-Length: 5\r\n", "transport_headers_invalid"),
    (b"Transfer-Encoding: chunked\r\n", "transport_framing_invalid"),
    (b"Content-Encoding: gzip\r\n", "transport_encoding_unsupported"),
    (b"Content-Encoding: identity, identity\r\n", "transport_encoding_unsupported"),
    (b"Bad Name: x\r\n", "transport_headers_invalid"),
    (b" X-Folded: x\r\n", "transport_headers_invalid"),
    (b"X-Test: bad\x00value\r\n", "transport_headers_invalid"),
])
def test_ambiguous_or_unsafe_headers_rejected(header, code):
    with pytest.raises(worker._TransportFailure) as caught:
        parse(response(headers=header))
    assert caught.value.code == code


@pytest.mark.parametrize("transfer", [b"gzip", b"gzip, chunked", b"chunked, chunked", b"identity", b"chunked\r\nTransfer-Encoding: chunked"])
def test_transfer_codings_are_strict(transfer):
    with pytest.raises(worker._TransportFailure):
        parse(response(b"0\r\n\r\n", b"Transfer-Encoding: " + transfer + b"\r\n", framing=False))


def test_chunked_exact_entity_and_bounded_trailers():
    result = parse(response(b"2\r\nhe\r\n3\r\nllo\r\n0\r\nX-Trace: safe\r\n\r\n", b"Transfer-Encoding: chunked\r\n", framing=False))
    assert result["body"] == b"hello" and result["complete"] is True


@pytest.mark.parametrize("body", [b"5\r\nhel", b"5\r\nhello\r\n", b"5\r\nhello\r\n0\r\n", b"5\r\nhello\r\n0\r\nX-T: x\r\n"])
def test_chunked_truncation_is_never_complete(body):
    with pytest.raises(worker._TransportFailure) as caught:
        parse(response(body, b"Transfer-Encoding: chunked\r\n", framing=False))
    assert caught.value.code == "transport_truncated"
    assert caught.value.complete is False


@pytest.mark.parametrize("body", [b"5\r\nhelloXX0\r\n\r\n", b"+5\r\nhello\r\n0\r\n\r\n", b"0\r\nContent-Type: evil\r\n\r\n", b"0\r\n\r\njunk"])
def test_malformed_chunk_framing_rejected(body):
    with pytest.raises(worker._TransportFailure):
        parse(response(body, b"Transfer-Encoding: chunked\r\n", framing=False))


def test_truncation_safe_partial_hash_and_extra_length_rejected():
    with pytest.raises(worker._TransportFailure) as caught:
        parse(response(b"hello")[:-2])
    err = caught.value
    assert (err.code, err.byte_count, err.complete) == ("transport_truncated", 3, False)
    assert err.body_sha256 == hashlib.sha256(b"hel").hexdigest()
    with pytest.raises(worker._TransportFailure, match="transport_framing_invalid"):
        parse(response(b"hello") + b"extra")


def test_entity_limit_before_large_allocation():
    limit = worker.MAX_BODY_BYTES
    assert len(parse(response(b"x" * limit))["body"]) == limit
    for raw in (response(b"x" * (limit + 1)), response(b"x" * (limit + 1), framing=False),
                response(b"100001\r\n", b"Transfer-Encoding: chunked\r\n", framing=False)):
        with pytest.raises(worker._TransportFailure, match="transport_body_too_large"):
            parse(raw)


def test_cumulative_headers_interim_chunk_overhead_and_trailers_bounded():
    for raw in (
        response(headers=b"X: " + b"x" * 65536 + b"\r\n"),
        response(headers=b"X: x\r\n" * 99),
        b"HTTP/1.1 100 Continue\r\nX: x\r\n\r\n" * 100 + response(),
        response((b"1\r\nx\r\n" * 17000) + b"0\r\n\r\n", b"Transfer-Encoding: chunked\r\n", framing=False),
        response(b"0\r\n" + b"X: x\r\n" * 100 + b"\r\n", b"Transfer-Encoding: chunked\r\n", framing=False),
    ):
        with pytest.raises(worker._TransportFailure, match="transport_headers_too_large"):
            parse(raw)


def test_interim_response_counts_and_final_metadata_only():
    result = parse(b"HTTP/1.1 100 Continue\r\nX-Interim: not-returned\r\n\r\n" + response())
    assert result["body"] == b"hello"


@pytest.mark.parametrize(("status", "code"), [(301,"transport_http_redirect"),(302,"transport_http_redirect"),(401,"transport_http_blocked"),(403,"transport_http_blocked"),(429,"transport_http_blocked"),(500,"transport_http_transient"),(503,"transport_http_transient"),(404,"transport_http_status")])
def test_failure_status_only_safe_fields(status, code):
    with pytest.raises(worker._TransportFailure) as caught:
        parse(response(b"private failure body", b"Retry-After: 120\r\nX-Secret: private\r\n", status=str(status).encode()+b" Secret reason"))
    err = caught.value
    assert (err.code, err.status) == (code, status)
    assert "private" not in str(err) and "Secret" not in str(err)
    if status == 429:
        assert err.retry_after == 120


@pytest.mark.parametrize(("value", "expected"), [("0", 0), ("3600", 3600), ("-1", None), ("9"*100, None), ("private", None), ("Wed, 21 Oct 2015 07:28:00 GMT", "2015-10-21T07:28:00Z")])
def test_retry_after_normalized(value, expected):
    assert worker._retry_after(value) == expected


@pytest.mark.parametrize("body", [b"<html>CAPTCHA required</html>", b"Access denied", "访问过于频繁".encode("gbk")])
def test_recognizable_restriction_is_blocked_without_body_disclosure(body):
    with pytest.raises(worker._TransportFailure, match="transport_restricted") as caught:
        parse(response(body))
    assert caught.value.complete is True and caught.value.byte_count == len(body)
    assert "body" not in caught.value.__dict__


@pytest.mark.parametrize("key,value", [("method", "POST"), ("url", "http://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get"), ("url", URL.replace("proxy.finance.qq.com", "proxy.finance.qq.com:443")), ("url", URL.replace("proxy.finance.qq.com", "x@proxy.finance.qq.com")), ("url", URL+"#x"), ("url", URL.replace("proxy.finance.qq.com", "evil.example")), ("url", URL.replace("/newfqkline/get", "/different")), ("headers", {"Accept":"*/*", "Accept-Encoding":"identity", "Authorization":"secret"})])
def test_fixed_worker_request_boundary(key, value):
    with pytest.raises(worker._TransportFailure, match="transport_request_invalid"):
        worker._validate_request({**REQUEST, key: value})


def test_proxy_credentials_environment_and_fd_not_inherited(tmp_path, monkeypatch):
    for name in ("HTTPS_PROXY", "ALL_PROXY", "HOME", "PATH", "SSL_CERT_FILE", "SECRET_TOKEN", "PYTHONPATH"):
        monkeypatch.setenv(name, "private-marker")
    script(tmp_path, monkeypatch, "import os,sys,json\nassert not set(os.environ) - {'SystemRoot', 'LC_CTYPE'}\nassert sys.flags.isolated and sys.flags.no_site\nprint(json.dumps({'error': {'code': 'transport_network_error'}}))\n")
    children = track_children(monkeypatch)
    with pytest.raises(transport.PublicTransportError, match="transport_network_error"):
        fetch_after(3)
    child, args, kwargs = children[0]
    assert child.poll() is not None and kwargs["close_fds"] is True
    assert kwargs["env"] == ({"SystemRoot": os.environ["SystemRoot"]} if os.name == "nt" else {})
    assert Path(args[0][0]).is_absolute() and "-I" in args[0] and "-S" in args[0]


@pytest.mark.parametrize("kind", ["dns", "tls", "headers", "slow_output", "slow_body"])
def test_absolute_deadline_reaps_real_subprocess_even_when_bytes_arrive(tmp_path, monkeypatch, kind):
    prefix = f"import importlib.util,time,socket,sys,io\nspec=importlib.util.spec_from_file_location('w', {str(Path(worker.__file__).resolve())!r})\nw=importlib.util.module_from_spec(spec);spec.loader.exec_module(w)\n"
    if kind == "dns":
        code = prefix + "socket.create_connection=lambda *a,**k: time.sleep(60)\nw.main()\n"
    elif kind == "tls":
        code = prefix + "class C:\n def __enter__(self): return self\n def __exit__(self,*a): pass\nsocket.create_connection=lambda *a,**k:C()\nw.ssl.create_default_context=lambda: type('TLS',(),{'wrap_socket':lambda *a,**k:time.sleep(60)})()\nw.main()\n"
    elif kind == "headers":
        code = prefix + "class Slow:\n def readline(self,*a): time.sleep(60)\nw._read_response(Slow(), 'https://unused')\n"
    elif kind == "slow_body":
        code = prefix + "class Slow(io.BytesIO):\n def read(self,n=-1): time.sleep(.08); return b'x'\nw._read_response(Slow(b'HTTP/1.1 200 OK\\r\\nContent-Type: text/html; charset=UTF-8\\r\\n\\r\\n'), 'https://unused')\n"
    else:
        code = "import sys,time\nwhile True:\n sys.stdout.write('x');sys.stdout.flush();time.sleep(.04)\n"
    script(tmp_path, monkeypatch, code)
    children = track_children(monkeypatch)
    started = time.monotonic()
    with pytest.raises(transport.PublicTransportError, match="transport_timeout"):
        fetch_after(.35)
    assert time.monotonic() - started < 2.35
    assert children and all(proc.poll() is not None for proc, _, _ in children)


@pytest.mark.parametrize(("stream", "count"), [("stdout", 2*1024*1024+1), ("stderr", 4097)])
def test_cumulative_ipc_limit_kills_before_worker_exits(tmp_path, monkeypatch, stream, count):
    script(tmp_path, monkeypatch, f"import sys,time\nsys.{stream}.buffer.write(b'x'*{count});sys.{stream}.flush();time.sleep(60)\n")
    children = track_children(monkeypatch)
    with pytest.raises(transport.PublicTransportError, match="transport_ipc_too_large"):
        fetch_after(3)
    assert children[0][0].poll() is not None


def test_cancel_before_spawn_and_during_read(tmp_path, monkeypatch):
    children = track_children(monkeypatch)
    with pytest.raises(transport.PublicTransportError, match="transport_cancelled"):
        fetch_after(3, cancelled=lambda: True)
    assert children == []
    script(tmp_path, monkeypatch, "import time\ntime.sleep(60)\n")
    start = time.monotonic()
    with pytest.raises(transport.PublicTransportError, match="transport_cancelled"):
        fetch_after(3, cancelled=lambda: time.monotonic()-start > .2)
    assert children[0][0].poll() is not None


def test_parent_verifies_success_protocol_and_body_hash(tmp_path, monkeypatch):
    result = parse(response())
    result["body_base64"] = base64.b64encode(result.pop("body")).decode("ascii")
    script(tmp_path, monkeypatch, f"print({json.dumps({'result': result})!r})\n")
    assert fetch_after(3)["body"] == b"hello"
    result["body_sha256"] = "0"*64
    script(tmp_path, monkeypatch, f"print({json.dumps({'result': result})!r})\n")
    with pytest.raises(transport.PublicTransportError, match="transport_protocol_invalid"):
        fetch_after(3)


def test_worker_does_not_import_store_or_optional_dependencies():
    source = Path(worker.__file__).read_text()
    assert "from anatrading" not in source and "import anatrading" not in source
    assert "import urllib.request" not in source and "import requests" not in source


def test_chunk_extensions_are_validated_but_not_part_of_entity():
    wire = b'2;name=value;quoted="safe\\\" value"\r\nhe\r\n3;flag\r\nllo\r\n0;done=yes\r\n\r\n'
    assert parse(response(wire, b"Transfer-Encoding: chunked\r\n", framing=False))["body"] == b"hello"
    for extension in (b";", b";name=", b';name="unterminated', b";bad name=x", b";name=bad\x00"):
        with pytest.raises(worker._TransportFailure, match="transport_framing_invalid"):
            parse(response(b"0" + extension + b"\r\n\r\n", b"Transfer-Encoding: chunked\r\n", framing=False))


def test_tls_default_verification_hostname_and_fixed_wire_request(monkeypatch):
    import ssl
    contexts = []
    wire = []
    real_context = ssl.create_default_context
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def sendall(self, value): wire.append(value)
        def makefile(self, *args, **kwargs): return io.BytesIO(response())
    connection = Connection()
    def context():
        ctx = real_context()
        assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
        class Context:
            def wrap_socket(self, sock, *, server_hostname):
                assert sock is connection and server_hostname == "proxy.finance.qq.com"
                contexts.append(ctx)
                return connection
        return Context()
    def connect(address, *, timeout):
        assert address == ("proxy.finance.qq.com", 443) and timeout == 15
        return connection
    monkeypatch.setattr(worker.ssl, "create_default_context", context)
    monkeypatch.setattr(worker.socket, "create_connection", connect)
    assert worker._request(REQUEST)["body"] == b"hello"
    assert len(contexts) == 1 and len(wire) == 1
    assert wire[0].split(b"\r\n")[1:] == [b"Host: proxy.finance.qq.com", b"Accept: */*", b"Accept-Encoding: identity", b"Connection: close", b"", b""]


def test_expired_deadline_never_spawns(monkeypatch):
    children = track_children(monkeypatch)
    with pytest.raises(transport.PublicTransportError, match="transport_timeout"):
        transport.fetch(REQUEST, deadline=time.monotonic()-1, cancelled=lambda: False)
    assert children == []


def test_kill_after_ignored_terminate_reaps_real_child(tmp_path, monkeypatch):
    if os.name == "nt":
        pytest.skip("Windows TerminateProcess has no ignorable SIGTERM; native cancellation is tested separately")
    script(tmp_path, monkeypatch, "import signal,time\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\ntime.sleep(60)\n")
    children = track_children(monkeypatch)
    started = time.monotonic()
    with pytest.raises(transport.PublicTransportError, match="transport_timeout"):
        fetch_after(.3)
    assert time.monotonic()-started < 2.3 and children[0][0].poll() is not None
    assert children[0][0].returncode < 0


@pytest.mark.parametrize("failure", ["noop", "os_error", "keyboard_interrupt"])
def test_unconfirmed_shutdown_holds_until_real_exit_then_reports_explicitly(tmp_path, monkeypatch, failure):
    script(tmp_path, monkeypatch, "import time\ntime.sleep(.45)\n")
    monkeypatch.setattr(transport, "_CLEANUP_SECONDS", .05)
    actual = subprocess.Popen
    children = []
    def launch(*args, **kwargs):
        child = actual(*args, **kwargs)
        children.append(child)
        def blocked():
            if failure == "os_error": raise OSError("private OS detail")
            if failure == "keyboard_interrupt": raise KeyboardInterrupt
        child.terminate = blocked
        child.kill = blocked
        return child
    monkeypatch.setattr(transport.subprocess, "Popen", launch)
    started = time.monotonic()
    with pytest.raises(transport.PublicTransportError, match="transport_shutdown_unconfirmed") as caught:
        fetch_after(.12)
    assert getattr(caught.value, "phase", "unknown") == "unknown"
    assert time.monotonic()-started >= .4
    assert children[0].poll() is not None


@pytest.mark.parametrize("payload", [
    '{"error":{"code":"arbitrary private reason"}}',
    '{"error":{"code":"transport_network_error","body":"secret"}}',
    '{"error":{"code":"transport_network_error","status":true}}',
    '{"error":{"code":"transport_network_error","retry_after":"private header"}}',
    '{"error":{"code":"transport_network_error","retry_after":"2024-99-99T00:00:00Z"}}',
    '{"error":{"code":"transport_network_error","byte_count":-1}}',
    '{"error":{"code":"transport_network_error","complete":"yes"}}',
    '{"error":{"code":"transport_timeout"},"error":{"code":"transport_network_error"}}',
    'NaN', '[]', '{invalid',
])
def test_malformed_or_unsafe_worker_protocol_never_escapes(payload):
    with pytest.raises(transport.PublicTransportError, match="transport_protocol_invalid"):
        transport._decode_output(payload.encode(), REQUEST)


def test_open_inheritable_file_descriptor_is_not_passed_to_worker(tmp_path, monkeypatch):
    secret = tmp_path / "private-open-file"
    secret.write_text("not for the worker")
    with secret.open("rb") as opened:
        descriptor = opened.fileno()
        os.set_inheritable(descriptor, True)
        identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
        script(tmp_path, monkeypatch, f"import os,json\ntry:\n st=os.fstat({descriptor})\n assert (st.st_dev,st.st_ino) != {identity!r}\nexcept OSError:\n pass\nprint(json.dumps({{'error': {{'code': 'transport_network_error'}}}}))\n")
        with pytest.raises(transport.PublicTransportError, match="transport_network_error"):
            fetch_after(3)


def test_stderr_exact_limit_is_allowed_and_contents_never_returned(tmp_path, monkeypatch):
    script(tmp_path, monkeypatch, "import sys,json\nsys.stderr.write('s'*4096)\nprint(json.dumps({'error':{'code':'transport_network_error'}}))\n")
    with pytest.raises(transport.PublicTransportError, match="transport_network_error") as caught:
        fetch_after(3)
    assert caught.value.__dict__ == {"code": "transport_network_error"}


def test_supervisor_uses_one_byte_limit_probe_instead_of_large_overread(monkeypatch):
    sizes = []
    class Stream:
        def fileno(self): return 999
    def read(fd, size):
        sizes.append(size)
        return b"x" * size
    monkeypatch.setattr(transport.os, "read", read)
    import queue
    import threading
    messages = queue.Queue()
    transport._read_pipe(Stream(), "stderr", 4096, messages, threading.Event())
    assert sizes == [4097]
    assert messages.get() == ("error", "transport_ipc_too_large")
