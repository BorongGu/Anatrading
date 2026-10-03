"""D01 uses fake sockets only; no packet or control payload is persisted."""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace
import zlib

import pytest

import baostock_frame_diagnostic as diagnostic
import baostock_acquisition_probe as probe
import baostock_transport as transport
from test_baostock_transport import Clock, FakeSocket, END, header


PRIVATE = "CONTROL_PRIVATE_MARKER_942"
KEYS = {
    "protocol_version", "response_type", "declared_compressed_bytes", "received_bytes",
    "d01_strict_branch", "marker_seen", "marker_at_end", "bytes_before_marker",
    "tail_shape", "digit_count", "tail_limit_reached", "crc_head_compressed_matches",
}


def request(kind="95", page=1):
    if kind == "00":
        parts = ["login", "anonymous", "123456", "0"]
    elif kind == "02":
        parts = ["logout", "anonymous", "20261004030000"]
    else:
        parts = ["query_history_k_data_plus", "anonymous", str(page), "2000", "sh.601577",
                 "date,time,code,open,high,low,close,volume,amount,adjustflag",
                 "2021-01-04", "2021-03-31", "5", "3"]
    body = "\x01".join(parts)
    return header(kind, len(body)).decode("ascii") + body + "\x010"


def frame(tail=None, *, kind="96", body=b"opaque_compressed_bytes"):
    head = header(kind, len(body))
    if tail is None:
        tail = b"\x01" + str(zlib.crc32(head + body)).encode("ascii")
    return head + body + tail + END


class Socket(FakeSocket):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.read_sizes = []
        self.closed = False

    def recv(self, size):
        self.read_sizes.append(size)
        return super().recv(size)

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def fake_clock(monkeypatch):
    clock = Clock()
    monkeypatch.setattr(diagnostic.time, "monotonic", clock)
    return clock


@pytest.mark.parametrize("kind", ["01", "03", "04", "99", "9B"])
def test_control_and_unknown_responses_stop_after_header_without_metadata(kind, capsys):
    sock = Socket([frame(PRIVATE.encode(), kind=kind)])
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(sock, request())
    assert caught.value.code == "unexpected_response_type"
    assert caught.value.metadata is None
    assert caught.value.__context__ is None
    assert sock.read_sizes == [21]
    assert PRIVATE not in str(caught.value)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("bad", [b"x" * 21, b"\xff" * 21, b"00.9.10|96|0000000001"])
def test_bad_header_never_exposes_bytes(bad):
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(Socket([bad + PRIVATE.encode()]), request())
    assert caught.value.code == "invalid_header" and caught.value.metadata is None


@pytest.mark.parametrize("message", [request("00"), request("02"), request(page=2), "bad" + PRIVATE])
def test_only_fixed_market_first_page_can_be_sent(message):
    sock = Socket()
    with pytest.raises(diagnostic.FrameDiagnosticError):
        diagnostic.observe_frame(sock, message)
    assert sock.sent == [] and sock.recv_calls == 0


def test_declared_body_over_budget_stops_at_header():
    sock = Socket([header("96", 9999999999)])
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(sock, request())
    assert caught.value.code == "wire_limit"
    assert sock.read_sizes == [21]
    assert set(caught.value.metadata) == KEYS
    assert caught.value.metadata["declared_compressed_bytes"] == 9999999999


def test_eof_in_declared_body_is_immediate():
    sock = Socket([header("96", 20), b"short", b""])
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(sock, request())
    assert caught.value.code == "unexpected_eof"
    assert caught.value.metadata["received_bytes"] == 26
    assert sock.recv_calls == 3


def test_eof_in_tail_retains_only_structural_summary():
    wire = frame(tail=PRIVATE.encode())[:-13]
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(Socket([wire]), request())
    meta = caught.value.metadata
    assert caught.value.code == "unexpected_eof" and not meta["marker_seen"]
    assert meta["crc_head_compressed_matches"] is None
    assert PRIVATE not in json.dumps(meta)


def test_tail_never_reads_beyond_64_bytes():
    body = b"opaque"
    wire = frame(tail=b"x" * 64, body=body)
    sock = Socket([wire])
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(sock, request())
    meta = caught.value.metadata
    assert caught.value.code == "tail_limit"
    assert meta["received_bytes"] == 21 + len(body) + 64
    assert meta["tail_limit_reached"] is True and meta["marker_seen"] is False
    assert meta["crc_head_compressed_matches"] is None
    assert b"".join(sock.chunks) == END


def test_wire_cap_includes_request_and_tail():
    body = b"opaque"
    budget = len((request() + "\n").encode()) + 21 + len(body) + 13
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(Socket([frame(body=body)]), request(), max_wire=budget)
    assert caught.value.code == "wire_limit"
    assert caught.value.metadata["received_bytes"] == 21 + len(body) + 13


def test_deadline_does_not_reset_for_short_reads(fake_clock):
    sock = Socket([b"0"] * 12, clock=fake_clock, recv_delays=[1] * 12)
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(sock, request())
    assert caught.value.code == "deadline_exceeded"
    assert sock.recv_calls == 10


@pytest.mark.parametrize("error,code", [(TimeoutError(PRIVATE), "socket_timeout"), (OSError(PRIVATE), "socket_error")])
def test_io_errors_do_not_echo_or_chain(error, code):
    with pytest.raises(diagnostic.FrameDiagnosticError) as caught:
        diagnostic.observe_frame(Socket([error]), request())
    assert caught.value.code == code and caught.value.__context__ is None
    assert PRIVATE not in str(caught.value)


@pytest.mark.parametrize("tail,shape,digits", [(b"", "empty", 0), (b"123", "decimal", 3),
                                               (b"\x01123", "soh_decimal", 3), (PRIVATE.encode(), "other", None)])
def test_complete_tail_has_only_allowlisted_structure(tail, shape, digits):
    wire = frame(tail=tail)
    meta = diagnostic.observe_frame(Socket([wire]), request())
    assert set(meta) == KEYS
    assert meta["protocol_version"] == "00.9.10" and meta["response_type"] == "96"
    assert meta["tail_shape"] == shape and meta["digit_count"] == digits
    assert meta["bytes_before_marker"] == len(tail)
    assert meta["received_bytes"] == len(wire)
    assert meta["marker_seen"] is True and meta["marker_at_end"] is True
    assert PRIVATE not in json.dumps(meta)


@pytest.mark.parametrize("soh", [False, True])
def test_only_predeclared_crc_candidate_can_match(soh):
    body = b"data" + PRIVATE.encode()
    head = header("96", len(body))
    tail = (b"\x01" if soh else b"") + str(zlib.crc32(head + body)).encode()
    meta = diagnostic.observe_frame(Socket([head + body + tail + END]), request())
    assert meta["crc_head_compressed_matches"] is True
    assert PRIVATE not in json.dumps(meta)


def test_crc_mismatch_is_false_without_testing_other_domains():
    body = b"compressed_body_candidate"
    value = zlib.crc32(body)
    assert value != zlib.crc32(header("96", len(body)) + body)
    meta = diagnostic.observe_frame(Socket([frame(str(value).encode(), body=body)]), request())
    assert meta["crc_head_compressed_matches"] is False


@pytest.mark.parametrize("tail", [b"", b"4294967296", b"0" * 11, b"\x01", b"-1", b" 123", b"\xff123"])
def test_unavailable_crc_comparison_is_null(tail):
    meta = diagnostic.observe_frame(Socket([frame(tail)]), request())
    assert meta["crc_head_compressed_matches"] is None


@pytest.mark.parametrize("split", range(1, 13))
def test_marker_split_never_reads_past_first_complete_marker(split):
    wire = frame()
    sock = Socket([wire[:-13], END[:split], END[split:] + PRIVATE.encode()])
    meta = diagnostic.observe_frame(sock, request())
    assert meta["marker_seen"] and meta["marker_at_end"]
    assert b"".join(sock.chunks) == PRIVATE.encode()
    assert sock.read_sizes[0] == 21
    assert sock.sent == [(request() + "\n").encode()]


def test_marker_inside_declared_body_is_not_a_terminator(monkeypatch):
    monkeypatch.setattr(diagnostic.zlib, "decompress", lambda *a, **k: pytest.fail("no decompression allowed"))
    monkeypatch.setattr(diagnostic.zlib, "decompressobj", lambda *a, **k: pytest.fail("no decompression allowed"))
    meta = diagnostic.observe_frame(Socket([frame(body=b"x" + END + b"y")]), request())
    assert meta["crc_head_compressed_matches"] is True


def test_old_rule_branch_is_for_d01_observation_only():
    assert diagnostic.observe_frame(Socket([frame(b"")]), request())["d01_strict_branch"] == "layout_matches"
    assert diagnostic.observe_frame(Socket([frame()]), request())["d01_strict_branch"] == "compressed_length_exceeded"


def fake_sdk(monkeypatch, sock, *, second_request=False):
    import baostock as sdk
    import baostock.common.context as context
    import baostock.util.socketutil as sdk_transport
    calls = []
    monkeypatch.setattr(context, "default_socket", sock, raising=False)
    monkeypatch.setattr(context, "apiKey", "0", raising=False)

    def login():
        calls.append("login")
        sdk_transport.send_msg(request("00"))
        print(PRIVATE)
        return SimpleNamespace(error_code="0")

    def logout():
        calls.append("logout")
        sdk_transport.send_msg(request("02"))
        print(PRIVATE)
        return SimpleNamespace(error_code="0")

    def query(**kwargs):
        calls.append("market")
        if second_request:
            for page in (1, 1, 2):
                try:
                    sdk_transport.send_msg(request(page=page))
                except probe.ProbeError:
                    pass
            return SimpleNamespace(error_code="0", next=lambda: pytest.fail("no next()"),
                                   get_data=lambda: pytest.fail("no get_data()"))
        sdk_transport.send_msg(request())
        pytest.fail("market observer must stop the worker")

    monkeypatch.setattr(sdk, "login", login)
    monkeypatch.setattr(sdk, "logout", logout)
    monkeypatch.setattr(sdk, "query_history_k_data_plus", query)
    monkeypatch.setattr(sdk, "query_daily_history_k_AStock", lambda **kw: pytest.fail("no P03"))
    return calls


def control_reply(kind):
    body = f"0\x01{PRIVATE}\x01control".encode()
    return header(kind, len(body)) + body + END


@pytest.mark.parametrize("second_request", [False, True])
def test_worker_never_writes_page_or_control_payload(monkeypatch, tmp_path, capsys, second_request):
    sock = Socket([control_reply("01"), frame(), control_reply("03")])
    calls = fake_sdk(monkeypatch, sock, second_request=second_request)
    old_send, old_save = transport.bounded_send, probe.save
    diagnostic.worker(tmp_path)
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["status"] == "diagnostic_incomplete" and status["pages"] == 0
    assert status["requests"] == 1 and status["case"] == "D01"
    assert status["protocol_sha256"] == "dcffeb5b5a18a3dc7aa50989550187074e98ec92848e33d5392c2cadf14bf14e"
    assert status["origin_run"] == "20261003T183357030285Z/P01"
    assert set(json.loads((tmp_path / "frame-summary.json").read_text())) == KEYS
    assert set(p.name for p in tmp_path.iterdir()) == {"status.json", "request.json", "frame-summary.json"}
    assert all(PRIVATE not in p.read_text() for p in tmp_path.iterdir())
    assert [data[8:10] for data in sock.sent] == [b"00", b"95", b"02"]
    assert calls == ["login", "market", "logout"] and sock.closed
    assert transport.bounded_send is old_send and probe.save is old_save
    assert capsys.readouterr() == ("", "")


def test_control_response_to_market_writes_no_frame_metadata(monkeypatch, tmp_path):
    sock = Socket([control_reply("01"), control_reply("01"), control_reply("03")])
    fake_sdk(monkeypatch, sock)
    diagnostic.worker(tmp_path)
    assert not (tmp_path / "frame-summary.json").exists()
    assert all(PRIVATE not in p.read_text() for p in tmp_path.iterdir())
    status = json.loads((tmp_path / "status.json").read_text())
    assert status["error_code"] == "unexpected_response_type"
    assert status["pages"] == 0 and sock.closed


def test_extra_metadata_is_rejected_before_writing(monkeypatch, tmp_path):
    sock = Socket([control_reply("01"), control_reply("03")])
    fake_sdk(monkeypatch, sock)
    monkeypatch.setattr(diagnostic, "observe_frame", lambda *a, **k: {"raw": PRIVATE})
    diagnostic.worker(tmp_path)
    assert not (tmp_path / "frame-summary.json").exists()
    assert all(PRIVATE not in p.read_text() for p in tmp_path.iterdir())


def test_parent_kills_and_reaps_at_45_seconds(monkeypatch, tmp_path):
    calls = []

    class Process:
        returncode = None

        def wait(self, timeout):
            calls.append(("wait", timeout))
            if timeout == 45:
                raise subprocess.TimeoutExpired("worker", timeout)
            self.returncode = -9

        def kill(self):
            calls.append(("kill",))

    def launch(command, **kwargs):
        calls.append(("launch", command))
        assert kwargs == {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        return Process()

    monkeypatch.setattr(diagnostic, "RUNS", tmp_path)
    monkeypatch.setattr(diagnostic, "_check_prerequisites", lambda: None)
    monkeypatch.setattr(diagnostic.subprocess, "Popen", launch)
    status = diagnostic.run()
    assert status["status"] == "diagnostic_incomplete" and status["pages"] == 0
    assert status["process_state"] == "killed"
    assert calls[1:] == [("wait", 45), ("kill",), ("wait", 5)]
    assert len(list(tmp_path.glob("*/D01/status.json"))) == 1


@pytest.mark.parametrize("arguments", [["--case", "P02"], ["--cases", "P01"], ["--retry"], ["P01"]])
def test_cli_has_no_case_or_retry_options(monkeypatch, arguments):
    monkeypatch.setattr(diagnostic, "run", lambda: pytest.fail("no network run"))
    with pytest.raises(SystemExit) as caught:
        diagnostic.main(arguments)
    assert caught.value.code == 2
