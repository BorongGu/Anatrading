"""Acquisition fault boundaries use synthetic cache bytes and a local ASGI writer."""
import importlib
import hashlib
import json
import os
import socket
import struct
import threading
import time

import pytest
from fastapi.testclient import TestClient

from anatrading.store import EvidenceStore, StoreError, _DirectoryLock
from anatrading.workbench import create_app


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows acquisition locks")
SYMBOL = "600059.SH"
TARGET = "2026-09-30"


@pytest.fixture
def module():
    return importlib.import_module("anatrading.tdx_acquisition")


def encoded(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False).encode()


def day(date=20260930, volume=104535745):
    return struct.pack("<5If2I", date, 1000, 1100, 900, 1050, 1205814912.0, volume, 0)


@pytest.mark.parametrize("symbol,date,port", [
    ("600059.SH&evil=1", TARGET, 8765), ("../600059.SH", TARGET, 8765),
    ("600000.SH", TARGET, 8765), ("600059.sh", TARGET, 8765),
    (SYMBOL, "2026-02-30", 8765), (SYMBOL, "2999-01-01", 8765),
    (SYMBOL, "2026-09-30&evil=1", 8765), (SYMBOL, TARGET, 0),
    (SYMBOL, TARGET, 65536), (SYMBOL, TARGET, True),
])
def test_invalid_parameters_never_probe_or_request(module, tmp_path, monkeypatch, symbol, date, port):
    calls = []
    monkeypatch.setattr(module, "_http", lambda *a, **k: calls.append("http"))
    monkeypatch.setattr(module, "_client_identity", lambda *a: calls.append("identity"))
    with pytest.raises(module.AcquireError) as caught:
        module.acquire(tmp_path / "root", tmp_path / "client", symbol, date, port=port)
    assert caught.value.code
    assert calls == []


@pytest.mark.parametrize("raw", [
    b'{"x":1,"x":1}', b'{"x":{"a":1,"a":2}}', b'{"x":NaN}',
    b'{"x":Infinity}', b'{"x":-Infinity}', b'{} garbage', b'\xff',
    b' ' * (1024 * 1024 + 1),
], ids=["duplicate", "nested-duplicate", "nan", "infinity", "negative-infinity", "trailing", "utf8", "limit"])
def test_strict_json_rejects_ambiguous_and_unbounded_input(module, raw):
    with pytest.raises(module.AcquireError) as caught:
        module._decode_json(raw)
    assert caught.value.code


@pytest.mark.parametrize("value", [
    {"id": True, "result": {"ErrorId": "0"}},
    {"id": 102, "result": {"ErrorId": "0"}},
    {"id": 101, "result": {"ErrorId": 0}},
    {"id": 101, "result": {"ErrorId": "1"}},
    {"id": 101, "result": []}, {"id": 101},
])
def test_refresh_rejects_wrong_rpc_identity_or_business_status(module, value):
    with pytest.raises(module.AcquireError) as caught:
        module._refresh_result(encoded(value), 101)
    assert caught.value.code


def test_wrong_workbench_root_stops_before_refresh(module, tmp_path, monkeypatch):
    calls = []
    state = tmp_path / "state"
    state.mkdir()
    monkeypatch.setattr(module, "_state_directory", lambda client: state)
    def request(port, method, path, body=b"", headers=None, *, budget=15):
        calls.append((port, method, path))
        assert method == "GET" and path == "/api/config" and port == 8765
        return 200, encoded({"data_root_id": module.data_root_id(tmp_path / "other"),
                             "csrf_token": "synthetic", "formats": ["tdx-public-day-v1"],
                             "max_upload_bytes": 16 * 1024 * 1024})
    monkeypatch.setattr(module, "_http", request)
    outcome = module.acquire(tmp_path / "root", tmp_path / "client", SYMBOL, TARGET)
    assert outcome["status"] == "failed"
    assert calls == [(8765, "GET", "/api/config")]


@pytest.fixture
def environment(module, tmp_path, monkeypatch):
    root, client_directory, state = tmp_path / "root", tmp_path / "client", tmp_path / "state"
    cache = client_directory / "vipdoc" / "sh" / "lday" / "sh600059.day"
    cache.parent.mkdir(parents=True)
    state.mkdir()
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<title>Synthetic acquisition</title>", encoding="utf-8")
    identity = {"path": str(client_directory / "TdxW.exe"), "pid": 12345,
                "started": "2026-10-08T03:19:49Z",
                "exe_sha256": "4c822464613fabe4b4235edf171b031d8b209ef68bd7d06dea403e1cd54c1fad",
                "sdk_sha256": "241358919fd394751a46bb51d64374eb0216f7c22bfa47bc13c48418ba26b1b0"}
    monkeypatch.setattr(module, "_state_directory", lambda directory: state)
    monkeypatch.setattr(module, "_client_identity", lambda directory: dict(identity))
    app = create_app(root, web_directory=web)
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        class Environment:
            raw = day(20260928, 71534143) + day(20260929, 69097909) + day()
            refresh_fault = None
            publication_fault = None
            calls = []

            def acquire(self, destination=None):
                try:
                    return module.acquire(destination or root, client_directory, SYMBOL, TARGET)
                except (module.AcquireError, StoreError) as error:
                    # CLI translates these typed refusals without replacing the journal.
                    return {"status": "failed", "error_code": error.code}

            def posts(self, port):
                return [call for call in self.calls if call[0] == port and call[1] == "POST"]

            def http(self, port, method, path, body=b"", headers=None, *, budget=15):
                self.calls.append((port, method, path))
                assert budget > 0
                if port == 17709:
                    assert method == "POST"
                    payload = json.loads(body)
                    assert payload["method"] == "refresh_kline"
                    assert payload["params"] == {"stock_list": [SYMBOL], "period": "1d"}
                    if self.refresh_fault == "timeout":
                        raise TimeoutError("synthetic refresh timeout")
                    if self.raw is not None:
                        cache.write_bytes(self.raw)
                    response = encoded({"id": payload["id"], "result": {"ErrorId": "0"}})
                    if self.refresh_fault == "business":
                        response = encoded({"id": payload["id"], "result": {"ErrorId": "1"}})
                    if self.refresh_fault == "duplicate":
                        response = b'{"id":1,"id":1,"result":{"ErrorId":"0"}}'
                    if self.refresh_fault == "session":
                        identity["pid"] += 1
                    return 200, response
                assert port == 8765
                if method == "POST" and self.publication_fault == "before":
                    raise OSError("synthetic disconnect before submission")
                if method == "POST" and self.publication_fault in {"forged-failed-missing", "forged-failed-id"}:
                    attempt = {"status": "failed", "format_id": "tdx-public-day-v1",
                               "raw_sha256": hashlib.sha256(body).hexdigest()}
                    if self.publication_fault == "forged-failed-id":
                        attempt["attempt_id"] = "1" * 32
                    return 200, encoded({"attempt": attempt})
                response = client.request(method, path, content=body, headers=headers or {})
                if method == "POST" and self.publication_fault == "raw-missing":
                    for raw_path in (root / "raw").rglob("*"):
                        if raw_path.is_file():
                            raw_path.unlink()
                if method == "GET" and path == "/api/config" and self.publication_fault == "session":
                    if self.posts(8765):
                        config = response.json()
                        config["csrf_token"] = "changed-synthetic-session"
                        return 200, encoded(config)
                if method == "GET" and path.startswith("/api/query/") and self.publication_fault == "query":
                    raise TimeoutError("synthetic query timeout")
                if method == "POST" and self.publication_fault == "after":
                    raise OSError("synthetic receipt lost after submission")
                return response.status_code, response.content

        env = Environment()
        env.root, env.client_directory, env.state, env.cache = root, client_directory, state, cache
        env.client, env.identity = client, identity
        monkeypatch.setattr(module, "_http", env.http)
        yield env


def test_acquires_through_existing_writer_and_reuses_identical_content(module, environment):
    env = environment
    with pytest.raises(StoreError) as caught:
        EvidenceStore(env.root)
    assert caught.value.code == "data_directory_busy"
    first = env.acquire()
    assert first["status"] == "committed" and first["reconciled"] is False
    second = env.acquire()
    assert second["status"] == "committed" and second["reconciled"] is False
    assert len(env.posts(17709)) == 2 and len(env.posts(8765)) == 2
    attempts = env.client.get("/api/attempts").json()["attempts"]
    snapshots = env.client.get("/api/snapshots").json()["snapshots"]
    assert len(attempts) == 2 and len(snapshots) == 1
    assert all(attempt["status"] == "committed" for attempt in attempts)
    assert second["reused"] is True
    assert attempts[0]["snapshot_id"] == attempts[1]["snapshot_id"]
    assert all(call[2] != "get_market_data" for call in env.calls)


@pytest.mark.parametrize("raw,status", [(b"", "refresh_unknown"), (b"x" * 31, "refresh_unknown"),
                                      (day(20260929), "not_covered"), (None, "not_covered")],
                         ids=["empty", "truncated", "target-absent", "file-absent"])
def test_empty_truncated_or_uncovered_cache_never_publishes(environment, raw, status):
    env = environment
    env.raw = raw
    result = env.acquire()
    assert result["status"] == status
    assert len(env.posts(17709)) == 1
    assert env.posts(8765) == []
    assert env.client.get("/api/attempts").json()["attempts"] == []


@pytest.mark.parametrize("fault", ["timeout", "business", "duplicate"])
def test_uncertain_refresh_blocks_same_and_other_root_without_new_post(environment, fault):
    env = environment
    env.refresh_fault = fault
    assert env.acquire()["status"] == "refresh_unknown"
    posted = len(env.posts(17709))
    assert env.acquire()["status"] != "committed"
    assert env.acquire(env.root.parent / "other-root")["status"] != "committed"
    assert len(env.posts(17709)) == posted == 1
    assert env.posts(8765) == []


def test_refresh_identity_change_stops_then_allows_proven_new_session(environment):
    env = environment
    env.refresh_fault = "session"
    assert env.acquire()["status"] == "refresh_unknown"
    assert len(env.posts(17709)) == 1 and env.posts(8765) == []
    env.refresh_fault = None
    assert env.acquire()["status"] == "committed"
    assert len(env.posts(17709)) == 2 and len(env.posts(8765)) == 1


def test_client_global_lock_blocks_cross_root_before_network(environment):
    env = environment
    with _DirectoryLock(env.state):
        assert env.acquire()["status"] == "failed"
        assert env.acquire(env.root.parent / "other-root")["status"] == "failed"
    assert env.calls == []


def test_lost_request_before_publication_remains_unknown_without_resubmission(environment):
    env = environment
    env.publication_fault = "before"
    assert env.acquire()["status"] == "publication_unknown"
    assert env.client.get("/api/snapshots").json()["snapshots"] == []
    before = len(env.posts(17709)), len(env.posts(8765))
    env.publication_fault = None
    assert env.acquire()["status"] == "publication_unknown"
    assert (len(env.posts(17709)), len(env.posts(8765))) == before == (1, 1)


def test_lost_receipt_after_commit_reconciles_without_duplicate_post(environment):
    env = environment
    env.publication_fault = "after"
    result = env.acquire()
    if result["status"] == "publication_unknown":
        env.publication_fault = None
        result = env.acquire()
    assert result["status"] == "committed" and result["reconciled"] is True
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1
    assert len(env.client.get("/api/attempts").json()["attempts"]) == 1
    assert len(env.client.get("/api/snapshots").json()["snapshots"]) == 1


def test_corrupt_pending_journal_is_preserved_and_blocks_network(environment):
    env = environment
    env.publication_fault = "before"
    assert env.acquire()["status"] == "publication_unknown"
    journal = env.state / "current.json"
    journal.write_bytes(b'{"broken":true,')
    env.calls.clear()
    assert env.acquire()["status"] == "failed"
    assert env.calls == [] and journal.read_bytes() == b'{"broken":true,'


def test_pending_publication_with_missing_raw_blocks_post(environment):
    env = environment
    env.publication_fault = "before"
    assert env.acquire()["status"] == "publication_unknown"
    removed = []
    for path in (env.root / "acquisition").rglob("*"):
        if path.is_file() and path.read_bytes() == env.raw:
            path.unlink()
            removed.append(path)
    assert removed
    env.calls.clear()
    assert env.acquire()["status"] == "publication_unknown"
    assert env.posts(17709) == env.posts(8765) == []


@pytest.mark.parametrize("fault", ["raw-missing", "query", "session"])
def test_catalog_commit_without_raw_query_or_same_session_is_not_success(environment, fault):
    env = environment
    env.publication_fault = fault
    assert env.acquire()["status"] == "publication_unknown"
    assert len(env.client.get("/api/snapshots").json()["snapshots"]) == 1
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1


def test_offline_client_stops_before_refresh(module, environment, monkeypatch):
    env = environment
    def offline(directory):
        raise module.AcquireError("synthetic_client_offline")
    monkeypatch.setattr(module, "_client_identity", offline)
    assert env.acquire()["status"] == "failed"
    assert env.posts(17709) == env.posts(8765) == []


def test_capture_rejects_unstable_file_before_refresh(module, environment, monkeypatch):
    env = environment
    def unstable(path):
        raise module.AcquireError("synthetic_unstable_capture")
    monkeypatch.setattr(module, "_capture", unstable)
    assert env.acquire()["status"] == "failed"
    assert env.posts(17709) == env.posts(8765) == []


@pytest.mark.parametrize("phase", ["header", "body"])
def test_http_slow_chunks_do_not_reset_absolute_deadline(module, phase):
    """A localhost fixture drips valid bytes slower than the total request budget."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    server.settimeout(2)
    port = server.getsockname()[1]
    def slow_response():
        try:
            connection, _ = server.accept()
            with connection:
                connection.recv(4096)
                if phase == "header":
                    connection.sendall(b"HTTP/1.1 200 OK\r\n")
                    for _ in range(20):
                        connection.sendall(b"X-Synthetic: drip\r\n")
                        time.sleep(0.04)
                    connection.sendall(b"Content-Length: 0\r\nConnection: close\r\n\r\n")
                else:
                    connection.sendall(b"HTTP/1.1 200 OK\r\nContent-Length: 20\r\nConnection: close\r\n\r\n")
                    for _ in range(20):
                        connection.sendall(b"x")
                        time.sleep(0.04)
        except OSError:
            pass
        finally:
            server.close()
    worker = threading.Thread(target=slow_response, daemon=True)
    worker.start()
    started = time.monotonic()
    try:
        with pytest.raises((module.AcquireError, OSError, TimeoutError)):
            module._http(port, "GET", "/synthetic", budget=0.12)
        assert time.monotonic() - started < 0.5
    finally:
        worker.join(timeout=2)
        assert not worker.is_alive()


def test_publication_recovery_refuses_new_workbench_session_with_committed_raw(module, environment, monkeypatch):
    env = environment
    env.publication_fault = "query"
    assert env.acquire()["status"] == "publication_unknown"
    assert len(env.client.get("/api/snapshots").json()["snapshots"]) == 1
    env.publication_fault = None
    original = env.http
    def restarted(port, method, path, body=b"", headers=None, *, budget=15):
        status, raw = original(port, method, path, body, headers, budget=budget)
        if port == 8765 and path == "/api/config":
            config = json.loads(raw)
            config["csrf_token"] = "restarted-synthetic-service"
            return status, encoded(config)
        return status, raw
    monkeypatch.setattr(module, "_http", restarted)
    assert env.acquire()["status"] == "publication_unknown"
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1


@pytest.mark.parametrize("field,value", [
    ("pid", 0), ("pid", True), ("pid", "12345"),
    ("started", "invalid"), ("started", "2026-10-08T03:19:49"),
    ("path", "C:/other/TdxW.exe"), ("exe_sha256", "0" * 64), ("sdk_sha256", "0" * 64),
], ids=["zero-pid", "bool-pid", "str-pid", "bad-start", "naive-start", "wrong-path", "wrong-exe", "wrong-sdk"])
def test_damaged_refresh_identity_cannot_unlock_new_task(environment, field, value):
    env = environment
    env.refresh_fault = "timeout"
    assert env.acquire()["status"] == "refresh_unknown"
    journal = env.state / "current.json"
    record = json.loads(journal.read_bytes())
    record["identity"][field] = value
    changed = encoded(record)
    journal.write_bytes(changed)
    env.calls.clear()
    assert env.acquire()["status"] == "failed"
    assert env.calls == [] and journal.read_bytes() == changed


@pytest.mark.parametrize("fault", ["forged-failed-missing", "forged-failed-id"])
def test_forged_failed_receipt_without_matching_ledger_keeps_publication_unknown(environment, fault):
    env = environment
    env.publication_fault = fault
    assert env.acquire()["status"] == "publication_unknown"
    assert env.client.get("/api/attempts").json()["attempts"] == []
    assert env.acquire()["status"] == "publication_unknown"
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1


def test_terminal_offline_initialization_can_retry_after_client_available(module, environment, monkeypatch):
    env = environment
    def offline(directory):
        raise module.AcquireError("synthetic_client_offline")
    monkeypatch.setattr(module, "_client_identity", offline)
    assert env.acquire()["status"] == "failed"
    assert json.loads((env.state / "current.json").read_bytes())["identity"] == {}
    monkeypatch.setattr(module, "_client_identity", lambda directory: dict(env.identity))
    assert env.acquire()["status"] == "committed"
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1


@pytest.mark.parametrize("status_value", [[], {}], ids=["list", "dict"])
def test_malformed_receipt_status_can_only_commit_by_readable_reconciliation(module, environment, monkeypatch, status_value):
    env = environment
    original = env.http
    def malformed(port, method, path, body=b"", headers=None, *, budget=15):
        status, raw = original(port, method, path, body, headers, budget=budget)
        if port == 8765 and method == "POST":
            response = json.loads(raw)
            response["attempt"]["status"] = status_value
            return status, encoded(response)
        return status, raw
    monkeypatch.setattr(module, "_http", malformed)
    result = env.acquire()
    assert result["status"] == "committed" and result["reconciled"] is True
    assert result["reused"] is None
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1
    assert len(env.client.get("/api/attempts").json()["attempts"]) == 1


@pytest.mark.parametrize("defect", ["missing-id", "invalid-id", "nonbool-reused"])
def test_committed_receipt_with_invalid_identity_or_reuse_remains_unknown(module, environment, monkeypatch, defect):
    env = environment
    original = env.http
    def malformed(port, method, path, body=b"", headers=None, *, budget=15):
        status, raw = original(port, method, path, body, headers, budget=budget)
        if port == 8765 and method == "POST":
            response = json.loads(raw)
            attempt = response["attempt"]
            if defect == "missing-id":
                attempt.pop("attempt_id")
            elif defect == "invalid-id":
                attempt["attempt_id"] = "not-an-attempt"
            else:
                attempt["reused"] = 1
            return status, encoded(response)
        return status, raw
    monkeypatch.setattr(module, "_http", malformed)
    assert env.acquire()["status"] == "publication_unknown"
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1
    assert len(env.client.get("/api/snapshots").json()["snapshots"]) == 1


def test_receipt_loss_and_committed_ledger_missing_identity_never_promotes_or_reposts(module, environment, monkeypatch):
    env = environment
    env.publication_fault = "after"
    original = env.http
    def damaged_ledger(port, method, path, body=b"", headers=None, *, budget=15):
        status, raw = original(port, method, path, body, headers, budget=budget)
        if port == 8765 and method == "GET" and path == "/api/attempts":
            ledger = json.loads(raw)
            for attempt in ledger["attempts"]:
                attempt.pop("attempt_id")
            return status, encoded(ledger)
        return status, raw
    monkeypatch.setattr(module, "_http", damaged_ledger)
    assert env.acquire()["status"] == "publication_unknown"
    env.publication_fault = None
    assert env.acquire()["status"] == "publication_unknown"
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1
    assert len(env.client.get("/api/snapshots").json()["snapshots"]) == 1
