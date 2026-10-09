"""Causal source-quantity comparisons and independent native integer oracle."""
from copy import deepcopy
from fractions import Fraction
import hashlib
from pathlib import Path
import struct

import pytest

from anatrading.daily_volume import daily_volume_report
from anatrading.store import EvidenceStore


def row(day, ordinal, volume):
    return dict(ordinal=ordinal, label=f"2026-09-{day:02d}", tokens={},
                values=dict(volume=volume, open="bad", amount=None))


def query(rows, unlocated=()):
    return dict(snapshot_id="a" * 64, query_id="b" * 64, metadata=dict(period="1d"),
                rows=rows, unlocated=list(unlocated))


def sample():
    return query([row(28, 1, "10"), row(29, 2, "30"), row(30, 3, "50")])


def test_hand_current_excluded_and_display_window_does_not_crop_history():
    context = sample()
    before = deepcopy(context)
    selected = query(context["rows"][-1:])
    selected["query_id"] = "c" * 64
    report = daily_volume_report(selected, context, 2)
    value = report["rows"][0]
    assert value["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert value["current"] == "50" and value["baseline_sum"] == "40"
    assert value["baseline_mean"] == dict(numerator="20", denominator="1", display="20.0000")
    assert value["ratio"] == dict(numerator="5", denominator="2", display="2.5000")
    assert [m["value"] for m in value["members"]] == ["10", "30"]
    assert report["query_id"] != report["context_query_id"] and context == before


@pytest.mark.parametrize("bad,reason", [(None, "missing_quantity"), ("bad", "invalid_quantity"),
    ("-1", "invalid_quantity"), ("1.5", "invalid_quantity"), (True, "invalid_quantity"),
    (1.0, "invalid_quantity"), ("9223372036854775808", "invalid_quantity")])
def test_bad_history_date_occupies_window_without_replacement(bad, reason):
    context = sample()
    context["rows"].insert(0, row(27, 4, "1000"))
    context["rows"][2]["values"]["volume"] = bad
    value = daily_volume_report(context, context, 2)["rows"][-1]
    assert value["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert value["reason"] == reason and value["ratio"] is None


def test_zero_and_wide_integer_sums():
    context = sample()
    context["rows"][-1]["values"]["volume"] = "0"
    value = daily_volume_report(context, context, 2)["rows"][-1]
    assert value["ratio"] == dict(numerator="0", denominator="1", display="0.0000")
    for r in context["rows"][:2]: r["values"]["volume"] = "0"
    value = daily_volume_report(context, context, 2)["rows"][-1]
    assert value["reason"] == "zero_baseline" and value["baseline_mean"]["numerator"] == "0"
    maximum = 9223372036854775807
    for r in context["rows"]: r["values"]["volume"] = str(maximum)
    value = daily_volume_report(context, context, 2)["rows"][-1]
    assert value["baseline_sum"] == str(2 * maximum) and value["ratio"]["display"] == "1.0000"


@pytest.mark.parametrize("day", [29, 30])
def test_duplicate_current_or_history_is_not_compared(day):
    context = sample()
    context["rows"].append(row(day, 4, "5000"))
    value = daily_volume_report(query([context["rows"][2]]), context, 2)["rows"][0]
    assert value["reason"] == "duplicate_date" and value["ratio"] is None


def test_dated_unlocated_blocks_window_and_unknown_date_is_disclosed():
    context = sample()
    dated = context["rows"].pop(1)
    dated.update(label=None, tokens=dict(source_date="20260929"))
    unknown = row(1, 4, "999")
    unknown.update(label=None, tokens=dict(date="unreadable"))
    context["unlocated"] = [dated, unknown]
    report = daily_volume_report(context, context, 2)
    assert report["rows"][-1]["reason"] == "unlocated_label"
    assert report["rows"][-1]["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert report["context_unlocated_rows"] == 2 and report["unreadable_date_rows"] == 1
    assert all(r["reason"] == "unlocated_label" for r in report["unlocated"])


def test_future_append_source_order_and_constant_scale_invariance():
    context = sample()
    original = daily_volume_report(context, context, 2)["rows"]
    future = row(30, 4, "9999")
    future["label"] = "2026-10-01"
    later = query([future, *reversed(deepcopy(context["rows"]))])
    assert daily_volume_report(context, later, 2)["rows"] == original
    scaled = deepcopy(context)
    for r in scaled["rows"]: r["values"]["volume"] = str(int(r["values"]["volume"]) * 100)
    assert daily_volume_report(scaled, scaled, 2)["rows"][-1]["ratio"] == original[-1]["ratio"]


def test_parameter_context_and_warmup_boundaries():
    context = sample()
    assert all(r["reason"] == "history_insufficient" for r in daily_volume_report(context, context)["rows"])
    for n in (1, 253, True, "20"):
        with pytest.raises(ValueError, match="invalid_lookback"): daily_volume_report(context, context, n)
    wrong = deepcopy(context)
    wrong["snapshot_id"] = "d" * 64
    with pytest.raises(ValueError, match="context_snapshot_mismatch"): daily_volume_report(context, wrong)
    wrong = deepcopy(context)
    wrong["metadata"]["period"] = "1m"
    assert all(r["reason"] == "unsupported_period" for r in daily_volume_report(wrong, wrong)["rows"])


def test_real_native_uint32_oracle_every_window(tmp_path):
    path = Path(__file__).resolve().parents[1] / "data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78/after.day"
    if not path.exists(): pytest.skip("Private real sample unavailable; no source compatibility claim")
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30"
    source = list(struct.iter_unpack("<IIIIIfII", data))
    assert len(source) == 7068 and all(a[0] < b[0] for a, b in zip(source, source[1:]))
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(data, "tdx-public-day-v1", interpretation=dict(instrument="600059.SH", venue="SH"))["snapshot_id"]
        context = store.query(sid)
        report = daily_volume_report(context, context)
        for i, value in enumerate(report["rows"]):
            assert value["current"] == str(source[i][6])
            if i < 20:
                assert value["reason"] == "history_insufficient"
                continue
            window = source[i-20:i]
            total = sum(x[6] for x in window)
            assert value["baseline_sum"] == str(total)
            mean, ratio = value["baseline_mean"], value["ratio"]
            assert Fraction(int(mean["numerator"]), int(mean["denominator"])) == Fraction(total, 20)
            assert Fraction(int(ratio["numerator"]), int(ratio["denominator"])) == Fraction(source[i][6] * 20, total)
            assert [d.replace("-", "") for d in value["history_dates"]] == [str(x[0]) for x in window]
            assert [m["value"] for m in value["members"]] == [str(x[6]) for x in window]
        assert [r["ratio"]["display"] for r in report["rows"][-3:]] == ["2.0931", "1.7651", "1.2994"]
        selected = store.query(sid, ordinal_start=7068, ordinal_end=7068)
        assert daily_volume_report(selected, context)["rows"] == report["rows"][-1:]
