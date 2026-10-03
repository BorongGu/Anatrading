"""Single-writer evidence storage; source values do not acquire trading semantics."""
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import threading
import uuid

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from .formats import FORMAT_IDS, decode, preflight
from .models import DecodeError, NonMarketPayload, VALUE_FIELDS, VERSIONS
from .numeric import decimal_text, decimal_value, exact_sum, integer_value


class StoreError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class _DirectoryLock:
    """One OS lock spans both database access and closed-database file operations."""
    def __init__(self, root):
        if os.name != "nt":
            raise StoreError("windows_required")
        import msvcrt
        self.stream = (root / ".operation.lock").open("a+b")
        self.stream.seek(0, os.SEEK_END)
        if self.stream.tell() == 0:
            self.stream.write(b"0")
            self.stream.flush()
        try:
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.stream.close()
            raise StoreError("data_directory_busy") from None

    def close(self):
        import msvcrt
        if not self.stream.closed:
            try:
                self.stream.seek(0)
                msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                self.stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"), default=lambda x: decimal_text(x) if isinstance(x, Decimal) else _bad_json())


def _bad_json():
    raise TypeError("Unsupported JSON value")


def _identity(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _utcnow():
    return datetime.now(timezone.utc).isoformat()


def _digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _publish_bytes(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() == content:
            return
        raise StoreError("destination_exists")
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".part", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


ROW_SCHEMA = pa.schema([
    ("batch_id", pa.string()), ("ordinal", pa.int64()), ("locator", pa.string()),
    ("source_label", pa.string()), ("label", pa.string()), ("tokens_json", pa.string()),
    ("checks_json", pa.string()),
    *[("source_" + name, pa.int64() if name == "volume" else pa.decimal128(38, 18)) for name in VALUE_FIELDS],
    ("volume_shares", pa.int64()), ("amount_cny", pa.decimal128(38, 18)),
])


class EvidenceStore:
    def __init__(self, root, checkpoint=None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._mutex = threading.RLock()
        self._checkpoint = checkpoint or (lambda stage: None)
        self.db = None
        self._guard = _DirectoryLock(self.root)
        try:
            if (self.root / ".restore-incomplete").exists():
                raise StoreError("restore_incomplete")
            self.db = duckdb.connect(str(self.root / "research.duckdb"))
            self._initialize()
            self.db.execute("UPDATE attempts SET status='committed', error_code=NULL WHERE status='running' AND snapshot_id IN (SELECT snapshot_id FROM snapshots)")
            self.db.execute("UPDATE attempts SET status='interrupted', error_code='process_interrupted' WHERE status='running'")
        except BaseException:
            self.close()
            raise

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        with self._mutex:
            try:
                if self.db is not None:
                    self.db.close()
                    self.db = None
            finally:
                self._guard.close()

    def _initialize(self):
        tables = {row[0] for row in self.db.execute("SHOW TABLES").fetchall()}
        if tables and "app_meta" not in tables:
            raise StoreError("unrecognized_database")
        self.db.execute("CREATE TABLE IF NOT EXISTS app_meta (key VARCHAR PRIMARY KEY, value VARCHAR)")
        version = self.db.execute("SELECT value FROM app_meta WHERE key='schema'").fetchone()
        if version and version[0] != VERSIONS["schema"]:
            raise StoreError("unsupported_schema")
        self.db.execute("INSERT INTO app_meta VALUES ('schema', ?) ON CONFLICT DO NOTHING", [VERSIONS["schema"]])
        self.db.execute("""
            CREATE TABLE IF NOT EXISTS raw_objects (sha VARCHAR PRIMARY KEY, byte_length BIGINT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts (
                attempt_id VARCHAR PRIMARY KEY, started_at VARCHAR NOT NULL, status VARCHAR NOT NULL,
                format_id VARCHAR NOT NULL, filename VARCHAR NOT NULL, interpretation_json VARCHAR NOT NULL,
                raw_sha256 VARCHAR, batch_id VARCHAR, snapshot_id VARCHAR, error_code VARCHAR);
            CREATE TABLE IF NOT EXISTS batches (
                batch_id VARCHAR PRIMARY KEY, raw_sha256 VARCHAR NOT NULL REFERENCES raw_objects(sha),
                manifest_json VARCHAR NOT NULL, metadata_json VARCHAR NOT NULL,
                checks_json VARCHAR NOT NULL, row_count BIGINT NOT NULL);
            CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id VARCHAR PRIMARY KEY, batch_id VARCHAR NOT NULL UNIQUE REFERENCES batches(batch_id),
                manifest_json VARCHAR NOT NULL);
            CREATE TABLE IF NOT EXISTS observations (
                batch_id VARCHAR NOT NULL REFERENCES batches(batch_id), ordinal BIGINT NOT NULL CHECK(ordinal>0),
                locator VARCHAR NOT NULL, source_label VARCHAR, label VARCHAR,
                tokens_json VARCHAR NOT NULL, checks_json VARCHAR NOT NULL,
                source_open DECIMAL(38,18), source_high DECIMAL(38,18), source_low DECIMAL(38,18),
                source_close DECIMAL(38,18), source_volume BIGINT CHECK(source_volume>=0), source_amount DECIMAL(38,18),
                volume_shares BIGINT CHECK(volume_shares>=0), amount_cny DECIMAL(38,18), PRIMARY KEY(batch_id,ordinal));
        """)

    def _raw_path(self, sha):
        if not re.fullmatch("[0-9a-f]{64}", sha):
            raise StoreError("invalid_object_id")
        path = self.root / "raw" / sha[:2] / sha
        if not path.resolve().is_relative_to(self.root):
            raise StoreError("raw_reference_outside_root")
        return path

    def _verify_raw(self, sha, expected_length=None):
        path = self._raw_path(sha)
        if not path.is_file():
            raise StoreError("raw_object_missing")
        if (expected_length is not None and path.stat().st_size != expected_length) or _digest(path) != sha:
            raise StoreError("raw_object_corrupt")
        return path

    def _write_raw(self, raw, sha):
        destination = self._raw_path(sha)
        if destination.exists():
            self._verify_raw(sha, len(raw))
            return
        staging = self.root / "staging"
        if not staging.resolve().is_relative_to(self.root):
            raise StoreError("staging_outside_root")
        staging.mkdir(exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=staging, suffix=".part", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if temporary.stat().st_size != len(raw) or _digest(temporary) != sha:
            raise StoreError("raw_write_mismatch")
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(temporary, destination)

    def _result(self, attempt_id):
        cursor = self.db.execute("SELECT attempt_id,status,raw_sha256,batch_id,snapshot_id,error_code FROM attempts WHERE attempt_id=?", [attempt_id])
        return dict(zip([item[0] for item in cursor.description], cursor.fetchone()))

    def _resolve_attempt(self, attempt_id, rollback=False):
        if rollback:
            try:
                self.db.execute("ROLLBACK")
            except (duckdb.Error, OSError):
                # A transaction may have committed before its caller saw an error.
                pass
        try:
            return self._result(attempt_id)
        except (duckdb.Error, OSError):
            try:
                self.db.close()
                self.db = duckdb.connect(str(self.root / "research.duckdb"))
                return self._result(attempt_id)
            except (duckdb.Error, OSError):
                raise StoreError("import_outcome_unavailable") from None

    def import_bytes(self, raw, format_id, filename="source", interpretation=None, cancelled=None):
        if not isinstance(raw, bytes):
            raise StoreError("invalid_import_spec")
        return self._import(raw, format_id, filename, interpretation, cancelled)

    def import_file(self, path, format_id, filename=None, interpretation=None, cancelled=None):
        path = Path(path)
        return self._import(path, format_id, filename or path.name, interpretation, cancelled)

    def _import(self, material, format_id, filename, interpretation, cancelled):
        interpretation = dict(interpretation or {})
        allowed = {"instrument", "venue", "asset_type", "volume_unit", "amount_unit"}
        if format_id not in FORMAT_IDS or set(interpretation) - allowed or any(not isinstance(v, str) for v in interpretation.values()):
            raise StoreError("invalid_import_spec")
        cancelled = cancelled or (lambda: False)
        with self._mutex:
            attempt_id = uuid.uuid4().hex
            self.db.execute("INSERT INTO attempts (attempt_id,started_at,status,format_id,filename,interpretation_json) VALUES (?,?,'running',?,?,?)",
                            [attempt_id, _utcnow(), format_id, Path(filename).name, _json(interpretation)])
            sha = None
            raw = None
            in_transaction = False
            try:
                self._checkpoint("attempt_started")
                if cancelled():
                    self.db.execute("UPDATE attempts SET status='cancelled' WHERE attempt_id=?", [attempt_id])
                    return self._result(attempt_id)
                raw = material.read_bytes() if isinstance(material, Path) else material
                preflight(raw, format_id)
                sha = hashlib.sha256(raw).hexdigest()
                self._write_raw(raw, sha)
                self._checkpoint("raw_published")
                decoded = decode(raw, format_id, interpretation)
                manifest = {"raw_sha256": sha, "source_contract_id": _identity(decoded.contract),
                            "contract": decoded.contract, "interpretation": interpretation,
                            "versions": dict(VERSIONS), "qualification": "source_evidence_retrospective_only"}
                batch_id = _identity(manifest)
                snapshot_manifest = {"batch_id": batch_id, "versions": dict(VERSIONS), "mode": "retrospective"}
                snapshot_id = _identity(snapshot_manifest)
                # No cancellation is accepted after this final serialized check.
                if cancelled():
                    self.db.execute("UPDATE attempts SET status='cancelled' WHERE attempt_id=?", [attempt_id])
                    return self._result(attempt_id)
                in_transaction = True
                self.db.execute("BEGIN TRANSACTION")
                self._checkpoint("transaction_open")
                self.db.execute("INSERT INTO raw_objects VALUES (?,?) ON CONFLICT DO NOTHING", [sha, len(raw)])
                existing = self.db.execute("SELECT batch_id FROM batches WHERE batch_id=?", [batch_id]).fetchone()
                if not existing:
                    self.db.execute("INSERT INTO batches VALUES (?,?,?,?,?,?)", [batch_id, sha, _json(manifest), _json(decoded.metadata), _json([asdict(c) for c in decoded.checks]), len(decoded.rows)])
                    payload = []
                    for row in decoded.rows:
                        if set(row.values) != set(VALUE_FIELDS) or row.volume_shares is not None or row.amount_cny is not None:
                            raise StoreError("unverified_normalization")
                        item = dict(batch_id=batch_id, ordinal=row.ordinal, locator=row.locator, source_label=row.source_label,
                                    label=row.label, tokens_json=_json(row.tokens), checks_json=_json([asdict(c) for c in row.checks]),
                                    volume_shares=None, amount_cny=None)
                        for field in VALUE_FIELDS:
                            value = row.values[field]
                            item["source_" + field] = None if value is None else (integer_value(value) if field == "volume" else decimal_value(value))
                        payload.append(item)
                    frame = pa.Table.from_pylist(payload, schema=ROW_SCHEMA)
                    self.db.register("incoming_observations", frame)
                    try:
                        self.db.execute("INSERT INTO observations SELECT * FROM incoming_observations")
                    finally:
                        self.db.unregister("incoming_observations")
                    self.db.execute("INSERT INTO snapshots VALUES (?,?,?)", [snapshot_id, batch_id, _json(snapshot_manifest)])
                self.db.execute("UPDATE attempts SET status='committed',raw_sha256=?,batch_id=?,snapshot_id=? WHERE attempt_id=?", [sha, batch_id, snapshot_id, attempt_id])
                self._checkpoint("before_commit")
                self.db.execute("COMMIT")
                in_transaction = False
                self._checkpoint("after_commit")
                result = self._result(attempt_id)
                result["reused"] = bool(existing)
                return result
            except BaseException as error:
                result = self._resolve_attempt(attempt_id, rollback=in_transaction)
                if result["status"] != "running":
                    return result
                if isinstance(error, NonMarketPayload):
                    status, code, sha = "rejected", error.code, None
                elif isinstance(error, DecodeError):
                    status, code = "rejected", error.code
                elif isinstance(error, OSError):
                    status, code = "failed", "storage_io_error"
                elif isinstance(error, duckdb.Error):
                    status, code = "failed", "database_error"
                else:
                    status, code = "failed", getattr(error, "code", "internal_error")
                try:
                    self.db.execute("BEGIN TRANSACTION")
                    if sha is not None and self._raw_path(sha).is_file() and _digest(self._raw_path(sha)) == sha:
                        self.db.execute("INSERT INTO raw_objects VALUES (?,?) ON CONFLICT DO NOTHING", [sha, len(raw)])
                    else:
                        sha = None
                    self.db.execute("UPDATE attempts SET status=?,raw_sha256=?,error_code=? WHERE attempt_id=?", [status, sha, code, attempt_id])
                    self.db.execute("COMMIT")
                except BaseException:
                    result = self._resolve_attempt(attempt_id, rollback=True)
                    if result["status"] != "running":
                        return result
                    raise StoreError("import_outcome_unavailable") from None
                return self._resolve_attempt(attempt_id)

    def attempts(self):
        with self._mutex:
            cursor = self.db.execute("SELECT attempt_id,started_at,status,format_id,filename,raw_sha256,batch_id,snapshot_id,error_code FROM attempts ORDER BY started_at,attempt_id")
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def list_snapshots(self):
        with self._mutex:
            return [dict(snapshot_id=s, batch_id=b, row_count=n) for s, b, n in self.db.execute("SELECT s.snapshot_id,s.batch_id,b.row_count FROM snapshots s JOIN batches b USING(batch_id) ORDER BY s.snapshot_id").fetchall()]

    @staticmethod
    def _quality(rows):
        counts = defaultdict(lambda: Counter(pass_=0, fail=0, not_evaluated=0))
        for row in rows:
            for check in row["checks"]:
                counts[check["name"]]["pass_" if check["outcome"] == "pass" else check["outcome"]] += 1
        return {name: {"pass" if key == "pass_" else key: value for key, value in count.items()} for name, count in sorted(counts.items())}

    def query(self, snapshot_id, cutoff=None, ordinal_start=None, ordinal_end=None, mode="retrospective"):
        if mode != "retrospective":
            raise StoreError("mode_not_supported")
        if not isinstance(snapshot_id, str) or not re.fullmatch("[0-9a-f]{64}", snapshot_id):
            raise StoreError("invalid_snapshot_id")
        for value in (ordinal_start, ordinal_end):
            if value is not None and (type(value) is not int or value < 1):
                raise StoreError("invalid_ordinal_range")
        if ordinal_start is not None and ordinal_end is not None and ordinal_start > ordinal_end:
            raise StoreError("invalid_ordinal_range")
        with self._mutex:
            found = self.db.execute("SELECT s.batch_id,b.raw_sha256,b.manifest_json,b.metadata_json,b.checks_json,b.row_count,r.byte_length FROM snapshots s JOIN batches b USING(batch_id) JOIN raw_objects r ON r.sha=b.raw_sha256 WHERE s.snapshot_id=?", [snapshot_id]).fetchone()
            if found is None:
                raise StoreError("snapshot_not_found")
            batch_id, sha, manifest_json, metadata_json, batch_checks, batch_rows, size = found
            self._verify_raw(sha, size)
            manifest, metadata = json.loads(manifest_json), json.loads(metadata_json)
            if cutoff is not None:
                try:
                    pattern = r"[0-9]{4}-[0-9]{2}-[0-9]{2}" if metadata["period"] == "1d" else r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}"
                    if not isinstance(cutoff, str) or not re.fullmatch(pattern, cutoff):
                        raise ValueError
                    datetime.fromisoformat(cutoff)
                except (ValueError, KeyError):
                    raise StoreError("invalid_label_cutoff") from None
            cursor = self.db.execute("SELECT * FROM observations WHERE batch_id=? ORDER BY label NULLS LAST,ordinal", [batch_id])
            names = [item[0] for item in cursor.description]
            selected, unlocated = [], []
            all_unlocated = 0
            for values in cursor.fetchall():
                item = dict(zip(names, values))
                all_unlocated += item["label"] is None
                if (ordinal_start is not None and item["ordinal"] < ordinal_start) or (ordinal_end is not None and item["ordinal"] > ordinal_end):
                    continue
                if item["label"] is not None and cutoff is not None and item["label"] > cutoff:
                    continue
                row = {key: item[key] for key in ("ordinal", "locator", "source_label", "label")}
                row.update(tokens=json.loads(item["tokens_json"]), checks=json.loads(item["checks_json"]),
                           values={key: None if item["source_" + key] is None else decimal_text(item["source_" + key]) for key in VALUE_FIELDS},
                           volume_shares=None, amount_cny=None)
                (unlocated if item["label"] is None else selected).append(row)
            totals = {}
            for field in VALUE_FIELDS:
                values = [Decimal(row["values"][field]) for row in selected if row["values"][field] is not None]
                totals[field] = {"known_sum": decimal_text(exact_sum(values)), "available_rows": len(values), "unavailable_rows": len(selected) - len(values), "meaning": "source_value_arithmetic"}
            selection = dict(snapshot_id=snapshot_id, mode=mode, cutoff=cutoff, ordinal_start=ordinal_start,
                             ordinal_end=ordinal_end, fields=list(VALUE_FIELDS), versions=manifest["versions"])
            return {"snapshot_id": snapshot_id, "batch_id": batch_id, "selection": selection, "query_id": _identity(selection),
                    "manifest": manifest, "metadata": metadata, "rows": selected, "unlocated": unlocated,
                    "counts": dict(selected_rows=len(selected), unlocated_rows=len(unlocated), batch_rows=batch_rows, batch_unlocated_rows=all_unlocated),
                    "quality": self._quality(selected), "unlocated_quality": self._quality(unlocated),
                    "batch_checks": json.loads(batch_checks), "totals": totals}

    def export_json(self, snapshot_id, destination=None, **selection):
        with self._mutex:
            result = self.query(snapshot_id, **selection)
            content = _json(result).encode("utf-8")
            path = Path(destination) if destination else self.root / "exports" / snapshot_id / (result["query_id"] + ".json")
            _publish_bytes(path, content)
            return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "query_id": result["query_id"]}

    def export_parquet(self, snapshot_id, destination=None, **selection):
        with self._mutex:
            result = self.query(snapshot_id, **selection)
            records = []
            for scope in ("rows", "unlocated"):
                for row in result[scope]:
                    record = {"scope": scope, **{name: row[name] for name in ("ordinal", "locator", "source_label", "label")},
                              "tokens_json": _json(row["tokens"]), "checks_json": _json(row["checks"]), "volume_shares": None, "amount_cny": None}
                    for name in VALUE_FIELDS:
                        value = row["values"][name]
                        record["source_" + name] = None if value is None else (integer_value(value) if name == "volume" else decimal_value(value))
                    records.append(record)
            schema = pa.schema([("scope", pa.string()), *[field for field in ROW_SCHEMA if field.name != "batch_id"]])
            metadata = {key: value for key, value in result.items() if key not in {"rows", "unlocated"}}
            table = pa.Table.from_pylist(records, schema=schema).replace_schema_metadata({b"anatrading_query": _json(metadata).encode("utf-8")})
            stream = pa.BufferOutputStream()
            pq.write_table(table, stream)
            content = stream.getvalue().to_pybytes()
            path = Path(destination) if destination else self.root / "exports" / snapshot_id / (result["query_id"] + ".parquet")
            _publish_bytes(path, content)
            return {"path": str(path), "sha256": hashlib.sha256(content).hexdigest(), "query_id": result["query_id"]}

    def backup(self, destination):
        with self._mutex:
            destination = Path(destination).resolve()
            if destination == self.root or self.root.is_relative_to(destination) or destination.is_relative_to(self.root):
                raise StoreError("backup_destination_overlaps_source")
            if destination.exists() and any(destination.iterdir()):
                raise StoreError("destination_not_empty")
            destination.mkdir(parents=True, exist_ok=True)
            objects = self.db.execute("SELECT sha,byte_length FROM raw_objects ORDER BY sha").fetchall()
            for sha, length in objects:
                self._verify_raw(sha, length)
            self.db.close()
            self.db = None
            try:
                self._checkpoint("backup_closed")
                wal = self.root / "research.duckdb.wal"
                if wal.exists() and wal.stat().st_size:
                    raise StoreError("database_not_cleanly_closed")
                files = [self.root / "research.duckdb", *[self._raw_path(sha) for sha, _ in objects]]
                manifest = {"schema": VERSIONS["schema"], "status": "complete", "files": {}}
                for source in files:
                    relative = source.relative_to(self.root).as_posix()
                    target = destination / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                    digest = _digest(source)
                    if _digest(target) != digest:
                        raise StoreError("backup_hash_mismatch")
                    manifest["files"][relative] = digest
                _publish_bytes(destination / "manifest.json", _json(manifest).encode("utf-8"))
                return manifest
            finally:
                self.db = duckdb.connect(str(self.root / "research.duckdb"))

    @staticmethod
    def restore(backup_dir, destination):
        backup_dir, destination = Path(backup_dir).resolve(), Path(destination).resolve()
        if destination == backup_dir or destination.is_relative_to(backup_dir) or backup_dir.is_relative_to(destination):
            raise StoreError("restore_destination_overlaps_backup")
        if destination.exists() and any(destination.iterdir()):
            raise StoreError("destination_not_empty")
        try:
            manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            raise StoreError("invalid_backup_manifest") from None
        if (not isinstance(manifest, dict) or manifest.get("status") != "complete"
                or manifest.get("schema") != VERSIONS["schema"] or not isinstance(manifest.get("files"), dict)
                or "research.duckdb" not in manifest["files"]):
            raise StoreError("invalid_backup_manifest")
        for relative, digest in manifest["files"].items():
            if not isinstance(digest, str) or not re.fullmatch("[0-9a-f]{64}", digest):
                raise StoreError("invalid_backup_manifest")
            source = (backup_dir / relative).resolve()
            if not source.is_relative_to(backup_dir) or not (relative == "research.duckdb" or re.fullmatch(r"raw/[0-9a-f]{2}/[0-9a-f]{64}", relative)):
                raise StoreError("invalid_backup_path")
            if not source.is_file() or _digest(source) != digest:
                raise StoreError("backup_hash_mismatch")
        destination.mkdir(parents=True, exist_ok=True)
        with _DirectoryLock(destination):
            if any(path.name != ".operation.lock" for path in destination.iterdir()):
                raise StoreError("destination_not_empty")
            incomplete = destination / ".restore-incomplete"
            _publish_bytes(incomplete, b"Restore has not passed verification.\n")
            for relative, digest in manifest["files"].items():
                target = destination / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(backup_dir / relative, target)
                if _digest(target) != digest:
                    raise StoreError("backup_hash_mismatch")
            # Byte equality preserves frozen query contents; verify referenced objects
            # again under the same lock, without opening a second application instance.
            with duckdb.connect(str(destination / "research.duckdb"), read_only=True) as database:
                version = database.execute("SELECT value FROM app_meta WHERE key='schema'").fetchone()
                if version != (VERSIONS["schema"],):
                    raise StoreError("unsupported_schema")
                for sha, length in database.execute("SELECT sha,byte_length FROM raw_objects").fetchall():
                    if not re.fullmatch("[0-9a-f]{64}", sha):
                        raise StoreError("invalid_object_id")
                    relative = f"raw/{sha[:2]}/{sha}"
                    path = destination / relative
                    if relative not in manifest["files"] or not path.is_file():
                        raise StoreError("raw_object_missing")
                    if path.stat().st_size != length or _digest(path) != sha:
                        raise StoreError("raw_object_corrupt")
            incomplete.unlink()
        return {"status": "restored", "destination": str(destination)}
