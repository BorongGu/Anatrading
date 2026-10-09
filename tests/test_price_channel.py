"""Independent arithmetic and source-date causality for prior price ranges."""
from copy import deepcopy
from fractions import Fraction
import hashlib
from pathlib import Path
import struct

import pytest

from anatrading.price_channel import channel_report
from anatrading.store import EvidenceStore


def row(day, ordinal, prices=("10", "12", "8", "11")):
    return dict(ordinal=ordinal, label=f"2026-09-{day:02d}", tokens={},
                values=dict(zip(("open", "high", "low", "close"), prices)))


def query(rows, unlocated=()):
    return dict(snapshot_id="a" * 64, query_id="b" * 64, metadata=dict(period="1d"),
                rows=rows, unlocated=list(unlocated))


def sample():
    return query([row(28, 1), row(29, 2, ("11", "13", "9", "12")),
                  row(30, 3, ("12", "14", "7", "13"))])


def test_hand_window_excludes_current_date_and_display_filter_does_not_remove_history():
    context = sample()
    before = deepcopy(context)
    selected = query(context["rows"][-1:])
    selected["query_id"] = "c" * 64
    report = channel_report(selected, context, 2)
    value = report["rows"][0]
    assert value["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert (value["upper"], value["lower"], value["width"]) == ("13", "8", "5")
    assert value["range_relation"] == "both" and value["close_relation"] == "touch_upper"
    assert value["touch_upper"] is False and value["touch_lower"] is False
    assert [m["ordinals"] for m in value["members"]] == [[1], [2]]
    assert report["query_id"] != report["context_query_id"] and context == before


@pytest.mark.parametrize("prices,range_relation,close_relation", [
    (("12", "14", "9", "14"), "upper_only", "above"),
    (("9", "12", "7", "7"), "lower_only", "below"),
    (("10", "13", "8", "10"), "neither", "inside"),
    (("10", "13", "8", "8"), "neither", "touch_lower"),
])
def test_strict_exceedance_and_close_are_separate(prices, range_relation, close_relation):
    context = sample()
    context["rows"][-1]["values"].update(zip(("open", "high", "low", "close"), prices))
    value = channel_report(context, context, 2)["rows"][-1]
    assert (value["range_relation"], value["close_relation"]) == (range_relation, close_relation)
    assert value["touch_upper"] is (prices[1] == "13")
    assert value["touch_lower"] is (prices[2] == "8")


def test_flat_zero_range_has_defined_comparisons_and_touch_both():
    context = query([row(day, i, ("0",) * 4) for i, day in enumerate((28, 29, 30), 1)])
    value = channel_report(context, context, 2)["rows"][-1]
    assert (value["upper"], value["lower"], value["width"]) == ("0", "0", "0")
    assert value["close_relation"] == "touch_both" and value["range_relation"] == "neither"
    assert value["touch_upper"] and value["touch_lower"]


@pytest.mark.parametrize("field,bad,reason", [("high", None, "missing_ohlc"), ("high", "bad", "invalid_price"),
    ("low", "-1", "negative_price"), ("close", "99", "invalid_ohlc"), ("high", True, "invalid_price")])
def test_bad_date_occupies_window_without_replacement(field, bad, reason):
    context = sample()
    context["rows"].insert(0, row(27, 4, ("100", "999", "1", "100")))
    context["rows"][2]["values"][field] = bad
    value = channel_report(context, context, 2)["rows"][-1]
    assert value["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert value["reason"] == reason and value["upper"] is None and value["range_relation"] is None


def test_duplicate_dates_block_history_and_current_comparison_separately():
    context = sample()
    context["rows"].append(row(29, 4))
    value = channel_report(query([context["rows"][2]]), context, 2)["rows"][0]
    assert value["reason"] == "duplicate_date" and value["members"][-1]["ordinals"] == [2, 4]
    context = sample()
    context["rows"].append(row(30, 4))
    values = channel_report(query(context["rows"][-2:]), context, 2)["rows"]
    assert all(v["reason"] is None and v["upper"] == "13" and v["comparison_reason"] == "duplicate_date"
               and v["range_relation"] is None for v in values)


def test_dated_unlocated_occupies_window_unknown_date_is_counted():
    context = sample()
    dated = context["rows"].pop(1)
    dated.update(label=None, tokens=dict(source_date="20260929"))
    unknown = row(1, 4)
    unknown.update(label=None, tokens=dict(date="unreadable"))
    context["unlocated"] = [dated, unknown]
    value = channel_report(context, context, 2)
    assert value["rows"][-1]["reason"] == "unlocated_label"
    assert value["rows"][-1]["history_dates"] == ["2026-09-28", "2026-09-29"]
    assert value["context_unlocated_rows"] == 2 and value["unreadable_date_rows"] == 1
    assert all(r["reason"] == "unlocated_label" for r in value["unlocated"])


def test_current_bad_ohlc_preserves_channel_and_bad_quantity_is_irrelevant():
    context = sample()
    for r in context["rows"]: r["values"].update(volume=None, amount="bad")
    context["rows"][-1]["values"]["open"] = "999"
    value = channel_report(context, context, 2)["rows"][-1]
    assert value["upper"] == "13" and value["reason"] is None
    assert value["comparison_reason"] == "invalid_ohlc" and value["close_relation"] is None


def test_future_append_source_order_and_positive_scale_invariance():
    context = sample()
    original = channel_report(context, context, 2)["rows"]
    later = deepcopy(context)
    future = row(30, 4, ("999",) * 4)
    future["label"] = "2026-10-01"
    later["rows"] = [future, *reversed(later["rows"])]
    assert channel_report(context, later, 2)["rows"] == original
    scaled = deepcopy(context)
    for r in scaled["rows"]:
        r["values"] = {key: str(int(value) * 100) for key, value in r["values"].items()}
    value = channel_report(scaled, scaled, 2)["rows"][-1]
    assert (value["upper"], value["lower"], value["width"]) == ("1300", "800", "500")
    assert (value["range_relation"], value["close_relation"]) == (original[-1]["range_relation"], original[-1]["close_relation"])


def test_decimal_precision_is_independent_of_global_context():
    from decimal import localcontext
    high = "99999999999999999999.999999999999999999"
    context = query([row(day, i, (high, high, "0.000000000000000001", high))
                     for i, day in enumerate((28, 29, 30), 1)])
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        value = channel_report(context, context, 2)["rows"][-1]
    assert value["width"] == "99999999999999999999.999999999999999998"


def test_default_warmup_period_and_parameter_boundaries():
    context = sample()
    assert all(r["reason"] == "history_insufficient" for r in channel_report(context, context)["rows"])
    for n in (1, 253, True, "20"):
        with pytest.raises(ValueError, match="invalid_lookback"): channel_report(context, context, n)
    wrong = deepcopy(context)
    wrong["snapshot_id"] = "d" * 64
    with pytest.raises(ValueError, match="context_snapshot_mismatch"): channel_report(context, wrong)
    wrong = deepcopy(context)
    wrong["metadata"]["period"] = "1m"
    assert all(r["reason"] == "unsupported_period" for r in channel_report(wrong, wrong)["rows"])


def test_real_native_uint32_oracle_every_window(tmp_path):
    path = Path(__file__).resolve().parents[1] / "data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78/after.day"
    if not path.exists(): pytest.skip("Private real sample unavailable; no source compatibility claim")
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30"
    source = list(struct.iter_unpack("<IIIIIfII", data))
    assert len(source) == 7068 and all(a[0] < b[0] for a, b in zip(source, source[1:]))
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(data, "tdx-public-day-v1", interpretation=dict(instrument="600059.SH", venue="SH", asset_type="stock"))["snapshot_id"]
        context = store.query(sid)
        report = channel_report(context, context)
        for i, value in enumerate(report["rows"]):
            if i < 20:
                assert value["reason"] == "history_insufficient"
                continue
            window = source[i-20:i]
            upper, lower = max(x[2] for x in window), min(x[3] for x in window)
            assert Fraction(value["upper"]) == Fraction(upper, 100)
            assert Fraction(value["lower"]) == Fraction(lower, 100)
            assert Fraction(value["width"]) == Fraction(upper-lower, 100)
            assert [d.replace("-", "") for d in value["history_dates"]] == [str(x[0]) for x in window]
            for offset, (member, raw) in enumerate(zip(value["members"], window), i-19):
                assert member["ordinals"] == [offset] and member["reason"] is None
                assert Fraction(member["high"]) == Fraction(raw[2], 100)
                assert Fraction(member["low"]) == Fraction(raw[3], 100)
            h, l, c = source[i][2:5]
            expected_range = "both" if h > upper and l < lower else "upper_only" if h > upper else "lower_only" if l < lower else "neither"
            expected_close = "above" if c > upper else "below" if c < lower else "touch_both" if c == upper == lower else "touch_upper" if c == upper else "touch_lower" if c == lower else "inside"
            assert (value["range_relation"], value["close_relation"]) == (expected_range, expected_close)
        selected = store.query(sid, ordinal_start=7068, ordinal_end=7068)
        assert channel_report(selected, context)["rows"] == report["rows"][-1:]
