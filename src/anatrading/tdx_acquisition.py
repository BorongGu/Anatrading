"""Bounded local daily capture; publication uses the workbench's existing writer."""
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import socket
import struct
import subprocess
import threading
import time
from urllib.parse import urlencode
import uuid

from .formats import decode
from .models import VERSIONS, VALUE_FIELDS
from .numeric import decimal_text
from .store import _DirectoryLock, _identity


_FORMAT = "tdx-public-day-v1"
_MAX_BYTES = 1024 * 1024
_EXE_SHA = "4c822464613fabe4b4235edf171b031d8b209ef68bd7d06dea403e1cd54c1fad"
_SDK_SHA = "241358919fd394751a46bb51d64374eb0216f7c22bfa47bc13c48418ba26b1b0"
_SYMBOLS = {"600059.SH", "000001.SZ"}
_TERMINAL = {"committed", "failed", "not_covered"}
_deadline = ContextVar("tdx_acquisition_deadline", default=None)
_post_guard = ContextVar("tdx_acquisition_post_guard", default=None)


class AcquireError(ValueError):
    def __init__(self, code, raw=b""):
        self.code, self.raw = code, raw
        super().__init__(code)


def _remaining(limit=None):
    deadline = _deadline.get()
    if deadline is None:
        return limit
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise AcquireError("acquisition_deadline")
    return remaining if limit is None else min(limit, remaining)


def _request(port, method, path, body=b"", headers=None, *, budget=15):
    _remaining()
    if method == "POST" and _post_guard.get() is not None:
        _post_guard.get()()
    return _http(port, method, path, body, headers, budget=_remaining(budget))


def data_root_id(root):
    return hashlib.sha256(str(Path(root).resolve()).casefold().encode("utf-8")).hexdigest()


def _decode_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def constant(value):
        raise ValueError

    if len(raw) > _MAX_BYTES:
        raise AcquireError("response_limit")
    try:
        return json.loads(raw.decode("utf-8-sig"), object_pairs_hook=pairs,
                          parse_float=Decimal, parse_constant=constant)
    except (ValueError, UnicodeError, RecursionError, ArithmeticError):
        raise AcquireError("invalid_response") from None


def _refresh_result(raw, request_id):
    reply = _decode_json(raw)
    if (type(reply) is not dict or type(reply.get("id")) is not int or reply["id"] != request_id
            or type(reply.get("result")) is not dict or reply["result"].get("ErrorId") != "0"):
        raise AcquireError("refresh_result_unknown")
    return reply["result"]


def _http(port, method, path, body=b"", headers=None, *, budget=15):
    deadline = time.monotonic() + budget
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=min(2, budget))
    raw = bytearray()
    response = None
    deadline_timer = None
    try:
        connection.connect()
        active_socket = connection.sock

        def stop_reading():
            try:
                active_socket.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        deadline_timer = threading.Timer(max(0, deadline - time.monotonic()), stop_reading)
        deadline_timer.daemon = True
        deadline_timer.start()

        def remaining():
            duration = deadline - time.monotonic()
            if duration <= 0:
                raise TimeoutError
            active_socket.settimeout(duration)

        remaining()
        if method == "POST" and _post_guard.get() is not None:
            _post_guard.get()()
            remaining()
        connection.request(method, path, body=body, headers=headers or {})
        remaining()
        response = connection.getresponse()
        while not response.isclosed():
            # Retain the socket reference for replies which detach it from the connection.
            remaining()
            chunk = response.read1(min(65536, _MAX_BYTES + 1 - len(raw)))
            raw.extend(chunk)
            if len(raw) > _MAX_BYTES:
                raise AcquireError("response_limit", bytes(raw))
            if not chunk:
                break
        if time.monotonic() > deadline:
            raise TimeoutError
        return response.status, bytes(raw)
    except (OSError, http.client.HTTPException):
        raise AcquireError("http_result_unknown", bytes(raw)) from None
    finally:
        if deadline_timer is not None:
            deadline_timer.cancel()
        if response is not None:
            response.close()
        connection.close()


def _inside(path, directory):
    path = Path(path).resolve()
    if not path.is_relative_to(directory):
        raise AcquireError("source_path_outside_client")
    return path


def _file_hash(path, limit):
    if path.stat().st_size > limit:
        raise AcquireError("source_file_limit")
    total, digest = 0, hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(65536):
            _remaining()
            total += len(chunk)
            if total > limit:
                raise AcquireError("source_file_limit")
            digest.update(chunk)
    return digest.hexdigest()


def _client_identity(client_directory):
    if os.name != "nt":
        raise AcquireError("windows_required")
    exe = _inside(client_directory / "TdxW.exe", client_directory)
    sdk = _inside(client_directory / "PYPlugins/user/tqcenter.py", client_directory)
    exe_sha, sdk_sha = _file_hash(exe, 32 * _MAX_BYTES), _file_hash(sdk, _MAX_BYTES)
    if exe_sha != _EXE_SHA or sdk_sha != _SDK_SHA:
        raise AcquireError("client_fingerprint_changed")
    with exe.open("rb") as source:
        if source.read(2) != b"MZ":
            raise AcquireError("client_architecture_changed")
        source.seek(60)
        offset = struct.unpack("<I", source.read(4))[0]
        source.seek(offset)
        if source.read(6) != b"PE\0\0\x64\x86":
            raise AcquireError("client_architecture_changed")
    command = """$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new()
$probeListeners=@(Get-NetTCPConnection -State Listen -LocalPort 17709 | Where-Object LocalAddress -eq '127.0.0.1')
if ($probeListeners.Count -ne 1) { throw 'listener_count' }
$probeOwner=Get-Process -Id $probeListeners[0].OwningProcess
@{path=$probeOwner.Path;pid=$probeOwner.Id;started=$probeOwner.StartTime.ToUniversalTime().ToString('o')} | ConvertTo-Json -Compress
"""
    try:
        observed = subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe",
                                   "-NoProfile", "-NonInteractive", "-Command", command],
                                  capture_output=True, timeout=_remaining(8), creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise AcquireError("client_identity_unavailable") from None
    if observed.returncode:
        raise AcquireError("client_identity_unavailable")
    identity = _decode_json(observed.stdout)
    if (type(identity) is not dict or type(identity.get("path")) is not str
            or type(identity.get("pid")) is not int or identity["pid"] < 1
            or type(identity.get("started")) is not str or Path(identity.get("path", "")).resolve() != exe):
        raise AcquireError("client_identity_unavailable")
    return {**identity, "exe_sha256": exe_sha, "sdk_sha256": sdk_sha}


def _capture(path):
    _remaining()
    def read():
        before = path.stat()
        if not 0 < before.st_size <= _MAX_BYTES or before.st_size % 32:
            raise AcquireError("invalid_day_capture")
        with path.open("rb") as source:
            raw = source.read(_MAX_BYTES + 1)
            opened = os.fstat(source.fileno())
        after = path.stat()
        signatures = [(s.st_size, s.st_mtime_ns, s.st_ino, s.st_dev) for s in (before, opened, after)]
        if signatures[0] != signatures[1] or signatures[0] != signatures[2] or len(raw) != before.st_size:
            raise AcquireError("cache_unstable")
        return raw, signatures[0]

    try:
        first, signature = read()
    except FileNotFoundError:
        return None
    time.sleep(0.25)
    try:
        second, next_signature = read()
    except FileNotFoundError:
        raise AcquireError("cache_unstable") from None
    if first != second or signature != next_signature:
        raise AcquireError("cache_unstable")
    _remaining()
    return first


def _state_directory(client_directory):
    if os.name != "nt" or not os.environ.get("LOCALAPPDATA"):
        raise AcquireError("windows_required")
    return Path(os.environ["LOCALAPPDATA"]) / "Anatrading/acquisition" / data_root_id(client_directory)


def _write(path, raw):
    with path.open("wb") as output:
        output.write(raw)
        output.flush()
        os.fsync(output.fileno())


def _save(record, state_directory):
    raw = json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    for path in (Path(record["evidence_directory"]) / "receipt.json", state_directory / "current.json"):
        temporary = path.with_suffix(".tmp")
        _write(temporary, raw)
        temporary.replace(path)


def _parameters(symbol, target_date, port):
    if type(symbol) is not str or symbol not in _SYMBOLS or type(port) is not int or not 1 <= port <= 65535 or port == 17709:
        raise AcquireError("invalid_acquisition_parameters")
    try:
        if not isinstance(target_date, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", target_date):
            raise ValueError
        target = date.fromisoformat(target_date)
        if target > datetime.now(timezone(timedelta(hours=8))).date():
            raise ValueError
    except ValueError:
        raise AcquireError("invalid_target_date") from None


def _config(root, port):
    status, raw = _request(port, "GET", "/api/config")
    value = _decode_json(raw)
    if (status != 200 or type(value) is not dict or value.get("data_root_id") != data_root_id(root)
            or type(value.get("csrf_token")) is not str or not value["csrf_token"]
            or type(value.get("formats")) is not list or _FORMAT not in value["formats"] or value.get("mode") != "retrospective"
            or type(value.get("max_upload_bytes")) is not int or value["max_upload_bytes"] < _MAX_BYTES):
        raise AcquireError("workbench_identity_mismatch")
    return value


def _expected(raw, record):
    interpretation = {"instrument": record["symbol"], "venue": record["symbol"][-2:], "asset_type": "stock"}
    decoded = decode(raw, _FORMAT, interpretation)
    previous, target = None, None
    for row in decoded.rows:
        if (row.label is None or previous is not None and row.label <= previous
                or any(row.values[field] is None for field in VALUE_FIELDS)):
            raise AcquireError("invalid_day_observations")
        previous = row.label
        if row.label == record["target_date"]:
            target = row
    manifest = {"raw_sha256": hashlib.sha256(raw).hexdigest(), "source_contract_id": _identity(decoded.contract),
                "contract": decoded.contract, "interpretation": interpretation, "versions": dict(VERSIONS),
                "qualification": "source_evidence_retrospective_only"}
    batch = _identity(manifest)
    snapshot = _identity({"batch_id": batch, "versions": dict(VERSIONS), "mode": "retrospective"})
    return manifest, batch, snapshot, target


def _verify_publication(record, raw, config, acknowledgement=None):
    port = record["port"]
    manifest, batch, snapshot, target = _expected(raw, record)
    if target is None:
        raise AcquireError("target_not_observed")
    if acknowledgement is not None and (
            type(acknowledgement.get("attempt_id")) is not str
            or not re.fullmatch(r"[0-9a-f]{32}", acknowledgement["attempt_id"])
            or type(acknowledgement.get("reused")) is not bool):
        raise AcquireError("publication_unverified")

    def get(path, name):
        status, content = _request(port, "GET", path)
        _write(Path(record["evidence_directory"]) / (name + ".json"), content)
        if status != 200:
            raise AcquireError("publication_unverified")
        return _decode_json(content)

    catalog = get("/api/snapshots", "catalog")
    attempts = get("/api/attempts", "attempts")
    if (type(catalog) is not dict or type(catalog.get("snapshots")) is not list
            or type(attempts) is not dict or type(attempts.get("attempts")) is not list):
        raise AcquireError("publication_unverified")
    found = [item for item in catalog["snapshots"] if type(item) is dict and item.get("snapshot_id") == snapshot
             and item.get("batch_id") == batch and item.get("manifest") == manifest]
    matching = [item for item in attempts["attempts"] if type(item) is dict and item.get("status") == "committed"
                and type(item.get("attempt_id")) is str and re.fullmatch(r"[0-9a-f]{32}", item["attempt_id"])
                and item.get("snapshot_id") == snapshot and item.get("batch_id") == batch
                and item.get("raw_sha256") == manifest["raw_sha256"]]
    if not found or not matching:
        raise AcquireError("publication_unverified")
    if acknowledgement is not None:
        matching = [item for item in matching if item.get("attempt_id") == acknowledgement.get("attempt_id")]
        if not matching or any(acknowledgement.get(key) != matching[0].get(key)
                               for key in ("status", "raw_sha256", "snapshot_id", "batch_id")):
            raise AcquireError("publication_unverified")
    selection = {"cutoff": record["target_date"], "ordinal_start": target.ordinal, "ordinal_end": target.ordinal}
    result = get(f"/api/query/{snapshot}?{urlencode(selection)}", "target-query")
    query = result.get("query", {}) if type(result) is dict else {}
    if type(query) is not dict:
        raise AcquireError("publication_unverified")
    expected_selection = dict(snapshot_id=snapshot, mode="retrospective", **selection,
                              fields=list(VALUE_FIELDS), versions=dict(VERSIONS))
    rows = query.get("rows", [])
    if (query.get("snapshot_id") != snapshot or query.get("batch_id") != batch or query.get("manifest") != manifest
            or query.get("selection") != expected_selection or query.get("query_id") != _identity(expected_selection)
            or not isinstance(rows, list) or len(rows) != 1 or type(rows[0]) is not dict or rows[0].get("ordinal") != target.ordinal
            or rows[0].get("label") != target.label or rows[0].get("tokens") != target.tokens
            or rows[0].get("values") != {key: decimal_text(target.values[key]) for key in VALUE_FIELDS}
            or rows[0].get("volume_shares") is not None or rows[0].get("amount_cny") is not None):
        raise AcquireError("publication_unverified")
    if (_config(record["root"], port)["csrf_token"] != config["csrf_token"]
            or hashlib.sha256(config["csrf_token"].encode()).hexdigest() != record["workbench_session_id"]):
        raise AcquireError("workbench_session_changed")
    record.update(status="committed", snapshot_id=snapshot, attempt_id=matching[-1]["attempt_id"],
                  raw_sha256=manifest["raw_sha256"], reconciled=acknowledgement is None,
                  reused=acknowledgement.get("reused") if acknowledgement is not None else None)


def _verify_failure(record, acknowledgement, config):
    attempt_id = acknowledgement.get("attempt_id")
    if type(attempt_id) is not str or not re.fullmatch(r"[0-9a-f]{32}", attempt_id):
        raise AcquireError("publication_unverified")
    status, content = _request(record["port"], "GET", "/api/attempts")
    _write(Path(record["evidence_directory"]) / "attempts.json", content)
    ledger = _decode_json(content)
    if status != 200 or type(ledger) is not dict or type(ledger.get("attempts")) is not list:
        raise AcquireError("publication_unverified")
    matching = [item for item in ledger["attempts"] if type(item) is dict and item.get("attempt_id") == attempt_id
                and item.get("status") == acknowledgement.get("status")
                and item.get("raw_sha256") == record["raw_sha256"] and item.get("format_id") == _FORMAT]
    if not matching or _config(record["root"], record["port"])["csrf_token"] != config["csrf_token"]:
        raise AcquireError("publication_unverified")
    record.update(status="failed", error_code="import_not_committed", attempt_id=attempt_id)


def _journal(path, client_directory):
    with path.open("rb") as source:
        record = _decode_json(source.read(_MAX_BYTES + 1))
    return _validate_journal(record, client_directory)


def _validate_journal(record, client_directory):
    required = {"run_id", "root", "data_root_id", "client_directory", "symbol", "target_date", "port",
                "status", "identity", "evidence_directory"}
    if (type(record) is not dict or not required <= record.keys()
            or any(type(record[key]) is not str for key in
                   ("root", "data_root_id", "client_directory", "evidence_directory", "status"))
            or not isinstance(record["run_id"], str) or not re.fullmatch(r"[0-9a-f]{32}", record["run_id"])
            or record["client_directory"] != str(client_directory)
            or record["data_root_id"] != data_root_id(record["root"])
            or type(record["identity"]) is not dict
            or record["status"] not in _TERMINAL and not {"path", "pid", "started", "exe_sha256", "sdk_sha256"} <= record["identity"].keys()
            or record["status"] not in {*_TERMINAL, "preparing", "refresh_unknown", "publication_unknown"}
            or Path(record["evidence_directory"]).resolve() != Path(record["root"]).resolve() / "acquisition" / record["run_id"]):
        raise AcquireError("invalid_acquisition_journal")
    if record["status"] == "publication_unknown" and (
            type(record.get("workbench_session_id")) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", record["workbench_session_id"])
            or type(record.get("raw_sha256")) is not str
            or not re.fullmatch(r"[0-9a-f]{64}", record["raw_sha256"])):
        raise AcquireError("invalid_acquisition_journal")
    if record["status"] not in _TERMINAL:
        identity = record["identity"]
        try:
            valid_start = type(identity["started"]) is str and datetime.fromisoformat(identity["started"]).tzinfo is not None
        except ValueError:
            valid_start = False
        if (type(identity["pid"]) is not int or identity["pid"] < 1 or not valid_start
                or type(identity["path"]) is not str or Path(identity["path"]).resolve() != client_directory / "TdxW.exe"
                or identity["exe_sha256"] != _EXE_SHA or identity["sdk_sha256"] != _SDK_SHA):
            raise AcquireError("invalid_acquisition_journal")
    _parameters(record["symbol"], record["target_date"], record["port"])
    return record


def _recover_locked(old, state):
    """Read-only publication recovery; never starts a new acquisition."""
    try:
        saved = Path(old["evidence_directory"]).resolve()
        with _inside(saved / "after.day", saved).open("rb") as source:
            raw = source.read(_MAX_BYTES + 1)
        if len(raw) > _MAX_BYTES or hashlib.sha256(raw).hexdigest() != old.get("raw_sha256"):
            raise AcquireError("captured_raw_corrupt")
        config = _config(old["root"], old["port"])
        if hashlib.sha256(config["csrf_token"].encode()).hexdigest() != old.get("workbench_session_id"):
            raise AcquireError("workbench_session_changed")
        _verify_publication(old, raw, config)
    except (AcquireError, OSError) as error:
        old["error_code"] = getattr(error, "code", "captured_raw_unavailable")
        if old["status"] == "committed":
            # A saved terminal receipt is not current proof of readable publication.
            return None
    _save(old, state)
    return old


def acquire(root, client_directory, symbol, target_date, *, port=8765):
    _parameters(symbol, target_date, port)
    root, client_directory = Path(root).resolve(), Path(client_directory).resolve()
    state = _state_directory(client_directory)
    state.mkdir(parents=True, exist_ok=True)
    with _DirectoryLock(state):
        from .tdx_schedule import _read_control

        control = _read_control(state, client_directory)
        if control is not None and control["active"] is not None:
            raise AcquireError("schedule_dispatch_unresolved")
        from .tdx_recovery import recovery_gate

        recovered = recovery_gate(state, client_directory)
        if recovered is not None:
            return recovered
        current = state / "current.json"
        if current.exists():
            old = _journal(current, client_directory)
            if old["status"] not in _TERMINAL:
                if old["status"] == "publication_unknown":
                    if old["data_root_id"] != data_root_id(root) or old["port"] != port:
                        raise AcquireError("acquisition_target_mismatch")
                    return _recover_locked(old, state)
                raise AcquireError("client_task_unresolved")
        return _collect_locked(root, client_directory, symbol, target_date, port, state)


def _collect_locked(root, client_directory, symbol, target_date, port, state, *,
                    run_id=None, association=None, on_prepared=None):
    run_id = run_id or uuid.uuid4().hex
    directory = root / "acquisition" / run_id
    directory.mkdir(parents=True, exist_ok=False)
    record = dict(run_id=run_id, root=str(root), data_root_id=data_root_id(root),
                  client_directory=str(client_directory), symbol=symbol, target_date=target_date, port=port,
                  status="preparing", identity={}, evidence_directory=str(directory),
                  started_at_utc=datetime.now(timezone.utc).isoformat(), observations=[],
                  coverage="unknown", units="unknown", target_observed=False)
    if association is not None:
        record.update(association)
        _save(record, state)
        on_prepared(record)
    try:
        _remaining()
        config = _config(root, port)
        record["workbench_session_id"] = hashlib.sha256(config["csrf_token"].encode()).hexdigest()
        identity = _client_identity(client_directory)
        record["identity"] = identity
        venue, code = symbol[-2:].lower(), symbol[:6]
        path = _inside(client_directory / f"vipdoc/{venue}/lday/{venue}{code}.day", client_directory)
        before = _capture(path)
        record["cache_before"] = "absent" if before is None else hashlib.sha256(before).hexdigest()
        if before is not None:
            _write(directory / "before.day", before)
        request_id = int(run_id[:8], 16)
        payload = json.dumps({"id": request_id, "method": "refresh_kline",
                              "params": {"stock_list": [symbol], "period": "1d"}}, separators=(",", ":")).encode()
        _write(directory / "refresh-request.json", payload)
        observed = _client_identity(client_directory)
        record["observations"].append(observed)
        if observed != identity:
            raise AcquireError("client_session_changed")
        record.update(status="refresh_unknown", request_sha256=hashlib.sha256(payload).hexdigest())
        _save(record, state)
        try:
            status, response = _request(17709, "POST", "/", payload, {"Content-Type": "application/json"}, budget=45)
        except (AcquireError, OSError) as error:
            _write(directory / "refresh-response.bin", getattr(error, "raw", b""))
            try:
                record["observations"].append(_client_identity(client_directory))
            except (AcquireError, OSError) as identity_error:
                record["identity_after_error"] = getattr(identity_error, "code", "client_identity_unavailable")
            _save(record, state)
            raise
        _write(directory / "refresh-response.bin", response)
        record.update(http_status=status, response_sha256=hashlib.sha256(response).hexdigest())
        observed = _client_identity(client_directory)
        record["observations"].append(observed)
        _save(record, state)
        if observed != identity or status != 200:
            raise AcquireError("refresh_result_unknown")
        _refresh_result(response, request_id)
        raw = _capture(_inside(path, client_directory))
        if raw is None:
            record.update(status="not_covered", capture_state="not_covered")
        else:
            _write(directory / "after.day", raw)
            observed = _client_identity(client_directory)
            record["observations"].append(observed)
            if observed != identity:
                raise AcquireError("client_session_changed")
            _remaining()
            manifest, _, _, target = _expected(raw, record)
            record.update(raw_sha256=manifest["raw_sha256"], target_observed=target is not None)
            record["capture_state"] = ("not_covered" if target is None else
                                       "unchanged_target_observed" if raw == before else "new_content")
            if target is None:
                record["status"] = "not_covered"
            else:
                record["status"] = "publication_unknown"
                _save(record, state)
                parameters = urlencode(dict(format_id=_FORMAT, filename=path.name, **manifest["interpretation"]))
                headers = {"Origin": f"http://127.0.0.1:{port}", "X-Anatrading-Token": config["csrf_token"],
                           "Content-Type": "application/octet-stream"}
                acknowledgement = None
                failure = None
                try:
                    status, reply = _request(port, "POST", f"/api/import?{parameters}", raw, headers)
                    _write(directory / "import-response.json", reply)
                    parsed = _decode_json(reply)
                    if status == 200 and type(parsed) is dict and type(parsed.get("attempt")) is dict:
                        attempt = parsed["attempt"]
                        if type(attempt.get("status")) is not str:
                            raise AcquireError("publication_unverified")
                        if attempt.get("status") == "committed":
                            acknowledgement = attempt
                        elif attempt.get("status") in {"failed", "rejected", "cancelled"}:
                            failure = attempt
                except (AcquireError, OSError) as error:
                    _write(directory / "import-response.json", getattr(error, "raw", b""))
                if failure is not None:
                    _verify_failure(record, failure, config)
                else:
                    _verify_publication(record, raw, config, acknowledgement)
    except (AcquireError, OSError, ValueError) as error:
        record["error_code"] = getattr(error, "code", "acquisition_io_error")
        if record["status"] == "preparing":
            record["status"] = "failed"
    _save(record, state)
    return record
