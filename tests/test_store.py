"""Public boundary cases for the evidence-store query and export contract."""
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import struct

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import anatrading.store as module
from anatrading.models import VERSIONS
from anatrading.store import EvidenceStore, StoreError


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows operation locks")
TEXT = "tdx-public-text-v1"
FIELDS = ("open", "high", "low", "close", "volume", "amount")


def text_bytes(rows):
    lines = ["601577 合成验收 1分钟线 不复权",
             "日期\t时间\t开盘\t最高\t最低\t收盘\t成交量\t成交额"]
    lines.extend(",".join(row) for row in rows)
    return ("\r\n".join([*lines, "数据来源:通达信"]) + "\r\n").encode("gbk")


def record(time="0931", **overrides):
    values = dict(open="10", high="11", low="9", close="10", volume="100", amount="1000")
    values.update(overrides)
    return ["2021/02/26", time, *(values[field] for field in FIELDS)]


def imported(store, rows, **kwargs):
    result = store.import_bytes(text_bytes(rows), TEXT, **kwargs)
    assert result["status"] == "committed", result
    return result["snapshot_id"]


def test_cutoff_and_ordinals_share_one_selection_with_separate_unlocated(tmp_path):
    with EvidenceStore(tmp_path / "root") as store:
        snapshot = imported(store, [record("0932"), record("2500", amount="bad"),
                                    record("0931"), record("0931", volume="200", amount="2000"),
                                    record("0933", open="")])
        result = store.query(snapshot, cutoff="2021-02-26T09:31", ordinal_start=2, ordinal_end=4)
        assert [row["ordinal"] for row in result["rows"]] == [3, 4]
        assert [row["ordinal"] for row in result["unlocated"]] == [2]
        assert result["counts"] == dict(selected_rows=2, unlocated_rows=1, batch_rows=5, batch_unlocated_rows=1)
        assert result["totals"]["volume"]["known_sum"] == "300"
        assert result["totals"]["amount"]["known_sum"] == "3000"
        assert result["quality"]["numeric.amount"] == {"pass": 2, "fail": 0, "not_evaluated": 0}
        assert result["quality"]["duplicate_label"]["fail"] == 2
        assert result["unlocated_quality"]["numeric.amount"]["fail"] == 1
        assert store.query(snapshot)["counts"]["selected_rows"] == 4
        assert store.query(snapshot, ordinal_start=4)["counts"]["unlocated_rows"] == 0
        empty = store.query(snapshot, cutoff="2020-01-01T00:00")
        assert empty["rows"] == [] and len(empty["unlocated"]) == 1
        assert empty["totals"]["volume"]["available_rows"] == 0
        assert empty["totals"]["volume"]["known_sum"] == "0"


def test_json_and_parquet_keep_exact_values_null_zero_and_all_selected_state(tmp_path):
    with EvidenceStore(tmp_path / "root") as store:
        snapshot = imported(store, [record(open="0.123456789012345678", volume="9007199254740993",
                                           amount="99999999999999999999.999999999999999999"),
                                    record("0932", open="", volume="0", amount="0"),
                                    record("2500", volume="1.5", amount="NaN"), record("0933")])
        selection = dict(cutoff="2021-02-26T09:32", ordinal_start=1, ordinal_end=3)
        result = store.query(snapshot, **selection)
        json_export = store.export_json(snapshot, **selection)
        content = Path(json_export["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == json_export["sha256"]
        assert json.loads(content) == result
        assert store.export_json(snapshot, **selection) == json_export
        first, second = result["rows"]
        assert first["values"]["open"] == "0.123456789012345678"
        assert first["values"]["volume"] == "9007199254740993"
        assert first["values"]["amount"] == "99999999999999999999.999999999999999999"
        assert second["values"]["open"] is None
        assert second["values"]["volume"] == second["values"]["amount"] == "0"
        assert result["unlocated"][0]["values"]["volume"] is None
        for row in result["rows"] + result["unlocated"]:
            assert row["volume_shares"] is row["amount_cny"] is None
            assert all(value is None or isinstance(value, str) for value in row["values"].values())
        parquet_export = store.export_parquet(snapshot, **selection)
        table = pq.read_table(parquet_export["path"])
        assert table.schema.field("source_volume").type == pa.int64()
        assert table.schema.field("source_amount").type == pa.decimal128(38, 18)
        metadata = json.loads(table.schema.metadata[b"anatrading_query"])
        assert metadata == {key: value for key, value in result.items() if key not in {"rows", "unlocated"}}
        records = table.to_pylist()
        assert [row["scope"] for row in records] == ["rows", "rows", "unlocated"]
        assert records[0]["source_open"] == Decimal("0.123456789012345678")
        assert records[0]["source_volume"] == 9007199254740993
        assert records[0]["source_amount"] == Decimal(first["values"]["amount"])
        assert records[1]["source_open"] is None and records[1]["source_volume"] == 0
        assert records[2]["source_volume"] is None
        for actual, expected in zip(records, result["rows"] + result["unlocated"]):
            assert json.loads(actual["checks_json"]) == expected["checks"]
            assert json.loads(actual["tokens_json"]) == expected["tokens"]
        empty = store.export_parquet(snapshot, cutoff="2020-01-01T00:00", ordinal_end=1)
        assert pq.read_table(empty["path"]).num_rows == 0


def test_wider_exact_sums_are_strings_without_single_value_column_cast(tmp_path):
    with EvidenceStore(tmp_path / "root") as store:
        row = record(amount="99999999999999999999.999999999999999999", volume="9223372036854775807")
        result = store.query(imported(store, [row, row]))
        assert result["totals"]["amount"]["known_sum"] == "199999999999999999999.999999999999999998"
        assert result["totals"]["volume"]["known_sum"] == "18446744073709551614"


def test_unusable_fields_keep_tokens_and_explicit_reasons(tmp_path):
    with EvidenceStore(tmp_path / "root") as store:
        result = store.query(imported(store, [record(open="1e-19", high="1e20", volume="1.5", amount="NaN"),
                                                record("0932", open="", amount="")]))
        first, second = result["rows"]
        assert first["values"]["open"] is first["values"]["high"] is first["values"]["volume"] is first["values"]["amount"] is None
        assert first["tokens"]["volume"] == "1.5"
        assert {c["name"]: c["reason"] for c in first["checks"]}["numeric.open"] == "decimal_scale"
        assert result["totals"]["amount"]["unavailable_rows"] == 2
        assert {c["name"]: c["outcome"] for c in second["checks"]}["numeric.amount"] == "not_evaluated"


def test_source_revision_interpretation_and_rule_version_have_distinct_snapshots(tmp_path, monkeypatch):
    with EvidenceStore(tmp_path / "root") as store:
        original = imported(store, [record()])
        frozen = store.query(original)
        declared = imported(store, [record()], interpretation=dict(volume_unit="shares", instrument="601577"))
        revised = imported(store, [record(close="10.5")])
        with monkeypatch.context() as patch:
            patch.setitem(VERSIONS, "quality", "test-new-rules")
            new_rules = imported(store, [record()])
        assert len({original, declared, revised, new_rules}) == 4
        assert store.query(original) == frozen
        declared_view = store.query(declared)
        contract_bytes = json.dumps(frozen["manifest"]["contract"], sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":")).encode("utf-8")
        contract_id = hashlib.sha256(contract_bytes).hexdigest()
        assert frozen["manifest"]["source_contract_id"] == contract_id
        assert store.query(revised)["manifest"]["source_contract_id"] == contract_id
        assert frozen["selection"]["fields"] == list(FIELDS)
        assert frozen["manifest"]["versions"]["normalization"] == "disabled-1"
        assert declared_view["metadata"]["instrument_id"] is None
        assert declared_view["rows"][0]["volume_shares"] is None
        assert declared_view["manifest"]["contract"]["standard_units"]["status"] == "unknown"


@pytest.mark.parametrize("arguments,code", [
    ({"mode": "assumed"}, "mode_not_supported"),
    ({"mode": "evidenced_pit"}, "mode_not_supported"),
    ({"cutoff": "2021-02-26"}, "invalid_label_cutoff"),
    ({"cutoff": "2021-02-30T09:31"}, "invalid_label_cutoff"),
    ({"cutoff": "2021-02-26T09:31Z"}, "invalid_label_cutoff"),
    ({"ordinal_start": True}, "invalid_ordinal_range"),
    ({"ordinal_start": 0}, "invalid_ordinal_range"),
    ({"ordinal_end": 1.5}, "invalid_ordinal_range"),
    ({"ordinal_start": 2, "ordinal_end": 1}, "invalid_ordinal_range"),
])
def test_query_invalid_selectors_fail_without_changing_snapshot(tmp_path, arguments, code):
    with EvidenceStore(tmp_path / "root") as store:
        snapshot = imported(store, [record()])
        with pytest.raises(StoreError) as caught:
            store.query(snapshot, **arguments)
        assert caught.value.code == code
        assert len(store.list_snapshots()) == 1


def test_daily_cutoff_stays_a_date_without_inventing_midnight(tmp_path):
    raw = b"".join(struct.pack("<IIIIIfII", day, 1000, 1100, 900, 1000, 1000, 100, 0)
                   for day in (20210225, 20210226))
    with EvidenceStore(tmp_path / "root") as store:
        attempt = store.import_bytes(raw, "tdx-public-day-v1")
        result = store.query(attempt["snapshot_id"], cutoff="2021-02-25")
        assert [row["label"] for row in result["rows"]] == ["2021-02-25"]
        assert result["manifest"]["contract"]["temporal_semantics"]["status"] == "unknown"
        with pytest.raises(StoreError, match="invalid_label_cutoff"):
            store.query(attempt["snapshot_id"], cutoff="2021-02-25T00:00")


def test_structural_rejection_preserves_original_without_creating_snapshot(tmp_path):
    raw = b"truncated-day-file"
    with EvidenceStore(tmp_path / "root") as store:
        result = store.import_bytes(raw, "tdx-public-day-v1")
        assert result["status"] == "rejected" and result["error_code"] == "invalid_day_length"
        digest = hashlib.sha256(raw).hexdigest()
        assert result["raw_sha256"] == digest
        assert (store.root / "raw" / digest[:2] / digest).read_bytes() == raw
        assert store.list_snapshots() == []


@pytest.mark.parametrize("format_id", module.FORMAT_IDS)
def test_recognizable_control_file_cannot_bypass_preflight_with_another_format(tmp_path, capsys, format_id):
    marker = b"SYNTHETIC_LOGIN_CONTROL_DO_NOT_PERSIST"
    body = b"0\x01success\x01login\x01anonymous\x01" + marker
    raw = f"00.9.10\x0101\x01{len(body):010d}".encode("ascii") + body
    root = tmp_path / "root"
    stages = []
    source = tmp_path / "source.txt"
    source.write_bytes(raw)
    with EvidenceStore(root, checkpoint=stages.append) as store:
        result = store.import_file(source, format_id)
        assert result["status"] == "rejected"
        assert result["error_code"] == "non_market_payload"
        assert result["raw_sha256"] is None
        assert store.list_snapshots() == []
        assert "raw_published" not in stages
        assert store.attempts()[0]["error_code"] == "non_market_payload"
    assert not (root / "raw").exists()
    assert not (root / "staging").exists()
    for path in root.rglob("*"):
        if path.is_file():
            assert marker not in path.read_bytes()
    captured = capsys.readouterr()
    assert marker.decode("ascii") not in captured.out + captured.err


def test_export_does_not_overwrite_different_existing_file(tmp_path):
    with EvidenceStore(tmp_path / "root") as store:
        snapshot = imported(store, [record()])
        target = tmp_path / "existing.json"
        target.write_bytes(b"user-content")
        with pytest.raises(StoreError, match="destination_exists"):
            store.export_json(snapshot, target)
        assert target.read_bytes() == b"user-content"
        assert len(store.list_snapshots()) == 1


def test_restore_rejects_nonempty_destination_and_modified_backup(tmp_path):
    root, backup = tmp_path / "root", tmp_path / "backup"
    with EvidenceStore(root) as store:
        imported(store, [record()])
        manifest = store.backup(backup)
        assert manifest["status"] == "complete"
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "keep.txt").write_bytes(b"keep")
    with pytest.raises(StoreError, match="destination_not_empty"):
        EvidenceStore.restore(backup, destination)
    assert (destination / "keep.txt").read_bytes() == b"keep"
    (backup / "research.duckdb").write_bytes(b"modified")
    with pytest.raises(StoreError, match="backup_hash_mismatch"):
        EvidenceStore.restore(backup, tmp_path / "new")


def test_failed_backup_has_no_complete_manifest_and_reopens_source(tmp_path, monkeypatch):
    with EvidenceStore(tmp_path / "root") as store:
        snapshot = imported(store, [record()])
        def fail_copy(*args):
            raise OSError("injected-copy-failure")
        with monkeypatch.context() as patch:
            patch.setattr(module.shutil, "copyfile", fail_copy)
            with pytest.raises(OSError):
                store.backup(tmp_path / "backup")
        assert not (tmp_path / "backup" / "manifest.json").exists()
        assert store.query(snapshot)["counts"]["selected_rows"] == 1
