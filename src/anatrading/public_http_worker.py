"""Short-lived, standard-library-only HTTPS worker for two fixed public endpoints.

Executed by absolute filename with Python -I -S and an empty/minimal environment.
This is a program/environment boundary, not an operating-system file sandbox.
Never import application modules, open a Store, or emit server failure content.
"""
import base64
from contextlib import contextmanager
from datetime import timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import re
import socket
import ssl
import sys
from urllib.parse import urlsplit


MAX_BODY_BYTES = 1024 * 1024
MAX_HEADER_BYTES = 64 * 1024
MAX_HEADER_FIELDS = 100
MAX_REQUEST_BYTES = 8192
_ALLOWED_ENDPOINTS = {
    "proxy.finance.qq.com": "/ifzqgtimg/appstock/app/newfqkline/get",
    "quotes.sina.cn": "/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData",
}
_ALLOWED_HEADERS = {"Accept": "*/*", "Accept-Encoding": "identity"}
_CRITICAL_HEADERS = {"content-type", "content-encoding", "content-length", "transfer-encoding"}
_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+")
_STATUS = re.compile(rb"HTTP/1\.[01] ([1-5][0-9]{2})(?: [\t\x20-\x7e\x80-\xff]*)?\r\n")
_SAFE_PHASES = frozenset({"dns", "connect", "tls", "http", "read", "unknown"})
_SAFE_CODES = frozenset({
    "transport_request_invalid", "transport_headers_invalid", "transport_headers_too_large",
    "transport_framing_invalid", "transport_encoding_unsupported", "transport_body_too_large",
    "transport_truncated", "transport_http_redirect", "transport_http_blocked",
    "transport_http_transient", "transport_http_status", "transport_restricted",
    "transport_timeout", "transport_network_error", "transport_tls_invalid",
    "transport_worker_failed", "transport_cancelled", "transport_shutdown_unconfirmed",
    "transport_ipc_too_large", "transport_protocol_invalid", "transport_spawn_failed",
})


class _TransportFailure(Exception):
    def __init__(self, code, **safe):
        self.code = code
        for name, value in safe.items():
            setattr(self, name, value)
        super().__init__(code)

    def record(self):
        return {name: value for name, value in self.__dict__.items()
                if name in {"code", "status", "retry_after", "byte_count", "body_sha256", "complete"}
                or name == "phase" and type(value) is str and value in _SAFE_PHASES}


def _validate_request(request):
    """Repeat security boundaries, without rebuilding source-specific parameters."""
    try:
        if (type(request) is not dict or set(request) != {"method", "url", "parameters", "headers"}
                or request["method"] != "GET" or type(request["headers"]) is not dict
                or request["headers"] != _ALLOWED_HEADERS or type(request["parameters"]) is not dict
                or any(type(k) is not str or type(v) is not str for k, v in request["parameters"].items())
                or type(request["url"]) is not str):
            raise ValueError
        url = request["url"]
        if (not url or len(url) > 4096 or any(ord(c) <= 32 or ord(c) >= 127 for c in url)
                or "#" in url or "\\" in url):
            raise ValueError
        parts = urlsplit(url)
        if (parts.scheme != "https" or parts.netloc not in _ALLOWED_ENDPOINTS
                or parts.path != _ALLOWED_ENDPOINTS[parts.netloc] or not parts.query
                or parts.username is not None or parts.password is not None
                or parts.port is not None or parts.fragment):
            raise ValueError
        return parts.netloc, parts.path + "?" + parts.query
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise _TransportFailure("transport_request_invalid") from None


def _retry_after(value):
    """Bounded safe seconds or normalized UTC HTTP date, never arbitrary text."""
    if type(value) is not str or len(value) > 128:
        return None
    if re.fullmatch(r"[0-9]{1,9}", value):
        return int(value)
    try:
        instant = parsedate_to_datetime(value)
        if instant.tzinfo is None:
            return None
        return instant.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    except (ValueError, TypeError, OverflowError):
        return None


def _chunk_count(line):
    """Bounded chunk-size/extensions grammar; extension values are discarded."""
    match = re.match(rb"[0-9A-Fa-f]{1,16}", line)
    if match is None:
        raise ValueError
    count = int(match.group(), 16)
    index = match.end()
    while index < len(line):
        while index < len(line) and line[index] in (9, 32):
            index += 1
        if index == len(line) or line[index] != 59:  # semicolon
            raise ValueError
        index += 1
        while index < len(line) and line[index] in (9, 32):
            index += 1
        name = _TOKEN.match(line, index)
        if name is None:
            raise ValueError
        index = name.end()
        while index < len(line) and line[index] in (9, 32):
            index += 1
        if index < len(line) and line[index] == 61:  # equals
            index += 1
            while index < len(line) and line[index] in (9, 32):
                index += 1
            if index < len(line) and line[index] == 34:
                index += 1
                while True:
                    if index >= len(line):
                        raise ValueError
                    byte = line[index]
                    index += 1
                    if byte == 34:
                        break
                    if byte == 92:  # quoted-pair
                        if index >= len(line):
                            raise ValueError
                        byte = line[index]
                        index += 1
                    if byte < 32 and byte != 9 or byte == 127:
                        raise ValueError
            else:
                value = _TOKEN.match(line, index)
                if value is None:
                    raise ValueError
                index = value.end()
    return count


class _ResponseReader:
    def __init__(self, stream):
        self.stream = stream
        self.metadata_bytes = 0
        self.fields = 0
        self.body = bytearray()
        self.digest = hashlib.sha256()
        self.status = None
        self.phase = "http"

    def fail(self, code, *, complete=False, retry_after=None):
        safe = {"phase": self.phase, "byte_count": len(self.body), "body_sha256": self.digest.hexdigest(), "complete": complete}
        if self.status is not None:
            safe["status"] = self.status
        if retry_after is not None:
            safe["retry_after"] = retry_after
        raise _TransportFailure(code, **safe)

    def line(self):
        remaining = MAX_HEADER_BYTES - self.metadata_bytes
        line = self.stream.readline(remaining + 1)
        self.metadata_bytes += len(line)
        if self.metadata_bytes > MAX_HEADER_BYTES:
            self.fail("transport_headers_too_large")
        if not line or not line.endswith(b"\n"):
            self.fail("transport_truncated")
        if not line.endswith(b"\r\n"):
            self.fail("transport_headers_invalid")
        return line

    def headers(self, *, trailer=False):
        headers = {}
        while True:
            line = self.line()
            if line == b"\r\n":
                return headers
            self.fields += 1
            if self.fields > MAX_HEADER_FIELDS:
                self.fail("transport_headers_too_large")
            name, sep, value = line[:-2].partition(b":")
            if not sep or _TOKEN.fullmatch(name) is None:
                self.fail("transport_headers_invalid")
            if any(byte < 32 and byte != 9 or byte == 127 for byte in value):
                self.fail("transport_headers_invalid")
            key = name.decode("ascii").lower()
            if key in _CRITICAL_HEADERS and (key in headers or trailer):
                self.fail("transport_headers_invalid")
            headers.setdefault(key, []).append(value.decode("latin-1").strip(" \t"))

    def append(self, chunk):
        if len(self.body) + len(chunk) > MAX_BODY_BYTES:
            self.fail("transport_body_too_large")
        self.body.extend(chunk)
        self.digest.update(chunk)

    def exact(self, count):
        if count > MAX_BODY_BYTES - len(self.body):
            self.fail("transport_body_too_large")
        while count:
            chunk = self.stream.read(min(count, 16384))
            if not chunk:
                self.fail("transport_truncated")
            self.append(chunk)
            count -= len(chunk)

    def end(self):
        if self.stream.read(1):
            self.fail("transport_framing_invalid")

    def body_bytes(self, headers):
        lengths = headers.get("content-length", [])
        transfer = headers.get("transfer-encoding", [])
        if lengths and transfer:
            self.fail("transport_framing_invalid")
        if transfer:
            if transfer[0].lower() != "chunked":
                self.fail("transport_framing_invalid")
            while True:
                try:
                    count = _chunk_count(self.line()[:-2])
                except ValueError:
                    self.fail("transport_framing_invalid")
                if not count:
                    self.headers(trailer=True)
                    self.end()
                    return
                self.exact(count)
                if self.line() != b"\r\n":
                    self.fail("transport_framing_invalid")
        elif lengths:
            if re.fullmatch(r"[0-9]{1,16}", lengths[0]) is None:
                self.fail("transport_framing_invalid")
            self.exact(int(lengths[0]))
            self.end()
        else:
            while True:
                chunk = self.stream.read(min(16384, MAX_BODY_BYTES - len(self.body) + 1))
                if not chunk:
                    return
                self.append(chunk)


def _is_restriction(body):
    # Strict format decoding is the caller's responsibility; these are only
    # unmistakable restriction markers and are never returned or logged.
    lowered = body.lower()
    markers = [b"captcha", b"access denied", b"too many requests", b"forbidden"]
    for marker in ("访问过于频繁", "访问频繁", "验证码", "禁止访问", "封禁"):
        markers.extend((marker.encode("utf-8"), marker.encode("gbk")))
    return any(marker in lowered for marker in markers)


def _read_response(stream, response_url):
    reader = _ResponseReader(stream)
    try:
        while True:
            status_line = reader.line()
            match = _STATUS.fullmatch(status_line)
            if match is None:
                reader.fail("transport_headers_invalid")
            reader.status = int(match.group(1))
            headers = reader.headers()
            # Check ambiguity before classification, even for non-200 responses.
            if "content-length" in headers and "transfer-encoding" in headers:
                reader.fail("transport_framing_invalid")
            if "transfer-encoding" in headers and headers["transfer-encoding"][0].lower() != "chunked":
                reader.fail("transport_framing_invalid")
            if "content-length" in headers and re.fullmatch(r"[0-9]{1,16}", headers["content-length"][0]) is None:
                reader.fail("transport_framing_invalid")
            encoding = headers.get("content-encoding", [""])[0]
            if encoding.lower() not in ("", "identity"):
                reader.fail("transport_encoding_unsupported")
            if reader.status >= 200:
                break
            if reader.status == 101 or "content-length" in headers or "transfer-encoding" in headers:
                reader.fail("transport_framing_invalid")
        status = reader.status
        if status in (401, 403, 429):
            retry = headers.get("retry-after", [])
            reader.fail("transport_http_blocked", retry_after=_retry_after(retry[0]) if len(retry) == 1 else None)
        if 500 <= status <= 599:
            reader.fail("transport_http_transient")
        if 300 <= status <= 399:
            reader.fail("transport_http_redirect")
        if status != 200:
            reader.fail("transport_http_status")
        if "content-type" not in headers:
            reader.fail("transport_headers_invalid")
        reader.phase = "read"
        reader.body_bytes(headers)
        body = bytes(reader.body)
        if _is_restriction(body):
            reader.fail("transport_restricted", complete=True)
        return {"status": 200, "response_url": response_url,
                "response_headers": [[name, headers[name][0]] for name in ("content-type", "content-encoding") if name in headers],
                "body": body, "byte_count": len(body), "body_sha256": reader.digest.hexdigest(), "complete": True}
    except _TransportFailure:
        raise
    except (socket.timeout, TimeoutError):
        reader.fail("transport_timeout")
    except (OSError, EOFError):
        reader.fail("transport_network_error")


@contextmanager
def _phase(phase):
    """Annotate only the enclosed operation, never resource entry or cleanup.

    Keep the outer request's existing exception-to-code mapping, including
    SSL errors during writes. Response reading keeps its own older mapping.
    """
    try:
        yield
    except ssl.SSLError:
        raise _TransportFailure("transport_tls_invalid", phase=phase) from None
    except (socket.timeout, TimeoutError):
        raise _TransportFailure("transport_timeout", phase=phase) from None
    except OSError:
        raise _TransportFailure("transport_network_error", phase=phase) from None


def _request(request):
    host, target = _validate_request(request)
    context = ssl.create_default_context()
    # No urllib/session/proxy/netrc/cookie handling and no content decompression.
    wire = (f"GET {target} HTTP/1.1\r\nHost: {host}\r\nAccept: */*\r\n"
            "Accept-Encoding: identity\r\nConnection: close\r\n\r\n").encode("ascii")
    try:
        with _phase("unknown"):
            try:
                connection = socket.create_connection((host, 443), timeout=15)
            except socket.gaierror:
                raise _TransportFailure("transport_network_error", phase="dns") from None
            except ConnectionRefusedError:
                raise _TransportFailure("transport_network_error", phase="connect") from None
        with connection as connection:
            with _phase("tls"):
                secured = context.wrap_socket(connection, server_hostname=host)
            with secured as secured:
                with _phase("http"):
                    secured.sendall(wire)
                    stream = secured.makefile("rb", buffering=16384)
                with stream as stream:
                    return _read_response(stream, request["url"])
    except _TransportFailure:
        raise
    except ssl.SSLError:
        raise _TransportFailure("transport_tls_invalid") from None
    except (socket.timeout, TimeoutError):
        raise _TransportFailure("transport_timeout") from None
    except OSError:
        raise _TransportFailure("transport_network_error") from None


def main():
    try:
        if len(sys.argv) != 2 or len(sys.argv[1].encode("utf-8")) > MAX_REQUEST_BYTES:
            raise _TransportFailure("transport_request_invalid")
        try:
            request = json.loads(sys.argv[1])
        except (ValueError, RecursionError):
            raise _TransportFailure("transport_request_invalid") from None
        result = _request(request)
        result["body_base64"] = base64.b64encode(result.pop("body")).decode("ascii")
        output = {"result": result}
    except _TransportFailure as error:
        output = {"error": error.record()}
    except Exception:
        output = {"error": {"code": "transport_worker_failed"}}
    sys.stdout.write(json.dumps(output, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
    sys.stdout.flush()


if __name__ == "__main__":
    main()
