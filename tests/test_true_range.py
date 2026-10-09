"""Exact rational oracles for source TR and bounded Wilder recursion."""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
from pathlib import Path
import struct

import pytest

from anatrading.true_range import range_report


def row(day, ordinal, high="12", low="8", close="10"):
    return dict(ordinal=ordinal, label=f"2026-09-{day:02d}", tokens={},
                values=dict(open=None, high=high, low=low, close=close, volume=None, amount=None))


def query(rows, unlocated=()):
    return dict(snapshot_id="a" * 64, query_id="b" * 64, metadata=dict(period="1d"),
                rows=rows, unlocated=list(unlocated))


def sample():
    return query([row(1, 1, "10", "8", "9"), row(2, 2, "13", "11", "12"),
                  row(3, 3, "12", "8", "9"), row(4, 4, "15", "14", "14")])


def enclosed(value, exact):
    assert Fraction(value["lower"]) <= exact <= Fraction(value["upper"])
    assert Fraction(value["lower"]) <= Fraction(value["value"]) <= Fraction(value["upper"])


def test_hand_gap_tr_seed_recursion_and_previous_atr_ratio():
    context = sample()
    before = deepcopy(context)
    values = range_report(context, context, 2)["rows"]
    assert values[0]["tr"] is None and values[0]["tr_reason"] == "no_previous_date"
    assert [v["tr"] for v in values[1:]] == ["4", "4", "6"]
    assert values[1]["components"] == dict(high_low="2", high_previous_close="4", low_previous_close="2")
    assert values[2]["atr"]["value"] == "4" and values[3]["atr"]["value"] == "5"
    assert values[3]["previous_date"] == "2026-09-03" and values[3]["previous_ordinals"] == [3]
    assert values[3]["prior_atr"]["value"] == "4"
    assert values[3]["tr_over_prior_atr"]["value"] == "1.5"
    assert context == before


def test_repeating_rationals_and_global_decimal_context_do_not_change_bounds():
    context = query([row(i+1, i+1, str(v), str(v), str(v)) for i, v in enumerate((0, 1, 3, 7, 8, 8))])
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        result = range_report(context, context, 3)
    assert result["seed_dates"] == ["2026-09-02", "2026-09-03", "2026-09-04"]
    for value, exact in zip(result["rows"][3:], (Fraction(7, 3), Fraction(17, 9), Fraction(34, 27))):
        enclosed(value["atr"], exact)
    assert result["rows"][3]["atr"]["display"] == "2.3333"


def test_full_context_display_subset_prefix_append_and_source_order():
    context = sample()
    selected = query(context["rows"][-1:])
    selected["query_id"] = "c" * 64
    expected = range_report(context, context, 2)["rows"]
    assert range_report(selected, context, 2)["rows"] == expected[-1:]
    later = deepcopy(context)
    later["rows"] = [row(5, 5, "999", "999", "999"), *reversed(later["rows"])]
    assert range_report(context, later, 2)["rows"] == expected
    assert range_report(query(context["rows"][:3]), query(context["rows"][:3]), 2)["rows"] == expected[:3]


@pytest.mark.parametrize("field,bad,reason", [("high", None, "missing_hl"), ("low", "bad", "invalid_price"),
    ("low", "-1", "negative_price"), ("low", "20", "invalid_hl"), ("high", True, "invalid_price")])
def test_bad_required_field_blocks_atr_without_skipping_or_reseeding(field, bad, reason):
    context = sample()
    context["rows"][1]["values"][field] = bad
    values = range_report(context, context, 2)["rows"]
    assert values[1]["tr_reason"] == reason and values[1]["tr"] is None
    assert all(v["atr"] is None and v["atr_reason"] == "invalid_history" for v in values[1:])
    assert values[-1]["tr"] == "6" and values[-1]["atr_blocked_date"] == "2026-09-02"


def test_current_close_problem_affects_next_tr_without_overblocking_current():
    for bad, reason in [(None, "missing_close"), ("bad", "invalid_price"), ("99", "close_outside_range")]:
        context = sample()
        context["rows"][2]["values"]["close"] = bad
        values = range_report(context, context, 2)["rows"]
        assert values[2]["tr"] == "4" and values[2]["atr"]["value"] == "4"
        assert values[3]["tr_reason"] == "previous_" + reason
        assert values[3]["prior_atr"]["value"] == "4" and values[3]["atr"] is None
    context = sample()
    context["rows"][1]["values"]["open"] = "bad"
    assert range_report(context, context, 2)["rows"][-1]["atr"]["value"] == "5"


def test_duplicate_and_dated_unlocated_dates_remain_dependencies():
    context = sample()
    context["rows"].append(row(2, 5))
    values = range_report(query(context["rows"][:4]), context, 2)["rows"]
    assert values[1]["tr_reason"] == "duplicate_date" and values[2]["tr_reason"] == "previous_duplicate_date"
    assert values[2]["previous_ordinals"] == [2, 5]
    context = sample()
    unlocated = context["rows"].pop(1)
    unlocated.update(label=None, tokens=dict(source_date="20260902"))
    context["unlocated"] = [unlocated]
    values = range_report(context, context, 2)
    assert values["rows"][1]["previous_date"] == "2026-09-02"
    assert values["rows"][1]["tr_reason"] == "previous_unlocated_label"
    assert values["unlocated"][0]["tr_reason"] == "unlocated_label"


def test_unknown_date_count_and_dated_unlocated_after_cutoff_do_not_enter_chain():
    context = sample()
    unknown, future = row(5, 5), row(6, 6)
    unknown.update(label=None, tokens=dict(date="unreadable"))
    future.update(label=None, tokens=dict(source_date="20260906"))
    context["unlocated"] = [unknown, future]
    context["selection"] = dict(cutoff="2026-09-04")
    result = range_report(context, context, 2)
    assert result["unreadable_date_rows"] == 1 and result["excluded_after_cutoff_unlocated"] == 1
    assert result["rows"][-1]["atr"]["value"] == "5"


def test_zero_range_ratio_and_period_one():
    context = query([row(i, i, "0", "0", "0") for i in range(1, 5)])
    value = range_report(context, context, 2)["rows"][-1]
    assert value["atr"]["value"] == "0" and value["tr_over_prior_atr"] is None
    assert value["ratio_reason"] == "zero_prior_atr"
    context = sample()
    values = range_report(context, context, 1)["rows"]
    assert [v["atr"]["value"] for v in values[1:]] == ["4", "4", "6"]


def test_parameters_period_and_snapshot_mismatch():
    context = sample()
    for period in (0, 253, True, "14"):
        with pytest.raises(ValueError, match="invalid_period"): range_report(context, context, period)
    wrong = deepcopy(context)
    wrong["snapshot_id"] = "d" * 64
    with pytest.raises(ValueError, match="context_snapshot_mismatch"): range_report(context, wrong)
    context["metadata"]["period"] = "1m"
    assert all(v["tr_reason"] == "unsupported_period" for v in range_report(context, context)["rows"])


def test_common_decimal_scale_and_price_offset_preserve_relative_range():
    context = sample()
    original = range_report(context, context, 2)["rows"][-1]
    scaled, shifted = deepcopy(context), deepcopy(context)
    for r in scaled["rows"]:
        for field in ("high", "low", "close"): r["values"][field] = str(int(r["values"][field]) * 100)
    for r in shifted["rows"]:
        for field in ("high", "low", "close"): r["values"][field] = str(int(r["values"][field]) + 100)
    scale_result = range_report(scaled, scaled, 2)["rows"][-1]
    assert scale_result["tr"] == "600" and scale_result["atr"]["value"] == "500"
    assert scale_result["tr_over_prior_atr"] == original["tr_over_prior_atr"]
    assert range_report(shifted, shifted, 2)["rows"][-1] == original


def test_display_is_undefined_if_numerical_endpoints_round_differently():
    from anatrading.true_range import _estimate
    result = _estimate((Decimal("1.00005"), Decimal("1.00004999"), Decimal("1.00005001")))
    assert result["display"] is None and result["display_reason"] == "ambiguous_display_rounding"


def test_real_native_uint32_tr_and_fraction_atr_bounds_every_row(tmp_path):
    from anatrading.store import EvidenceStore
    path = Path(__file__).resolve().parents[1] / "data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78/after.day"
    if not path.exists(): pytest.skip("Private real sample unavailable; no source compatibility claim")
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30"
    raw = list(struct.iter_unpack("<IIIIIfII", data))
    assert len(raw) == 7068
    source_tr = [Fraction(max(r[2]-r[3], abs(r[2]-p[4]), abs(r[3]-p[4])), 100) for p, r in zip(raw, raw[1:])]
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(data, "tdx-public-day-v1")["snapshot_id"]
        context = store.query(sid)
        result = range_report(context, context)
        exact = None
        for i, value in enumerate(result["rows"]):
            if i == 0:
                assert value["tr"] is None
                continue
            assert Fraction(value["tr"]) == source_tr[i-1]
            previous = exact
            if i == 14: exact = sum(source_tr[:14]) / 14
            elif i > 14: exact = (13*exact+source_tr[i-1])/14
            if exact is None: assert value["atr"] is None
            else: enclosed(value["atr"], exact)
            if previous is not None:
                enclosed(value["tr_over_prior_atr"], source_tr[i-1] / previous)
        assert result["rows"][-1]["tr"] == "1.12"
        assert result["rows"][-1]["atr"]["display"] == "0.7349"
        selected = store.query(sid, ordinal_start=7068, ordinal_end=7068)
        assert range_report(selected, context)["rows"] == result["rows"][-1:]
