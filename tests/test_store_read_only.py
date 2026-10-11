"""Synthetic-only qualification of explicit database read-only access."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import duckdb
import pyarrow.parquet as pq
import pytest

import anatrading.store as module
from anatrading.cli import _parser, _run
from anatrading.models import VERSIONS
from anatrading.store import EvidenceStore, StoreError


RESERVED = ("research.duckdb", "research.duckdb.wal", "research.duckdb.wal.checkpoint",
            "research.duckdb.wal.recovery", ".operation.lock", ".restore-incomplete")
RAW = ("601577 合成验收 1分钟线 不复权\r\n"
       "日期\t时间\t开盘\t最高\t最低\t收盘\t成交量\t成交额\r\n"
       "2021/02/26,0932,0.123456789012345678,11,0.1,10,9007199254740993,1000\r\n"
       "2021/02/26,2500,10,11,9,10,bad,NaN\r\n"
       "2021/02/26,0931,,11,9,10,0,0\r\n"
       "数据来源:通达信\r\n").encode("gbk")


def fingerprint(root):
    """Exclude access time, lock and intentional export writes."""
    result = {}
    for name in RESERVED[:4]:
        path = root / name
        result[name] = None if not path.exists() else (
            hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)
    return result


@pytest.fixture
def populated(tmp_path):
    root = tmp_path / "root"
    with EvidenceStore(root) as store:
        result = store.import_bytes(RAW, "tdx-public-text-v1")
        assert result["status"] == "committed"
    return root, result["snapshot_id"]


def test_read_only_missing_directory_is_not_created(tmp_path):
    root = tmp_path / "missing" / "root"
    with pytest.raises(StoreError, match="database_missing"):
        EvidenceStore(root, read_only=True)
    assert not root.parent.exists()


def test_read_only_preserves_database_and_running_attempts(populated):
    root, snapshot = populated
    with EvidenceStore(root) as store:
        store.db.execute("UPDATE attempts SET status='running',error_code='preserved'")
        store.db.execute("INSERT INTO attempts VALUES ('uncommitted','now','running','x','x','{}',NULL,NULL,NULL,NULL)")
        attempts = store.attempts()
        expected = store.query(snapshot)
    before = fingerprint(root)
    stages = []
    store = EvidenceStore(root, checkpoint=stages.append, read_only=True)
    with store:
        assert store.db.execute("SELECT current_setting('access_mode')").fetchone() == ("read_only",)
        assert store.attempts() == attempts
        assert store.query(snapshot) == expected
        assert store.query(snapshot) == expected
        assert fingerprint(root) == before
    store.close()
    assert stages == [] and fingerprint(root) == before
    with EvidenceStore(root) as store:
        assert {a["status"] for a in store.attempts()} == {"committed", "interrupted"}


def test_read_only_import_and_backup_reject_before_side_effects(populated, tmp_path, monkeypatch):
    root, snapshot = populated
    before = fingerprint(root)
    with EvidenceStore(root, read_only=True) as store:
        database = store.db
        def forbidden(*args, **kwargs):
            pytest.fail("read-only mutation attempted")
        monkeypatch.setattr(module.duckdb, "connect", forbidden)
        monkeypatch.setattr(Path, "read_bytes", forbidden)
        store._checkpoint = forbidden
        for action in (
            lambda: store.import_bytes(b"x", "bad"),
            lambda: store.import_bytes(None, "bad"),
            lambda: store.import_file(tmp_path / "missing", "bad"),
            lambda: store._import(None, None, None, None, None),
            lambda: store.backup(tmp_path / "new-backup"),
        ):
            with pytest.raises(StoreError, match="read_only_store"):
                action()
            assert store.db is database
        assert not (tmp_path / "new-backup").exists()
    monkeypatch.undo()
    assert fingerprint(root) == before


def test_cli_read_only_is_explicit_and_missing_root_stays_missing(tmp_path):
    root = tmp_path / "missing"
    arguments = _parser().parse_args(["--root", str(root), "snapshots", "--read-only"])
    with pytest.raises(StoreError, match="database_missing"):
        _run(arguments)
    assert not root.exists()


@pytest.mark.parametrize("case", ["missing", "directory", "empty", "unrecognized", "version_missing", "old",
                                  "table", "column", "type", "view", "ambiguous_version"])
def test_read_only_missing_or_unsupported_schema_releases_lock(tmp_path, case):
    root = tmp_path / "root"
    root.mkdir()
    database = root / "research.duckdb"
    if case == "directory":
        database.mkdir()
    elif case == "empty":
        duckdb.connect(str(database)).close()
    elif case != "missing":
        with EvidenceStore(root) as store:
            if case == "unrecognized":
                store.db.execute("DROP TABLE app_meta")
            elif case == "version_missing":
                store.db.execute("DELETE FROM app_meta WHERE key='schema'")
            elif case == "old":
                store.db.execute("UPDATE app_meta SET value='previous' WHERE key='schema'")
            elif case == "table":
                store.db.execute("DROP TABLE observations")
            elif case == "column":
                store.db.execute("ALTER TABLE observations DROP source_close")
            elif case == "type":
                store.db.execute("ALTER TABLE observations ALTER source_close TYPE DOUBLE")
            elif case == "view":
                store.db.execute("ALTER TABLE observations RENAME TO saved_observations")
                store.db.execute("CREATE VIEW observations AS SELECT * FROM saved_observations")
            elif case == "ambiguous_version":
                store.db.execute("CREATE TABLE duplicated_meta AS SELECT * FROM app_meta")
                store.db.execute("DROP TABLE app_meta")
                store.db.execute("ALTER TABLE duplicated_meta RENAME TO app_meta")
                store.db.execute("INSERT INTO app_meta VALUES ('schema', ?)", [VERSIONS['schema']])
    expected = "database_missing" if case in {"missing", "directory"} else "unsupported_schema"
    before = None if case == "directory" else fingerprint(root)
    with pytest.raises(StoreError, match=expected):
        EvidenceStore(root, read_only=True)
    with module._DirectoryLock(root):
        pass
    if before is not None:
        assert fingerprint(root) == before


def test_read_only_accepts_extra_columns_and_tables_and_minimal_read_schema(populated):
    root, snapshot = populated
    with EvidenceStore(root) as store:
        expected = store.query(snapshot)
        store.db.execute("CREATE TABLE extra (x INTEGER)")
        store.db.execute("ALTER TABLE snapshots ADD extra VARCHAR")
        store.db.execute("ALTER TABLE snapshots DROP manifest_json")
        store.db.execute("ALTER TABLE attempts DROP interpretation_json")
        # Copy in reversed column order with no original constraints.
        names = [row[0] for row in store.db.execute("DESCRIBE observations").fetchall()]
        names = [name for name in reversed(names) if name not in {'volume_shares', 'amount_cny'}]
        store.db.execute("CREATE TABLE replacement AS SELECT " + ",".join(names) + " FROM observations")
        store.db.execute("DROP TABLE observations")
        store.db.execute("ALTER TABLE replacement RENAME TO observations")
    before = fingerprint(root)
    with EvidenceStore(root, read_only=True) as store:
        assert store.query(snapshot) == expected
    assert fingerprint(root) == before


def test_read_only_restore_marker_and_connection_errors_do_not_retry(populated, monkeypatch):
    root, _ = populated
    marker = root / ".restore-incomplete"
    marker.write_bytes(b"synthetic incomplete restore")
    before = fingerprint(root)
    with pytest.raises(StoreError, match="restore_incomplete"):
        EvidenceStore(root, read_only=True)
    with module._DirectoryLock(root):
        pass
    marker.unlink()
    calls = []
    def fail_connect(*args, **kwargs):
        calls.append((args, kwargs))
        raise duckdb.IOException("synthetic failure")
    monkeypatch.setattr(module.duckdb, "connect", fail_connect)
    with pytest.raises(StoreError, match="database_error"):
        EvidenceStore(root, read_only=True)
    assert len(calls) == 1 and calls[0][1] == {"read_only": True}
    with module._DirectoryLock(root):
        pass
    assert fingerprint(root) == before


def test_read_only_only_selects_and_excludes_parallel_readers(populated, monkeypatch):
    root, snapshot = populated
    real_connect = duckdb.connect
    statements, connections, closed = [], [], []
    class ReadSpy:
        def __init__(self, database):
            self.database = database
        def execute(self, sql, *args):
            assert sql.lstrip().upper().startswith("SELECT"), sql
            statements.append(sql)
            return self.database.execute(sql, *args)
        def close(self):
            closed.append(True)
            self.database.close()
    def connect(*args, **kwargs):
        connections.append(kwargs)
        return ReadSpy(real_connect(*args, **kwargs))
    def forbidden(*args):
        pytest.fail("initialization or callback reached")
    monkeypatch.setattr(module.duckdb, "connect", connect)
    monkeypatch.setattr(EvidenceStore, "_initialize", forbidden)
    inode = (root / ".operation.lock").stat().st_ino
    with EvidenceStore(root, checkpoint=forbidden, read_only=True) as store:
        assert store.query(snapshot)["snapshot_id"] == snapshot
        with pytest.raises(StoreError, match="data_directory_busy"):
            EvidenceStore(root, read_only=True)
        with pytest.raises(StoreError, match="data_directory_busy"):
            EvidenceStore(root)
    store.close()
    assert connections == [{"read_only": True}] and closed == [True]
    assert len(statements) >= 5
    if os.name != "nt":
        assert (root / ".operation.lock").stat().st_ino == inode


def test_failed_schema_validation_closes_connection(populated, monkeypatch):
    root, _ = populated
    def fail(store):
        raise StoreError("unsupported_schema")
    with monkeypatch.context() as patch:
        patch.setattr(EvidenceStore, "_validate_read_schema", fail)
        with pytest.raises(StoreError, match="unsupported_schema"):
            EvidenceStore(root, read_only=True)
    # A leaked DuckDB read-only connection would reject this read-write open.
    with EvidenceStore(root):
        pass


@pytest.mark.parametrize("empty_wal", [False, True])
def test_read_only_clean_or_empty_wal_stays_unchanged(populated, empty_wal):
    root, snapshot = populated
    if empty_wal:
        (root / "research.duckdb.wal").touch()
    before = fingerprint(root)
    raw = {p: p.read_bytes() for p in (root / "raw").rglob("*") if p.is_file()}
    with EvidenceStore(root, read_only=True) as store:
        assert store.query(snapshot)["counts"]["batch_rows"] == 3
        assert fingerprint(root) == before
    assert fingerprint(root) == before
    assert {p: p.read_bytes() for p in raw} == raw


def test_read_only_replays_committed_wal_without_changing_files(populated):
    root, _ = populated
    writer = r'''
import json, os, sys
from anatrading.store import EvidenceStore
store = EvidenceStore(sys.argv[1])
store.db.execute("SET checkpoint_threshold='1GB'")
store.db.execute("UPDATE attempts SET status='running',error_code='preserved'")
raw = bytes.fromhex(sys.argv[2]).replace(b'0932', b'0933')
result = store.import_bytes(raw, 'tdx-public-text-v1')
assert result['status'] == 'committed'
print(json.dumps(result), flush=True)
os._exit(0)
'''
    process = subprocess.run([sys.executable, "-c", writer, str(root), RAW.hex()],
                             capture_output=True, text=True, timeout=30)
    assert process.returncode == 0, process.stderr
    imported = json.loads(process.stdout)
    assert (root / "research.duckdb.wal").stat().st_size > 0
    before = fingerprint(root)
    with EvidenceStore(root, read_only=True) as store:
        assert len(store.list_snapshots()) == 2
        query = store.query(imported["snapshot_id"])
        assert query["rows"][-1]["label"] == "2021-02-26T09:33"
        assert sorted(a["status"] for a in store.attempts()) == ["committed", "running"]
        assert fingerprint(root) == before
    assert fingerprint(root) == before
    # Check after a separate reader has closed and exited, not only this process.
    reader = subprocess.run([sys.executable, "-c",
        "from anatrading.store import EvidenceStore; import sys; "
        "s=EvidenceStore(sys.argv[1],read_only=True); assert len(s.list_snapshots())==2; s.close()", str(root)],
        capture_output=True, text=True, timeout=30)
    assert reader.returncode == 0, reader.stderr
    assert fingerprint(root) == before


@pytest.mark.parametrize("extension", ["json", "parquet"])
@pytest.mark.parametrize("name", RESERVED)
@pytest.mark.parametrize("variant", ["direct", "dotdot", "symlink", "child", "symlink_child"])
def test_read_only_export_rejects_reserved_paths_before_publication(populated, tmp_path, monkeypatch,
                                                                   extension, name, variant):
    root, snapshot = populated
    target = root / name
    if variant == "dotdot":
        target = root / "nonexistent" / ".." / name
    elif variant.startswith("symlink"):
        target = tmp_path / "alias"
        target.symlink_to(root / name)
    if variant.endswith("child"):
        target = target / "export" / ("result." + extension)
    before = fingerprint(root)
    tree = sorted(str(p.relative_to(root)) for p in root.rglob("*"))
    with EvidenceStore(root, read_only=True) as store:
        def forbidden(*args):
            pytest.fail("reserved target reached publication")
        monkeypatch.setattr(module, "_publish_bytes", forbidden)
        with pytest.raises(StoreError, match="export_destination_reserved"):
            getattr(store, "export_" + extension)(snapshot, target)
    assert sorted(str(p.relative_to(root)) for p in root.rglob("*")) == tree
    assert fingerprint(root) == before


@pytest.mark.parametrize("extension", ["json", "parquet"])
def test_read_only_default_export_cannot_follow_exports_symlink_to_reserved(populated, extension):
    root, snapshot = populated
    (root / "exports").symlink_to(root / "research.duckdb.wal.checkpoint", target_is_directory=True)
    before = fingerprint(root)
    with EvidenceStore(root, read_only=True) as store:
        with pytest.raises(StoreError, match="export_destination_reserved"):
            getattr(store, "export_" + extension)(snapshot)
    assert fingerprint(root) == before


@pytest.mark.parametrize("selection", [{}, {"cutoff": "2021-02-26T09:31", "ordinal_start": 2},
                                       {"cutoff": "2020-01-01T00:00", "ordinal_end": 1},
                                       {"ordinal_start": 9999999999999999999999999}])
def test_read_only_read_and_export_semantics_equal_legacy(populated, tmp_path, selection):
    root, snapshot = populated
    with EvidenceStore(root) as store:
        expected = store.query(snapshot, **selection)
        projection = store._research_query(snapshot, cutoff=selection.get("cutoff"))
        catalog = store.snapshot_catalog(snapshot)
        attempts = store.attempts()
        snapshots = store.list_snapshots()
        count = store.query_row_count(snapshot, cutoff=selection.get("cutoff"))
        navigation = store.label_navigation(expected["batch_id"], **selection)
        original_json = Path(store.export_json(snapshot, tmp_path / "legacy.json", **selection)["path"]).read_bytes()
        original_parquet = pq.read_table(store.export_parquet(snapshot, tmp_path / "legacy.parquet", **selection)["path"])
    before = fingerprint(root)
    with EvidenceStore(root, read_only=True) as store:
        assert store.query(snapshot, **selection) == expected
        assert store._research_query(snapshot, cutoff=selection.get("cutoff")) == projection
        assert store.snapshot_catalog(snapshot) == catalog and store.list_snapshots() == snapshots
        assert store.attempts() == attempts
        assert store.query_row_count(snapshot, cutoff=selection.get("cutoff")) == count
        assert store.label_navigation(expected["batch_id"], **selection) == navigation
        for destination in (None, root / "ordinary" / "result", tmp_path / "outside" / "result"):
            for extension in ("json", "parquet"):
                target = None if destination is None else destination.with_suffix("." + extension)
                result = getattr(store, "export_" + extension)(snapshot, target, **selection)
                assert result["query_id"] == expected["query_id"]
                if extension == "json":
                    assert Path(result["path"]).read_bytes() == original_json
                else:
                    assert pq.read_table(result["path"]).equals(original_parquet, check_metadata=True)
    assert fingerprint(root) == before


@pytest.mark.parametrize("corrupt", [False, True])
def test_read_only_still_verifies_raw_on_every_query_including_empty_selection(populated, corrupt):
    root, snapshot = populated
    with EvidenceStore(root, read_only=True) as store:
        query = store.query(snapshot)
        path = store._raw_path(query["manifest"]["raw_sha256"])
        if corrupt:
            content = path.read_bytes()
            path.write_bytes(b"X" + content[1:])
        else:
            path.unlink()
        for selection in ({}, {"ordinal_start": 99999}):
            with pytest.raises(StoreError, match="raw_object_corrupt" if corrupt else "raw_object_missing"):
                store.query(snapshot, **selection)


@pytest.mark.parametrize("command", ["snapshots", "attempts", "query", "export", "candle-geometry"])
def test_cli_read_only_commands_match_default_and_leave_database_unchanged(populated, command):
    root, snapshot = populated
    args = ["--root", str(root), command]
    if command in {"query", "export", "candle-geometry"}:
        args += [snapshot]
    expected = _run(_parser().parse_args(args))
    before = fingerprint(root)
    assert _run(_parser().parse_args([*args, "--read-only"])) == expected
    assert fingerprint(root) == before


@pytest.mark.parametrize("args", [["import", "source", "--format", "tdx-public-day-v1"], ["backup", "destination"],
                                  ["restore", "backup", "destination"], ["serve"], ["read-tdx-minutes", "--symbol", "x"]])
def test_cli_mutating_commands_reject_read_only_before_open(tmp_path, args):
    root = tmp_path / "missing"
    with pytest.raises(SystemExit) as error:
        _parser().parse_args(["--root", str(root), *args, "--read-only"])
    assert error.value.code == 2 and not root.exists()


def test_read_only_may_create_lock_but_does_not_delete_it(populated):
    root, snapshot = populated
    lock = root / ".operation.lock"
    lock.unlink()  # Fixture is closed and has no active owners.
    before = fingerprint(root)
    with EvidenceStore(root, read_only=True) as store:
        assert lock.is_file() and store.query(snapshot)["snapshot_id"] == snapshot
        inode = lock.stat().st_ino
    assert lock.is_file()
    if os.name != "nt":
        assert lock.stat().st_ino == inode
    assert fingerprint(root) == before


@pytest.mark.parametrize("extension", ["json", "parquet"])
def test_read_only_resolves_reserved_database_symlink_both_sides(populated, tmp_path, extension):
    root, snapshot = populated
    external = tmp_path / "moved.duckdb"
    database = root / "research.duckdb"
    database.rename(external)
    database.symlink_to(external)
    before = external.read_bytes(), external.stat().st_mtime_ns
    with EvidenceStore(root, read_only=True) as store:
        with pytest.raises(StoreError, match="export_destination_reserved"):
            getattr(store, "export_" + extension)(snapshot, external)
    assert (external.read_bytes(), external.stat().st_mtime_ns) == before


@pytest.mark.parametrize("extension", ["json", "parquet"])
def test_legacy_export_destination_policy_is_unchanged(populated, monkeypatch, extension):
    root, snapshot = populated
    published = []
    monkeypatch.setattr(module, "_publish_bytes", lambda path, content: published.append(path))
    with EvidenceStore(root) as store:
        target = root / "research.duckdb.wal.checkpoint"
        getattr(store, "export_" + extension)(snapshot, target)
    assert published == [target]


@pytest.mark.parametrize("case,code", [("missing", "database_missing"), ("empty", "unsupported_schema"),
                                       ("corrupt", "database_error"), ("marker", "restore_incomplete")])
def test_cli_read_only_errors_are_typed_without_traceback(tmp_path, case, code):
    root = tmp_path / "root"
    if case != "missing":
        root.mkdir()
        if case == "empty":
            duckdb.connect(str(root / "research.duckdb")).close()
        elif case == "corrupt":
            (root / "research.duckdb").write_bytes(b"synthetic non-database")
        elif case == "marker":
            (root / ".restore-incomplete").write_bytes(b"synthetic marker")
    result = subprocess.run([sys.executable, "-m", "anatrading.cli", "--root", str(root),
                             "snapshots", "--read-only"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 2 and not result.stderr
    assert json.loads(result.stdout) == {"status": "error", "error_code": code}
    if case == "missing":
        assert not root.exists()
