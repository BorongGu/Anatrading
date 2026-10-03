"""Offline transport boundaries; fake frames do not qualify a market source."""
from collections import deque
import contextlib
import io
import traceback
import unittest
from unittest.mock import patch
import zlib

import baostock_transport as transport
from baostock_transport import BoundedTransportError, bounded_send


END = b"<![CDATA[]]>\n"


def header(kind, length):
    return f"00.9.10\x01{kind}\x01{length:010d}".encode("ascii")


def compressed(body=b"sample", kind="96", *, trailer=b""):
    packed = zlib.compress(body)
    return header(kind, len(packed)) + packed + trailer + END


def control(body=b"ok", declared=None):
    return header("02", len(body) if declared is None else declared) + body + END


class Clock:
    now = 100.0

    def __call__(self):
        return self.now


class FakeSocket:
    def __init__(self, chunks=(), *, clock=None, send_delay=0, recv_delays=(), send_error=None):
        self.chunks = deque(chunks)
        self.clock = clock
        self.send_delay = send_delay
        self.recv_delays = deque(recv_delays)
        self.send_error = send_error
        self.sent = []
        self.timeouts = []
        self.recv_calls = 0

    def send(self, value):
        raise AssertionError("sendall is required")

    def sendall(self, value):
        self.sent.append(value)
        if self.clock:
            self.clock.now += self.send_delay
        if self.send_error:
            raise self.send_error

    def settimeout(self, timeout):
        self.timeouts.append(timeout)

    def recv(self, size):
        self.recv_calls += 1
        if self.clock and self.recv_delays:
            self.clock.now += self.recv_delays.popleft()
        item = self.chunks.popleft() if self.chunks else b""
        if isinstance(item, Exception):
            raise item
        if len(item) > size:
            self.chunks.appendleft(item[size:])
            item = item[:size]
        return item


class BoundedTransportTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        patcher = patch.object(transport.time, "monotonic", self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fails(self, code, sock, **limits):
        with self.assertRaises(BoundedTransportError) as caught:
            bounded_send(sock, "request", **limits)
        self.assertEqual(caught.exception.code, code)
        self.assertEqual(str(caught.exception), code)
        self.assertIsNone(caught.exception.__context__)
        return caught.exception

    def test_eof_before_header_stops_immediately(self):
        sock = FakeSocket([b""])
        self.fails("unexpected_eof", sock)
        self.assertEqual(sock.recv_calls, 1)

    def test_eof_during_frame_does_not_spin(self):
        sock = FakeSocket([compressed()[:-1], b""])
        self.fails("unexpected_eof", sock)
        self.assertEqual(sock.recv_calls, 3)

    def test_bad_header_shape_is_rejected(self):
        valid = compressed()
        for bad in (b"x" * 21, header("96", -1), b"00.9.10\x0196\x01000000000x",
                    b"00.9.10|96|0000000012", b"\xff" + valid[1:21]):
            with self.subTest(header=bad.hex()):
                self.fails("invalid_header", FakeSocket([bad + valid[21:]]))

    def test_invalid_compressed_terminator_is_rejected(self):
        self.fails("unexpected_eof", FakeSocket([compressed()[:-13] + b"<![CDATA[]]X\n"]))

    def test_short_declared_length_is_rejected(self):
        packed = zlib.compress(b"sample")
        self.fails("incomplete_compressed_body", FakeSocket([header("96", len(packed) - 1) + packed + END]))

    def test_long_declared_length_cannot_complete_at_early_marker(self):
        packed = zlib.compress(b"sample")
        sock = FakeSocket([header("96", len(packed) + 1) + packed + END])
        self.fails("unexpected_eof", sock)

    def test_bytes_after_compressed_frame_are_rejected(self):
        self.fails("invalid_frame", FakeSocket([compressed() + b"extra"]))

    def test_trailer_prefix_above_51_bytes_is_rejected(self):
        for kind in ("96", "99"):
            with self.subTest(kind=kind):
                self.fails("invalid_frame", FakeSocket([compressed(kind=kind, trailer=b"x" * 52)]))

    def test_marker_missing_at_64_byte_trailer_limit_stops_without_another_read(self):
        sock = FakeSocket([compressed()[:-len(END)], b"x" * 64, END])
        self.fails("invalid_frame", sock)
        self.assertEqual(sock.recv_calls, 3)
        self.assertEqual(list(sock.chunks), [END])

    def test_incomplete_marker_at_trailer_limit_does_not_read_remaining_marker(self):
        sock = FakeSocket([compressed()[:-len(END)], b"x" * 52 + END[:-1], END[-1:]])
        self.fails("invalid_frame", sock)
        self.assertEqual(sock.recv_calls, 3)
        self.assertEqual(list(sock.chunks), [END[-1:]])

    def test_next_read_is_capped_at_declared_body_plus_64_trailer_bytes(self):
        sock = FakeSocket([compressed()[:-len(END)], b"x" * 100])
        self.fails("invalid_frame", sock)
        self.assertEqual(list(sock.chunks), [b"x" * 36])

    def test_coalesced_header_cannot_read_more_than_64_trailer_bytes(self):
        wire = compressed(trailer=b"x" * 1000)
        body_end = 21 + len(zlib.compress(b"sample"))
        sock = FakeSocket([wire])
        self.fails("invalid_frame", sock)
        unread = b"".join(sock.chunks)
        self.assertEqual(len(wire) - len(unread), body_end + 64)
        self.assertEqual(unread, wire[body_end + 64:])

    def test_partial_header_cannot_prefetch_an_oversized_trailer(self):
        wire = compressed(trailer=b"x" * 1000)
        body_end = 21 + len(zlib.compress(b"sample"))
        for split in range(1, 21):
            with self.subTest(split=split):
                sock = FakeSocket([wire[:split], wire[split:]])
                self.fails("invalid_frame", sock)
                unread = b"".join(sock.chunks)
                self.assertEqual(len(wire) - len(unread), body_end + 64)
                self.assertEqual(unread, wire[body_end + 64:])

    def test_already_buffered_bytes_after_marker_with_opaque_trailer_are_rejected(self):
        self.fails("invalid_frame", FakeSocket([compressed(trailer=b"x" * 12) + b"extra"]))

    def test_opaque_trailer_prefix_boundaries_match_sdk_shape(self):
        body = "0\x01中文\x013".encode("utf-8")
        for kind in ("96", "99"):
            for prefix in (b"", b"\xffSECRET_TAIL", b"x" * 51):
                with self.subTest(kind=kind, prefix_length=len(prefix)):
                    wire = compressed(body, kind, trailer=prefix)
                    self.assertEqual(bounded_send(FakeSocket([wire]), "request"),
                                     wire[:21].decode("ascii") + body.decode("utf-8"))

    def test_marker_every_split_after_12_byte_opaque_prefix(self):
        for kind in ("96", "99"):
            wire = compressed(kind=kind, trailer=b"\xffSECRET_TAIL")
            for split in range(len(END) + 1):
                with self.subTest(kind=kind, split=split):
                    at = len(wire) - len(END) + split
                    sock = FakeSocket([wire[:at], wire[at:]])
                    self.assertEqual(bounded_send(sock, "request"), wire[:21].decode("ascii") + "sample")

    def test_opaque_trailer_is_excluded_from_zlib_input(self):
        make_decoder = zlib.decompressobj
        inputs = []

        class TrackingDecoder:
            def __init__(self):
                self.decoder = make_decoder()

            def decompress(self, data, max_length):
                inputs.append(bytes(data))
                return self.decoder.decompress(data, max_length)

            def __getattr__(self, name):
                return getattr(self.decoder, name)

        with patch.object(transport.zlib, "decompressobj", TrackingDecoder):
            bounded_send(FakeSocket([compressed(trailer=b"\xffSECRET_TAIL")]), "request")
        self.assertEqual(inputs, [zlib.compress(b"sample")])

    def test_opaque_trailer_counts_towards_cumulative_wire_budget(self):
        wire = compressed(trailer=b"x" * 51)
        sock = FakeSocket([wire[:21], wire[21:-30], wire[-30:]])
        self.fails("wire_limit", sock, max_wire=len(b"request\n") + len(wire) - 1)

    def test_opaque_trailer_does_not_count_as_decoded_text(self):
        wire = compressed(trailer=b"x" * 51)
        self.assertEqual(bounded_send(FakeSocket([wire]), "request", max_decoded=27)[21:], "sample")

    def test_opaque_trailer_keeps_absolute_deadline(self):
        wire = compressed(trailer=b"x" * 12)
        sock = FakeSocket([wire[:-25]] + [wire[index:index + 1] for index in range(len(wire) - 25, len(wire))],
                          clock=self.clock, recv_delays=[0] + [1] * 25)
        self.fails("deadline_exceeded", sock)
        self.assertEqual(sock.recv_calls, 11)

    def test_opaque_trailer_never_enters_output_or_safe_error(self):
        for extra in (b"", b"extra"):
            with self.subTest(extra=bool(extra)):
                output = io.StringIO()
                wire = compressed(trailer=b"\xffSECRET_TAIL") + extra
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                    if extra:
                        error = self.fails("invalid_frame", FakeSocket([wire]))
                        result = "".join(traceback.format_exception(error))
                    else:
                        result = bounded_send(FakeSocket([wire]), "request")
                self.assertEqual(output.getvalue(), "")
                self.assertNotIn("SECRET_TAIL", result)

    def test_bytes_after_control_terminator_are_rejected(self):
        self.fails("invalid_frame", FakeSocket([control() + b"extra"]))

    def test_control_without_terminator_stops_at_eof(self):
        self.fails("unexpected_eof", FakeSocket([control()[:-13] + b"\n"]))

    def test_invalid_compressed_stream_is_rejected(self):
        self.fails("invalid_compressed_body", FakeSocket([header("96", 4) + b"junk" + END]))

    def test_truncated_zlib_stream_is_rejected(self):
        packed = zlib.compress(b"sample")[:-1]
        self.fails("incomplete_compressed_body", FakeSocket([header("96", len(packed)) + packed + END]))

    def test_bad_zlib_checksum_is_rejected(self):
        packed = bytearray(zlib.compress(b"sample"))
        packed[-1] ^= 1
        self.fails("invalid_compressed_body", FakeSocket([header("96", len(packed)) + packed + END]))

    def test_extra_bytes_inside_declared_compressed_body_are_rejected(self):
        for suffix in (b"trailing", zlib.compress(b"second stream")):
            with self.subTest(suffix=suffix.hex()):
                packed = zlib.compress(b"sample") + suffix
                self.fails("compressed_trailing_data", FakeSocket([header("96", len(packed)) + packed + END]))

    def test_compression_bomb_has_bounded_output(self):
        limits = []
        make_decoder = zlib.decompressobj

        class TrackingDecoder:
            def __init__(self):
                self.decoder = make_decoder()

            def decompress(self, data, max_length=0):
                limits.append(max_length)
                if not 0 < max_length <= 33:
                    raise AssertionError("decompression needs a finite output budget")
                return self.decoder.decompress(data, max_length)

            def __getattr__(self, name):
                return getattr(self.decoder, name)

        sock = FakeSocket([compressed(b"A" * 1024 * 1024)])
        with patch.object(transport.zlib, "decompressobj", TrackingDecoder), \
                patch.object(transport.zlib, "decompress", side_effect=AssertionError("unbounded decoder")):
            self.fails("decoded_limit", sock, max_decoded=53)
        self.assertTrue(limits)

    def test_invalid_utf8_compressed_and_control_are_safe_failures(self):
        for wire in (compressed(b"\xffSECRET_VALUE"), control(b"\xffSECRET_VALUE")):
            with self.subTest(compressed=wire[8:10] == b"96"):
                error = self.fails("invalid_utf8", FakeSocket([wire]))
                self.assertNotIn("SECRET_VALUE", "".join(traceback.format_exception(error)))

    def test_unsupported_sdk_compressed_types_are_not_control_text(self):
        for kind in ("9B", "9D"):
            with self.subTest(kind=kind):
                self.fails("unsupported_compressed_type", FakeSocket([compressed(kind=kind)]))

    def test_request_bytes_count_towards_wire_limit_before_send(self):
        sock = FakeSocket()
        self.fails("wire_limit", sock, max_wire=7)
        self.assertEqual(sock.sent, [])
        self.assertEqual(sock.recv_calls, 0)

    def test_cumulative_wire_limit_applies_across_short_reads(self):
        wire = control(b"x" * 60)
        sock = FakeSocket([wire[:21], wire[21:40], wire[40:]])
        self.fails("wire_limit", sock, max_wire=60)
        self.assertGreater(sock.recv_calls, 1)

    def test_single_receive_cannot_exceed_wire_limit(self):
        self.fails("wire_limit", FakeSocket([control(b"x" * 100)]), max_wire=60)

    def test_declared_compressed_frame_over_budget_stops_after_header(self):
        sock = FakeSocket([header("96", 99999)])
        self.fails("wire_limit", sock, max_wire=100)
        self.assertEqual(sock.recv_calls, 1)

    def test_decoded_limit_counts_utf8_bytes_and_header(self):
        wire = compressed("中文".encode("utf-8"))
        self.fails("decoded_limit", FakeSocket([wire]), max_decoded=26)
        self.assertEqual(bounded_send(FakeSocket([wire]), "request", max_decoded=27)[21:], "中文")

    def test_decoded_limit_applies_to_whole_control_reply(self):
        wire = control("中文".encode("utf-8"), declared=2)
        self.fails("decoded_limit", FakeSocket([wire]), max_decoded=len(wire) - 1)

    def test_deadline_is_not_reset_by_progress(self):
        sock = FakeSocket([b"0"] * 12, clock=self.clock, recv_delays=[1] * 12)
        self.fails("deadline_exceeded", sock)
        self.assertEqual(sock.recv_calls, 10)

    def test_sendall_time_consumes_exchange_deadline(self):
        sock = FakeSocket([compressed()], clock=self.clock, send_delay=10)
        self.fails("deadline_exceeded", sock)
        self.assertEqual(sock.recv_calls, 0)

    def test_complete_response_received_after_deadline_is_rejected(self):
        sock = FakeSocket([compressed()], clock=self.clock, recv_delays=[0, 10])
        self.fails("deadline_exceeded", sock)

    def test_decompression_time_is_inside_deadline(self):
        make_decoder = zlib.decompressobj
        clock = self.clock

        class SlowDecoder:
            def __init__(self):
                self.decoder = make_decoder()

            def decompress(self, data, max_length):
                output = self.decoder.decompress(data, max_length)
                clock.now += 10
                return output

            def __getattr__(self, name):
                return getattr(self.decoder, name)

        with patch.object(transport.zlib, "decompressobj", SlowDecoder):
            self.fails("deadline_exceeded", FakeSocket([compressed()]))

    def test_socket_timeouts_and_errors_do_not_echo_or_chain(self):
        for error, expected in ((TimeoutError("SECRET_VALUE"), "socket_timeout"),
                                (OSError("SECRET_VALUE"), "socket_error")):
            for sending in (True, False):
                with self.subTest(error=type(error).__name__, sending=sending):
                    sock = FakeSocket(send_error=error) if sending else FakeSocket([error])
                    output = io.StringIO()
                    with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                        caught = self.fails(expected, sock)
                    self.assertEqual(output.getvalue(), "")
                    self.assertNotIn("SECRET_VALUE", "".join(traceback.format_exception(caught)))

    def test_invalid_limits_fail_without_io(self):
        for key in ("exchange_timeout", "socket_timeout", "max_wire", "max_decoded"):
            for value in (0, -1, True, "8", None, float("nan"), float("inf")):
                with self.subTest(key=key, value=value):
                    sock = FakeSocket()
                    self.fails("invalid_limits", sock, **{key: value})
                    self.assertEqual(sock.sent, [])
        for key in ("max_wire", "max_decoded"):
            self.fails("invalid_limits", FakeSocket(), **{key: 1.5})

    def test_invalid_message_type_and_encoding_are_safe(self):
        for message, code in ((b"secret", "invalid_message"), (None, "invalid_message"),
                              ("\ud800SECRET_VALUE", "invalid_utf8")):
            with self.subTest(code=code):
                sock = FakeSocket()
                with self.assertRaises(BoundedTransportError) as caught:
                    bounded_send(sock, message)
                self.assertEqual(caught.exception.code, code)
                self.assertIsNone(caught.exception.__context__)
                self.assertEqual(sock.sent, [])

    def test_partial_compressed_reads_96_and_99_match_sdk_shape(self):
        body = "0\x01中文\x013".encode("utf-8")
        for kind in ("96", "99"):
            with self.subTest(kind=kind):
                wire = compressed(body, kind)
                sock = FakeSocket([wire[index:index + 1] for index in range(len(wire))])
                result = bounded_send(sock, "request")
                self.assertEqual(result, wire[:21].decode("ascii") + body.decode("utf-8"))
                self.assertEqual(sock.sent, [b"request\n"])
                self.assertEqual(len(END), 13)

    def test_noncompressed_control_keeps_original_shape_and_character_length(self):
        wire = control("控制回复".encode("utf-8"), declared=4)
        sock = FakeSocket([wire[:22], wire[22:-2], wire[-2:]])
        self.assertEqual(bounded_send(sock, "request"), wire.decode("utf-8"))

    def test_sendall_uses_utf8_and_sdk_newline_once(self):
        wire = control()
        sock = FakeSocket([wire])
        bounded_send(sock, "请求")
        self.assertEqual(sock.sent, ["请求\n".encode("utf-8")])

    def test_timeouts_use_remaining_deadline(self):
        wire = compressed()
        sock = FakeSocket([wire[:7], wire[7:21], wire[21:]], clock=self.clock,
                          send_delay=3, recv_delays=[2, 1, 1])
        bounded_send(sock, "request")
        self.assertEqual(sock.timeouts, [8, 7, 5, 4])

    def test_exact_wire_and_decoded_limits_are_accepted(self):
        for wire, decoded_length in ((compressed(), 27), (control(), len(control()))):
            with self.subTest(kind=wire[8:10]):
                bounded_send(FakeSocket([wire]), "request", max_wire=len(b"request\n") + len(wire),
                             max_decoded=decoded_length)

    def test_marker_bytes_inside_compressed_data_are_not_an_early_frame_end(self):
        body = b"prefix" + END + b"suffix"
        packed = zlib.compress(body, level=0)
        split_at = packed.index(END) + len(END)
        sock = FakeSocket([header("96", len(packed)) + packed[:split_at], packed[split_at:] + END])
        self.assertEqual(bounded_send(sock, "request")[21:].encode("utf-8"), body)


if __name__ == "__main__":
    unittest.main()
