"""Frozen event rule, horizon slots and leakage-safe descriptive evaluation."""
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import json

import pytest

from anatrading.event_study import event_report
from anatrading.research_series import daily_bars
from anatrading.signal_research import signal_report
from test_research_series import source_query, source_row


def report(prices, **kwargs):
    return event_report(daily_bars(source_query(prices)), lookback=2, **kwargs)


def test_decimal_breakout_strict_equality_and_current_high_excluded():
    tiny = "10.000000000000000001"
    query = source_query([10, 10, tiny])
    query["rows"][-1]["values"]["high"] = "99999"
    with localcontext() as context:
        context.prec = 3
        result = event_report(daily_bars(query), lookback=2, horizon=1)
    assert result["signals"][-1]["prior_high"] == "10"
    assert result["signals"][-1]["breakout"] is True
    assert report([10, 10, 10], horizon=1)["signals"][-1]["breakout"] is False
    assert result["rows"][0]["evaluation_status"] == "immature"


def test_bad_window_and_duplicate_slots_never_replaced():
    query = source_query([100, 10, 0, 20, 30, 40])
    result = event_report(daily_bars(query), lookback=2)
    assert result["signals"][3]["reason"] == "invalid_history_window"
    assert result["signals"][4]["reason"] == "invalid_history_window"
    assert result["signals"][5]["breakout"] is True
    query["rows"].append(source_row(4, "30", ordinal=9))
    result = event_report(daily_bars(query), lookback=2)
    assert result["signals"][4]["reason"] == "duplicate_date"
    assert result["signals"][5]["reason"] == "invalid_history_window"


def test_greedy_overlap_is_strict_and_does_not_reset_at_test_split():
    result = report(range(10, 22), horizon=5, test_start="2026-01-07")
    events = result["rows"]
    assert [row["index"] for row in events if row["selected"]] == [2, 8]
    assert [row["evaluation_status"] for row in events if row["selected"]] == ["purged", "immature"]
    assert events[4]["partition"] == "test" and events[4]["evaluation_status"] == "overlap_excluded"
    assert result["counts"] == dict(candidate_dates=12, rule_computable=10, raw_events=10,
        overlap_excluded=8, selected_events=2, valid=0, immature=1, invalid=0, purged=1)
    for group in [result, *result["partitions"].values()]:
        c = group["counts"]
        assert c["raw_events"] == c["overlap_excluded"] + c["valid"] + c["immature"] + c["invalid"] + c["purged"]
        assert c["selected_events"] == c["valid"] + c["immature"] + c["invalid"] + c["purged"]


def test_horizon_matures_exactly_and_statistics_match_hand_fractions():
    result = report([10, 11, 12, 15, 13, 16, 12, 20], horizon=1)
    selected = [r for r in result["rows"] if r["evaluation_status"] == "valid"]
    expected = [Fraction(15, 12) - 1, Fraction(12, 16) - 1]
    assert [row["price_change"] for row in selected] == list(map(float, expected))
    assert result["statistics"]["mean"] == 0
    assert result["statistics"]["median"] == 0
    assert result["statistics"]["q25"] == pytest.approx(-.125)
    assert result["statistics"]["q75"] == pytest.approx(.125)
    assert result["statistics"]["positive_fraction"] == .5
    assert result["counts"]["immature"] == 1
    assert result["baseline"]["statistics"]["count"] == 5
    assert result["baseline"]["counts"]["candidate_dates"] == 6


def test_invalid_middle_path_and_zero_endpoint_are_not_skipped_or_minus_one():
    result = report([10, 11, 12, 13, 0, 15, 16, 17, 18], horizon=5)
    first = result["rows"][0]
    assert first["label_end"] == "2026-01-08"
    assert first["label_status"] == first["evaluation_status"] == "invalid"
    assert first["label_reason"] == "invalid_label_window" and first["price_change"] is None
    endpoint = report([10, 11, 12, 0], horizon=1)["rows"][0]
    assert endpoint["label_status"] == "invalid" and endpoint["price_change"] is None


def test_selection_independent_of_future_success_validity_or_maturity():
    prefix = report(range(10, 18), horizon=5)
    full = report(range(10, 24), horizon=5)
    assert [(e["date"], e["selected"]) for e in prefix["rows"]] == [(e["date"], e["selected"]) for e in full["rows"][:len(prefix["rows"])]]
    changed = report([10, 11, 12, 13, 14, 15, 16, 0, 18, 19, 20, 21], horizon=5)
    assert changed["rows"][0]["selected"] is True and changed["rows"][0]["evaluation_status"] == "invalid"
    assert changed["rows"][1]["selected"] is False


def test_cutoff_stability_and_purge_endpoint_equality():
    query = source_query(range(10, 20), selection=dict(cutoff="2026-01-07"))
    first = signal_report(query, lookback=2, horizon=1, test_start="2026-01-04")
    assert first["events"]["rows"][0]["evaluation_status"] == "purged"
    assert first["events"]["rows"][0]["label_end"] == "2026-01-04"
    later = deepcopy(query)
    later["rows"].extend(source_row(i, "999") for i in range(10, 20))
    assert signal_report(later, lookback=2, horizon=1, test_start="2026-01-04")["events"] == first["events"]
    assert first["events"]["evaluation_as_of"] == "2026-01-07"


def test_empty_no_events_and_single_value_quantiles():
    empty = report([], horizon=1)
    assert empty["statistics"]["count"] == 0 and empty["statistics"]["mean"] is None
    flat = report([10] * 10, horizon=1)
    assert flat["counts"]["raw_events"] == 0 and flat["baseline"]["statistics"]["mean"] == 0
    one = report([10, 11, 12, 15], horizon=1)["statistics"]
    assert all(one[k] == .25 for k in ("mean", "median", "q05", "q25", "q75", "q95"))
    json.dumps(empty, allow_nan=False)


def test_all_allowed_horizons_and_default_descriptive_mode():
    for horizon in (1, 5, 10, 20):
        result = report(range(1, 40), horizon=horizon)
        selected = [e["index"] for e in result["rows"] if e["selected"]]
        assert all(b > a + horizon for a, b in zip(selected, selected[1:]))
        assert result["mode"] == "descriptive" and set(result["partitions"]) == {"descriptive"}


def test_decimal_sub_float_ulp_change_still_has_correct_sign_and_ratio():
    prices = ["9", "9", "10", "10.000000000000000001"]
    result = report(prices, horizon=1)
    assert result["rows"][0]["price_change"] == pytest.approx(1e-19, rel=1e-12, abs=0)
    assert result["statistics"]["positive_count"] == 1
    assert result["statistics"]["positive_fraction"] == 1


def test_non_event_baseline_carries_same_partition_and_purge_rules():
    result = report([10, 11, 10, 11, 10, 11, 10], horizon=1, test_start="2026-01-05")
    assert result["counts"]["raw_events"] == 0
    assert result["partitions"]["train"]["baseline"]["counts"] == dict(candidate_dates=2, valid=1, immature=0, invalid=0, purged=1)
    assert result["partitions"]["test"]["baseline"]["counts"] == dict(candidate_dates=3, valid=2, immature=1, invalid=0, purged=0)


def test_independent_naive_breakout_and_counter_reference_with_bad_slots():
    import random
    randomizer = random.Random(26)
    query = source_query([randomizer.randint(8, 30) for _ in range(150)])
    for index in (5, 19, 20, 39, 100):
        query["rows"][index]["values"]["open"] = None
    query["rows"].append(source_row(63, "20", ordinal=199))
    bars = daily_bars(query)
    for window in (2, 5, 20):
        for horizon in (1, 5, 10, 20):
            result = event_report(bars, lookback=window, horizon=horizon, test_start="2026-03-20")
            selected, last = [], -1000
            for index, row in enumerate(bars):
                valid = (index >= window and all(b["reason"] is None for b in bars[index-window:index+1]))
                expected = row["close"] > max(b["high"] for b in bars[index-window:index]) if valid else None
                assert result["signals"][index]["breakout"] is expected
                if expected and index > last + horizon:
                    selected.append(index)
                    last = index
            assert [e["index"] for e in result["rows"] if e["selected"]] == selected
            for event in result["rows"]:
                start, end = event["index"], event["index"] + horizon
                expected_status = ("immature" if end >= len(bars) else "invalid"
                                   if any(b["reason"] for b in bars[start:end+1]) else "valid")
                assert event["label_status"] == expected_status
                if expected_status == "valid":
                    assert event["price_change"] == float(Fraction(bars[end]["close"]) / Fraction(bars[start]["close"]) - 1)
