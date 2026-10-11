"""Independent arithmetic and causal boundaries for the source-template slice."""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from fractions import Fraction
import itertools
import json
import math

import pytest

import anatrading.intraday_sampling as module
from anatrading.intraday_sampling import intraday_sampling_report


DAY = "2026-10-08"
START = datetime(2026, 10, 8, 9, 31)


def label(i):
    return (START + timedelta(minutes=i)).isoformat(timespec="minutes")


def evidence(version="1"):
    return [dict(source_id="synthetic-source-template", version=version, declared_by="project_template")]


def sample(prices=(1, 2, 1, 2, 1, 1), last=10):
    rows = [dict(ordinal=i + 1, label=label(i), tokens={}, checks=[],
                 values=dict.fromkeys(("open", "high", "low", "close"), str(price)))
            for i, price in enumerate(prices)]
    query = dict(snapshot_id="a" * 64, query_id="b" * 64,
                 metadata=dict(period="1m", source_code="sh.600059"),
                 rows=rows, unlocated=[], selection={})
    descriptor = dict(schema_version=1, snapshot_id=query["snapshot_id"], symbol="600059.SH", market="CN_A",
        source_date=DAY, clock_basis="source_label", label_semantics="declared_end_label",
        timezone=dict(name=None, evidence_status="unknown", evidence_refs=[]), evidence_refs=evidence(),
        segments=[dict(segment_id="morning", first_label=label(0), last_label=label(last),
                       step_seconds=60, stage="unknown", stage_evidence_status="unknown", evidence_refs=[])])
    return query, descriptor


def run(query, descriptor, i=5, **kwargs):
    return intraday_sampling_report(query, descriptor, cutoff=label(i), **kwargs)


def first(query, descriptor, i=5, **kwargs):
    return run(query, descriptor, i, **kwargs)["segments"][0]


@pytest.mark.parametrize("powers, fine, coarse", [
    ([0, 1, 0, 1, 0, 0], 4, 0), ([0, 1, 2, 3, 4, 5], 5, 25),
    ([0, 0, 0, 1, 1, 1], 1, 1), ([0, 0, 0, 0, 0, 0], 0, 0),
])
def test_hand_computed_log_two_paths(powers, fine, coarse):
    query, desc = sample([2 ** power for power in powers])
    before = deepcopy((query, desc))
    result = run(query, desc)
    row = result["segments"][0]
    value = row["main_values"]
    assert value["rv_1_same"] == pytest.approx(fine * math.log(2) ** 2)
    assert value["rv_5"] == pytest.approx(coarse * math.log(2) ** 2)
    assert value["net_log_change"] == pytest.approx((powers[-1] - powers[0]) * math.log(2))
    assert value["n_returns_1"] == 5 and value["n_returns_5"] == 1
    if coarse:
        assert value["sensitivity_ratio"] == pytest.approx(Fraction(fine, coarse))
    else:
        assert value["sensitivity_ratio"] is None and value["ratio_reason"] == "zero_scale"
    assert row["coverage_status"] == "complete_declared_grid" and row["closure_status"] == "unknown"
    assert row["comparison_end_label"] == label(5)
    assert row["located_subset_values"] is None
    assert result["scope"] == "source_template_only" and result["mode"] == "retrospective"
    assert (query, desc) == before
    json.dumps(result, allow_nan=False)


def test_missing_expected_last_close_never_rolls_back():
    query, desc = sample([10] * 10)
    row = first(query, desc, 10)
    assert row["k"] == row["m"] == 10
    assert row["comparison_end_label"] == label(10)
    assert row["main_values"] is None and row["located_subset_values"] is None
    assert row["counts"]["expected_slots"] == 11 and row["counts"]["missing_slots"] == 1
    assert row["last_observed_label"] == label(9)


@pytest.mark.parametrize("missing", [0, 2, 5])
def test_missing_first_interior_or_coarse_endpoint_closes_both_outputs(missing):
    query, desc = sample()
    query["rows"].pop(missing)
    row = first(query, desc)
    assert row["main_values"] is row["located_subset_values"] is None
    assert row["counts"]["missing_slots"] == 1


def test_tail_bad_or_unclosed_is_visible_but_not_in_common_sum():
    query, desc = sample([1, 2, 1, 2, 1, 1, 10, 20, 30, 40])
    original = first(query, desc, 9)["main_values"]
    query["rows"][6]["values"]["close"] = "NaN"
    query["rows"].pop(8)
    closure = {"10": dict(status="unclosed", evidence_refs=evidence())}
    row = first(query, desc, 9, closure_by_ordinal=closure)
    assert row["m"] == 5 and row["k"] == 9 and row["main_values"] == original
    assert row["tail"]["counts"]["missing_slots"] == row["tail"]["counts"]["invalid_slots"] == 1
    assert row["tail"]["counts"]["unclosed_slots"] == 1 and row["closure_status"] == "unknown"
    assert row["cutoff_delay_nominal_minutes"] == 4


def test_empty_not_started_short_and_after_end_have_expected_grid():
    query, desc = sample([])
    before = first(query, desc, -1)
    assert before["k"] == -1 and before["m"] is None and before["reason"] == "not_started"
    assert before["main_values"] is None and before["comparison_end_label"] is None
    short = first(query, desc, 4)
    assert short["reason"] == "insufficient_common_span" and short["m"] == 0
    after = first(query, desc, 20)
    assert after["k"] == after["m"] == 10 and after["counts"]["missing_slots"] == 11


def test_full_120_close_template_has_115_fine_23_coarse_and_four_tail():
    query, desc = sample([10 + i for i in range(120)], last=119)
    row = first(query, desc, 119)
    assert row["main_values"]["n_returns_1"] == 115
    assert row["main_values"]["n_returns_5"] == 23
    assert row["tail"]["counts"]["expected_slots"] == 4


def test_all_prefixes_changed_future_prices_and_future_bad_rows():
    query, desc = sample([10 + i % 7 for i in range(31)], last=30)
    for end in range(31):
        whole = first(query, desc, end)
        prefix = deepcopy(query)
        prefix["rows"] = prefix["rows"][:end + 1]
        assert first(prefix, desc, end) == whole
        changed = deepcopy(query)
        for row in changed["rows"][end + 1:]:
            row["values"] = dict.fromkeys(("open", "high", "low", "close"), "NaN")
            row["checks"] = [dict(name="numeric.close", outcome="fail")]
        assert first(changed, desc, end) == whole


@pytest.mark.parametrize("location, affects", [(None, True), (DAY, True), ("2026-10-09", False), ("2026-10-07", False)])
def test_unlocated_date_scope_and_conditional_same_grid(location, affects):
    query, desc = sample()
    baseline = first(query, desc)["main_values"]
    query["unlocated"] = [dict(ordinal=30, label=None, tokens=dict(source_date=location) if location else {}, values={})]
    row = first(query, desc)
    if affects:
        assert row["main_values"] is None and row["coverage_status"] == "unknown"
        assert row["located_subset_values"] == {**baseline, "estimate_scope": "located_source_subset"}
    else:
        assert row["main_values"] == baseline and row["located_subset_values"] is None
    # Even with an unknown extra row, a known hole must not be compressed.
    query["rows"].pop(2)
    assert first(query, desc)["located_subset_values"] is None


def test_same_day_bad_clock_and_undetailed_batch_unknown_are_not_ignored():
    query, desc = sample()
    query["rows"].append(dict(ordinal=99, label=DAY + "Txx:00", values={}, tokens={}))
    result = run(query, desc)
    assert result["coverage"]["unlocated_ordinals"] == [99]
    assert result["segments"][0]["main_values"] is None
    query["rows"].pop()
    query["counts"] = dict(batch_unlocated_rows=2)
    result = run(query, desc)
    assert result["coverage"]["undetailed_unlocated_rows"] == 2
    assert result["segments"][0]["main_values"] is None


def test_duplicate_label_not_deduplicated_and_numeric_field_failures_are_local():
    query, desc = sample()
    duplicate = deepcopy(query["rows"][2]); duplicate["ordinal"] = 50
    query["rows"].append(duplicate)
    row = first(query, desc)
    assert row["counts"]["duplicate_slots"] == 1 and row["main_values"] is None
    query["rows"].pop()
    query["rows"][2]["values"].update(volume="NaN", amount="bad")
    query["rows"][2]["checks"] = [dict(name="numeric.volume", outcome="fail")]
    assert first(query, desc)["main_values"] is not None


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "-1", "0", "1e999", "1e-999", True, 1.0])
def test_invalid_source_price_never_emits_nan_or_mutates(value):
    query, desc = sample()
    query["rows"][2]["values"]["close"] = value
    before = deepcopy(query)
    result = run(query, desc)
    assert result["segments"][0]["main_values"] is None
    assert result["segments"][0]["counts"]["invalid_slots"] == 1
    assert query == before
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("change", ["code", "adjustflag", "source_adjustment", "numeric.close"])
def test_explicit_source_conflicts_and_price_parse_checks_are_not_washed(change):
    query, desc = sample()
    query["metadata"]["source_adjustflag"] = "3"
    if change in {"code", "adjustflag"}:
        query["rows"][2]["tokens"][change] = "sz.000001" if change == "code" else "2"
    else:
        query["rows"][2]["checks"] = [dict(name=change, outcome="fail")]
    assert first(query, desc)["main_values"] is None
    query["rows"][2]["label"] = None
    with pytest.raises(ValueError, match="source_"):
        run(query, desc)


@pytest.mark.parametrize("name", ["known_negative_sample", "declared_instrument", "declared_venue", "structure"])
def test_failed_batch_evidence_refuses_entire_source(name):
    query, desc = sample()
    query["batch_checks"] = [dict(name=name, outcome="fail")]
    with pytest.raises(ValueError):
        run(query, desc)


def test_quarantine_and_source_descriptor_binding():
    query, desc = sample()
    query["metadata"]["quarantined"] = True
    with pytest.raises(ValueError, match="known_negative_source"):
        run(query, desc)
    query["metadata"].pop("quarantined")
    for field, value in (("snapshot_id", "d" * 64), ("symbol", "000001.SZ"), ("market", "US")):
        altered = {**desc, field: value}
        with pytest.raises(ValueError, match="descriptor_source_mismatch"):
            run(query, altered)


def test_explicit_negative_closure_blocks_only_common_members():
    query, desc = sample()
    query["rows"][2]["closed"] = True
    assert first(query, desc)["closure_status"] == "unknown"
    mapping = {"3": dict(status="unclosed", evidence_refs=evidence())}
    row = first(query, desc, closure_by_ordinal=mapping)
    assert row["main_values"] is row["located_subset_values"] is None
    assert row["counts"]["unclosed_slots"] == 1 and row["closure_status"] == "unclosed"


@pytest.mark.parametrize("mapping", [
    {"03": dict(status="unclosed", evidence_refs=evidence())},
    {"0": dict(status="unclosed", evidence_refs=evidence())},
    {"999": dict(status="unclosed", evidence_refs=evidence())},
    {3: dict(status="unclosed", evidence_refs=evidence())},
    {"3": dict(status="closed", evidence_refs=evidence())},
    {"3": dict(status="verified", evidence_refs=evidence())},
    {"3": dict(status="unclosed", evidence_refs=[])},
])
def test_closure_input_cannot_certify_or_alias_ordinals(mapping):
    query, desc = sample()
    with pytest.raises(ValueError):
        run(query, desc, closure_by_ordinal=mapping)


@pytest.mark.parametrize("cutoff", [None, DAY, DAY + " 09:36", DAY + "T9:36", DAY + "T09:36:00",
                                    DAY + "T09:36+08:00", "2026-02-30T09:36", "2026-10-09T09:36"])
def test_strict_cutoff(cutoff):
    query, desc = sample()
    with pytest.raises(ValueError, match="invalid_cutoff"):
        intraday_sampling_report(query, desc, cutoff=cutoff)


def test_ordinal_crop_cutoff_conflict_and_unknown_clock_never_reinitialize():
    query, desc = sample()
    for selection, code in ((dict(ordinal_start=2), "ordinal_window_not_supported"),
                            (dict(ordinal_end=5), "ordinal_window_not_supported"),
                            (dict(cutoff=label(4)), "input_cutoff_mismatch")):
        query["selection"] = selection
        with pytest.raises(ValueError, match=code):
            run(query, desc)
    query["selection"] = {}
    assert run(query, desc)["descriptor"]["timezone"]["name"] is None


def test_budgets_preflight_before_row_parsing_or_grid_expansion(monkeypatch):
    query, desc = sample()
    query["rows"] = [None] * 20_001
    with pytest.raises(ValueError, match="research_row_limit"):
        run(query, desc)
    query, desc = sample()
    desc["evidence_refs"][0]["source_id"] = "x" * 16_384
    with pytest.raises(ValueError, match="auxiliary_input_limit"):
        run(query, desc)
    query, desc = sample()
    desc["segments"] *= 9
    with pytest.raises(ValueError, match="segment_limit"):
        run(query, desc)
    query, desc = sample()
    monkeypatch.setattr(module, "MAX_EXPECTED_SLOTS", 5)
    with pytest.raises(ValueError, match="expected_slot_limit"):
        run(query, desc)


def test_invalid_grids_evidence_timezone_and_extra_parameters():
    query, desc = sample()
    for mutate in (
        lambda d: d.update(extra=True),
        lambda d: d["segments"][0].update(step_seconds=30),
        lambda d: d["segments"][0].update(first_label=label(8), last_label=label(5)),
        lambda d: d["segments"].append(deepcopy(d["segments"][0])),
        lambda d: d["timezone"].update(name="../etc/passwd"),
        lambda d: d["timezone"].update(evidence_status="verified"),
        lambda d: d["segments"][0].update(stage="continuous", stage_evidence_status="verified"),
    ):
        invalid = deepcopy(desc); mutate(invalid)
        with pytest.raises(ValueError):
            run(query, invalid)


def test_independent_segment_does_not_bridge_lunch_or_prior_invalid_grid():
    query, desc = sample([10] * 6, last=5)
    query["rows"][2]["values"]["close"] = "0"
    afternoon = {**desc["segments"][0], "segment_id": "afternoon", "first_label": DAY + "T13:01",
                 "last_label": DAY + "T13:06", "stage": "mixed"}
    desc["segments"].append(afternoon)
    for i in range(6):
        query["rows"].append(dict(ordinal=i + 7, label=DAY + f"T13:0{i + 1}", tokens={},
                                  values=dict.fromkeys(("open", "high", "low", "close"), "100")))
    result = intraday_sampling_report(query, desc, cutoff=DAY + "T13:06")
    assert result["segments"][0]["main_values"] is None
    assert result["segments"][1]["main_values"]["rv_1_same"] == 0
    assert result["segments"][1]["stage"] == "mixed"
    assert all("12:" not in slot["label"] for slot in result["slot_trace"])
    assert not any(key in result for key in ("total", "aggregate", "cross_segment_return"))


def test_identity_binds_every_declared_interpretation_and_evidence_without_mutation():
    query, desc = sample()
    original = run(query, desc)
    for mutate in (lambda d: d["evidence_refs"][0].update(version="2"),
                   lambda d: d["segments"][0].update(stage="mixed"),
                   lambda d: d["timezone"].update(name="Asia/Shanghai")):
        changed = deepcopy(desc); mutate(changed)
        result = run(query, changed)
        assert result["descriptor_id"] != original["descriptor_id"]
        assert result["analysis_id"] != original["analysis_id"]
    altered_query = {**query, "query_id": "c" * 64}
    assert run(altered_query, desc)["analysis_id"] != original["analysis_id"]
    closure = {"1": dict(status="unclosed", evidence_refs=evidence())}
    assert run(query, desc, closure_by_ordinal=closure)["analysis_id"] != original["analysis_id"]
    original["descriptor"]["segments"].clear()
    assert desc["segments"]
    from anatrading.store import _identity
    assert run(query, desc)["descriptor_id"] == _identity(desc)


def test_numeric_precision_loss_low_decimal_context_and_price_scale():
    query, desc = sample(["10.000000000000000001", "10.000000000000000002"] * 3)
    row = first(query, desc)
    assert row["main_values"] is None and row["numerical_reason"] == "precision_loss"
    query, desc = sample([10, 11, 12, 13, 14, 15])
    baseline = first(query, desc)["main_values"]
    with localcontext() as context:
        context.prec = 3
        assert first(query, desc)["main_values"] == baseline
    scaled, _ = sample([1000, 1100, 1200, 1300, 1400, 1500])
    for key in ("rv_1_same", "rv_5", "net_log_change", "sensitivity_ratio"):
        assert first(scaled, desc)["main_values"][key] == pytest.approx(baseline[key], rel=1e-12)
    with pytest.raises(ArithmeticError, match="numerical_underflow"):
        module._square(1e-200)


def test_ratio_overflow_closes_only_ratio_with_finite_rv(monkeypatch):
    values = iter([0., 1., 0., 1., 0., 1e-155])
    monkeypatch.setattr(module.math, "log", lambda value: next(values))
    result = module._estimates([Decimal(i) for i in range(1, 7)])
    assert result["rv_1_same"] > 0 and result["rv_5"] > 0
    assert result["sensitivity_ratio"] is None and result["ratio_reason"] == "ratio_out_of_range"
    json.dumps(result, allow_nan=False)


def test_cauchy_bound_and_independent_five_return_reference():
    # A small exhaustive integer-log experiment. The reference does not call
    # product grid or return helpers; powers of two retain exact source prices.
    for increments in itertools.product((-1, 0, 1), repeat=5):
        powers = [5]
        for increment in increments:
            powers.append(powers[-1] + increment)
        query, desc = sample([2 ** exponent for exponent in powers])
        value = first(query, desc)["main_values"]
        exact_fine = sum(Fraction(increment) ** 2 for increment in increments)
        exact_coarse = sum(increments) ** 2
        assert exact_coarse <= 5 * exact_fine
        assert value["rv_1_same"] == pytest.approx(float(exact_fine) * math.log(2) ** 2, abs=1e-12)
        assert value["rv_5"] == pytest.approx(exact_coarse * math.log(2) ** 2, abs=1e-12)
        if exact_coarse:
            assert value["sensitivity_ratio"] >= .2 - 1e-14
