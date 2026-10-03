"""D01 structure-only observation. Never accepts, decompresses, or saves a page."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess
import sys
import time
import zlib

import baostock_acquisition_probe as probe
import baostock_transport as transport


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts" / "qualification" / "baostock-frame-diagnostic"
PROTOCOL_SHA256 = "dcffeb5b5a18a3dc7aa50989550187074e98ec92848e33d5392c2cadf14bf14e"
ORIGIN_RUN = "20261003T183357030285Z/P01"
ORIGIN_STATUS_SHA256 = "5a90f2831f8f9d033ec63929cc6bbf022d9f9228c4867157f1f85475fd319086"
MAX_WIRE = 5 * 1024 * 1024
_END = b"<![CDATA[]]>\n"
_HEADER = re.compile(rb"([0-9]{2}\.[0-9]\.[0-9]{2})\x01([0-9A-F]{2})\x01([0-9]{10})")
_ERRORS = {
    "not_observed", "diagnostic_only", "diagnostic_request_limit", "diagnostic_worker_error",
    "invalid_diagnostic_metadata", "unexpected_artifact", "invalid_limits", "invalid_message",
    "request_not_allowed", "invalid_envelope", "invalid_header", "unexpected_response_type",
    "wire_limit", "tail_limit", "unexpected_eof", "deadline_exceeded", "socket_timeout",
    "socket_error", "invalid_utf8", "login_failed", "unapproved_sdk_or_credentials",
    "unexpected_control_response", "missing_or_extra_response", "invalid_frame", "decoded_limit",
}
_BRANCHES = {"not_evaluated", "needs_more_bytes", "layout_matches",
             "compressed_length_exceeded", "compressed_marker_mismatch"}
_METADATA_KEYS = {
    "protocol_version", "response_type", "declared_compressed_bytes", "received_bytes",
    "d01_strict_branch", "marker_seen", "marker_at_end", "bytes_before_marker",
    "tail_shape", "digit_count", "tail_limit_reached", "crc_head_compressed_matches",
}


def _safe_code(code):
    return code if type(code) is str and code in _ERRORS else "diagnostic_worker_error"


class FrameDiagnosticError(probe.ProbeError):
    def __init__(self, code, metadata=None):
        self.metadata = metadata
        super().__init__(_safe_code(code))


def _summarize_tail(metadata, tail, crc):
    """Apply old layout rules to this D01 buffer, never infer the original P01 branch."""
    expected = 21 + metadata["declared_compressed_bytes"] + len(_END)
    received = metadata["received_bytes"]
    marker = tail.find(_END)
    metadata["marker_seen"] = marker >= 0
    metadata["marker_at_end"] = marker >= 0 and marker + len(_END) == len(tail)
    metadata["tail_limit_reached"] = len(tail) == 64
    metadata["d01_strict_branch"] = (
        "compressed_length_exceeded" if received > expected else
        "needs_more_bytes" if received < expected else
        "layout_matches" if metadata["marker_at_end"] else "compressed_marker_mismatch")
    if marker < 0:
        return
    trailer = tail[:marker]
    metadata["bytes_before_marker"] = len(trailer)
    digits = trailer[1:] if trailer.startswith(b"\x01") else trailer
    if not trailer:
        metadata.update(tail_shape="empty", digit_count=0)
    elif digits and digits.isdigit():
        metadata.update(tail_shape="soh_decimal" if trailer.startswith(b"\x01") else "decimal",
                        digit_count=len(digits))
        if len(digits) <= 10 and int(digits) <= 0xFFFFFFFF:
            metadata["crc_head_compressed_matches"] = int(digits) == crc
    else:
        metadata["tail_shape"] = "other"


def observe_frame(sock, message, *, exchange_timeout=10, socket_timeout=8, max_wire=MAX_WIRE):
    """Observe one fixed P01 first-page exchange; return only allowlisted metadata."""
    metadata, tail, body_complete, crc = None, bytearray(), False, None
    received = 0
    try:
        if (any(type(value) not in (int, float) or not 0 < value <= limit
                for value, limit in ((exchange_timeout, 10), (socket_timeout, 8)))
                or type(max_wire) is not int or not 0 < max_wire <= MAX_WIRE):
            raise FrameDiagnosticError("invalid_limits")
        deadline = time.monotonic() + exchange_timeout

        def remaining():
            seconds = deadline - time.monotonic()
            if seconds <= 0:
                raise FrameDiagnosticError("deadline_exceeded")
            return min(seconds, socket_timeout)

        if type(message) is not str:
            raise FrameDiagnosticError("invalid_message")
        if probe.inspect_request(message, "P01", 1) != "market":
            raise FrameDiagnosticError("request_not_allowed")
        outgoing = (message + "\n").encode("utf-8")
        if len(outgoing) > max_wire:
            raise FrameDiagnosticError("wire_limit")
        sock.settimeout(remaining())
        sock.sendall(outgoing)
        remaining()

        def receive(maximum):
            nonlocal received
            budget = max_wire - len(outgoing) - received
            if budget <= 0:
                raise FrameDiagnosticError("wire_limit")
            sock.settimeout(remaining())
            chunk = sock.recv(min(maximum, budget))
            received += len(chunk)
            if metadata is not None:
                metadata["received_bytes"] = received
            remaining()
            if not chunk:
                raise FrameDiagnosticError("unexpected_eof")
            if len(chunk) > maximum or len(outgoing) + received > max_wire:
                raise FrameDiagnosticError("wire_limit")
            return chunk

        head = bytearray()
        while len(head) < 21:
            head.extend(receive(21 - len(head)))
        match = _HEADER.fullmatch(head)
        if match is None:
            raise FrameDiagnosticError("invalid_header")
        if match[2] != b"96":
            raise FrameDiagnosticError("unexpected_response_type")
        length = int(match[3])
        metadata = dict(protocol_version=match[1].decode("ascii"), response_type="96",
                        declared_compressed_bytes=length, received_bytes=received,
                        d01_strict_branch="not_evaluated", marker_seen=False, marker_at_end=False,
                        bytes_before_marker=None, tail_shape=None, digit_count=None,
                        tail_limit_reached=False, crc_head_compressed_matches=None)
        if len(outgoing) + 21 + length + len(_END) > max_wire:
            raise FrameDiagnosticError("wire_limit")
        crc = zlib.crc32(head)
        unread = length
        while unread:
            chunk = receive(min(8192, unread))
            crc = zlib.crc32(chunk, crc)
            unread -= len(chunk)
        body_complete = True
        # Bytewise tail observation stops exactly at the first complete marker.
        while len(tail) < 64:
            tail.extend(receive(1))
            if tail.endswith(_END):
                _summarize_tail(metadata, tail, crc)
                remaining()
                return metadata
        raise FrameDiagnosticError("tail_limit")
    except probe.ProbeError as error:
        code = _safe_code(error.code)
    except TimeoutError:
        code = "socket_timeout"
    except OSError:
        code = "socket_error"
    except UnicodeError:
        code = "invalid_utf8"
    if metadata is not None and body_complete:
        _summarize_tail(metadata, tail, crc)
    raise FrameDiagnosticError(code, metadata)


def _validate_metadata(metadata):
    valid = type(metadata) is dict and set(metadata) == _METADATA_KEYS
    if valid:
        valid = (type(metadata["protocol_version"]) is str
                 and re.fullmatch(r"[0-9]{2}\.[0-9]\.[0-9]{2}", metadata["protocol_version"])
                 and metadata["response_type"] == "96"
                 and metadata["d01_strict_branch"] in _BRANCHES
                 and metadata["tail_shape"] in {None, "empty", "decimal", "soh_decimal", "other"})
        for name, maximum, nullable in (("declared_compressed_bytes", 9999999999, False),
                                        ("received_bytes", MAX_WIRE, False),
                                        ("bytes_before_marker", 51, True), ("digit_count", 51, True)):
            value = metadata[name]
            valid = valid and ((value is None and nullable) or (type(value) is int and 0 <= value <= maximum))
        valid = valid and all(type(metadata[key]) is bool for key in ("marker_seen", "marker_at_end", "tail_limit_reached"))
        valid = valid and (metadata["crc_head_compressed_matches"] is None
                           or type(metadata["crc_head_compressed_matches"]) is bool)
    if not valid:
        raise FrameDiagnosticError("invalid_diagnostic_metadata")


def _check_prerequisites():
    files = ((ROOT / "docs/qualification/FRAME_DIAGNOSTIC_PROTOCOL.md", PROTOCOL_SHA256),
             (ROOT / "artifacts/qualification/baostock-acquisition" / ORIGIN_RUN / "status.json", ORIGIN_STATUS_SHA256))
    if (importlib.metadata.version("baostock") != "0.9.4"
            or any(not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected for path, expected in files)):
        raise SystemExit("diagnostic_prerequisites_changed")


def _initial_status():
    return dict(case="D01", status="diagnostic_incomplete", pages=0, requests=0, phase="created",
                protocol_sha256=PROTOCOL_SHA256, origin_run=ORIGIN_RUN, origin_status_sha256=ORIGIN_STATUS_SHA256,
                evidence_kind="frame_structure_only", started_at=probe.utcnow(), finished_at=None,
                error_code="not_observed", process_state="worker",
                code_sha256={path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in (Path(__file__), Path(probe.__file__), Path(transport.__file__))})


def worker(destination):
    _check_prerequisites()
    destination = Path(destination)
    status = _initial_status()
    original_send, original_save = transport.bounded_send, probe.save

    def save_summary(metadata):
        if metadata is not None:
            _validate_metadata(metadata)
            original_save(destination / "frame-summary.json", metadata)

    def guarded_send(sock, message, **limits):
        kind = probe.inspect_request(message, "P01", 1)
        if kind != "market":
            return original_send(sock, message, **limits)
        if status["requests"]:
            raise probe.ProbeError("diagnostic_request_limit")
        status["requests"] = 1
        original_save(destination / "status.json", status)
        try:
            metadata = observe_frame(sock, message)
        except FrameDiagnosticError as error:
            save_summary(error.metadata)
            code = error.code
        else:
            save_summary(metadata)
            code = "diagnostic_only"
        raise probe.ProbeError(code)

    def guarded_save(path, content):
        if path.parent.resolve() != destination.resolve():
            raise probe.ProbeError("unexpected_artifact")
        if path.name == "request.json":
            case = probe.CASES["P01"]
            safe = {key: case[key] for key in ("method", "code", "start_date", "end_date", "frequency", "adjustflag", "fields")}
            original_save(path, dict(case="D01", protocol_sha256=PROTOCOL_SHA256, origin_run=ORIGIN_RUN,
                                     page=1, page_size=2000, max_market_requests=1, parameters=safe))
        elif path.name == "status.json":
            if content.get("phase") in {"login", "market", "logout", "finished"}:
                status["phase"] = content["phase"]
            if "error_code" in content:
                status["error_code"] = _safe_code(content["error_code"])
            if content.get("cleanup_error") == "logout_failed":
                status["cleanup_error"] = "logout_failed"
            original_save(path, status)
        else:
            raise probe.ProbeError("unexpected_artifact")

    try:
        transport.bounded_send, probe.save = guarded_send, guarded_save
        probe.worker("P01", destination)
    except Exception:
        status["error_code"] = "diagnostic_worker_error"
    finally:
        transport.bounded_send, probe.save = original_send, original_save
        status.update(phase="finished", finished_at=probe.utcnow())
        original_save(destination / "status.json", status)


def run():
    _check_prerequisites()
    destination = RUNS / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") / "D01"
    destination.mkdir(parents=True, exist_ok=False)
    status = _initial_status()
    probe.save(destination / "status.json", status)
    process = subprocess.Popen([sys.executable, "-X", "utf8", __file__, "--worker", str(destination)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        process.wait(timeout=45)
        process_state = "exited" if process.returncode == 0 else "nonzero_exit"
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=5)
            process_state = "killed"
        except subprocess.TimeoutExpired:
            process_state = "termination_unconfirmed"
    try:
        child = json.loads((destination / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        child = {}
    if type(child) is dict:
        if type(child.get("requests")) is int and child["requests"] in (0, 1):
            status["requests"] = child["requests"]
        status["error_code"] = _safe_code(child.get("error_code"))
        if child.get("cleanup_error") == "logout_failed":
            status["cleanup_error"] = "logout_failed"
    status.update(process_state=process_state, phase="finished", finished_at=probe.utcnow())
    probe.save(destination / "status.json", status)
    if process_state == "termination_unconfirmed":
        raise SystemExit("diagnostic_worker_exit_unconfirmed")
    return status


def main(argv=None):
    parser = argparse.ArgumentParser(description="D01: one structure-only observation, always incomplete")
    parser.add_argument("--worker", help=argparse.SUPPRESS)
    arguments = parser.parse_args(argv)
    if arguments.worker:
        destination = Path(arguments.worker).resolve()
        try:
            relative = destination.relative_to(RUNS.resolve())
        except ValueError:
            raise SystemExit("invalid_worker_destination") from None
        if len(relative.parts) != 2 or relative.parts[1] != "D01" or not re.fullmatch(r"[0-9]{8}T[0-9]{12}Z", relative.parts[0]):
            raise SystemExit("invalid_worker_destination")
        worker(destination)
    else:
        print(json.dumps(run(), ensure_ascii=False))


if __name__ == "__main__":
    main()
