"""Independent exact examples and source-shape tests; no private market fixtures."""
from copy import deepcopy
from dataclasses import asdict
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
from itertools import combinations_with_replacement

import pytest

from anatrading.formats import decode
from anatrading.models import VALUE_FIELDS, VERSIONS
from anatrading.peer_relative_research import peer_relative_report
from anatrading.public_market import build_capture, build_request, canonical_json
from anatrading.store import EvidenceStore


A, B = "2026-09-28", "2026-09-30"
FMT = "tencent-daily-capture-v1"


def capture(symbol, closes, dates=(A, B)):
    request = build_request("tencent", symbol, "1d", start=min(dates), end=max(dates), count=640)
    rows = [[day, str(close), str(close), str(close), str(close), "123.4500", {}, "0", "10", "0", "0"]
            for day, close in zip(dates, closes)]
    body = request["parameters"]["_var"].encode() + b"=" + canonical_json(
        dict(code=0, msg="", data={symbol[-2:].lower() + symbol[:6]: {"day": rows}}))
    return build_capture("tencent", request, status=200, response_url=request["url"],
                         response_headers=[("Content-Type", "text/html; charset=UTF-8")], body=body)


def source_query(symbol, closes, dates=(A, B)):
    """Synthetic consistent DTO, not a claim to have queried a real Store."""
    raw = capture(symbol, closes, dates)
    decoded = decode(raw, FMT)
    sha = hashlib.sha256(raw).hexdigest()
    snapshot = hashlib.sha256(raw + b"synthetic snapshot").hexdigest()
    rows = [asdict(row) for row in decoded.rows]
    selection = dict(snapshot_id=snapshot, mode="retrospective", cutoff=None, ordinal_start=None,
                     ordinal_end=None, fields=list(VALUE_FIELDS), versions=dict(VERSIONS))
    return dict(snapshot_id=snapshot, batch_id=hashlib.sha256(raw + b"synthetic batch").hexdigest(),
                query_id=hashlib.sha256(canonical_json(selection)).hexdigest(), selection=selection,
                metadata=decoded.metadata, manifest=dict(raw_sha256=sha,
                    source_contract_id=hashlib.sha256(canonical_json(decoded.contract)).hexdigest(),
                    contract=decoded.contract, versions=dict(VERSIONS), qualification="source_evidence_retrospective_only"),
                rows=rows, unlocated=[], counts=dict(selected_rows=len(rows), unlocated_rows=0,
                    batch_rows=len(rows), batch_unlocated_rows=0), batch_checks=[asdict(c) for c in decoded.checks],
                quality={}, unlocated_quality={}, totals={})


def refs():
    return [dict(source_id="synthetic-selection", version="1", declared_by="project_test")]


def descriptor(queries):
    return dict(schema_version=1, group_name="Synthetic peers", group_axis="explicit_sample",
                selection_date="2026-10-11", membership="current_members_retrospective",
                selection_basis="Independent synthetic arithmetic examples", evidence_refs=refs(),
                scope={key: dict(value=value, evidence_status="declared") for key, value in
                       dict(asset_type="stock", share_class="A_share", price_currency="CNY",
                            daily_label_basis="CN_exchange_date").items()},
                members=[dict(symbol=q["metadata"]["source_code"], snapshot_id=q["snapshot_id"], query_id=q["query_id"])
                         for q in queries], events=[])


def setup(changes=(3, 5, 5, 5)):
    queries = [source_query(f"{600000 + index}.SH", [100, 100 + change]) for index, change in enumerate(changes)]
    return queries, descriptor(queries)


def run(queries, group, a=A, b=B):
    return peer_relative_report(queries, group, "600000.SH", a, b)


def value(number):
    return Fraction(int(number["numerator"]), int(number["denominator"]))


def recount(query):
    query["counts"] = dict(selected_rows=len(query["rows"]), unlocated_rows=len(query["unlocated"]),
                           batch_rows=len(query["rows"]) + len(query["unlocated"]),
                           batch_unlocated_rows=len(query["unlocated"]))


def fail(row, name):
    row["checks"] = [check for check in row["checks"] if check["name"] != name]
    row["checks"].append(dict(name=name, outcome="fail"))


def event(queries, kind, start=A, end=B):
    return dict(symbol="600000.SH", snapshot_id=queries[0]["snapshot_id"], start_date=start,
                end_date=end, kind=kind, evidence_refs=refs())


@pytest.mark.parametrize("changes,median_pp,mean_pp,disagree", [
    ((3,) + (5,) * 9, Fraction(-2), Fraction(-2), False),
    ((-3,) + (-5,) * 9, Fraction(2), Fraction(2), False),
    ((5, 0, 1, 2, 3, 4, 5, 6, 7, 80), Fraction(1), Fraction(-7), True),
    ((10,) + (5,) * 9, Fraction(5), Fraction(5), False),
    ((0, 0, 0, 0), Fraction(0), Fraction(0), False),
    ((0, 0, 2, 4, 6), Fraction(-3), Fraction(-3), False),
    ((2, 0, 2, 9), Fraction(0), Fraction(-5, 3), False),
])
def test_independent_exact_examples(changes, median_pp, mean_pp, disagree):
    queries, group = setup(changes)
    report = run(queries, group)
    assert report["status"] == "source_price_comparison_only"
    assert value(report["comparison"]["median_difference_pp"]) == median_pp
    assert value(report["comparison"]["mean_difference_pp"]) == mean_pp
    assert report["comparison"]["strict_sign_disagreement"] is disagree
    assert report["comparison"]["median_difference_pp"]["unit"] == "percentage_point"
    assert report["comparison"]["peer_median"]["unit"] == "ratio"
    assert report["limitations"]["economic_return_qualified"] is False
    json.dumps(report, allow_nan=False)


def test_no_rounding_before_order_or_difference():
    queries = [source_query(f"{600000+i}.SH", ["1", close]) for i, close in enumerate([
        "1.000000000000000004", "1.000000000000000001", "1.000000000000000002", "1.000000000000000003"])]
    report = run(queries, descriptor(queries))
    assert value(report["comparison"]["median_difference_pp"]) == Fraction(2, 10**16)


def test_identity_order_invariance_input_unchanged_and_fifty_member_budget():
    queries, group = setup(tuple(range(50)))
    original = deepcopy((queries, group))
    expected = run(queries, group)
    assert len(canonical_json(group)) < 16384
    assert expected == run(list(reversed(queries)), {**group, "members": list(reversed(group["members"]))})
    assert (queries, group) == original
    for key, changed in (("group_name", "Changed"), ("group_axis", "listing_board"), ("selection_date", "2026-10-10")):
        assert run(queries, {**group, key: changed})["analysis_id"] != expected["analysis_id"]


@pytest.mark.parametrize("index", [0, 1])
@pytest.mark.parametrize("which", [0, 1])
def test_missing_endpoint_never_rolls_back_or_removes_member(index, which):
    queries, group = setup()
    queries[index]["rows"].pop(which)
    recount(queries[index])
    report = run(queries, group)
    assert report["status"] == "unavailable" and report["comparison"] is None
    assert report["coverage"]["selected_peer_count"] == 3
    assert report["coverage"]["valid_peer_endpoint_count"] == (3 if index == 0 else 2)
    assert report["members"][index]["source_change"] is None
    assert "missing_endpoint" in report["members"][index]["reasons"]


@pytest.mark.parametrize("bad", ["0", "-1", "NaN", "Infinity", "1e100000", "1e-19", "100000000000000000000", "9" * 200])
def test_price_domain_rejections_are_structured(bad):
    queries, group = setup()
    queries[1]["rows"][1]["values"]["close"] = bad
    queries[1]["rows"][1]["tokens"]["close"] = bad
    report = run(queries, group)
    assert report["comparison"] is None
    assert "invalid_price" in report["members"][1]["reasons"]


@pytest.mark.parametrize("mutation,reason", [
    (lambda r: r["values"].update(open=None), "missing_ohlc"),
    (lambda r: r["values"].update(high="1"), "invalid_ohlc"),
    (lambda r: r["tokens"].update(close="999"), "endpoint_price_check_failed"),
    (lambda r: fail(r, "numeric.close"), "endpoint_price_check_failed"),
    (lambda r: fail(r, "duplicate_label"), "duplicate_endpoint"),
])
def test_complete_ohlc_and_token_checks(mutation, reason):
    queries, group = setup()
    mutation(queries[1]["rows"][1])
    report = run(queries, group)
    assert report["comparison"] is None
    assert reason in report["members"][1]["reasons"]


def test_duplicate_and_unlocated_endpoint_both_retained():
    queries, group = setup()
    extra = deepcopy(queries[1]["rows"][1])
    extra.update(ordinal=3, label=None)
    queries[1]["unlocated"].append(extra)
    recount(queries[1])
    report = run(queries, group)
    assert {"duplicate_endpoint", "unlocated_endpoint"} <= set(report["members"][1]["reasons"])
    assert report["members"][1]["endpoints"]["end"]["ordinal"] is None
    assert report["comparison"] is None


@pytest.mark.parametrize("label,source_date,blocked", [
    (None, "2026-10-01", False), (None, "2026-09-29", False),
    (None, B, True), (None, None, True), (None, "2026/10/01", True),
    ("2026-10-01", B, True), ("2026-10-01", None, True),
])
def test_date_scope_does_not_guess_or_repair(label, source_date, blocked):
    queries, group = setup()
    extra = deepcopy(queries[1]["rows"][0])
    extra.update(ordinal=3, label=label)
    extra["tokens"]["source_date"] = source_date
    extra["values"]["close"] = None
    fail(extra, "numeric.close")
    queries[1]["unlocated" if label is None else "rows"].append(extra)
    recount(queries[1])
    report = run(queries, group)
    assert (report["comparison"] is None) is blocked


@pytest.mark.parametrize("day,blocked", [("2026-09-27", False), ("2026-09-29", True), ("2026-10-01", False), (None, True)])
@pytest.mark.parametrize("check", ["source_code", "source_adjustment", "structure", "new_failure"])
def test_scoped_source_conflicts(day, blocked, check):
    queries, group = setup()
    extra = deepcopy(queries[1]["rows"][0])
    extra.update(ordinal=3, label=day)
    extra["tokens"]["source_date"] = day
    fail(extra, check)
    queries[1]["unlocated" if day is None else "rows"].append(extra)
    recount(queries[1])
    report = run(queries, group)
    assert (report["comparison"] is None) is blocked


@pytest.mark.parametrize("check", ["numeric.volume", "numeric.amount", "conditional_price_bounds", "source_order"])
def test_nonprice_failures_do_not_block_source_arithmetic(check):
    queries, group = setup()
    expected = run(queries, group)["comparison"]
    fail(queries[1]["rows"][1], check)
    assert run(queries, group)["comparison"] == expected


@pytest.mark.parametrize("kind,start,end,status,reason", [
    ("corporate_action_unresolved", A, B, "diagnostic_only", "corporate_action_unresolved"),
    ("halt", A, A, "diagnostic_only", "halted_endpoint_source_value"),
    ("halt", B, B, "diagnostic_only", "halted_endpoint_source_value"),
    ("halt", "2026-09-29", "2026-09-29", "source_price_comparison_only", None),
])
def test_negative_events_never_upgrade_qualification(kind, start, end, status, reason):
    queries, group = setup()
    group["events"] = [event(queries, kind, start, end)]
    report = run(queries, group)
    assert report["status"] == status
    assert report["comparison"] is not None
    if reason:
        assert reason in report["reasons"]
    assert report["limitations"]["corporate_action_coverage"] == "unknown"


def test_unresolved_split_example_and_missing_halted_endpoint():
    queries, group = setup((-50, 0, 0, 0))
    group["events"] = [event(queries, "corporate_action_unresolved")]
    report = run(queries, group)
    assert report["status"] == "diagnostic_only"
    assert value(report["comparison"]["median_difference_pp"]) == -50
    group["events"] = [event(queries, "halt", A, A)]
    queries[0]["rows"].pop(0)
    recount(queries[0])
    report = run(queries, group)
    assert report["comparison"] is None
    assert "halted_endpoint_source_value" not in report["reasons"]


@pytest.mark.parametrize("mutation,code", [
    (lambda q: q["metadata"].update(quarantined=True), "known_negative_source"),
    (lambda q: q["batch_checks"].append(dict(name="known_negative_sample", outcome="fail")), "known_negative_source"),
    (lambda q: q["batch_checks"].append(dict(name="declared_instrument", outcome="fail")), "source_identity_conflict"),
    (lambda q: q["batch_checks"].append(dict(name="source_adjustment", outcome="fail")), "source_adjustment_conflict"),
    (lambda q: q["metadata"].update(requested_adjustment="qfq"), "source_adjustment_conflict"),
    (lambda q: q["metadata"]["interpretation"].update(asset_type="index"), "scope_conflict"),
    (lambda q: q["metadata"].update(price_currency="USD"), "scope_conflict"),
    (lambda q: q["metadata"].update(daily_label_basis="US_exchange_date"), "scope_conflict"),
    (lambda q: q["metadata"]["interpretation"].update(daily_label_basis="US_exchange_date"), "scope_conflict"),
    (lambda q: q["batch_checks"].append(dict(name="numeric.close", outcome="fail")), "unsupported_source_check"),
    (lambda q: q["batch_checks"].append(dict(name="label", outcome="fail")), "unsupported_source_check"),
    (lambda q: q["selection"].update(cutoff=A), "full_query_required"),
    (lambda q: q["selection"].update(ordinal_start=1), "full_query_required"),
    (lambda q: q["counts"].update(batch_unlocated_rows=1), "invalid_counts"),
    (lambda q: q["rows"][1].update(ordinal=1), "invalid_source_ordinal"),
    (lambda q: q.update(query_id="x"), "invalid_source_id"),
    (lambda q: q["selection"].update(snapshot_id="f"*64), "source_identity_mismatch"),
    (lambda q: q["rows"][1]["values"].update(close=True), "invalid_query"),
    (lambda q: q["rows"][1]["values"].update(close=1.0), "invalid_query"),
])
def test_structure_and_global_source_failures(mutation, code):
    queries, group = setup()
    mutation(queries[1])
    with pytest.raises(ValueError, match="^" + code + "$"):
        run(queries, group)


def test_cn_a_helper_result_does_not_certify_b_share_scope():
    queries, group = setup()
    queries[1] = source_query("900901.SH", [100, 105])
    group = descriptor(queries)
    group["events"] = [dict(symbol="900901.SH", snapshot_id=queries[1]["snapshot_id"],
                            start_date=A, end_date=B, kind="scope_conflict", evidence_refs=refs())]
    with pytest.raises(ValueError, match="^scope_conflict$"):
        run(queries, group)
    del group["scope"]
    with pytest.raises(ValueError, match="^invalid_descriptor$"):
        run(queries, group)


@pytest.mark.parametrize("key,value_", [("group_axis", []), ("group_axis", {}), ("schema_version", True), ("extra", "unknown")])
def test_descriptor_bad_types_have_stable_error(key, value_):
    queries, group = setup()
    group[key] = value_
    with pytest.raises(ValueError, match="^invalid_descriptor$"):
        run(queries, group)


def test_descriptor_budget_and_row_budget_are_preflight():
    queries, group = setup()
    group["selection_basis"] = "x" * 2000
    with pytest.raises(ValueError, match="^auxiliary_input_limit$"):
        run(queries, group)
    group = descriptor(queries)
    queries[0]["rows"] = [None] * 20_001
    with pytest.raises(ValueError, match="^research_row_limit$"):
        run(queries, group)
    queries = [{"rows": [None] * 20_000, "unlocated": []} for _ in range(11)]
    with pytest.raises(ValueError, match="^universe_row_limit$"):
        run(queries, group)
    with pytest.raises(ValueError, match="^member_limit$"):
        run([{}] * 51, group)


def test_future_prefix_and_price_rescaling_invariance():
    base, group = setup((3, 5, 8, 1))
    expected = run(base, group)
    for extra_day, future in (("2026-10-01", 200), ("2026-10-02", 5), ("2026-10-03", 999)):
        queries = [source_query(f"{600000+i}.SH", [100, 100 + change, future], (A, B, extra_day))
                   for i, change in enumerate((3, 5, 8, 1))]
        report = run(queries, descriptor(queries))
        assert report["comparison"] == expected["comparison"]
        assert report["analysis_id"] != expected["analysis_id"]
    scaled = [source_query(f"{600000+i}.SH", [100*(i+2), (100+change)*(i+2)]) for i, change in enumerate((3, 5, 8, 1))]
    assert run(scaled, descriptor(scaled))["comparison"] == expected["comparison"]


def test_leave_one_out_preserves_order_and_ties_with_exact_oracle():
    for changes in combinations_with_replacement((-10, 0, 3), 4):
        queries, group = setup(changes)
        medians, means = [], []
        for index, original in enumerate(changes):
            report = peer_relative_report(queries, group, f"{600000+index}.SH", A, B)
            medians.append(value(report["comparison"]["median_difference_pp"]))
            means.append(value(report["comparison"]["mean_difference_pp"]))
            others = changes[:index] + changes[index+1:]
            assert means[-1] == Fraction(original) - Fraction(sum(others), len(others))
        for i in range(4):
            for j in range(4):
                assert (changes[i] < changes[j]) == (medians[i] < medians[j]) == (means[i] < means[j])
                assert (changes[i] == changes[j]) == (medians[i] == medians[j]) == (means[i] == means[j])


def test_duplicate_members_and_recursive_descriptor_rejected():
    queries, group = setup()
    with pytest.raises(ValueError, match="^duplicate_member$"):
        run([queries[0], queries[0], *queries[2:]], group)
    group["events"].append(group)
    with pytest.raises(ValueError, match="^auxiliary_input_limit$"):
        run(queries, group)


def test_actual_decoder_store_public_and_projection_equivalent(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        snapshots = [store.import_bytes(capture(f"{600000+i}.SH", [100, end]), FMT)["snapshot_id"]
                     for i, end in enumerate((103, 105, 108, 101))]
        public = [store.query(snapshot) for snapshot in snapshots]
        compact = [store._research_query(snapshot) for snapshot in snapshots]
        group = descriptor(public)
        assert run(public, group) == run(compact, group)
