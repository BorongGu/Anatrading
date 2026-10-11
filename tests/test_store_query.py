"""SQL filtering matches an independent full-batch Python selection oracle."""
from decimal import Decimal, localcontext
import hashlib
import itertools
import json

import pytest

from anatrading.store import EvidenceStore, StoreError
from test_formats import bao_payload
from test_store import record, text_bytes


FIELDS = ("open", "high", "low", "close", "volume", "amount")


def fixed_text(value):
    if value is None:
        return None
    if isinstance(value, int):
        return str(value)
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def quality(rows):
    counts = {}
    for row in rows:
        for check in row["checks"]:
            bucket = counts.setdefault(check["name"], dict.fromkeys(("pass", "fail", "not_evaluated"), 0))
            bucket[check["outcome"]] += 1
    return counts


def reference_query(store, snapshot, cutoff=None, ordinal_start=None, ordinal_end=None):
    batch, sha, manifest, metadata, checks, batch_rows = store.db.execute(
        "SELECT s.batch_id,b.raw_sha256,b.manifest_json,b.metadata_json,b.checks_json,b.row_count "
        "FROM snapshots s JOIN batches b USING(batch_id) WHERE s.snapshot_id=?", [snapshot]).fetchone()
    cursor = store.db.execute("SELECT * FROM observations WHERE batch_id=?", [batch])
    names = [column[0] for column in cursor.description]
    all_rows = [dict(zip(names, values)) for values in cursor.fetchall()]
    all_rows.sort(key=lambda row: (row["label"] is None, row["label"] or "", row["ordinal"]))
    selected, unlocated = [], []
    for row in all_rows:
        if ordinal_start is not None and row["ordinal"] < ordinal_start:
            continue
        if ordinal_end is not None and row["ordinal"] > ordinal_end:
            continue
        if row["label"] is not None and cutoff is not None and row["label"] > cutoff:
            continue
        value = {key: row[key] for key in ("ordinal", "locator", "source_label", "label")}
        value.update(tokens=json.loads(row["tokens_json"]), checks=json.loads(row["checks_json"]),
                     values={field: fixed_text(row["source_" + field]) for field in FIELDS},
                     volume_shares=None, amount_cny=None)
        (unlocated if row["label"] is None else selected).append(value)
    totals = {}
    for field in FIELDS:
        values = [Decimal(row["values"][field]) for row in selected if row["values"][field] is not None]
        with localcontext() as context:
            context.prec = 128
            total = sum(values, Decimal(0))
        totals[field] = dict(known_sum=fixed_text(total), available_rows=len(values),
                             unavailable_rows=len(selected) - len(values), meaning="source_value_arithmetic")
    manifest = json.loads(manifest)
    selection = dict(snapshot_id=snapshot, mode="retrospective", cutoff=cutoff,
                     ordinal_start=ordinal_start, ordinal_end=ordinal_end, fields=list(FIELDS), versions=manifest["versions"])
    serialized = json.dumps(selection, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    return dict(snapshot_id=snapshot, batch_id=batch, selection=selection,
                query_id=hashlib.sha256(serialized.encode()).hexdigest(), manifest=manifest,
                metadata=json.loads(metadata), rows=selected, unlocated=unlocated,
                counts=dict(selected_rows=len(selected), unlocated_rows=len(unlocated), batch_rows=batch_rows,
                            batch_unlocated_rows=sum(row["label"] is None for row in all_rows)),
                quality=quality(selected), unlocated_quality=quality(unlocated),
                batch_checks=json.loads(checks), totals=totals)


@pytest.fixture(params=["minute", "daily"])
def sample(tmp_path, request):
    if request.param == "minute":
        raw = text_bytes([record("0933"), record("2500", amount="bad"),
                          record("0931", open="0.123456789012345678", volume="9007199254740993",
                                 amount="99999999999999999999.999999999999999999"),
                          record("0931", volume="0", amount="0"), record("0932", open=""),
                          record("2501", amount="NaN"), record("0934")])
        format_id = "tdx-public-text-v1"
        cutoffs = [None, "2020-01-01T00:00", "2021-02-26T09:31", "2021-02-26T09:32", "2022-01-01T00:00"]
    else:
        dates = ["2021-02-28", "invalid", "2021-02-26", "2021-02-26", "2021-02-27", "2021-02-30", "2021-03-01"]
        rows = [[date, "sh.601577", "10", "11", "9", "10", "100", "1000", "3"] for date in dates]
        rows[2][2], rows[2][6], rows[2][7] = "0.123456789012345678", "9007199254740993", "99999999999999999999.999999999999999999"
        rows[1][7], rows[3][6], rows[3][7], rows[4][2] = "bad", "0", "0", ""
        raw, format_id = bao_payload(rows), "baostock-decoded-v0.9.4"
        cutoffs = [None, "2020-01-01", "2021-02-26", "2021-02-27", "2022-01-01"]
    with EvidenceStore(tmp_path) as store:
        imported = store.import_bytes(raw, format_id)
        assert imported["status"] == "committed", imported
        yield store, imported["snapshot_id"], cutoffs


def test_all_cutoff_and_ordinal_selections_match_full_batch_reference(sample):
    store, snapshot, cutoffs = sample
    starts = [None, 1, 2, 3, 6, 7, 8, 2**63, 10**100]
    ends = [None, 1, 2, 4, 6, 7, 8, 2**63, 10**100]
    for cutoff, start, end in itertools.product(cutoffs, starts, ends):
        if start is not None and end is not None and start > end:
            continue
        selection = dict(cutoff=cutoff, ordinal_start=start, ordinal_end=end)
        assert store.query(snapshot, **selection) == reference_query(store, snapshot, **selection), selection


class TrackingConnection:
    def __init__(self, connection):
        self.connection = connection
        self.calls = []
        self.fetched = []

    def execute(self, statement, parameters=None):
        self.calls.append((statement, parameters))
        self.connection.execute(statement, parameters)
        return self

    @property
    def description(self):
        return self.connection.description

    def fetchone(self):
        return self.connection.fetchone()

    def fetchall(self):
        values = self.connection.fetchall()
        if self.calls[-1][0].startswith("SELECT * FROM observations"):
            self.fetched.append(len(values))
        return values

    def close(self):
        self.connection.close()


def test_query_materializes_only_sql_selected_rows_and_counts_full_batch(sample):
    store, snapshot, cutoffs = sample
    tracked = store.db = TrackingConnection(store.db)
    result = store.query(snapshot, cutoff=cutoffs[2], ordinal_start=3, ordinal_end=4)
    assert result["counts"] == dict(selected_rows=2, unlocated_rows=0, batch_rows=7, batch_unlocated_rows=2)
    assert tracked.fetched == [2]
    statement, parameters = next(call for call in tracked.calls if call[0].startswith("SELECT * FROM observations"))
    assert "ordinal>=?" in statement and "ordinal<=?" in statement
    assert "(label IS NULL OR label<=?)" in statement
    assert parameters[1:] == [3, 4, cutoffs[2]]


def test_budget_preflight_counts_unlocated_and_never_materializes_rows(sample):
    store, snapshot, cutoffs = sample
    expected = [len(reference_query(store, snapshot, cutoff=c)["rows"]) + 2 for c in cutoffs]
    tracked = store.db = TrackingConnection(store.db)
    assert [store.query_row_count(snapshot, cutoff=c) for c in cutoffs] == expected
    assert tracked.fetched == []
    assert all(not sql.startswith("SELECT * FROM observations") for sql, _ in tracked.calls)
    for cutoff in (True, "2021-02-30", "invalid", 3, "2021-02-26T09:31:00"):
        with pytest.raises(StoreError, match="invalid_label_cutoff"):
            store.query_row_count(snapshot, cutoff=cutoff)
    for invalid in (None, "", "f" * 63, True):
        with pytest.raises(StoreError, match="invalid_snapshot_id"):
            store.query_row_count(invalid)
    with pytest.raises(StoreError, match="snapshot_not_found"):
        store.query_row_count("0" * 64)


def test_repeated_query_and_preflight_never_bypass_original_hash(sample):
    store, snapshot, _ = sample
    first = store.query(snapshot)
    sha = first["manifest"]["raw_sha256"]
    path = store.root / "raw" / sha[:2] / sha
    original = path.read_bytes()
    path.write_bytes(bytes([original[0] ^ 1]) + original[1:])
    # Counting is explicitly only admission metadata, never proof of evidence.
    assert store.query_row_count(snapshot) == 7
    with pytest.raises(StoreError, match="raw_object_corrupt"):
        store.query(snapshot, ordinal_start=10**100)
    path.write_bytes(original)
    assert store.query(snapshot) == first
