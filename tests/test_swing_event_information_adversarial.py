"""Independent 035 synthetic review: no product helpers in the oracle.

Exact comparisons, raw-source date groups and direct slices are intentionally
separate from the production normalization, event selection and ER code.
These fixtures establish no real-data, predictive or trading qualification.
"""
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json

import pytest

import anatrading.swing_event_information as subject


def day(index):
    return (date(2025, 10, 1) + timedelta(days=index)).isoformat()


def query(prices, *, cutoff=None):
    end = cutoff or day(len(prices) - 1)
    versions = {"synthetic": "035-independent-v1"}
    selection = dict(snapshot_id="a" * 64, mode="retrospective", cutoff=end,
                     ordinal_start=None, ordinal_end=None,
                     fields=["open", "high", "low", "close", "volume", "amount"],
                     versions=versions)
    canonical = json.dumps(selection, sort_keys=True, separators=(",", ":"))
    return dict(snapshot_id="a" * 64, batch_id="b" * 64,
                query_id=hashlib.sha256(canonical.encode()).hexdigest(), selection=selection,
                manifest=dict(raw_sha256="c" * 64, source_contract_id="d" * 64,
                              versions=versions),
                metadata=dict(period="1d", source_code="600123.SH"),
                rows=[dict(ordinal=i + 1, label=day(i), tokens={}, checks=[],
                           values={key: str(price) for key in ("open", "high", "low", "close")})
                      for i, price in enumerate(prices)],
                unlocated=[], counts=dict(batch_unlocated_rows=0), batch_checks=[])


def run(source, *, cut=None, start=None):
    return subject.swing_event_report(source, report_start=start or day(0),
                                     test_start=cut or day(20), cutoff=source["selection"]["cutoff"])


def ratio(value):
    assert isinstance(value, dict), value
    return Fraction(int(value["numerator"]), int(value["denominator"]))


def oracle(source, cut):
    """Small direct reference for unique/duplicate, bad and unlocated fixtures.

    It implements only the fixture contract, using exact rational prices and a
    fresh 20-slot max for each date. No production helper is called here.
    """
    grouped = defaultdict(list)
    for row in source["rows"]:
        if row["label"] <= source["selection"]["cutoff"]:
            grouped[row["label"]].append(row)
    rejected = source["metadata"].get("quarantined") is True
    admitted = not rejected and not source["unlocated"] and not source["counts"]["batch_unlocated_rows"]
    slots = []
    for stamp, rows in sorted(grouped.items()):
        item = dict(date=stamp, ordinal=rows[0]["ordinal"] if len(rows) == 1 else None,
                    valid=False, close=None, high=None)
        if len(rows) == 1:
            row = rows[0]
            try:
                prices = {key: Fraction(row["values"][key]) for key in ("open", "high", "low", "close")}
                item.update(close=prices["close"], high=prices["high"])
                bounds = all(0 < value < 10 ** 20 and (value * 10 ** 18).denominator == 1
                             for value in prices.values())
                geometry = (prices["low"] <= prices["open"] <= prices["high"] and
                            prices["low"] <= prices["close"] <= prices["high"])
                conflict = row["tokens"].get("code", source["metadata"]["source_code"]) != source["metadata"]["source_code"]
                item["valid"] = bounds and geometry and not rejected and not conflict
            except (ValueError, TypeError, ZeroDivisionError):
                pass
        slots.append(item)
    expected, occupied_until = [], -1
    for i in range(20, len(slots)):
        if not all(slot["valid"] for slot in slots[i - 20:i + 1]):
            continue
        prior_high = max(slot["high"] for slot in slots[i - 20:i])
        if slots[i]["close"] <= prior_high:
            continue
        selected = i > occupied_until
        if selected:
            occupied_until = i + 5
        ending = slots[i + 5] if i + 5 < len(slots) else None
        label_status = ("immature" if ending is None else "invalid"
                        if not all(slot["valid"] for slot in slots[i:i + 6]) else "valid")
        end_date = ending["date"] if ending else None
        partition = "train" if slots[i]["date"] < cut else "test"
        evaluation = ("overlap_excluded" if not selected else "purged"
                      if partition == "train" and end_date is not None and end_date >= cut else label_status)
        change = ending["close"] / slots[i]["close"] - 1 if label_status == "valid" else None
        background = None
        if admitted:
            prices = [slot["close"] for slot in slots[i - 11:i]]
            net = prices[-1] - prices[0]
            path = sum(abs(prices[j] - prices[j - 1]) for j in range(1, 11))
            background = dict(net=net, path=path, er=abs(net) / path if path else Fraction(0),
                              direction_up=net > 0, efficient=bool(path and 2 * abs(net) >= path),
                              start_index=i - 11, end_index=i - 1,
                              start_date=slots[i - 11]["date"], end_date=slots[i - 1]["date"],
                              start_ordinal=slots[i - 11]["ordinal"], end_ordinal=slots[i - 1]["ordinal"],
                              reason=None if path else "zero_path_convention")
        expected.append(dict(index=i, date=slots[i]["date"], ordinal=slots[i]["ordinal"],
                             prior_high=prior_high, selected=selected, partition=partition,
                             label_status=label_status, evaluation_status=evaluation, label_end=end_date,
                             price_change=float(change) if change is not None else None,
                             label_sign=("positive" if change > 0 else "negative" if change < 0 else "zero")
                             if change is not None and admitted else None, background=background))
    return expected


def assert_events(actual, expected):
    assert len(actual["events"]) == len(expected)
    for row, ref in zip(actual["events"], expected):
        for key in ("index", "date", "ordinal", "selected", "partition", "label_status",
                    "evaluation_status", "label_end", "price_change", "label_sign"):
            assert row[key] == ref[key], (key, row, ref)
        assert Fraction(row["prior_high"]) == ref["prior_high"]
        if ref["background"] is None:
            assert row["background"] is None
        else:
            for key in ("net", "path", "er"):
                assert ratio(row["background"][key]) == ref["background"][key]
            for key in ("direction_up", "efficient"):
                assert row["background"][key] is ref["background"][key]
            for key in ("start_index", "end_index", "start_date", "end_date", "start_ordinal", "end_ordinal", "reason"):
                assert row["background"][key] == ref["background"][key]


def assert_period(period, expected, *, closed=False):
    events = [row for row in expected if period["start"] <= row["date"] <= period["end"]]
    selected = [row for row in events if row["selected"]]
    valid = [row for row in selected if row["evaluation_status"] == "valid"]
    counts = dict(raw_events=len(events), overlap_excluded=len(events) - len(selected),
                  selected_events=len(selected))
    for status in ("valid", "immature", "invalid", "purged"):
        counts[status] = sum(row["evaluation_status"] == status for row in selected)
    assert period["old_counts"] == counts
    statuses = ("valid", "immature", "invalid", "purged", "overlap_excluded")
    assert period["label_evaluation_counts"] == {
        label: {status: sum(row["label_status"] == label and row["evaluation_status"] == status
                            for row in events) for status in statuses}
        for label in ("valid", "immature", "invalid")}
    assert period["qualification_counts"] == {
        status: {qualification: sum(row["evaluation_status"] == status for row in events)
                 if qualification == ("source_unavailable" if closed else "admitted") else 0
                 for qualification in ("admitted", "source_unavailable", "internal_failure")}
        for status in statuses}
    assert period["selection_qualification"] == dict(
        comparable=0 if closed else len(valid), source_unavailable_valid=len(valid) if closed else 0,
        internal_failure_valid=0, condition_computed=0 if closed else len(selected),
        condition_source_unavailable=len(selected) if closed else 0, condition_internal_failure=0)
    if closed:
        for key in ("condition_counts", "groups", "costs", "delta", "distinct_signal_dates"):
            assert period[key] is None
        return
    direction = [row for row in selected if row["background"]["direction_up"]]
    assert period["condition_counts"] == dict(D_true=len(direction), D_false=len(selected) - len(direction),
        E_true=sum(row["background"]["efficient"] for row in direction),
        E_false=sum(not row["background"]["efficient"] for row in direction))
    groups = dict(a0=valid, a1=[row for row in valid if row["background"]["direction_up"]])
    groups["e_true"] = [row for row in groups["a1"] if row["background"]["efficient"]]
    groups["e_false"] = [row for row in groups["a1"] if not row["background"]["efficient"]]
    for name, rows in groups.items():
        stats = period["groups"][name]
        assert stats["count"] == len(rows)
        for sign in ("positive", "zero", "negative"):
            assert stats[sign + "_count"] == sum(row["label_sign"] == sign for row in rows)
        assert period["distinct_signal_dates"][name] == len({row["date"] for row in rows})
    if all(groups[name] for name in ("e_true", "e_false")):
        proportions = [Fraction(sum(row["label_sign"] != "positive" for row in groups[name]), len(groups[name]))
                       for name in ("e_true", "e_false")]
        assert ratio(period["delta"]) == proportions[0] - proportions[1]
    else:
        assert period["delta"] is None
    missed = sum(row["label_sign"] == "positive" for row in groups["e_false"])
    positives = sum(row["label_sign"] == "positive" for row in groups["a1"])
    assert period["costs"]["missed_positive_count"] == missed
    if positives:
        assert ratio(period["costs"]["missed_positive_fraction"]) == Fraction(missed, positives)
    else:
        assert period["costs"]["missed_positive_fraction"] is None
    if groups["a1"]:
        assert ratio(period["costs"]["retention"]) == Fraction(len(groups["e_true"]), len(groups["a1"]))
    else:
        assert period["costs"]["retention"] is None


@pytest.mark.parametrize("last,efficient", [
    ("101.999999999999999999", False), ("102", True), ("102.000000000000000001", True),
])
def test_exact_half_boundary_under_low_decimal_context(last, efficient):
    path = ["100", "103"] + ["102"] * 8 + [last]
    source = query(["90"] * 9 + path + ["111"] + ["110"] * 5)
    frozen = deepcopy(source)
    with localcontext() as context:
        context.prec = 3
        result = run(source)
    assert_events(result, oracle(source, day(20)))
    event = next(row for row in result["events"] if row["index"] == 20)
    assert event["background"]["direction_up"] is True
    assert event["background"]["efficient"] is efficient
    assert source == frozen


def test_downward_high_efficiency_does_not_gain_direction():
    source = query(["100"] * 9 + list(range(110, 99, -1)) + ["111"] + ["112"] * 5)
    result = run(source)
    assert_events(result, oracle(source, day(20)))
    event = next(row for row in result["events"] if row["index"] == 20)
    assert ratio(event["background"]["er"]) == 1
    assert event["background"]["efficient"] is True
    assert event["background"]["direction_up"] is False


def test_b_only_selection_precedes_direction_and_later_label_failure():
    source = query([90] * 20 + [100, 99, 99, 101, 99, 99, 102] + [99] * 5)
    result = run(source)
    assert_events(result, oracle(source, day(20)))
    assert [row["index"] for row in result["events"] if row["selected"]] == [20, 26]
    first, second = result["events"][:2]
    assert first["background"]["direction_up"] is False
    assert second["background"]["direction_up"] is True
    assert second["selected"] is False
    broken = deepcopy(source)
    broken["rows"][24]["values"]["open"] = None
    failed = run(broken)
    assert_events(failed, oracle(broken, day(20)))
    assert failed["events"][0]["evaluation_status"] == "invalid"
    assert next(row for row in failed["events"] if row["index"] == 23)["selected"] is False


def test_report_start_does_not_restart_b_only_selection():
    source = query([90] * 20 + [100, 99, 99, 101, 99, 99, 102] + [99] * 5)
    result = run(source, start=day(21), cut=day(25))
    assert_events(result, oracle(source, day(25)))
    full = result["periods"]["full"]
    assert full["old_counts"]["raw_events"] == 2
    assert full["old_counts"]["overlap_excluded"] == 1
    assert full["old_counts"]["selected_events"] == 1
    assert next(row for row in result["events"] if row["index"] == 23)["selected"] is False


def test_absent_calendar_dates_do_not_change_five_source_slot_label():
    source = query(list(range(100, 133)))
    for index, row in enumerate(source["rows"]):
        if index >= 22:
            row["label"] = day(index + 50)
    source["selection"]["cutoff"] = day(82)
    result = run(source)
    assert_events(result, oracle(source, day(20)))
    assert result["events"][0]["index"] == 20
    assert result["events"][0]["label_end"] == day(75)
    assert result["events"][0]["price_change"] == float(Fraction(125, 120) - 1)


def test_invalid_label_crossing_cut_is_purged_but_incomplete_bad_path_immature():
    source = query(list(range(100, 127)))
    source["rows"][24]["values"]["low"] = "10000"
    result = run(source, cut=day(23))
    assert_events(result, oracle(source, day(23)))
    assert result["events"][0]["label_status"] == "invalid"
    assert result["events"][0]["evaluation_status"] == "purged"
    shorter = deepcopy(source)
    shorter["selection"]["cutoff"] = day(24)
    incomplete = run(shorter, cut=day(23))
    assert_events(incomplete, oracle(shorter, day(23)))
    assert incomplete["events"][0]["label_status"] == "immature"
    assert incomplete["events"][0]["evaluation_status"] == "immature"


@pytest.mark.parametrize("end,sign,rounded", [
    ("99999999999999999999.999999999999999999", "positive", False),
    ("0.000000000000000001", "negative", True),
])
def test_supported_domain_extremes_keep_exact_sign(end, sign, rounded):
    previous = "99999999999999999999.999999999999999997"
    current = "99999999999999999999.999999999999999998"
    source = query([previous] * 20 + [current] * 5 + [end])
    result = run(source)
    assert_events(result, oracle(source, day(20)))
    row = result["events"][0]
    assert row["label_sign"] == sign
    assert row["price_change"] == -1.0 if rounded else row["price_change"] > 0
    assert Decimal(row["end_close"]) > 0


def test_future_append_and_event_close_changes_leave_background_frozen():
    source = query(list(range(100, 149)))
    before = run(source)
    changed = deepcopy(source)
    for row in changed["rows"][27:]:
        row["values"] = dict.fromkeys(("open", "high", "low", "close"), "700")
    after = run(changed)
    left = [row for row in before["events"] if row["index"] <= 26]
    right = [row for row in after["events"] if row["index"] <= 26]
    for a, b in zip(left, right, strict=True):
        for key in ("date", "ordinal", "index", "selected", "partition", "background"):
            assert a[key] == b[key]
    changed = deepcopy(source)
    changed["rows"][26]["values"] = dict.fromkeys(("open", "high", "low", "close"), "150")
    current = run(changed)
    a = next(row for row in before["events"] if row["index"] == 26)
    b = next(row for row in current["events"] if row["index"] == 26)
    assert a["background"] == b["background"]


def test_every_small_prefix_matches_direct_independent_reference():
    # Deliberate irregular waves give both ER groups without picking outcomes.
    prices = [100 + i // 3 + ((i * 17) % 11) for i in range(72)]
    for length in range(23, 73):
        source = query(prices[:length])
        result = run(source, cut=day(22))
        assert_events(result, oracle(source, day(22)))


def test_duplicate_and_invalid_ohlc_preserve_slots_and_endpoint():
    source = query(list(range(100, 172)))
    source["rows"].append(dict(deepcopy(source["rows"][29]), ordinal=1001))
    source["rows"][59]["values"]["close"] = "0"
    source["rows"].reverse()
    result = run(source)
    assert_events(result, oracle(source, day(20)))


def test_unlocated_coverage_closes_new_conditions_without_erasing_old_events():
    source = query(list(range(100, 145)))
    source["unlocated"] = [dict(ordinal=1000, label=None, tokens={}, checks=[], values={})]
    result = run(source)
    assert_events(result, oracle(source, day(20)))
    assert result["calculation_status"] == "source_unavailable"
    assert any(row["evaluation_status"] == "valid" for row in result["events"])
    assert all(row["background"] is None for row in result["events"])
    for period in result["periods"].values():
        assert_period(period, oracle(source, day(20)), closed=True)


def test_each_fixed_period_uses_one_ledger_and_exact_denominators():
    prices = list(range(100, 140)) + [140 + i // 4 + (i * 13) % 17 for i in range(40)] + list(range(200, 240))
    source = query(prices)
    result = run(source, cut=day(41), start=day(10))
    expected = oracle(source, day(41))
    assert_events(result, expected)
    assert result["periods"]["primary"]["start"] == day(41)
    assert result["periods"]["primary"]["end"] == day(119)
    assert result["periods"]["development"]["start"] == day(10)
    assert result["periods"]["development"]["end"] == day(40)
    assert result["periods"]["full"]["start"] == day(10)
    assert set(result["periods"]) == {"primary", "development", "full", "2025-Q4", "2026-Q1"}
    for period in result["periods"].values():
        assert_period(period, expected)


@pytest.mark.parametrize("corruption", ["sign", "index"])
def test_new_invariant_failure_closes_every_new_event_without_partial_rescue(monkeypatch, corruption):
    source = query(list(range(100, 150)))
    original = subject.event_report
    def corrupt(*args, **kwargs):
        report = original(*args, **kwargs)
        if corruption == "sign":
            report["rows"][0]["price_change"] = 0.0
        else:
            report["rows"][0]["index"] += 1
        return report
    monkeypatch.setattr(subject, "event_report", corrupt)
    result = run(source)
    assert result["calculation_status"] == "connection_invariant_failure"
    assert result["legacy"] is not None
    assert result["events"]
    if corruption == "index":
        # An in-bounds index referring to another date cannot supply trustworthy
        # derived provenance for the original, retained legacy event.
        assert result["events"][0]["prior_high"] is None
    assert all(row["background"] is None and row["label_sign"] is None
               and row["comparison_status"] == "internal_failure" for row in result["events"])
    for period in result["periods"].values():
        assert period["selection_qualification"]["internal_failure_valid"] == period["old_counts"]["valid"]
        for key in ("condition_counts", "groups", "costs", "delta", "distinct_signal_dates"):
            assert period[key] is None


def test_legacy_exception_has_no_partial_old_or_new_result(monkeypatch):
    def failing(*args, **kwargs):
        raise OverflowError("synthetic_legacy_failure")
    monkeypatch.setattr(subject, "event_report", failing)
    result = run(query(list(range(100, 130))))
    assert result["calculation_status"] == "legacy_event_failure"
    assert result["coverage"] is not None
    assert result["legacy"] is result["events"] is result["periods"] is None


def test_normalization_and_legacy_event_each_execute_once(monkeypatch):
    calls = dict(daily_bars=0, daily_coverage=0, event_report=0)
    for name in calls:
        original = getattr(subject, name)
        def counting(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(subject, name, counting)
    result = run(query(list(range(100, 140))))
    assert result["calculation_status"] == "computed"
    assert calls == dict(daily_bars=1, daily_coverage=1, event_report=1)


def test_empty_quarters_are_retained_and_tenth_quarter_is_rejected():
    source = query([100] * 22, cutoff="2026-04-02")
    result = run(source)
    assert set(result["periods"]) == {"primary", "development", "full", "2025-Q4", "2026-Q1", "2026-Q2"}
    assert result["periods"]["2026-Q1"]["old_counts"]["raw_events"] == 0
    assert result["periods"]["2026-Q2"]["groups"]["a1"]["count"] == 0
    with pytest.raises(ValueError, match="^invalid_swing_dates$"):
        run(source, start="2023-12-31")


def test_limit_rejection_precedes_normalization_and_event_work(monkeypatch):
    source = query([100] * 20001)
    # Explicit date span stays small: the row budget must reject before the
    # duplicate or date normalization could be used to shrink this input.
    for row in source["rows"]:
        row["label"] = day(21)
    source["selection"]["cutoff"] = day(22)
    def forbidden(*args, **kwargs):
        pytest.fail("Oversized source reached calculation")
    monkeypatch.setattr(subject, "daily_bars", forbidden)
    monkeypatch.setattr(subject, "event_report", forbidden)
    with pytest.raises(ValueError, match="^research_row_limit$"):
        run(source)
