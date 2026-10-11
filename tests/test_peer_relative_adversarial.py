"""Independent review fixtures, exact oracles and real Store shape checks.

Fixtures are not imported from the implementation author's tests. Synthetic
DTO mutations exercise the defensive contract; they do not authenticate data.
"""
from copy import deepcopy
from decimal import Decimal, localcontext
from fractions import Fraction
import hashlib
import json
from statistics import median

import pytest

from anatrading.peer_relative_research import peer_relative_report
from anatrading.public_market import build_capture, build_legacy_capture, build_request, public_contract
from anatrading.store import EvidenceStore


START, END = "2026-01-05", "2026-01-09"
FIELDS = ["open", "high", "low", "close", "volume", "amount"]
VERSIONS = {"schema": "1", "decode": "1", "normalization": "disabled-1", "quality": "1",
            "numeric": "decimal38.18-bigint-v1"}
PRICES = ("open", "high", "low", "close")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def record(day, price, ordinal):
    return {"ordinal": ordinal, "label": day,
            "tokens": {"source_date": day, **{f: str(price) for f in PRICES}},
            "values": {f: str(price) for f in PRICES}, "checks": []}


def recount(q):
    q["counts"] = {"selected_rows": len(q["rows"]), "unlocated_rows": len(q["unlocated"]),
                   "batch_rows": len(q["rows"]) + len(q["unlocated"]),
                   "batch_unlocated_rows": len(q["unlocated"])}


def fixture(n=4, ends=None):
    ends = ends or ["11", "12", "10", "9"] + ["10"] * (n - 4)
    queries = []
    for i in range(n):
        symbol = f"{601000+i}.SH"
        sid, raw = digest(symbol + "snapshot"), digest(symbol + "raw")
        selection = {"snapshot_id": sid, "mode": "retrospective", "cutoff": None,
                     "ordinal_start": None, "ordinal_end": None, "fields": FIELDS[:],
                     "versions": VERSIONS.copy()}
        q = {"snapshot_id": sid, "batch_id": digest(symbol + "batch"),
             "query_id": digest(symbol + "query"), "selection": selection,
             "manifest": {"raw_sha256": raw, "source_contract_id": digest("synthetic contract"),
                          "qualification": "source_evidence_retrospective_only", "versions": VERSIONS.copy(),
                          "contract": public_contract("tencent-daily-capture-v1")},
             "metadata": {"source_code": symbol, "source_venue": "SH", "requested_symbol": symbol,
                          "source_symbol": "sh" + symbol[:6], "raw_sha256": raw,
                          "source": "tencent", "period": "1d", "requested_period": "1d",
                          "requested_adjustment": "none", "response_branch": "day",
                          "interpretation": {}, "coverage": "unverified"},
             "rows": [record(START, "10", 1), record(END, ends[i], 2)], "unlocated": [],
             "batch_checks": [], "quality": {}, "unlocated_quality": {}, "totals": {}}
        recount(q)
        queries.append(q)
    return queries, group_for(queries)


def refs(name="fixed-review-selection"):
    return [{"source_id": name, "version": "review-1", "declared_by": "project_test"}]


def group_for(queries):
    return {"schema_version": 1, "group_name": "Independent synthetic group", "group_axis": "explicit_sample",
            "selection_date": "2026-10-11", "membership": "current_members_retrospective",
            "selection_basis": "Frozen independent review cases", "evidence_refs": refs(),
            "scope": {k: {"value": v, "evidence_status": "assumed"} for k, v in
                      {"asset_type": "stock", "share_class": "A_share", "price_currency": "CNY",
                       "daily_label_basis": "CN_exchange_date"}.items()},
            "members": [{"symbol": q["metadata"]["source_code"], "snapshot_id": q["snapshot_id"],
                         "query_id": q["query_id"]} for q in queries], "events": []}


def report(queries, group, target=None):
    return peer_relative_report(queries, group, target or "601000.SH", START, END)


def rational(value):
    assert isinstance(value["numerator"], str) and isinstance(value["denominator"], str)
    n, d = int(value["numerator"]), int(value["denominator"])
    f = Fraction(n, d)
    assert d > 0 and f.numerator == n and f.denominator == d
    return f


def append(q, row):
    q["unlocated" if row["label"] is None else "rows"].append(row)
    recount(q)


def failed(row, name):
    row["checks"].append({"name": name, "outcome": "fail"})


def event(q, kind, first=START, last=END):
    return {"symbol": q["metadata"]["source_code"], "snapshot_id": q["snapshot_id"],
            "start_date": first, "end_date": last, "kind": kind, "evidence_refs": refs(kind)}


@pytest.mark.parametrize("ends", [
    ["11", "12", "10", "9"], ["10", "10", "10", "10"],
    ["9", "12", "11", "10", "8"],
    ["10.000000000000000009", "10.000000000000000001", "10.000000000000000002", "10.000000000000000003"],
])
def test_exact_independent_oracle_at_every_target(ends):
    qs, group = fixture(len(ends), ends)
    all_changes = [Fraction(p) / 10 - 1 for p in ends]
    for i, q in enumerate(qs):
        with localcontext() as context:
            context.prec = 2
            result = report(qs, group, q["metadata"]["source_code"])
        peers = all_changes[:i] + all_changes[i+1:]
        comp = result["comparison"]
        assert rational(comp["peer_median"]) == median(peers)
        assert rational(comp["peer_mean"]) == sum(peers) / len(peers)
        assert rational(comp["median_difference_pp"]) == 100 * (all_changes[i] - median(peers))
        assert rational(comp["mean_difference_pp"]) == 100 * (all_changes[i] - sum(peers) / len(peers))
        assert comp["strict_sign_disagreement"] == ((all_changes[i] - median(peers)) *
                                                    (all_changes[i] - sum(peers) / len(peers)) < 0)


def test_exact_extremes_and_decimal_context_do_not_overflow_or_round():
    qs, group = fixture()
    tiny, huge = "0.000000000000000001", "99999999999999999999.999999999999999999"
    for i, q in enumerate(qs):
        q["rows"] = [record(START, tiny if i % 2 == 0 else huge, 1),
                     record(END, huge if i % 2 == 0 else tiny, 2)]
    with localcontext() as context:
        context.prec = 1
        result = report(qs, group)
    assert rational(result["members"][0]["source_change"]) == Fraction(huge) / Fraction(tiny) - 1
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"),
                                 Decimal("1e999999"), Decimal("1e-999999"), 10**5000, "0", "-0"],
                         ids=["nan", "snan", "infinity", "huge-exponent", "tiny-exponent", "huge-int", "zero", "negative-zero"])
def test_extreme_bad_prices_are_structured(bad):
    qs, group = fixture()
    qs[1]["rows"][1]["values"]["close"] = bad
    result = report(qs, group)
    assert result["comparison"] is None
    assert "invalid_price" in result["members"][1]["reasons"]


@pytest.mark.parametrize("day,blocked", [("2026-01-04", False), ("2026-01-07", True),
                                         ("2026-01-10", False), (None, True)])
@pytest.mark.parametrize("kind", ["source_code", "source_adjustment", "source_date_range", "structure", "never_seen_check"])
def test_every_failure_scope_is_explicit(day, blocked, kind):
    qs, group = fixture()
    row = record(day, "10", 3)
    failed(row, kind)
    append(qs[2], row)
    result = report(qs, group)
    assert (result["comparison"] is None) == blocked
    assert result["coverage"]["selected_peer_count"] == 3
    assert result["coverage"]["valid_peer_endpoint_count"] == (2 if blocked else 3)
    assert kind in result["members"][2]["anomalies"][0]["codes"]


@pytest.mark.parametrize("day", ["2026-01-04", "2026-01-07", "2026-01-10"])
def test_nonendpoint_bad_price_and_missing_ohlc_are_path_diagnostics(day):
    qs, group = fixture()
    baseline = report(qs, group)["comparison"]
    row = record(day, "10", 3)
    row["values"]["close"] = None
    row["tokens"]["close"] = "NaN"
    failed(row, "numeric.close")
    append(qs[1], row)
    result = report(qs, group)
    assert result["comparison"] == baseline
    assert result["members"][1]["anomalies"][0]["ordinal"] == 3


def test_unknown_future_ordinal_cannot_hide_possible_duplicate_endpoint():
    qs, group = fixture()
    row = record(None, "11", 10000)
    row["tokens"]["source_date"] = "bad"
    append(qs[1], row)
    result = report(qs, group)
    assert result["comparison"] is None
    assert "endpoint_integrity_unknown" in result["members"][1]["reasons"]
    assert result["members"][0]["source_change"] is not None


@pytest.mark.parametrize("change", ["ambiguous", "unlocated"])
def test_duplicate_endpoint_never_selects_last_or_repairs_raw_date(change):
    qs, group = fixture()
    extra = record(END, "99", 99)
    if change == "unlocated":
        extra["label"] = None
    append(qs[1], extra)
    result = report(qs, group)
    assert result["comparison"] is None
    assert "duplicate_endpoint" in result["members"][1]["reasons"]
    assert result["members"][1]["endpoints"]["end"]["ordinal"] is None


@pytest.mark.parametrize("member", [0, 1])
@pytest.mark.parametrize("at", [START, END])
def test_halt_endpoint_existing_quote_is_diagnostic_and_missing_quote_unavailable(member, at):
    qs, group = fixture()
    baseline = report(qs, group)["comparison"]
    group["events"] = [event(qs[member], "halt", at, at)]
    result = report(qs, group)
    assert result["status"] == "diagnostic_only" and result["comparison"] == baseline
    assert "halted_endpoint_source_value" in result["members"][member]["reasons"]
    qs[member]["rows"] = [row for row in qs[member]["rows"] if row["label"] != at]
    recount(qs[member])
    missing = report(qs, group)
    assert missing["status"] == "unavailable" and missing["comparison"] is None


def test_diagnostics_cannot_restore_another_members_bad_endpoint():
    qs, group = fixture()
    group["events"] = [event(qs[0], "corporate_action_unresolved"), event(qs[0], "halt", START, START)]
    qs[2]["rows"].pop()
    recount(qs[2])
    result = report(qs, group)
    assert result["status"] == "unavailable"
    assert result["comparison"] is None
    assert {"missing_endpoint", "corporate_action_unresolved", "halted_endpoint_source_value"} <= set(result["reasons"])


@pytest.mark.parametrize("check", ["numeric.volume", "numeric.amount", "nonnegative_amount",
                                   "source_quantity_decimal", "conditional_price_bounds", "source_order"])
def test_unrelated_known_failures_preserve_price_result(check):
    qs, group = fixture()
    expected = report(qs, group)["comparison"]
    failed(qs[0]["rows"][0], check)
    assert report(qs, group)["comparison"] == expected


def test_unknown_pass_is_not_qualification_and_unknown_batch_fail_is_rejected():
    qs, group = fixture()
    qs[0]["batch_checks"] = [{"name": "all_adjustment_verified", "outcome": "pass"}]
    result = report(qs, group)
    assert result["limitations"]["economic_return_qualified"] is False
    qs[0]["batch_checks"][0]["outcome"] = "fail"
    with pytest.raises(ValueError, match="^unsupported_source_check$"):
        report(qs, group)


@pytest.mark.parametrize("check", ["numeric.close", "ohlc_bounds", "nonnegative_prices", "label",
                                   "duplicate_label", "source_date_range", "source_order"])
def test_unscoped_batch_price_or_position_failures_cannot_be_ignored(check):
    qs, group = fixture()
    qs[1]["batch_checks"] = [{"name": check, "outcome": "fail"}]
    with pytest.raises(ValueError, match="^unsupported_source_check$"):
        report(qs, group)


@pytest.mark.parametrize("level", ["metadata", "interpretation"])
def test_explicit_foreign_daily_date_basis_cannot_be_overridden_by_group_scope(level):
    qs, group = fixture()
    obj = qs[1]["metadata"] if level == "metadata" else qs[1]["metadata"]["interpretation"]
    obj["daily_label_basis"] = "US_exchange_date"
    with pytest.raises(ValueError, match="^scope_conflict$"):
        report(qs, group)


@pytest.mark.parametrize("which", ["currency", "share_class", "asset_type"])
def test_explicit_scope_counterevidence_rejected(which):
    qs, group = fixture()
    qs[0]["metadata"][which] = {"currency": "USD", "share_class": "B_share", "asset_type": "index"}[which]
    with pytest.raises(ValueError, match="^scope_conflict$"):
        report(qs, group)


@pytest.mark.parametrize("at", [START, END])
def test_explicit_endpoint_source_date_range_failure_blocks_comparison(at):
    qs, group = fixture()
    failed(next(r for r in qs[1]["rows"] if r["label"] == at), "source_date_range")
    result = report(qs, group)
    assert result["comparison"] is None
    assert "local_source_conflict" in result["members"][1]["reasons"]


def test_permutations_and_source_decimal_rendering_preserve_valid_report():
    qs, group = fixture()
    group["evidence_refs"] += refs("second-reference")
    group["events"] = [event(qs[0], "halt", "2026-01-06", "2026-01-07"),
                       event(qs[1], "corporate_action_unresolved")]
    before = deepcopy((qs, group))
    expected = report(qs, group)
    assert (qs, group) == before
    group["members"].reverse(); group["events"].reverse(); group["evidence_refs"].reverse()
    for q in qs:
        q["rows"].reverse()
        for row in q["rows"]:
            row["values"] = {key: Decimal(value) for key, value in row["values"].items()}
    assert report(tuple(reversed(qs)), group) == expected


def test_descriptor_budget_boundary_is_real_bytes_and_fifty_members_fit():
    qs, group = fixture(50)
    result = report(qs, group)
    assert len(result["members"]) == 50
    group["evidence_refs"] = [dict(source_id="界" * 1000, version=str(i), declared_by="project_test") for i in range(6)]
    with pytest.raises(ValueError, match="^auxiliary_input_limit$"):
        report(qs, group)


@pytest.mark.parametrize("mode", ["cycle", "duplicates", "verified", "bool_version"])
def test_descriptor_cannot_upgrade_or_smuggle_nonjson_structure(mode):
    qs, group = fixture()
    if mode == "cycle": group["events"].append(group)
    if mode == "duplicates": group["evidence_refs"] *= 2
    if mode == "verified": group["scope"]["price_currency"]["evidence_status"] = "verified"
    if mode == "bool_version": group["schema_version"] = True
    with pytest.raises(ValueError) as exc:
        report(qs, group)
    assert str(exc.value) in {"auxiliary_input_limit", "invalid_descriptor"}


def test_descriptor_budget_stops_before_expanding_a_shared_container_dag(monkeypatch):
    import anatrading.peer_relative_research as module
    qs, group = fixture()
    shared = []
    for _ in range(4):
        shared = [shared] * 64
    group["events"] = shared
    visits = 0
    def bounded_id(obj):
        nonlocal visits
        visits += 1
        if visits > 20000:
            raise AssertionError("descriptor admission walked beyond its 16 KiB budget")
        return id(obj)
    monkeypatch.setattr(module, "id", bounded_id, raising=False)
    with pytest.raises(ValueError) as exc:
        report(qs, group)
    assert str(exc.value) in {"auxiliary_input_limit", "invalid_descriptor"}


def test_budget_fails_before_source_scan_and_does_not_mutate():
    qs, group = fixture()
    qs[0]["rows"] = [None] * 20001
    with pytest.raises(ValueError, match="^research_row_limit$"):
        report(qs, group)
    qs = [{"rows": [None] * 20000, "unlocated": []} for _ in range(11)]
    with pytest.raises(ValueError, match="^universe_row_limit$"):
        report(qs, group)


@pytest.mark.parametrize("key", ["cutoff", "ordinal_start", "ordinal_end"])
def test_cropped_input_rejected_even_when_endpoints_present(key):
    qs, group = fixture()
    qs[0]["selection"][key] = END if key == "cutoff" else 1
    with pytest.raises(ValueError, match="^full_query_required$"):
        report(qs, group)


@pytest.mark.parametrize("bad_check", [[{}], [{"name": "x"}], [{"name": "x", "outcome": []}], {}])
def test_malformed_checks_never_become_silent_pass(bad_check):
    qs, group = fixture()
    qs[1]["rows"][0]["checks"] = bad_check
    with pytest.raises(ValueError, match="^invalid_source_checks$"):
        report(qs, group)


def capture(symbol, legacy=False):
    request = build_request("tencent", symbol, "1d", start=START, end=END, count=640)
    # Bad volume is intentional: price eligibility must remain independent.
    rows = [[day, p, p, p, p, "bad-volume", {}, "0", "12", "0", "0"]
            for day, p in [("2025-12-31", "8.00"), (START, "10.00"), (END, "11.00")]]
    text = json.dumps({"code": 0, "msg": "", "data": {"sh" + symbol[:6]: {"day": rows}}},
                      separators=(",", ":"))
    body = (request["parameters"]["_var"] + "=" + text).encode()
    args = dict(status=200, response_url=request["url"], body=body)
    if legacy:
        return build_legacy_capture("tencent", request, **args,
            selected_headers={"content-type": "text/html; charset=UTF-8", "content-encoding": ""},
            provenance={"capture_mode": "legacy_reconstruction", "header_cardinality": "unrecorded",
                        "transport_evidence": "not_established", "original_manifest_sha256": "a" * 64,
                        "capture_script_sha256": "b" * 64})
    return build_capture("tencent", request, **args,
                         response_headers=[("Content-Type", "text/html; charset=UTF-8")])


@pytest.mark.parametrize("legacy", [False, True])
def test_real_decoder_store_equivalence_with_quantity_failure_and_earlier_context(tmp_path, legacy):
    with EvidenceStore(tmp_path / "source-store") as store:
        sids = [store.import_bytes(capture(f"{601000+i}.SH", legacy), "tencent-daily-capture-v1")["snapshot_id"]
                for i in range(4)]
        full = [store.query(sid) for sid in sids]
        compact = [store._research_query(sid) for sid in sids]
        assert all(q["metadata"]["request_range_mismatch"] for q in full)
        assert all(q["manifest"]["contract"]["source_semantics"]["fields"]["adjustment"]["status"] == "unknown" for q in full)
        group = group_for(full)
        original = deepcopy((full, compact, group))
        a, b = report(full, group), report(compact, group)
        assert a == b and a["status"] == "source_price_comparison_only"
        assert rational(a["members"][0]["source_change"]) == Fraction(1, 10)
        assert a["members"][0]["endpoints"]["start"]["close_token"] == "10.00"
        assert a["limitations"]["adjustment"] == "request_declared_semantics_unverified"
        assert (full, compact, group) == original
        json.dumps(a, allow_nan=False)
