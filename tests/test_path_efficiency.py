"""Exact close-path arithmetic, causality and native integer oracles."""
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import hashlib
from pathlib import Path
import struct

import pytest

from anatrading.path_efficiency import efficiency_report
from anatrading.store import EvidenceStore


def row(day, ordinal, close):
    return dict(ordinal=ordinal, label=f"2026-09-{day:02d}", tokens={},
                values=dict(close=close, high=None, low=None, open="bad", volume=None, amount=None))


def query(rows, unlocated=()):
    return dict(snapshot_id="a" * 64, query_id="b" * 64, metadata=dict(period="1d"),
                rows=rows, unlocated=list(unlocated))


def sample(prices=("1", "4", "2")):
    return query([row(i+1, i+1, p) for i, p in enumerate(prices)])


@pytest.mark.parametrize("prices,net,path,direction,ratio,reason", [
    (("1", "4", "2"), "1", "5", "up", ("1", "5", "0.2000"), None),
    (("4", "1", "3"), "-1", "5", "down", ("1", "5", "0.2000"), None),
    (("1", "2", "1"), "0", "2", "flat", ("0", "1", "0.0000"), None),
    (("1", "1", "1"), "0", "0", "flat", ("0", "1", "0.0000"), "zero_path_convention"),
    (("1", "2", "3"), "2", "2", "up", ("1", "1", "1.0000"), None),
    (("3", "2", "1"), "-2", "2", "down", ("1", "1", "1.0000"), None),
])
def test_hand_paths_and_explicit_flat_convention(prices, net, path, direction, ratio, reason):
    context = sample(prices)
    before = deepcopy(context)
    value = efficiency_report(context, context, 2)["rows"][-1]
    assert (value["net_change"], value["path_length"], value["direction"], value["reason"]) == (net, path, direction, reason)
    assert tuple(value["efficiency"][key] for key in ("numerator", "denominator", "display")) == ratio
    assert value["window_dates"] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert context == before


@pytest.mark.parametrize("bad,reason", [(None, "missing_close"), ("bad", "invalid_price"),
    ("-1", "negative_price"), (True, "invalid_price"), (1.0, "invalid_price")])
def test_invalid_close_is_not_skipped_to_complete_window(bad, reason):
    context = sample(("1", "2", "3", "4"))
    context["rows"][2]["values"]["close"] = bad
    value = efficiency_report(context, context, 2)["rows"][-1]
    assert value["window_dates"] == ["2026-09-02", "2026-09-03", "2026-09-04"]
    assert value["reason"] == reason and value["efficiency"] is None


def test_only_valid_available_high_low_interval_can_contradict_close():
    context = sample()
    context["rows"][1]["values"].update(high="3", low="1")
    assert efficiency_report(context, context, 2)["rows"][-1]["reason"] == "close_outside_range"
    for high, low in ((None, "1"), ("bad", "1"), ("1", "3"), ("-1", "1")):
        context["rows"][1]["values"].update(high=high, low=low, volume="bad", amount="bad")
        assert efficiency_report(context, context, 2)["rows"][-1]["efficiency"]["display"] == "0.2000"


@pytest.mark.parametrize("day", [2, 3])
def test_duplicate_history_and_current_dates_block(day):
    context = sample()
    context["rows"].append(row(day, 4, "999"))
    value = efficiency_report(query([context["rows"][2]]), context, 2)["rows"][0]
    assert value["reason"] == "duplicate_date" and value["efficiency"] is None


def test_dated_unlocated_occupies_window_and_unreadable_dates_are_counted():
    context = sample()
    dated = context["rows"].pop(1)
    dated.update(label=None, tokens=dict(source_date="20260902"))
    unknown = row(4, 4, "999")
    unknown.update(label=None, tokens=dict(date="bad"))
    context["unlocated"] = [dated, unknown]
    report = efficiency_report(context, context, 2)
    assert report["rows"][-1]["reason"] == "unlocated_label"
    assert report["rows"][-1]["window_dates"] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert report["unreadable_date_rows"] == 1 and report["context_unlocated_rows"] == 2
    assert all(r["reason"] == "unlocated_label" for r in report["unlocated"])


def test_future_append_display_window_positive_scale_and_translation_invariance():
    context = sample()
    original = efficiency_report(context, context, 2)["rows"]
    selected = query(context["rows"][-1:])
    assert efficiency_report(selected, context, 2)["rows"] == original[-1:]
    future = row(4, 4, "999")
    later = query([future, *reversed(deepcopy(context["rows"]))])
    assert efficiency_report(context, later, 2)["rows"] == original
    for scale, offset in ((100, 0), (1, 10), (10, 10)):
        transformed = deepcopy(context)
        for r in transformed["rows"]:
            r["values"]["close"] = str(int(r["values"]["close"]) * scale + offset)
        value = efficiency_report(transformed, transformed, 2)["rows"][-1]
        assert value["efficiency"] == original[-1]["efficiency"] and value["direction"] == "up"


def test_exact_derived_values_may_exceed_source_decimal_range():
    maximum = "99999999999999999999.999999999999999999"
    context = sample(("0", maximum, "0", maximum))
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        value = efficiency_report(context, context, 3)["rows"][-1]
    assert Fraction(value["path_length"]) == 3 * Fraction(maximum)
    assert value["net_change"] == maximum
    assert value["efficiency"] == dict(numerator="1", denominator="3", display="0.3333")


def test_parameter_context_and_n_plus_one_warmup_boundaries():
    context = sample()
    assert all(r["reason"] == "history_insufficient" for r in efficiency_report(context, context)["rows"])
    assert all(r["reason"] == "history_insufficient" for r in efficiency_report(context, context, 3)["rows"])
    for n in (1, 253, True, "10"):
        with pytest.raises(ValueError, match="invalid_lookback"): efficiency_report(context, context, n)
    wrong = deepcopy(context)
    wrong["snapshot_id"] = "d" * 64
    with pytest.raises(ValueError, match="context_snapshot_mismatch"): efficiency_report(context, wrong)
    wrong = deepcopy(context)
    wrong["metadata"]["period"] = "1m"
    assert all(r["reason"] == "unsupported_period" for r in efficiency_report(wrong, wrong)["rows"])


def test_real_native_integer_close_oracle_every_window(tmp_path):
    path = Path(__file__).resolve().parents[1] / "data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78/after.day"
    if not path.exists(): pytest.skip("Private real sample unavailable; no compatibility claim")
    data = path.read_bytes()
    assert hashlib.sha256(data).hexdigest() == "f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30"
    source = list(struct.iter_unpack("<IIIIIfII", data))
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(data, "tdx-public-day-v1", interpretation=dict(instrument="600059.SH", venue="SH"))["snapshot_id"]
        context = store.query(sid)
        report = efficiency_report(context, context)
        assert len(report["rows"]) == len(source) == 7068
        for i, value in enumerate(report["rows"]):
            if i < 10:
                assert value["reason"] == "history_insufficient"
                continue
            window = source[i-10:i+1]
            net = window[-1][4] - window[0][4]
            distance = sum(abs(b[4] - a[4]) for a, b in zip(window, window[1:]))
            assert Fraction(value["net_change"]) == Fraction(net, 100)
            assert Fraction(value["path_length"]) == Fraction(distance, 100)
            ratio = value["efficiency"]
            assert Fraction(int(ratio["numerator"]), int(ratio["denominator"])) == (Fraction(abs(net), distance) if distance else 0)
            assert 0 <= Fraction(int(ratio["numerator"]), int(ratio["denominator"])) <= 1
            assert [Fraction(m["close"]) for m in value["members"]] == [Fraction(x[4], 100) for x in window]
        assert [r["efficiency"]["display"] for r in report["rows"][-3:]] == ["0.5797", "0.4492", "0.5144"]
