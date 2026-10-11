"""Fixed-source-change contracts; synthetic data only, no model selection."""
from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal, Inexact, ROUND_DOWN, localcontext
from fractions import Fraction
import hashlib
import json
import sys
import base64

import pytest

from anatrading.formats import decode
from anatrading.models import VALUE_FIELDS, VERSIONS
from anatrading.public_market import build_capture, build_legacy_capture, build_request, canonical_json
from anatrading.store import EvidenceStore
from anatrading.pair_stability_research import (
    _exact_evaluate, _exact_fit, _scalar, pair_fixed_change_report,
)


DAYS = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(85)]


def capture(symbol, closes, dates):
    request = build_request("tencent", symbol, "1d", start=min(dates), end=max(dates), count=640)
    rows = [[day, str(v), str(v), str(v), str(v), "123.45", {}, "0", "10", "0", "0"]
            for day, v in zip(dates, closes)]
    body = request["parameters"]["_var"].encode() + b"=" + canonical_json(
        dict(code=0, msg="", data={symbol[-2:].lower() + symbol[:6]: {"day": rows}}))
    return build_capture("tencent", request, status=200, response_url=request["url"],
                         response_headers=[("Content-Type", "text/html; charset=UTF-8")], body=body)


def source(symbol, closes, dates=None):
    raw = capture(symbol, closes, dates or DAYS[:len(closes)])
    decoded = decode(raw, "tencent-daily-capture-v1")
    digest = hashlib.sha256(raw).hexdigest()
    snapshot = hashlib.sha256(raw + b"synthetic snapshot").hexdigest()
    rows = [asdict(row) for row in decoded.rows]
    selection = dict(snapshot_id=snapshot, mode="retrospective", cutoff=None, ordinal_start=None,
                     ordinal_end=None, fields=list(VALUE_FIELDS), versions=dict(VERSIONS))
    result = dict(snapshot_id=snapshot, batch_id=hashlib.sha256(raw + b"synthetic batch").hexdigest(),
                  query_id=hashlib.sha256(canonical_json(selection)).hexdigest(), selection=selection,
                  metadata=decoded.metadata, manifest=dict(raw_sha256=digest,
                      source_contract_id=hashlib.sha256(canonical_json(decoded.contract)).hexdigest(),
                      contract=decoded.contract, versions=dict(VERSIONS),
                      qualification="source_evidence_retrospective_only"), rows=rows, unlocated=[],
                  batch_checks=[asdict(c) for c in decoded.checks], quality={}, unlocated_quality={}, totals={})
    recount(result)
    return result


def recount(q):
    q["counts"] = dict(selected_rows=len(q["rows"]), unlocated_rows=len(q["unlocated"]),
                       batch_rows=len(q["rows"]) + len(q["unlocated"]),
                       batch_unlocated_rows=len(q["unlocated"]))


def setup(n=81, continued=False):
    left = ["100" if i % 2 == 0 else "102" if i <= 60 or continued else "100.5" for i in range(n)]
    right = ["100" if i % 2 == 0 else "101" for i in range(n)]
    return source("600001.SH", left), source("000001.SZ", right)


def report(left, right, cutoff=DAYS[80], anchor=DAYS[60]):
    return pair_fixed_change_report(left, right, fit_end=anchor, evaluation_cutoff=cutoff)


def fail(row, name):
    row["checks"] = [c for c in row["checks"] if c["name"] != name] + [dict(name=name, outcome="fail")]


def set_price(row, value):
    for key in ("open", "high", "low", "close"):
        row["values"][key] = row["tokens"][key] = str(value)


def test_finite_source_example_frozen_baselines_and_output():
    left, right = setup()
    before = deepcopy((left, right))
    result = report(left, right)
    assert result["status"] == "source_description_complete"
    assert result["fit"]["status"] == "ready"
    assert result["fit"]["observed_intervals"] == 60
    assert result["evaluation"]["observed"] == result["evaluation"]["eligible"] == 20
    assert len(result["trace"]) == 81 and len(result["evaluation"]["rows"]) == 20
    assert result["evaluation"]["mse"]["delta_PM"]["sign"] == 1
    assert result["evaluation"]["mse"]["delta_PU"]["sign"] == 1
    assert result["fit"]["beta"] == _scalar(Fraction(20402, 10251))
    assert (left, right) == before
    assert len(canonical_json(result)) <= 262144
    assert result["limitations"]["stability_certified"] is False
    assert result["limitations"]["corporate_action_coverage"] == "unknown"


def test_exact_fit_loss_and_perfect_continuation():
    x = [Fraction(1, 100), Fraction(-1, 101)] * 30
    y = [Fraction(1, 50), Fraction(-1, 51)] * 30
    fit = _exact_fit(x, y)
    assert fit["alpha"] == Fraction(1, 10251)
    assert fit["beta"] == Fraction(20402, 10251)
    exact = _exact_evaluate(fit, x[:20], [Fraction(1, 200), Fraction(-1, 201)] * 10)
    assert exact["mse"]["P"] == Fraction(205083001, 934071120000)
    assert exact["mse"]["delta_PM"] == Fraction(226139, 1161780000)
    assert exact["mse"]["delta_PU"] == Fraction(385021963, 1975219630000)
    result = report(*setup(continued=True))
    assert result["evaluation"]["mse"]["P"] == {"display": "0", "sign": 0}


@pytest.mark.parametrize("index", [0, 1])
def test_single_missing_day_disables_adjacent_intervals_without_shrinking(index):
    pair = list(setup())
    pair[index]["rows"].pop(65)
    recount(pair[index])
    result = report(*pair)
    assert result["fit"]["status"] == "ready"
    assert result["evaluation"]["status"] == "invalid"
    assert result["evaluation"]["eligible"] == 18
    assert all(v is None for v in result["evaluation"]["mse"].values())
    rows = result["evaluation"]["rows"]
    assert rows[4]["x"] is None and rows[5]["y"] is None
    assert "missing_endpoint" in rows[4]["reasons"]


@pytest.mark.parametrize("which,reason", [("duplicate", "duplicate_endpoint"),
                                          ("fail", "unclassified_source_failure"),
                                          ("identity", "local_source_conflict")])
def test_selected_local_failure_keeps_fit(which, reason):
    left, right = setup()
    if which == "duplicate":
        duplicate = deepcopy(left["rows"][65]); duplicate["ordinal"] = 999
        left["rows"].append(duplicate); recount(left)
    elif which == "fail":
        fail(left["rows"][65], "unknown.future_check")
    else:
        left["rows"][65]["tokens"]["code"] = "600999.SH"
    result = report(left, right)
    assert result["fit"]["status"] == "ready"
    assert result["evaluation"]["eligible"] == 18
    assert reason in result["reasons"]


def test_shared_boundary_failure_invalidates_fit_and_first_evaluation():
    left, right = setup()
    left["rows"].pop(60); recount(left)
    result = report(left, right)
    assert result["fit"]["status"] == "unavailable"
    assert result["evaluation"]["eligible"] == 19
    assert all(row["M"] is None for row in result["evaluation"]["rows"])
    assert "anchor_invalid" in result["reasons"]


@pytest.mark.parametrize("n,observed,status", [(61, 0, "pending"), (62, 1, "pending"),
                                               (80, 19, "pending"), (81, 20, "complete"),
                                               (82, 20, "complete")])
def test_evaluation_maturity_never_uses_partial_denominator(n, observed, status):
    result = report(*setup(n), cutoff=DAYS[84])
    assert result["evaluation"]["status"] == status
    assert result["evaluation"]["observed"] == observed
    if status == "pending":
        assert all(value is None for value in result["evaluation"]["mse"].values())


def test_constant_training_x_preserves_only_fixed_baselines():
    left, _ = setup()
    right = source("000001.SZ", [100] * 81)
    result = report(left, right)
    assert result["status"] == "baseline_only"
    assert result["fit"]["beta"] is None
    assert result["evaluation"]["mse"]["P"] is None
    assert result["evaluation"]["mse"]["M"] is not None
    assert result["evaluation"]["x_range"]["constant"] is True


def test_local_future_price_does_not_change_fit_or_past_and_boundary_dependency():
    left, right = setup(83)
    result = report(left, right)
    set_price(left["rows"][82], "9000")
    assert report(left, right) == result
    set_price(left["rows"][61], "99")
    changed = report(left, right)
    assert changed["fit"] == result["fit"]
    assert changed["evaluation"]["rows"][2:] == result["evaluation"]["rows"][2:]
    set_price(left["rows"][60], "99")
    assert report(left, right)["fit"] != result["fit"]


def test_unknown_position_conservatively_closes_comparison_even_outside_window():
    left, right = setup(83)
    left["rows"][82]["tokens"]["source_date"] = "not-a-date"
    result = report(left, right)
    assert result["status"] == "unavailable"
    assert "position_integrity_unknown" in result["reasons"]
    assert result["fit"]["alpha"] is None


def test_anchor_missing_and_insufficient_history():
    left, right = setup()
    result = report(left, right, anchor="2025-12-31")
    assert result["evaluation"]["status"] == "not_located"
    assert result["evaluation"]["eligible"] is None and result["trace"] == []
    result = report(left, right, anchor=DAYS[59])
    assert "history_insufficient" in result["reasons"]
    assert result["fit"]["status"] == "unavailable"


@pytest.mark.parametrize("where", [40, 65])
def test_quantity_only_failure_does_not_destroy_price_arithmetic(where):
    left, right = setup()
    expected = report(left, right)
    fail(left["rows"][where], "numeric.volume")
    result = report(left, right)
    assert result["fit"] == expected["fit"]
    assert result["evaluation"]["mse"] == expected["evaluation"]["mse"]


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity", "1e-19", "1e100000"])
def test_invalid_selected_price_is_structured(bad):
    left, right = setup()
    set_price(left["rows"][65], bad)
    result = report(left, right)
    assert result["evaluation"]["status"] == "invalid"
    assert "invalid_price" in result["reasons"]


def test_bounded_display_ties_extreme_exponents_and_context_isolation():
    midpoint = Fraction(1234567890125, 10**12)
    assert _scalar(midpoint)["display"] == "1.23456789012e+0"
    assert _scalar(midpoint + Fraction(1, 10**6000))["display"] == "1.23456789013e+0"
    limit = sys.get_int_max_str_digits()
    values = [Fraction(0), Fraction(1, 10**6000), Fraction(-1, 10**30646), Fraction(10**30646)]
    expected = [_scalar(value) for value in values]
    with localcontext() as context:
        context.prec = 2; context.rounding = ROUND_DOWN; context.Emin = -9; context.Emax = 9
        context.traps[Inexact] = True; context.flags[Inexact] = True
        before = context.copy()
        assert [_scalar(value) for value in values] == expected
        assert context.prec == before.prec and context.flags == before.flags and context.traps == before.traps
    assert sys.get_int_max_str_digits() == limit
    assert all(len(item["display"]) <= 21 for item in expected)


@pytest.mark.parametrize("field,bad", [("fit_end", True), ("evaluation_cutoff", "2026-02-30"),
                                       ("evaluation_cutoff", DAYS[60])])
def test_invalid_dates_rejected(field, bad):
    args = dict(fit_end=DAYS[60], evaluation_cutoff=DAYS[80]); args[field] = bad
    with pytest.raises(ValueError, match="invalid_dates"):
        pair_fixed_change_report(*setup(), **args)


def test_identity_and_row_count_preflight():
    left, right = setup()
    with pytest.raises(ValueError, match="research_duplicate_symbol"):
        report(left, deepcopy(left))
    right["rows"] = [None] * 20001
    with pytest.raises(ValueError, match="research_row_limit"):
        report(left, right)


def test_role_swap_refits_and_public_projection_identity_is_stable():
    left, right = setup()
    original = report(left, right)
    swapped = report(right, left)
    assert swapped["analysis_id"] != original["analysis_id"]
    assert swapped["fit"]["beta"] != original["fit"]["beta"]
    projections = []
    for q in (left, right):
        q = deepcopy(q)
        for key in ("quality", "unlocated_quality", "totals"):
            q.pop(key)
        q["read_projection"] = "daily_ohlc_input_v1"
        projections.append(q)
    assert report(*projections) == original


@pytest.mark.parametrize("legacy", [False, True])
def test_strict_legacy_decoder_store_projections_match(tmp_path, legacy):
    a = ["100" if i % 2 == 0 else "102" if i <= 60 else "100.5" for i in range(81)]
    b = ["100" if i % 2 == 0 else "101" for i in range(81)]
    raws = [capture(symbol, values, DAYS[:81]) for symbol, values in (("600001.SH", a), ("000001.SZ", b))]
    if legacy:
        converted = []
        for raw in raws:
            envelope = json.loads(raw)
            converted.append(build_legacy_capture("tencent", envelope["request"], status=200,
                response_url=envelope["response"]["url"], selected_headers=envelope["response"]["headers"],
                body=base64.b64decode(envelope["body_base64"]), provenance=dict(
                    capture_mode="legacy_reconstruction", header_cardinality="unrecorded",
                    transport_evidence="not_established", original_manifest_sha256="a" * 64,
                    capture_script_sha256="b" * 64)))
        raws = converted
    with EvidenceStore(tmp_path / "store") as store:
        snapshots = [store.import_bytes(raw, "tencent-daily-capture-v1")["snapshot_id"] for raw in raws]
        public = [store.query(snapshot) for snapshot in snapshots]
        compact = [store._research_query(snapshot) for snapshot in snapshots]
        assert report(*public) == report(*compact)
        assert report(*public)["status"] == "source_description_complete"


@pytest.mark.parametrize("p_errors,m_errors,expected_mse,expected_mae", [
    ([1, 1, 10] + [0] * 17, [2, 2, 2] + [0] * 17, Fraction(90, 20), Fraction(6, 20)),
    ([0, 0, 10] + [0] * 17, [4, 4, 4] + [0] * 17, Fraction(52, 20), Fraction(-2, 20)),
])
def test_ideal_core_single_point_dominance_and_loss_disagreement(p_errors, m_errors, expected_mse, expected_mae):
    # Actual kernel inputs realize the specified P/M errors. U is independently
    # determined by x; this ideal vector is not a finite-decimal source fixture.
    x = [Fraction(m - p, 2) for p, m in zip(p_errors, m_errors)]
    y = list(map(Fraction, m_errors))
    fit = dict(mx=Fraction(0), my=Fraction(0), Sxx=Fraction(1), alpha=Fraction(0), beta=Fraction(2))
    result = _exact_evaluate(fit, x, y)
    assert [row["eP"] for row in result["rows"]] == p_errors
    assert [row["eM"] for row in result["rows"]] == m_errors
    assert result["mse"]["delta_PM"] == expected_mse
    assert result["mae"]["delta_PM"] == expected_mae
    assert result["rows"][2]["squared_delta_PM"] > sum(
        row["squared_delta_PM"] for row in result["rows"] if row != result["rows"][2])


def test_changed_slope_can_win_both_baselines_without_stability_claim():
    x = [Fraction(-1, 100), Fraction(1, 100)] * 30
    fit = _exact_fit(x, [2 * value for value in x])
    result = _exact_evaluate(fit, x[:20], [Fraction(9, 5) * value for value in x[:20]])
    assert result["mse"]["delta_PM"] < 0 and result["mse"]["delta_PU"] < 0


def test_exact_source_scale_invariance_and_no_external_decimal_effect():
    left, right = setup()
    original = report(left, right)
    for q, multiplier in ((left, Decimal("1000")), (right, Decimal("0.001"))):
        for row in q["rows"]:
            set_price(row, Decimal(row["tokens"]["close"]) * multiplier)
    scaled = report(left, right)
    assert scaled["fit"] == original["fit"]
    assert scaled["evaluation"] == original["evaluation"]
    with localcontext() as context:
        context.prec = 2; context.rounding = ROUND_DOWN
        context.traps[Inexact] = True
        assert report(left, right) == scaled


def test_decimal_support_extremes_do_not_escape_exact_or_display_bounds():
    small, large = "0.000000000000000001", "99999999999999999999.999999999999999999"
    left = source("600001.SH", [small if i % 2 == 0 else large for i in range(81)])
    right = source("000001.SZ", [large if i % 2 == 0 else small for i in range(81)])
    result = report(left, right)
    assert result["status"] == "source_description_complete"
    assert result["fit"]["beta"]["sign"] == -1
    assert result["evaluation"]["mse"]["P"] == {"display": "0", "sign": 0}
    assert len(canonical_json(result)) <= 262144


def test_duplicate_trace_is_bounded_and_preserves_candidate_count():
    left, right = setup()
    for i in range(20):
        row = deepcopy(left["rows"][65]); row["ordinal"] = 1000 + i
        left["rows"].append(row)
    recount(left)
    result = report(left, right)
    detail = result["trace"][65]["left"]
    assert detail["candidate_count"] == 21
    assert detail["candidate_ordinals"] == [66, 1000, 1001]
    assert detail["omitted_candidates"] == 18
    assert detail["close_exact"] is None and detail["close_token"] is None


def test_duplicate_snapshot_and_price_token_mismatch_keep_fixed_rejections():
    left, right = setup()
    right["snapshot_id"] = right["selection"]["snapshot_id"] = left["snapshot_id"]
    with pytest.raises(ValueError, match="research_duplicate_snapshot"):
        report(left, right)
    left, right = setup()
    left["rows"][65]["tokens"]["close"] = "99"
    result = report(left, right)
    assert "endpoint_price_check_failed" in result["reasons"]
    assert result["evaluation"]["eligible"] == 18
