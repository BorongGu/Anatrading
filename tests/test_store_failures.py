"""Contract expectations for publication, recovery and rejected payloads.

Only synthetic records enter these tests. Process-death cases use os._exit so
Python cleanup cannot make an incomplete transaction appear crash-safe.
"""

import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

import duckdb
import pytest

from anatrading.store import EvidenceStore, StoreError


pytestmark = pytest.mark.skipif(os.name != "nt", reason="The v1 store targets Windows OS locks")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FORMAT = "tdx-public-text-v1"
TDX_SAMPLE = (
    "601577 合成测试 1分钟线 不复权\r\n"
    "      日期\t    时间\t    开盘\t    最高\t    最低\t    收盘\t    成交量\t    成交额\r\n"
    "2021/02/26,0931,10.00,10.02,9.99,10.01,100,1001.00\r\n"
    "2021/02/26,0932,10.01,10.03,10.00,10.02,200,2004.00\r\n"
    "数据来源:通达信\r\n"
).encode("gbk")
SENSITIVE_MARKER = "SYNTHETIC_AUTH_SECRET_DO_NOT_PERSIST_74f2"
CRASH_EXIT = 73

CRASH_SCRIPT = """
import base64
import os
from pathlib import Path
import sys
from anatrading.store import EvidenceStore

def checkpoint(stage):
    if stage == sys.argv[2]:
        os._exit(73)

with EvidenceStore(Path(sys.argv[1]), checkpoint=checkpoint) as store:
    store.import_bytes(base64.b64decode(sys.argv[3]), 'tdx-public-text-v1')
raise AssertionError('Requested checkpoint was not reached')
"""

LOCK_PROBE_SCRIPT = """
import json
from pathlib import Path
import sys
from anatrading.store import EvidenceStore, StoreError

try:
    with EvidenceStore(Path(sys.argv[1])):
        result = {'opened': True}
except StoreError as exc:
    result = {'opened': False, 'code': exc.code}
print(json.dumps(result))
"""


def run_child(script, *arguments):
    environment = os.environ.copy()
    source_path = str(PROJECT_ROOT / "src")
    previous_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = source_path + (os.pathsep + previous_path if previous_path else "")
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-c", script, *map(str, arguments)],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=False,
    )


def lock_probe(root):
    result = run_child(LOCK_PROBE_SCRIPT, root)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def raw_path(root, raw=TDX_SAMPLE):
    digest = hashlib.sha256(raw).hexdigest()
    return root / "raw" / digest[:2] / digest


@pytest.mark.parametrize(
    ("stage", "expected_status", "expected_snapshots"),
    [
        ("attempt_started", "interrupted", 0),
        ("raw_published", "interrupted", 0),
        ("before_commit", "interrupted", 0),
        ("after_commit", "committed", 1),
    ],
)
def test_process_death_recovers_the_durable_outcome(tmp_path, stage, expected_status, expected_snapshots):
    root = tmp_path / "evidence"
    result = run_child(CRASH_SCRIPT, root, stage, base64.b64encode(TDX_SAMPLE).decode("ascii"))
    assert result.returncode == CRASH_EXIT, result.stderr

    with EvidenceStore(root) as store:
        attempts = store.attempts()
        assert len(attempts) == 1
        previous = attempts[0]
        assert previous["status"] == expected_status
        snapshots = store.list_snapshots()
        assert len(snapshots) == expected_snapshots
        assert raw_path(root).exists() == (stage != "attempt_started")
        if expected_snapshots:
            assert snapshots[0]["snapshot_id"] == previous["snapshot_id"]
            assert previous["batch_id"]
            committed_view = store.query(previous["snapshot_id"])
        else:
            assert previous["snapshot_id"] is None

        retried = store.import_bytes(TDX_SAMPLE, FORMAT, filename="retried.txt")
        assert retried["status"] == "committed"
        assert retried["attempt_id"] != previous["attempt_id"]
        assert len(store.list_snapshots()) == 1
        recovered = {attempt["attempt_id"]: attempt for attempt in store.attempts()}
        assert len(recovered) == 2
        assert recovered[previous["attempt_id"]]["status"] == expected_status
        assert recovered[retried["attempt_id"]]["status"] == "committed"
        if expected_snapshots:
            assert retried["batch_id"] == previous["batch_id"]
            assert retried["snapshot_id"] == previous["snapshot_id"]
            assert store.query(retried["snapshot_id"]) == committed_view
        assert raw_path(root).read_bytes() == TDX_SAMPLE


def test_same_content_from_bytes_and_file_has_one_batch_and_distinct_attempts(tmp_path):
    source = tmp_path / "renamed-source.txt"
    source.write_bytes(TDX_SAMPLE)
    root = tmp_path / "evidence"
    with EvidenceStore(root) as store:
        first = store.import_bytes(TDX_SAMPLE, FORMAT, filename="first.txt")
        second = store.import_bytes(TDX_SAMPLE, FORMAT, filename="different-name.txt")
        third = store.import_file(source, FORMAT)
        results = [first, second, third]
        assert all(result["status"] == "committed" for result in results)
        assert len({result["attempt_id"] for result in results}) == 3
        assert len({result["batch_id"] for result in results}) == 1
        assert len({result["snapshot_id"] for result in results}) == 1
        assert len(store.list_snapshots()) == 1
        assert len(store.attempts()) == 3
        assert all(attempt["status"] == "committed" for attempt in store.attempts())
    objects = [path for path in (root / "raw").rglob("*") if path.is_file()]
    assert objects == [raw_path(root)]


@pytest.mark.parametrize("stage", ["attempt_started", "raw_published"])
def test_accepted_cancellation_never_publishes_a_snapshot(tmp_path, stage):
    requested = False
    reached = []

    def checkpoint(current):
        nonlocal requested
        reached.append(current)
        if current == stage:
            requested = True

    with EvidenceStore(tmp_path / "evidence", checkpoint=checkpoint) as store:
        result = store.import_bytes(TDX_SAMPLE, FORMAT, cancelled=lambda: requested)
        assert stage in reached
        assert "transaction_open" not in reached
        assert result["status"] == "cancelled"
        assert result["snapshot_id"] is None
        assert store.list_snapshots() == []
        attempts = store.attempts()
        assert len(attempts) == 1
        assert attempts[0]["attempt_id"] == result["attempt_id"]
        assert attempts[0]["status"] == "cancelled"


@pytest.mark.parametrize("stage", ["transaction_open", "before_commit", "after_commit"])
def test_cancellation_after_the_acceptance_boundary_reports_commit(tmp_path, stage):
    requested = False

    def checkpoint(current):
        nonlocal requested
        if current == stage:
            requested = True

    with EvidenceStore(tmp_path / "evidence", checkpoint=checkpoint) as store:
        result = store.import_bytes(TDX_SAMPLE, FORMAT, cancelled=lambda: requested)
        assert requested, "The requested synchronization point was not reached"
        assert result["status"] == "committed"
        assert len(store.list_snapshots()) == 1
        assert store.list_snapshots()[0]["snapshot_id"] == result["snapshot_id"]
        assert store.attempts()[0]["status"] == "committed"


def test_injected_disk_full_records_failure_without_publishing(tmp_path):
    armed = True

    def checkpoint(stage):
        nonlocal armed
        if stage == "attempt_started" and armed:
            armed = False
            raise OSError(errno.ENOSPC, "synthetic disk-full fault")

    root = tmp_path / "evidence"
    with EvidenceStore(root, checkpoint=checkpoint) as store:
        result = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert not armed
        assert result["status"] == "failed"
        assert result["error_code"] == "storage_io_error"
        assert result["snapshot_id"] is None
        assert store.list_snapshots() == []
        assert store.attempts()[0]["status"] == "failed"
        assert not raw_path(root).exists()
        retried = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert retried["status"] == "committed"
        assert retried["attempt_id"] != result["attempt_id"]
        assert len(store.list_snapshots()) == 1


def test_raw_rename_failure_does_not_commit_a_batch(tmp_path, monkeypatch):
    root = tmp_path / "evidence"
    destination = raw_path(root)
    replace = os.replace
    injected = []

    def failing_replace(source, target, *args, **kwargs):
        if Path(target) == destination:
            injected.append(str(target))
            raise OSError(errno.EACCES, "synthetic raw-publish fault")
        return replace(source, target, *args, **kwargs)

    with EvidenceStore(root) as store:
        with monkeypatch.context() as patch:
            patch.setattr(os, "replace", failing_replace)
            result = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert injected, "The raw-object publication operation was not exercised"
        assert result["status"] == "failed"
        assert result["error_code"] == "storage_io_error"
        assert result["snapshot_id"] is None
        assert store.list_snapshots() == []
        assert store.attempts()[0]["status"] == "failed"
        assert not destination.exists()
        assert store.import_bytes(TDX_SAMPLE, FORMAT)["status"] == "committed"
        assert len(store.list_snapshots()) == 1


def test_missing_input_records_a_failed_attempt(tmp_path):
    with EvidenceStore(tmp_path / "evidence") as store:
        result = store.import_file(tmp_path / "missing.txt", FORMAT)
        assert result["status"] == "failed"
        assert result["error_code"] == "storage_io_error"
        assert result["snapshot_id"] is None
        assert store.list_snapshots() == []
        attempts = store.attempts()
        assert len(attempts) == 1
        assert attempts[0]["attempt_id"] == result["attempt_id"]
        assert attempts[0]["status"] == "failed"


@pytest.mark.parametrize(
    ("damage", "code"),
    [("changed", "raw_object_corrupt"), ("missing", "raw_object_missing")],
)
def test_snapshot_query_fails_closed_when_its_raw_evidence_is_damaged(tmp_path, damage, code):
    root = tmp_path / "evidence"
    with EvidenceStore(root) as store:
        imported = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert imported["status"] == "committed"
    path = raw_path(root)
    if damage == "changed":
        path.write_bytes(b"tampered synthetic evidence")
    else:
        path.unlink()
    with EvidenceStore(root) as store:
        with pytest.raises(StoreError) as caught:
            store.query(imported["snapshot_id"])
        assert caught.value.code == code
        assert len(store.list_snapshots()) == 1
    if damage == "changed":
        assert path.read_bytes() == b"tampered synthetic evidence"
    else:
        assert not path.exists()


def test_second_instance_is_rejected_and_lock_is_released_on_close(tmp_path):
    root = tmp_path / "evidence"
    with EvidenceStore(root):
        with pytest.raises(StoreError) as caught:
            with EvidenceStore(root):
                pytest.fail("A second store acquired the same data-root lock")
        assert caught.value.code == "data_directory_busy"
        assert lock_probe(root) == {"opened": False, "code": "data_directory_busy"}
    assert lock_probe(root) == {"opened": True}


def test_backup_keeps_the_operation_lock_after_database_close(tmp_path):
    root = tmp_path / "evidence"
    probes = []

    def checkpoint(stage):
        if stage == "backup_closed":
            probes.append(lock_probe(root))

    backup_directory = tmp_path / "backup"
    with EvidenceStore(root, checkpoint=checkpoint) as store:
        imported = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert imported["status"] == "committed"
        original = store.query(imported["snapshot_id"])
        manifest = store.backup(backup_directory)
        assert isinstance(manifest, dict)
        assert probes == [{"opened": False, "code": "data_directory_busy"}]
        assert store.query(imported["snapshot_id"]) == original
    restored_directory = tmp_path / "restored"
    EvidenceStore.restore(backup_directory, restored_directory)
    with EvidenceStore(restored_directory) as restored:
        assert restored.query(imported["snapshot_id"]) == original


def rejected_envelope(case):
    separator = "\x01"
    message_type = {"login": "01", "logout": "03"}.get(case, "96")
    method = {"login": "login", "logout": "logout", "method": "not_a_market_method"}.get(
        case, "query_history_k_data_plus"
    )
    user = "private_user" if case == "user" else "anonymous"
    code = "10003001" if case == "business_error" else "0"
    fields = "date,code,open,high,low,close,volume,amount,adjustflag"
    record = ["2021-02-26", "sh.601577", "10.00", "10.02", "9.99", "10.01", "100", "1001.00", "3"]
    if case == "fields":
        fields += ",auth_token"
        record.append(SENSITIVE_MARKER)
    body = separator.join(
        [code, SENSITIVE_MARKER, method, user, "1", "2000", json.dumps({"record": [record]}),
         "sh.601577", fields, "2021-02-26", "2021-02-26", "d", "3"]
    )
    header = f"00.9.10{separator}{message_type}{separator}{len(body.encode('utf-8')):010d}"
    assert len(header) == 21
    return (header + body).encode("utf-8")


@pytest.mark.parametrize("case", ["login", "logout", "method", "user", "business_error", "fields"])
def test_non_market_payload_is_never_archived(tmp_path, case, capsys, caplog):
    root = tmp_path / "evidence"
    raw = rejected_envelope(case)
    reached = []
    with EvidenceStore(root, checkpoint=reached.append) as store:
        result = store.import_bytes(raw, "baostock-decoded-v0.9.4", filename="response.txt")
        assert result["status"] == "rejected"
        assert result["raw_sha256"] is None
        assert result["batch_id"] is None
        assert result["snapshot_id"] is None
        assert result["error_code"]
        assert result["error_code"].isascii()
        assert all(character.isalnum() or character == "_" for character in result["error_code"])
        assert "raw_published" not in reached
        assert store.list_snapshots() == []
        attempts = store.attempts()
        assert len(attempts) == 1
        assert attempts[0]["status"] == "rejected"
        assert attempts[0]["raw_sha256"] is None
        assert attempts[0]["error_code"] == result["error_code"]
        assert SENSITIVE_MARKER not in json.dumps([result, attempts])
    output = capsys.readouterr()
    assert SENSITIVE_MARKER not in output.out + output.err + caplog.text
    for directory in ("raw", "staging", "quarantine"):
        assert not any(path.is_file() for path in (root / directory).rglob("*"))
    for path in root.rglob("*"):
        if path.is_file():
            assert SENSITIVE_MARKER.encode("ascii") not in path.read_bytes(), path.name


class CommitFault:
    """Inject once at the final import COMMIT, leaving recovery SQL usable."""

    def __init__(self, connection, apply_before_error, disconnect=False):
        self.connection = connection
        self.apply_before_error = apply_before_error
        self.disconnect = disconnect
        self.armed = False
        self.fired = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **kwargs):
        is_commit = statement.strip().rstrip(";").upper() in {"COMMIT", "COMMIT TRANSACTION"}
        if is_commit and self.armed and not self.fired:
            self.fired = True
            self.armed = False
            if self.apply_before_error:
                self.connection.execute(statement, *args, **kwargs)
            if self.disconnect:
                self.connection.close()
                raise duckdb.ConnectionException("synthetic connection loss at final COMMIT")
            raise duckdb.IOException("synthetic final-COMMIT failure")
        return self.connection.execute(statement, *args, **kwargs)


@pytest.mark.parametrize("commit_applied", [False, True], ids=["before_commit_applies", "after_commit_applies"])
def test_commit_exception_is_reconciled_with_the_durable_result(tmp_path, commit_applied):
    proxy = None

    def checkpoint(stage):
        if stage == "before_commit":
            proxy.armed = True

    with EvidenceStore(tmp_path / "evidence", checkpoint=checkpoint) as store:
        proxy = CommitFault(store.db, apply_before_error=commit_applied)
        store.db = proxy
        returned, raised = None, None
        try:
            returned = store.import_bytes(TDX_SAMPLE, FORMAT)
        except Exception as error:
            raised = error

        assert proxy.fired, "The final-COMMIT fault was not exercised"
        attempts = store.attempts()
        snapshots = store.list_snapshots()
        assert len(attempts) == 1
        expected_status = "committed" if commit_applied else "failed"
        assert attempts[0]["status"] == expected_status
        assert len(snapshots) == int(commit_applied)
        if not commit_applied:
            for table in ("batches", "observations", "snapshots"):
                assert store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
        assert raised is None, (
            f"Durable status is {expected_status}, but import raised "
            f"{type(raised).__name__}: {raised}"
        )
        assert returned["status"] == expected_status
        if commit_applied:
            assert returned["snapshot_id"] == snapshots[0]["snapshot_id"] == attempts[0]["snapshot_id"]
            assert returned["batch_id"] == attempts[0]["batch_id"]
            assert store.query(returned["snapshot_id"])["counts"]["selected_rows"] == 2
        else:
            assert returned["snapshot_id"] is None


def make_restore_backup(tmp_path):
    backup_directory = tmp_path / "backup"
    with EvidenceStore(tmp_path / "source") as store:
        imported = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert imported["status"] == "committed"
        original = store.query(imported["snapshot_id"])
        assert store.backup(backup_directory)["status"] == "complete"
    return backup_directory, imported["snapshot_id"], original


def test_restore_holds_destination_lock_during_file_copy(tmp_path, monkeypatch):
    backup_directory, snapshot_id, original = make_restore_backup(tmp_path)
    destination = tmp_path / "restored"
    copyfile = shutil.copyfile
    probes = []

    def copy_with_competing_open(source, target, *args, **kwargs):
        if Path(target).resolve().is_relative_to(destination) and not probes:
            probes.append(lock_probe(destination))
        return copyfile(source, target, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(shutil, "copyfile", copy_with_competing_open)
        restored = EvidenceStore.restore(backup_directory, destination)
    assert probes == [{"opened": False, "code": "data_directory_busy"}]
    assert restored["status"] == "restored"
    with EvidenceStore(destination) as store:
        assert store.query(snapshot_id) == original


@pytest.mark.parametrize("damaged_file", ["database", "raw"])
def test_restore_rejects_bytes_corrupted_during_copy(tmp_path, monkeypatch, damaged_file):
    backup_directory, _, _ = make_restore_backup(tmp_path)
    destination = tmp_path / "restored"
    relative = Path("research.duckdb") if damaged_file == "database" else raw_path(Path("."))
    corruption_target = destination / relative
    copyfile = shutil.copyfile
    injected = []

    def corrupt_after_copy(source, target, *args, **kwargs):
        copied = copyfile(source, target, *args, **kwargs)
        if Path(target) == corruption_target:
            with Path(target).open("ab") as stream:
                stream.write(b"synthetic-copy-corruption")
            assert hashlib.sha256(Path(target).read_bytes()).digest() != hashlib.sha256(Path(source).read_bytes()).digest()
            injected.append(str(target))
        return copied

    with monkeypatch.context() as patch:
        patch.setattr(shutil, "copyfile", corrupt_after_copy)
        with pytest.raises(StoreError):
            EvidenceStore.restore(backup_directory, destination)
    assert injected == [str(corruption_target)]


def test_reimport_cannot_overwrite_or_reuse_a_corrupt_existing_raw_object(tmp_path):
    root = tmp_path / "evidence"
    with EvidenceStore(root) as store:
        first = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert first["status"] == "committed"
        damaged = TDX_SAMPLE.replace(b"1001.00", b"1009.00", 1)
        assert len(damaged) == len(TDX_SAMPLE) and damaged != TDX_SAMPLE
        raw_path(root).write_bytes(damaged)

        retried = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert retried["status"] == "failed"
        assert retried["error_code"] == "raw_object_corrupt"
        assert retried["snapshot_id"] is None
        assert retried["attempt_id"] != first["attempt_id"]
        assert raw_path(root).read_bytes() == damaged
        assert [snapshot["snapshot_id"] for snapshot in store.list_snapshots()] == [first["snapshot_id"]]
        statuses = {attempt["attempt_id"]: attempt["status"] for attempt in store.attempts()}
        assert statuses == {first["attempt_id"]: "committed", retried["attempt_id"]: "failed"}


def test_failed_restore_stays_incomplete_for_new_instances(tmp_path, monkeypatch):
    backup_directory, _, _ = make_restore_backup(tmp_path)
    destination = tmp_path / "restored"
    copyfile = shutil.copyfile
    injected = []

    def fail_during_copy(source, target, *args, **kwargs):
        copied = copyfile(source, target, *args, **kwargs)
        if Path(target).resolve().is_relative_to(destination) and not injected:
            injected.append(str(target))
            raise OSError(errno.ENOSPC, "synthetic interrupted restore copy")
        return copied

    with monkeypatch.context() as patch:
        patch.setattr(shutil, "copyfile", fail_during_copy)
        with pytest.raises((OSError, StoreError)):
            EvidenceStore.restore(backup_directory, destination)
    assert len(injected) == 1
    with pytest.raises(StoreError) as caught:
        with EvidenceStore(destination):
            pytest.fail("An incompletely restored directory was opened")
    assert caught.value.code == "restore_incomplete"
    assert lock_probe(destination) == {"opened": False, "code": "restore_incomplete"}


def test_concurrent_close_waits_for_backup_without_releasing_root_lock(tmp_path):
    root = tmp_path / "evidence"
    backup_directory = tmp_path / "backup"
    backup_paused = threading.Event()
    resume_backup = threading.Event()
    close_started = threading.Event()
    close_finished = threading.Event()
    outcome = {}

    def checkpoint(stage):
        if stage == "backup_closed":
            backup_paused.set()
            if not resume_backup.wait(20):
                raise AssertionError("Backup was not released within 20 seconds")

    store = EvidenceStore(root, checkpoint=checkpoint)
    imported = store.import_bytes(TDX_SAMPLE, FORMAT)
    assert imported["status"] == "committed"
    original = store.query(imported["snapshot_id"])

    def run_backup():
        try:
            outcome["backup"] = store.backup(backup_directory)
        except BaseException as error:
            outcome["backup_error"] = error

    def run_close():
        close_started.set()
        try:
            store.close()
        except BaseException as error:
            outcome["close_error"] = error
        finally:
            close_finished.set()

    backup_thread = threading.Thread(target=run_backup, daemon=True)
    close_thread = threading.Thread(target=run_close, daemon=True)
    try:
        backup_thread.start()
        assert backup_paused.wait(20), "Backup did not reach the closed-database window"
        close_thread.start()
        assert close_started.wait(20), "Concurrent close did not start"
        assert backup_thread.ident != close_thread.ident
        assert not close_finished.wait(0.25), "Close returned while backup was still paused"
        assert lock_probe(root) == {"opened": False, "code": "data_directory_busy"}
        assert not close_finished.is_set()
    finally:
        resume_backup.set()
        if backup_thread.ident is not None:
            backup_thread.join(20)
        if close_thread.ident is not None:
            close_thread.join(20)
        if not backup_thread.is_alive() and not close_thread.is_alive():
            store.close()
    assert not backup_thread.is_alive(), "Backup thread exceeded its join timeout"
    assert not close_thread.is_alive(), "Close thread exceeded its join timeout"
    assert "backup_error" not in outcome, repr(outcome.get("backup_error"))
    assert "close_error" not in outcome, repr(outcome.get("close_error"))
    assert outcome["backup"]["status"] == "complete"
    assert close_finished.is_set()
    assert lock_probe(root) == {"opened": True}
    restored = tmp_path / "restored"
    EvidenceStore.restore(backup_directory, restored)
    with EvidenceStore(restored) as recovered:
        assert recovered.query(imported["snapshot_id"]) == original


@pytest.mark.parametrize("commit_applied", [False, True], ids=["uncommitted_connection_lost", "committed_connection_lost"])
def test_commit_connection_loss_reconnects_under_the_same_root_lock(tmp_path, monkeypatch, commit_applied):
    root = tmp_path / "evidence"
    proxy = None
    reconnect_probes = []

    def checkpoint(stage):
        if stage == "before_commit":
            proxy.armed = True

    with EvidenceStore(root, checkpoint=checkpoint) as store:
        proxy = CommitFault(store.db, apply_before_error=commit_applied, disconnect=True)
        store.db = proxy
        connect = duckdb.connect

        def reconnect_with_lock_check(*args, **kwargs):
            reconnect_probes.append(lock_probe(root))
            return connect(*args, **kwargs)

        with monkeypatch.context() as patch:
            patch.setattr(duckdb, "connect", reconnect_with_lock_check)
            result = store.import_bytes(TDX_SAMPLE, FORMAT)
        assert proxy.fired
        assert reconnect_probes == [{"opened": False, "code": "data_directory_busy"}]
        assert store.db is not proxy
        expected_status = "committed" if commit_applied else "failed"
        assert result["status"] == expected_status
        assert store.attempts()[0]["status"] == expected_status
        assert len(store.list_snapshots()) == int(commit_applied)
        if commit_applied:
            assert store.query(result["snapshot_id"])["counts"]["selected_rows"] == 2
        else:
            assert result["snapshot_id"] is None
            for table in ("batches", "observations", "snapshots"):
                assert store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_durable_cancelled_attempt_survives_interrupted_result_read(tmp_path, monkeypatch):
    root = tmp_path / "evidence"
    injected = []
    with EvidenceStore(root) as store:
        read_result = store._result

        def interrupt_once_after_cancellation(attempt_id):
            result = read_result(attempt_id)
            if result["status"] == "cancelled" and not injected:
                injected.append(attempt_id)
                raise KeyboardInterrupt("synthetic interruption after durable cancellation")
            return result

        returned, raised = None, None
        with monkeypatch.context() as patch:
            patch.setattr(store, "_result", interrupt_once_after_cancellation)
            try:
                returned = store.import_bytes(TDX_SAMPLE, FORMAT, cancelled=lambda: True)
            except BaseException as error:
                raised = error
        assert len(injected) == 1
        attempts = store.attempts()
        assert len(attempts) == 1
        assert attempts[0]["status"] == "cancelled"
        assert raised is None, f"Durable cancellation was obscured by {raised!r}"
        assert returned["status"] == "cancelled"
        assert returned["attempt_id"] == injected[0]
        assert returned["snapshot_id"] is None
        assert store.list_snapshots() == []
        assert not raw_path(root).exists()


def test_durable_file_rejection_survives_error_after_its_commit(tmp_path):
    root = tmp_path / "evidence"
    truncated = TDX_SAMPLE.removesuffix("数据来源:通达信\r\n".encode("gbk"))
    assert truncated != TDX_SAMPLE
    proxy = None

    def checkpoint(stage):
        if stage == "raw_published":
            proxy.armed = True

    with EvidenceStore(root, checkpoint=checkpoint) as store:
        proxy = CommitFault(store.db, apply_before_error=True)
        store.db = proxy
        returned, raised = None, None
        try:
            returned = store.import_bytes(truncated, FORMAT)
        except Exception as error:
            raised = error
        assert proxy.fired, "The rejection transaction COMMIT was not exercised"
        attempts = store.attempts()
        assert len(attempts) == 1
        assert attempts[0]["status"] == "rejected"
        assert raised is None, f"Durable rejection was obscured by {raised!r}"
        assert returned["status"] == "rejected"
        assert returned["attempt_id"] == attempts[0]["attempt_id"]
        assert returned["snapshot_id"] is None
        assert returned["error_code"]
        assert store.list_snapshots() == []
        assert raw_path(root, truncated).read_bytes() == truncated


class BeginFault:
    """Raise once after BEGIN has actually opened a transaction."""

    def __init__(self, connection):
        self.connection = connection
        self.armed = False
        self.fired = False

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def execute(self, statement, *args, **kwargs):
        is_begin = statement.strip().rstrip(";").upper() in {"BEGIN", "BEGIN TRANSACTION"}
        if is_begin and self.armed and not self.fired:
            self.fired = True
            self.armed = False
            self.connection.execute(statement, *args, **kwargs)
            raise duckdb.IOException("synthetic error after BEGIN took effect")
        return self.connection.execute(statement, *args, **kwargs)


@pytest.mark.parametrize("phase", ["primary", "terminal"])
def test_applied_begin_error_leaves_a_usable_connection_and_truthful_attempt(tmp_path, phase):
    root = tmp_path / "evidence"
    proxy = None

    def checkpoint(stage):
        if stage == "raw_published":
            proxy.armed = True

    with EvidenceStore(root, checkpoint=checkpoint) as store:
        proxy = BeginFault(store.db)
        store.db = proxy
        if phase == "primary":
            result = store.import_bytes(TDX_SAMPLE, FORMAT)
            assert result["status"] == "failed"
            assert result["snapshot_id"] is None
            expected_status = "failed"
        else:
            truncated = TDX_SAMPLE.removesuffix("数据来源:通达信\r\n".encode("gbk"))
            with pytest.raises(StoreError) as caught:
                store.import_bytes(truncated, FORMAT)
            assert caught.value.code == "import_outcome_unavailable"
            expected_status = "running"

        assert proxy.fired, "The applied-BEGIN fault was not exercised"
        attempts = store.attempts()
        assert len(attempts) == 1
        first_id = attempts[0]["attempt_id"]
        assert attempts[0]["status"] == expected_status
        assert attempts[0]["snapshot_id"] is None
        assert store.list_snapshots() == []
        assert store.db.execute("SELECT 42").fetchone() == (42,)
        for table in ("batches", "observations", "snapshots"):
            assert store.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0

        following = store.import_bytes(TDX_SAMPLE, FORMAT, filename="following-normal-import.txt")
        assert following["status"] == "committed"
        assert following["attempt_id"] != first_id
        assert store.query(following["snapshot_id"])["counts"]["selected_rows"] == 2
        by_id = {attempt["attempt_id"]: attempt for attempt in store.attempts()}
        assert by_id[first_id]["status"] == expected_status
        assert by_id[following["attempt_id"]]["status"] == "committed"
        assert len(store.list_snapshots()) == 1

    with EvidenceStore(root) as recovered:
        by_id = {attempt["attempt_id"]: attempt for attempt in recovered.attempts()}
        assert by_id[first_id]["status"] == ("interrupted" if phase == "terminal" else "failed")
        assert by_id[first_id]["snapshot_id"] is None
        assert by_id[following["attempt_id"]]["status"] == "committed"
        assert [snapshot["snapshot_id"] for snapshot in recovered.list_snapshots()] == [following["snapshot_id"]]
