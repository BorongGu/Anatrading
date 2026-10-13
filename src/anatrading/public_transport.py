"""Bounded supervisor for the isolated public HTTPS worker.

The caller supplies an absolute monotonic deadline before any spawn. Only the
child performs network I/O. Reader threads handle bounded IPC, never requests.
Even when OS shutdown fails, this function holds its caller until actual child
exit; it reports shutdown_unconfirmed instead of claiming the deadline held.
POSIX/Windows use Popen's native termination; Windows must be tested natively.
"""
import base64
import binascii
import hashlib
import json
import math
import os
from pathlib import Path
import queue
import re
import subprocess
import sys
import threading
import time

from .public_http_worker import (
    MAX_BODY_BYTES, MAX_HEADER_BYTES, MAX_REQUEST_BYTES, _SAFE_CODES, _SAFE_PHASES,
    _TransportFailure, _validate_request,
)


MAX_STDOUT_BYTES = 2 * 1024 * 1024
MAX_STDERR_BYTES = 4096
_CLEANUP_SECONDS = 2.0
_WORKER_SCRIPT = Path(__file__).with_name("public_http_worker.py").resolve()
_HASH = re.compile(r"[0-9a-f]{64}")


class PublicTransportError(Exception):
    """Only stable codes and explicitly sanitized metadata cross this boundary."""
    def __init__(self, code, *, status=None, retry_after=None, byte_count=None,
                 body_sha256=None, complete=None, phase=None):
        self.code = code if code in _SAFE_CODES else "transport_protocol_invalid"
        for name, value in (("status", status), ("retry_after", retry_after),
                            ("byte_count", byte_count), ("body_sha256", body_sha256),
                            ("complete", complete)):
            if value is not None:
                setattr(self, name, value)
        if phase is not None:
            self.phase = phase if type(phase) is str and phase in _SAFE_PHASES else "unknown"
        super().__init__(self.code)


def _environment():
    # Windows Python/system DLL lookup may need this nonsecret OS directory.
    # Do not copy PATH, HOME, temporary paths, SSL overrides, proxies or tokens.
    if os.name == "nt":
        root = os.environ.get("SystemRoot")
        if not root or not os.path.isabs(root):
            raise PublicTransportError("transport_spawn_failed")
        return {"SystemRoot": root}
    return {}


def _check(deadline, cancelled):
    if cancelled():
        raise PublicTransportError("transport_cancelled")
    if time.monotonic() >= deadline:
        raise PublicTransportError("transport_timeout")


def _send(queue_, item, stopped):
    while not stopped.is_set():
        try:
            queue_.put(item, timeout=.025)
            return
        except queue.Full:
            continue


def _read_pipe(stream, name, limit, messages, stopped):
    consumed = 0
    try:
        while not stopped.is_set():
            chunk = os.read(stream.fileno(), min(16384, limit - consumed + 1))
            if not chunk:
                _send(messages, (name, None), stopped)
                return
            consumed += len(chunk)
            if consumed > limit:
                _send(messages, ("error", "transport_ipc_too_large"), stopped)
                return
            if name == "stdout":
                _send(messages, (name, chunk), stopped)
            # Stderr is counted but never copied into any result or log.
    except (OSError, ValueError):
        _send(messages, ("error", "transport_protocol_invalid"), stopped)


def _reap(process, cleanup_deadline):
    """Return only after confirmed exit, marking any breached cleanup budget.

    An OS that refuses termination cannot provide both a hard return deadline
    and proof of shutdown. Fail closed: keep the caller/root lock held until
    exit, then return the explicit unconfirmed-shutdown error to the caller.
    """
    try:
        if process.poll() is not None:
            return False
    except (OSError, KeyboardInterrupt):
        pass
    try:
        process.terminate()
    except (OSError, KeyboardInterrupt):
        pass
    try:
        process.wait(timeout=max(0, min(.2, cleanup_deadline - time.monotonic())))
        return time.monotonic() > cleanup_deadline
    except subprocess.TimeoutExpired:
        pass
    except (OSError, KeyboardInterrupt):
        pass
    try:
        process.kill()
    except (OSError, KeyboardInterrupt):
        pass
    late = False
    while True:
        remaining = cleanup_deadline - time.monotonic()
        if remaining <= 0:
            late = True
        try:
            process.wait(timeout=max(.025, remaining) if remaining > 0 else .2)
            return late or time.monotonic() > cleanup_deadline
        except subprocess.TimeoutExpired:
            continue
        except (OSError, KeyboardInterrupt):
            # No proof of termination: never release caller's root lock.
            late = True
            try:
                time.sleep(.05)
            except KeyboardInterrupt:
                pass


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _safe_error(value):
    allowed = {"code", "status", "retry_after", "byte_count", "body_sha256", "complete", "phase"}
    if (type(value) is not dict or not set(value) <= allowed
            or type(value.get("code")) is not str or value["code"] not in _SAFE_CODES):
        raise ValueError
    if "phase" in value and (type(value["phase"]) is not str or value["phase"] not in _SAFE_PHASES):
        raise ValueError
    if "status" in value and (type(value["status"]) is not int or not 100 <= value["status"] <= 599):
        raise ValueError
    if "byte_count" in value and (type(value["byte_count"]) is not int or not 0 <= value["byte_count"] <= MAX_BODY_BYTES):
        raise ValueError
    if "body_sha256" in value and (type(value["body_sha256"]) is not str or _HASH.fullmatch(value["body_sha256"]) is None):
        raise ValueError
    if "complete" in value and type(value["complete"]) is not bool:
        raise ValueError
    if "retry_after" in value:
        retry = value["retry_after"]
        valid_seconds = type(retry) is int and 0 <= retry <= 999999999
        valid_date = (type(retry) is str and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z", retry))
        if not (valid_seconds or valid_date):
            raise ValueError
        if valid_date:
            from datetime import datetime
            datetime.fromisoformat(retry)
    return PublicTransportError(**value)


def _decode_output(raw, request):
    try:
        payload = json.loads(raw, object_pairs_hook=_pairs,
                             parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
        if type(payload) is not dict:
            raise ValueError
        if set(payload) == {"error"}:
            raise _safe_error(payload["error"])
        if set(payload) != {"result"}:
            raise ValueError
        result = payload["result"]
        expected = {"status", "response_url", "response_headers", "body_base64", "byte_count", "body_sha256", "complete"}
        if (type(result) is not dict or set(result) != expected or type(result["status"]) is not int
                or result["status"] != 200 or result["response_url"] != request["url"]
                or result["complete"] is not True or type(result["byte_count"]) is not int
                or not 0 <= result["byte_count"] <= MAX_BODY_BYTES
                or type(result["body_sha256"]) is not str or _HASH.fullmatch(result["body_sha256"]) is None
                or type(result["body_base64"]) is not str):
            raise ValueError
        headers = result["response_headers"]
        if type(headers) is not list or not 1 <= len(headers) <= 2:
            raise ValueError
        seen = set()
        for pair in headers:
            if (type(pair) is not list or len(pair) != 2 or any(type(item) is not str for item in pair)
                    or pair[0] not in {"content-type", "content-encoding"} or pair[0] in seen
                    or len(pair[1]) > MAX_HEADER_BYTES or any(ord(c) < 32 and c != "\t" or ord(c) == 127 for c in pair[1])):
                raise ValueError
            if pair[0] == "content-encoding" and pair[1].lower() not in ("", "identity"):
                raise ValueError
            seen.add(pair[0])
        if "content-type" not in seen:
            raise ValueError
        encoded = result.pop("body_base64")
        if len(encoded) > 4 * ((MAX_BODY_BYTES + 2) // 3):
            raise ValueError
        body = base64.b64decode(encoded, validate=True)
        if (len(body) != result["byte_count"] or len(body) > MAX_BODY_BYTES
                or base64.b64encode(body).decode("ascii") != encoded
                or hashlib.sha256(body).hexdigest() != result["body_sha256"]):
            raise ValueError
        return {**result, "body": body}
    except PublicTransportError:
        raise
    except (ValueError, TypeError, KeyError, RecursionError, UnicodeError, binascii.Error):
        raise PublicTransportError("transport_protocol_invalid") from None


def fetch(request, *, deadline, cancelled):
    """Fetch one prevalidated canonical request without retries or redirection."""
    if type(deadline) not in (int, float) or not math.isfinite(deadline) or not callable(cancelled):
        raise PublicTransportError("transport_request_invalid")
    _check(deadline, cancelled)
    try:
        _validate_request(request)
        encoded = json.dumps(request, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        if len(encoded.encode("utf-8")) > MAX_REQUEST_BYTES:
            raise _TransportFailure("transport_request_invalid")
    except (_TransportFailure, ValueError, TypeError, RecursionError, UnicodeError):
        raise PublicTransportError("transport_request_invalid") from None
    executable = str(Path(sys.executable).absolute())
    arguments = [executable, "-I", "-S", str(_WORKER_SCRIPT), encoded]
    process = None
    readers = []
    stopped = threading.Event()
    messages = queue.Queue(maxsize=8)
    output = bytearray()
    shutdown_unconfirmed = False
    try:
        _check(deadline, cancelled)
        try:
            process = subprocess.Popen(arguments, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, close_fds=True, env=_environment(),
                                       bufsize=0)
        except (OSError, ValueError):
            raise PublicTransportError("transport_spawn_failed") from None
        for name, stream, limit in (("stdout", process.stdout, MAX_STDOUT_BYTES),
                                    ("stderr", process.stderr, MAX_STDERR_BYTES)):
            reader = threading.Thread(target=_read_pipe, args=(stream, name, limit, messages, stopped),
                                      daemon=True, name="public-http-" + name)
            readers.append(reader)
            reader.start()
        ended = set()
        while len(ended) < 2 or process.poll() is None:
            _check(deadline, cancelled)
            try:
                name, value = messages.get(timeout=min(.025, max(.001, deadline - time.monotonic())))
            except queue.Empty:
                continue
            if name == "error":
                raise PublicTransportError(value)
            if value is None:
                ended.add(name)
            elif name == "stdout":
                if len(output) + len(value) > MAX_STDOUT_BYTES:
                    raise PublicTransportError("transport_ipc_too_large")
                output.extend(value)
        _check(deadline, cancelled)
        if process.returncode != 0:
            raise PublicTransportError("transport_worker_failed")
        return _decode_output(output, request)
    finally:
        if process is not None:
            cleanup_deadline = time.monotonic() + _CLEANUP_SECONDS
            stopped.set()
            shutdown_unconfirmed = _reap(process, cleanup_deadline)
            for reader in readers:
                if reader.ident is not None:
                    reader.join(timeout=max(0, cleanup_deadline - time.monotonic()))
            process.stdout.close()
            process.stderr.close()
            if shutdown_unconfirmed:
                raise PublicTransportError("transport_shutdown_unconfirmed") from None
