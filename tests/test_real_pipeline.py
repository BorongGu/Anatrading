"""Private G1 controls through the product store and both export paths.

Control values are frozen from docs/qualification/{tdx-public-samples,
baostock-samples}.md, not calculated by the product decoder as an oracle.
Original market files remain private under data/reference and artifacts.
Missing fixtures explicitly skip; these tests never fetch replacement data.
The 1m/5m comparison reproduces the audit's label-end hypothesis only and
does not establish true bar boundaries or introduce product resampling.
"""
from collections import Counter
from datetime import datetime, timedelta
from decimal import Context, Decimal, Inexact, InvalidOperation, Overflow, Rounded, localcontext
import hashlib
import json
import os
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from anatrading.store import EvidenceStore


pytestmark = pytest.mark.skipif(os.name != "nt", reason="The first store contract requires Windows OS locking")
ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("open", "high", "low", "close", "volume", "amount")
EXACT = Context(prec=128, traps=[Inexact, Rounded, Overflow, InvalidOperation])
TEXT = "tdx-public-text-v1"
DAY = "tdx-public-day-v1"
BAO = "baostock-decoded-v0.9.4"

# Each tuple: private path, format, original hash, rows, canonical hash,
# O/H/L/C/V/A sums, strict failures, old-cent diagnostic failures, zero-volume rows.
SAMPLES = {
    "tdx-1m": (
        "data/reference/601577.txt", TEXT,
        "c82327940c47a64890c2b7c2c0114216e5583aef85daca2744ef524e668dba3b", 15840,
        "0b7e20dc3eec62330c67d6f2b78830103394f733e3b0791e6ab4f9b7682f4561",
        ("152726.68", "152884.38", "152572.88", "152730.96", "1766836700", "17405632976.00"),
        1228, 211, 102,
    ),
    "tdx-5m": (
        "data/reference/SH_601577.txt", TEXT,
        "46aee68ca6f442d00e18e3fafb209c01dbed0856baa3cfabb13791682d376993", 3216,
        "79a0d775307041e8a9678c558a35b09fbd73a017d0d9e2bae0fba757056da2ca",
        ("30979.89", "31052.46", "30912.14", "30982.04", "1790109400", "17616628447.00"),
        7, 0, 0,
    ),
    "tdx-day": (
        "data/reference/sz000001.day", DAY,
        "9e817ed7cca1abe86becf39d0c2257858d7db5bb4f57674622fc970c94684dd9", 4995,
        "169cfff4724103e561501978a181cb110fdaba9ff73a340110f6572572eb9b4f",
        ("71701.97", "72968.25", "70572.62", "71754.49", "256093361808", "3682749273576"),
        2, 0, 0,
    ),
    "bao-daily-overlap": (
        "artifacts/qualification/baostock/20261003T161007746978Z/daily-overlap/market-sdk-decoded.txt", BAO,
        "c45a26783b0e90ecbb4c5f0c81a3d891dd7d7ceec5013a6af15e728e4e68af71", 2,
        "caeab1c2db8b517c1c0a988390f29f3110e61d8cf29fa3289625923cadafbcd6",
        ("46.66", "47.02", "45.44", "46.39", "111343786", "2572197242.22"), 0, 0, 0,
    ),
    "bao-minute-overlap": (
        "artifacts/qualification/baostock/20261003T161007746978Z/minute-overlap/market-sdk-decoded.txt", BAO,
        "5741ee0ce09e1b978e08b77b3d3fb31bedd1a08b060d0ff50eb033a78f305134", 48,
        "5d6cfea599be85afb13e45a43ffb1834319567580e579227260a9c383cbdaaad",
        ("487.78", "489.24", "486.15", "487.73", "36455648", "371165424.00"), 0, 0, 0,
    ),
    "bao-minute-recent": (
        "artifacts/qualification/baostock/20261003T161007746978Z/minute-recent/market-sdk-decoded.txt", BAO,
        "3602fd38725805ec17b3826b3b6c792f9f422f1bec4c61f1c528496d7345c7bd", 48,
        "5bda8c0e5fbe3e55eab980dfffce1fe16e91601af9d2d43fa5bf18eda3de1d9b",
        ("463.33", "464.08", "462.86", "463.63", "21868563", "210683227.00"), 0, 0, 0,
    ),
    "bao-bank-overlap": (
        "artifacts/qualification/baostock/20261003T161821401061Z/daily-bank-overlap/market-sdk-decoded.txt", BAO,
        "6cdc6a61ec20dc948f40bb51d09b391d4efd33b28dd75d736b22867a50790d49", 1,
        "57f4664772986e1d0c66ffe37d2576535f9af9d7a423f6e787b4ee8d65d52edb",
        ("10.30", "10.43", "9.99", "10.16", "36455648", "371165422.99"), 0, 0, 0,
    ),
    "bao-bank-recent": (
        "artifacts/qualification/baostock/20261003T161821401061Z/daily-bank-recent/market-sdk-decoded.txt", BAO,
        "1eb4d66ae85fc91a298270f344ca962c63cf22d1e81ad8c0457d569b945ca931", 1,
        "027ebb6775ed7a96aa9132d253a33a1122e990cab44d24a27f9dc8248c57b2dc",
        ("9.51", "9.73", "9.48", "9.71", "21868563", "210683227.15"), 0, 0, 0,
    ),
}


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fixed_text(value):
    # Independent rendering: never format an int with float's `f` conversion.
    if isinstance(value, int):
        return str(value)
    number = value if isinstance(value, Decimal) else Decimal(value)
    text = format(number, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def canonical_hash(rows):
    text = "".join(",".join([row["label"], *(fixed_text(row["values"][field]) for field in FIELDS)]) + "\n"
                   for row in rows)
    return hashlib.sha256(text.encode("ascii")).hexdigest()


def read_parquet_result(path):
    table = pq.read_table(path)
    assert table.schema.field("source_volume").type == pa.int64()
    for field in ("open", "high", "low", "close", "amount"):
        assert table.schema.field("source_" + field).type == pa.decimal128(38, 18)
    assert table.schema.field("volume_shares").type == pa.int64()
    assert table.schema.field("amount_cny").type == pa.decimal128(38, 18)
    result = json.loads(table.schema.metadata[b"anatrading_query"])
    result.update(rows=[], unlocated=[])
    for item in table.to_pylist():
        assert item["scope"] in {"rows", "unlocated"}
        assert type(item["source_volume"]) is int
        assert all(isinstance(item["source_" + name], Decimal) for name in FIELDS if name != "volume")
        row = {key: item[key] for key in ("ordinal", "locator", "source_label", "label")}
        row.update(tokens=json.loads(item["tokens_json"]), checks=json.loads(item["checks_json"]),
                   values={name: fixed_text(item["source_" + name]) for name in FIELDS},
                   volume_shares=item["volume_shares"], amount_cny=item["amount_cny"])
        result[item["scope"]].append(row)
    return result


@pytest.fixture(scope="module")
def pipeline_samples(tmp_path_factory):
    root = tmp_path_factory.mktemp("real-pipeline")
    cache = {}
    with EvidenceStore(root / "evidence") as store:
        def load(name):
            if name in cache:
                return cache[name]
            relative, format_id, raw_hash, *_ = SAMPLES[name]
            source = ROOT / relative
            if not source.is_file():
                pytest.skip(f"Private G1 fixture absent: {relative}; see the two qualification audit reports; no fetch")
            assert digest(source) == raw_hash, f"Frozen private input changed: {name}"
            imported = store.import_file(source, format_id)
            assert imported["status"] == "committed", imported
            assert imported["raw_sha256"] == raw_hash
            snapshot = imported["snapshot_id"]
            queried = store.query(snapshot)
            json_export = store.export_json(snapshot)
            assert digest(json_export["path"]) == json_export["sha256"]
            json_result = json.loads(Path(json_export["path"]).read_text(encoding="utf-8"))
            parquet_export = store.export_parquet(snapshot)
            assert digest(parquet_export["path"]) == parquet_export["sha256"]
            parquet_result = read_parquet_result(parquet_export["path"])
            assert json_export["query_id"] == parquet_export["query_id"] == queried["query_id"]
            assert json_result == queried
            assert parquet_result == queried
            copied_raw = root / "evidence" / "raw" / raw_hash[:2] / raw_hash
            assert digest(copied_raw) == digest(source) == raw_hash
            cache[name] = {"query": queried, "json": json_result, "parquet": parquet_result}
            return cache[name]
        yield load


@pytest.mark.parametrize("name", SAMPLES)
def test_frozen_real_controls_through_import_query_json_parquet(pipeline_samples, name):
    _, format_id, raw_hash, count, expected_hash, totals, strict, cent, zero = SAMPLES[name]
    for route, result in pipeline_samples(name).items():
        rows = result["rows"]
        assert len(rows) == count, route
        assert result["unlocated"] == []
        assert result["counts"] == {"selected_rows": count, "unlocated_rows": 0,
                                     "batch_rows": count, "batch_unlocated_rows": 0}
        assert result["manifest"]["raw_sha256"] == raw_hash
        assert canonical_hash(rows) == expected_hash, route
        assert [row["ordinal"] for row in rows] == list(range(1, count + 1))
        assert all(type(value) is str for row in rows for value in row["values"].values())
        assert all(row["volume_shares"] is None and row["amount_cny"] is None for row in rows)
        assert result["metadata"]["instrument_id"] is None
        for field, expected in zip(FIELDS, totals):
            with localcontext(EXACT):
                independent_sum = sum((Decimal(row["values"][field]) for row in rows), Decimal(0))
            assert independent_sum == Decimal(expected), (route, field)
            reported = result["totals"][field]
            assert reported["known_sum"] == fixed_text(Decimal(expected))
            assert reported["available_rows"] == count and reported["unavailable_rows"] == 0
        for check_name, failures in (("conditional_price_bounds", strict), ("conditional_price_bounds_cent", cent)):
            stored = [check for row in rows for check in row["checks"] if check["name"] == check_name]
            assert len(stored) == count
            assert all(check["assumption"] == "shares_cny_same_coverage" for check in stored)
            assert Counter(check["outcome"] for check in stored) == Counter(
                {"pass": count - failures - zero, "fail": failures, "not_evaluated": zero})
            assert result["quality"][check_name] == {"pass": count - failures - zero,
                                                     "fail": failures, "not_evaluated": zero}
        if format_id == BAO:
            # G1 independently verified the raw tail is 3; SDK's truncated top-level value was empty.
            assert result["metadata"]["source_adjustflag"] == "3"
            assert all(row["tokens"]["adjustflag"] == "3" for row in rows)


@pytest.mark.parametrize("route", ["query", "json", "parquet"])
def test_known_53_cross_period_differences_survive_all_routes(pipeline_samples, route):
    minutes = pipeline_samples("tdx-1m")[route]["rows"]
    five_minutes = pipeline_samples("tdx-5m")[route]["rows"]
    by_label = {row["label"]: row for row in minutes}
    assert len(by_label) == len(minutes)  # Do not silently hide duplicates in the test comparison.
    common_days = {row["label"][:10] for row in minutes} & {row["label"][:10] for row in five_minutes}
    assert len(common_days) == 66
    reference = [row for row in five_minutes if row["label"][:10] in common_days]
    aggregate = []
    for row in reference:
        endpoint = datetime.fromisoformat(row["label"])
        labels = [(endpoint - timedelta(minutes=offset)).isoformat(timespec="minutes") for offset in range(4, -1, -1)]
        assert all(label in by_label and label[:10] == row["label"][:10] for label in labels)
        window = [by_label[label]["values"] for label in labels]
        with localcontext(EXACT):
            values = {
                "open": Decimal(window[0]["open"]), "high": max(Decimal(item["high"]) for item in window),
                "low": min(Decimal(item["low"]) for item in window), "close": Decimal(window[-1]["close"]),
                "volume": sum(int(item["volume"]) for item in window),
                "amount": sum((Decimal(item["amount"]) for item in window), Decimal(0)),
            }
        aggregate.append({"label": row["label"], "values": values})
    assert len(aggregate) == len(reference) == 3168
    assert canonical_hash(aggregate) == "7f9c2b7f7fc738ca0a6331b3965dead4eb942d6da16ff33a0d34752ce7460a23"
    assert canonical_hash(reference) == "75fce0112a4e988339f807bbaafdf5d09937354bb33c4afb2b96c10a8e0f1f33"
    differing = Counter()
    maximum = {field: Decimal(0) for field in FIELDS}
    different_windows = 0
    with localcontext(EXACT):
        for calculated, original in zip(aggregate, reference):
            changed = False
            for field in FIELDS:
                difference = Decimal(calculated["values"][field]) - Decimal(original["values"][field])
                if difference:
                    differing[field] += 1
                    changed = True
                maximum[field] = max(maximum[field], abs(difference))
            different_windows += changed
    assert different_windows == 53 and len(reference) - different_windows == 3115
    assert differing == Counter(open=13, high=2, low=0, close=18, volume=51, amount=52)
    assert maximum == dict(zip(FIELDS, map(Decimal, ("0.04", "0.01", "0", "0.02", "109500", "983294"))))


@pytest.mark.parametrize("route", ["query", "json", "parquet"])
def test_daily_cross_source_and_minute_amount_differences_are_not_repaired(pipeline_samples, route):
    daily = {row["label"]: row["values"] for row in pipeline_samples("tdx-day")[route]["rows"]}
    bao_daily = pipeline_samples("bao-daily-overlap")[route]["rows"]
    with localcontext(EXACT):
        for row, expected_amount_delta in zip(bao_daily, ("58.62", "63.60")):
            tdx = daily[row["label"]]
            assert all(Decimal(row["values"][name]) == Decimal(tdx[name]) for name in FIELDS if name != "amount")
            assert Decimal(row["values"]["amount"]) - Decimal(tdx["amount"]) == Decimal(expected_amount_delta)
        for period, expected_amount_delta in (("overlap", "1.01"), ("recent", "-0.15")):
            minute_rows = pipeline_samples("bao-minute-" + period)[route]["rows"]
            day = pipeline_samples("bao-bank-" + period)[route]["rows"][0]["values"]
            assert sum(int(row["values"]["volume"]) for row in minute_rows) == int(day["volume"])
            minute_amount = sum((Decimal(row["values"]["amount"]) for row in minute_rows), Decimal(0))
            assert minute_amount - Decimal(day["amount"]) == Decimal(expected_amount_delta)
