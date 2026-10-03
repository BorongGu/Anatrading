"""Bounded transport for the approved probe; never logs or persists payloads."""
import math
import re
import time
import zlib


_END = b"<![CDATA[]]>\n"
_HEADER = re.compile(rb"[0-9]{2}\.[0-9]\.[0-9]{2}\x01([0-9A-F]{2})\x01([0-9]{10})")
_CODES = {
    "invalid_limits", "invalid_message", "wire_limit", "decoded_limit", "deadline_exceeded",
    "socket_timeout", "socket_error", "unexpected_eof", "invalid_header", "invalid_frame",
    "invalid_compressed_body", "incomplete_compressed_body", "compressed_trailing_data",
    "invalid_utf8", "unsupported_compressed_type", "transport_error",
}


class BoundedTransportError(Exception):
    def __init__(self, code):
        self.code = code if type(code) is str and code in _CODES else "transport_error"
        super().__init__(self.code)


def _exchange(sock, message, exchange_timeout, socket_timeout, max_wire, max_decoded):
    if (any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
            for value in (exchange_timeout, socket_timeout))
            or any(type(value) is not int or value <= 0 for value in (max_wire, max_decoded))):
        raise BoundedTransportError("invalid_limits")
    deadline = time.monotonic() + exchange_timeout

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise BoundedTransportError("deadline_exceeded")
        return min(socket_timeout, seconds)

    if type(message) is not str:
        raise BoundedTransportError("invalid_message")
    if len(message) + 1 > max_wire:
        raise BoundedTransportError("wire_limit")
    outgoing = (message + "\n").encode("utf-8")
    if len(outgoing) > max_wire:
        raise BoundedTransportError("wire_limit")
    sock.settimeout(remaining())
    sock.sendall(outgoing)
    remaining()
    received = bytearray()
    kind = None
    frame_length = None
    while True:
        sock.settimeout(remaining())
        # One extra byte detects a breached budget without reading an unbounded chunk.
        chunk = sock.recv(min(8192, max_wire - len(outgoing) - len(received) + 1))
        remaining()
        if not chunk:
            raise BoundedTransportError("unexpected_eof")
        if len(outgoing) + len(received) + len(chunk) > max_wire:
            raise BoundedTransportError("wire_limit")
        received.extend(chunk)
        if kind is None and len(received) >= 21:
            match = _HEADER.fullmatch(received[:21])
            if match is None:
                raise BoundedTransportError("invalid_header")
            kind = match[1]
            if kind in (b"9B", b"9D"):
                raise BoundedTransportError("unsupported_compressed_type")
            if kind in (b"96", b"99"):
                frame_length = 21 + int(match[2]) + len(_END)
                if len(outgoing) + frame_length > max_wire:
                    raise BoundedTransportError("wire_limit")
        if frame_length is not None:
            if len(received) > frame_length:
                raise BoundedTransportError("invalid_frame")
            if len(received) == frame_length:
                if not received.endswith(_END):
                    raise BoundedTransportError("invalid_frame")
                break
        elif kind is not None:
            if len(received) > max_decoded:
                raise BoundedTransportError("decoded_limit")
            terminator = received.find(_END, 21)
            if terminator >= 0:
                if terminator + len(_END) != len(received):
                    raise BoundedTransportError("invalid_frame")
                break
    remaining()
    if frame_length is not None:
        body_budget = max_decoded - 21
        if body_budget < 0:
            raise BoundedTransportError("decoded_limit")
        decoder = zlib.decompressobj()
        body = decoder.decompress(received[21:-len(_END)], body_budget + 1)
        remaining()
        if len(body) > body_budget or decoder.unconsumed_tail:
            raise BoundedTransportError("decoded_limit")
        if not decoder.eof:
            raise BoundedTransportError("incomplete_compressed_body")
        if decoder.unused_data:
            raise BoundedTransportError("compressed_trailing_data")
        result = received[:21].decode("ascii") + body.decode("utf-8")
    else:
        # SDK control replies retain the complete frame; advertised character length
        # is deliberately not interpreted as a UTF-8 byte count.
        result = received.decode("utf-8")
    remaining()
    return result


def bounded_send(sock, message: str, *, exchange_timeout=10, socket_timeout=8,
                 max_wire=5 * 1024 * 1024, max_decoded=5 * 1024 * 1024) -> str:
    """One exchange: shared send/receive wire budget, UTF-8 decoded-reply budget.

    The caller owns the socket. Only response types 96/99 are decompressed.
    Errors expose fixed codes without retaining the underlying exception chain.
    """
    try:
        return _exchange(sock, message, exchange_timeout, socket_timeout, max_wire, max_decoded)
    except BoundedTransportError as error:
        code = error.code
    except TimeoutError:
        code = "socket_timeout"
    except OSError:
        code = "socket_error"
    except UnicodeError:
        code = "invalid_utf8"
    except zlib.error:
        code = "invalid_compressed_body"
    except OverflowError:
        code = "invalid_limits"
    raise BoundedTransportError(code)
