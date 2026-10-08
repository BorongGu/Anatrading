"""Causal source-date windows and integer arithmetic; no trading efficacy claim."""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct

import pytest

from anatrading.store import EvidenceStore
from anatrading.volume_at_time import _fraction, volume_report


def row(day, clock, value, ordinal):
    return dict(label=f"2026-09-{day:02d}T{clock}", ordinal=ordinal,
                tokens={}, values=dict(volume=value, open=None, amount=None))


def query(rows, unlocated=()):
    return dict(snapshot_id="a" * 64, query_id="b" * 64, metadata=dict(period="1m"),
                rows=rows, unlocated=list(unlocated))


def sample():
    return query([row(day, clock, str(value), ordinal)
                  for ordinal, (day, clock, value) in enumerate([
                      (28, "09:31", 10), (28, "09:32", 20),
                      (29, "09:31", 30), (29, "09:32", 40),
                      (30, "09:31", 50), (30, "09:32", 60)], 1)])


def test_hand_calculation_full_context_and_no_mutation():
    context = sample()
    before = deepcopy(context)
    selected = query(context["rows"][-2:])
    selected["query_id"] = "c" * 64
    result = volume_report(selected, context, 2)
    first, second = result["rows"]
    assert first["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert first["regular"]["baseline_sum"] == "40"
    assert first["regular"]["baseline_mean"] == _fraction(20, 1)
    assert first["regular"]["ratio"] == _fraction(5, 2)
    assert first["cumulative"] == first["regular"]
    assert second["regular"]["ratio"] == _fraction(2, 1)
    assert second["cumulative"]["current"] == "110"
    assert second["cumulative"]["ratio"] == _fraction(11, 5)
    assert result["query_id"] == selected["query_id"] and result["context_query_id"] == context["query_id"]
    assert context == before


def test_default_does_not_shrink_window_or_include_current_date():
    context = sample()
    result = volume_report(context, context)
    assert result["lookback"] == 20
    for entry in result["rows"]:
        for mode in ("regular", "cumulative"):
            assert entry[mode]["ratio"] is None
            assert entry[mode]["reason"] == "history_insufficient"
    assert result["rows"][-1]["history_dates"] == ["2026-09-28", "2026-09-29"]


@pytest.mark.parametrize("problem,reason", [("missing", "missing_slot"), ("duplicate", "duplicate_slot"),
                                           (None, "missing_quantity"), ("-1", "invalid_quantity"),
                                           ("1.5", "invalid_quantity"), (True, "invalid_quantity")])
def test_bad_historical_slot_is_not_filled_or_skipped(problem, reason):
    context = sample()
    context["rows"].insert(0, row(27, "09:31", "999", 7))
    if problem == "missing":
        context["rows"] = [r for r in context["rows"] if r["ordinal"] != 4]
    elif problem == "duplicate":
        context["rows"].append(row(29, "09:32", "7", 8))
    else:
        next(r for r in context["rows"] if r["ordinal"] == 4)["values"]["volume"] = problem
    report = volume_report(query([next(r for r in context["rows"] if r["ordinal"] == 6)]), context, 2)
    last = report["rows"][0]
    assert last["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert last["regular"]["ratio"] is None and last["regular"]["reason"] == reason
    assert last["cumulative"]["ratio"] is None and last["cumulative"]["reason"] == reason


def test_missing_earlier_slot_blocks_only_cumulative_later_slot():
    context = sample()
    context["rows"] = [r for r in context["rows"] if r["ordinal"] != 3]
    value = volume_report(query([context["rows"][-1]]), context, 2)["rows"][0]
    assert value["regular"]["ratio"] == _fraction(2, 1)
    assert value["cumulative"]["ratio"] is None
    assert value["cumulative"]["reason"] == "missing_slot"


def test_zero_is_data_and_zero_denominator_is_undefined():
    context = sample()
    for r in context["rows"]: r["values"]["volume"] = "0"
    value = volume_report(context, context, 2)["rows"][-1]
    assert value["regular"]["current"] == "0"
    assert value["regular"]["baseline_mean"] == _fraction(0, 1)
    assert value["regular"]["ratio"] is None and value["regular"]["reason"] == "zero_baseline"
    context["rows"][1]["values"]["volume"] = "1"
    assert volume_report(context, context, 2)["rows"][-1]["regular"]["ratio"] == _fraction(0, 1)


def test_future_append_and_bad_later_slot_do_not_change_earlier_values():
    context = sample()
    before = volume_report(context, context, 2)["rows"][-2]
    context["rows"][3]["values"]["volume"] = None
    context["rows"][5]["values"]["volume"] = "9223372036854775807"
    future = row(1, "09:31", "9999999", 8)
    future["label"] = "2026-10-01T09:31"
    context["rows"].extend([row(30, "15:00", None, 7), future])
    context["query_id"] = "d" * 64
    assert volume_report(context, context, 2)["rows"][4] == before


@pytest.mark.parametrize("source_date", ["20260929", "2026-09-29", "2026/09/29"])
def test_dated_unlocated_record_keeps_date_in_window(source_date):
    context = sample()
    context["rows"] = [r for r in context["rows"] if r["label"][:10] != "2026-09-29"]
    context["unlocated"] = [dict(label=None, ordinal=3, tokens=dict(source_date=source_date), values=dict(volume="100"))]
    report = volume_report(context, context, 2)
    assert report["excluded_unlocated_rows"] == 1
    assert report["rows"][-1]["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert report["rows"][-1]["regular"]["reason"] == "missing_slot"
    assert report["unlocated"][0]["reason"] == "unlocated_label"


def test_valid_slot_and_additional_unlocated_quantity_are_explicitly_separate():
    context = sample()
    context["unlocated"] = [dict(label=None, ordinal=7, tokens=dict(source_date="20260929"), values=dict(volume="1000000"))]
    report = volume_report(context, context, 2)
    assert report["excluded_unlocated_rows"] == 1
    assert report["qualification"] == "conditional_source_values"
    assert report["rows"][-2]["regular"]["ratio"] == _fraction(5, 2)
    assert report["rows"][-2]["cumulative"]["ratio"] == _fraction(5, 2)


def test_unreadable_date_cannot_establish_calendar_completeness():
    context = sample()
    context["rows"] = [r for r in context["rows"] if r["label"][:10] != "2026-09-29"]
    context["rows"].insert(0, row(27, "09:31", "10", 7))
    context["unlocated"] = [dict(label=None, ordinal=3, tokens=dict(source_date="unreadable"), values=dict(volume="30"))]
    report = volume_report(context, context, 2)
    assert report["rows"][-2]["history_dates"] == ["2026-09-27", "2026-09-28"]
    assert report["rows"][-2]["regular"]["ratio"] == _fraction(5, 1)
    assert report["excluded_unlocated_rows"] == 1 and "calendar" in report["unknowns"]


def test_wide_integer_sums_and_ratio_are_exact():
    context = sample()
    maximum = 9223372036854775807
    for r in context["rows"]: r["values"]["volume"] = str(maximum)
    context["rows"][-1]["values"]["volume"] = str(maximum - 1)
    value = volume_report(context, context, 2)["rows"][-1]
    assert value["cumulative"]["baseline_sum"] == str(maximum * 4)
    assert value["cumulative"]["current"] == str(maximum * 2 - 1)
    ratio = value["cumulative"]["ratio"]
    assert Fraction(int(ratio["numerator"]), int(ratio["denominator"])) == Fraction(maximum * 2 - 1, maximum * 2)


def test_common_scale_cancels_but_single_date_scale_changes_comparison():
    context = sample()
    before = volume_report(context, context, 2)["rows"][-1]
    for r in context["rows"]:
        r["values"]["volume"] = str(int(r["values"]["volume"]) * 100)
    scaled = volume_report(context, context, 2)["rows"][-1]
    for mode in ("regular", "cumulative"):
        assert scaled[mode]["ratio"] == before[mode]["ratio"]
    for r in context["rows"][-2:]:
        r["values"]["volume"] = str(int(r["values"]["volume"]) * 2)
    changed = volume_report(context, context, 2)["rows"][-1]
    for mode in ("regular", "cumulative"):
        original = before[mode]["ratio"]
        assert changed[mode]["ratio"] == _fraction(int(original["numerator"]) * 2, int(original["denominator"]))


@pytest.mark.parametrize("number,display", [(1, "0.0000"), (3, "0.0002"), (5, "0.0002"), (7, "0.0004")])
def test_display_rounding_half_even(number, display):
    assert _fraction(number, 20000)["display"] == display


@pytest.mark.parametrize("lookback", [True, 1, 253, 2.0, "2"])
def test_invalid_window(lookback):
    with pytest.raises(ValueError, match="invalid_lookback"):
        volume_report(sample(), sample(), lookback)


def test_other_period_and_outside_template_not_computed():
    context = query([row(30, "09:30", "100", 1)])
    assert volume_report(context, context, 2)["rows"][0]["reason"] == "outside_observed_template"
    context["metadata"]["period"] = "5m"
    assert volume_report(context, context, 2)["rows"][0]["reason"] == "unsupported_period"


def test_private_real_capture_against_independent_cache_integer_oracle(tmp_path):
    root = Path(__file__).resolve().parents[1]
    folder = root / "artifacts/qualification/minute-read/20261008T140439Z"
    cache = root / "artifacts/qualification/minute-cache/20261008-manual-real/d81bc1657ddc7ad43036a30fd294c778b7d9c2881039ea7f2151941102a5497d.lc1"
    if not folder.exists() or not cache.exists():
        pytest.skip("Private real samples unavailable; no network fallback")
    raw = (folder / "response.bin").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "826e7bcca37b7dde90a74f6348877044c77dbc1f678629b1a92c1793a6dba4a2"
    binary = cache.read_bytes()
    assert hashlib.sha256(binary).hexdigest() == "d81bc1657ddc7ad43036a30fd294c778b7d9c2881039ea7f2151941102a5497d"
    quantities = [struct.unpack_from("<I", binary, offset + 24)[0] for offset in range(0, len(binary), 32)]
    bundle = dict(request_utf8=(folder / "request.json").read_text(), response_utf8=raw.decode())
    with EvidenceStore(tmp_path / "store") as store:
        attempt = store.import_bytes(json.dumps(bundle).encode(), "tdx-http-market-v1")
        context = store.query(attempt["snapshot_id"])
    assert [int(r["values"]["volume"]) for r in context["rows"]] == quantities
    assert all(r["regular"]["reason"] == "history_insufficient" for r in volume_report(context, context)["rows"])
    last_day = volume_report(context, context, 2)["rows"][480:]
    assert sum(r["regular"]["ratio"] is not None for r in last_day) == 239
    assert sum(r["cumulative"]["ratio"] is not None for r in last_day) == 240
    for slot, r in enumerate(last_day):
        denominator = quantities[slot] + quantities[240 + slot]
        expected = Fraction(2 * quantities[480 + slot], denominator) if denominator else None
        ratio = r["regular"]["ratio"]
        assert (Fraction(int(ratio["numerator"]), int(ratio["denominator"])) if ratio else None) == expected
        expected_cumulative = Fraction(2 * sum(quantities[480:481 + slot]),
                                       sum(quantities[:slot + 1]) + sum(quantities[240:241 + slot]))
        ratio = r["cumulative"]["ratio"]
        assert Fraction(int(ratio["numerator"]), int(ratio["denominator"])) == expected_cumulative
    assert last_day[0]["regular"]["ratio"] == _fraction(10592, 8249)
    assert last_day[-1]["cumulative"]["ratio"] == _fraction(899711, 1179692)
    assert last_day[-2]["regular"]["reason"] == "zero_baseline"
    assert last_day[-3]["regular"]["ratio"] == _fraction(0, 1)
