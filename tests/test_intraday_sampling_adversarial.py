"""Independent adversarial checks for the source-template sampling contract.

Every source in this file is constructed. Importer integration does not certify
compatibility with a private real export, bar finality, or trading performance.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
import json
import random

import pytest

from anatrading.intraday_sampling import intraday_sampling_report


DAY = "2026-10-08"
START = datetime(2026, 10, 8, 9, 31)
SYMBOL = "600059.SH"


def label(offset, start=START):
    return (start + timedelta(minutes=offset)).isoformat(timespec="minutes")


def evidence(version="1"):
    return [dict(source_id="independent-synthetic-template", version=version,
                 declared_by="project_template")]


def source(prices=range(100, 111), *, start=START):
    rows = []
    for i, price in enumerate(prices):
        clock = label(i, start)
        rows.append(dict(ordinal=i+1, label=clock,
                         source_label=clock, locator=f"synthetic:{i+1}",
                         tokens=dict(source_date=clock[:10].replace("-", "")), checks=[],
                         values=dict.fromkeys(("open", "high", "low", "close"), str(price))
                                | dict(volume=None, amount=None)))
    return dict(snapshot_id="a" * 64, query_id="b" * 64,
                metadata=dict(period="1m", source_code=SYMBOL, source_venue="SH",
                              source_adjustment="none", interpretation={}),
                manifest=dict(qualification="source_evidence_retrospective_only"),
                selection=dict(cutoff=None, ordinal_start=None, ordinal_end=None,
                               mode="retrospective"), batch_checks=[], rows=rows, unlocated=[],
                counts=dict(selected_rows=len(rows), unlocated_rows=0, batch_rows=len(rows),
                            batch_unlocated_rows=0))


def descriptor(q, *, first=label(0), last=label(10)):
    return dict(schema_version=1, snapshot_id=q["snapshot_id"], symbol=SYMBOL, market="CN_A",
                source_date=DAY, clock_basis="source_label", label_semantics="declared_end_label",
                timezone=dict(name=None, evidence_status="unknown", evidence_refs=[]),
                segments=[dict(segment_id="morning", first_label=first, last_label=last,
                               step_seconds=60, stage="unknown", stage_evidence_status="unknown",
                               evidence_refs=[])], evidence_refs=evidence())


def report(q, d=None, cutoff=label(10), closure=None):
    return intraday_sampling_report(q, descriptor(q) if d is None else d,
                                   cutoff=cutoff, closure_by_ordinal=closure)


def segment(q, d=None, cutoff=label(10), closure=None):
    return report(q, d, cutoff, closure)["segments"][0]


def add_unknown(q, *, date=None):
    q["unlocated"].append(dict(ordinal=9999, label=None, tokens={} if date is None else
                               dict(source_date=date), values={}, checks=[]))
    q["counts"].update(unlocated_rows=1, batch_unlocated_rows=1,
                       batch_rows=len(q["rows"]) + 1)


def unclosed(ordinal, version="1"):
    return {str(ordinal): dict(status="unclosed", evidence_refs=evidence(version))}


def numbers(values):
    return {key: value for key, value in values.items() if key != "estimate_scope"}


def independent_oracle(prices):
    """High-precision log price-ratios, distinct from float log differences."""
    with localcontext() as ctx:
        ctx.prec = 70
        prices = list(map(Decimal, map(str, prices)))
        fine = [(b/a).ln() for a, b in zip(prices, prices[1:])]
        coarse = [(prices[i]/prices[i-5]).ln() for i in range(5, len(prices), 5)]
        return (float(sum((x*x for x in fine), Decimal(0))),
                float(sum((x*x for x in coarse), Decimal(0))),
                float((prices[-1]/prices[0]).ln()))


def test_random_prices_match_independent_decimal_ratio_oracle_and_cauchy_bound():
    rng = random.Random(20261011)
    prices = [rng.randrange(500, 1500) for _ in range(101)]
    q = source(prices)
    got = segment(q, descriptor(q, last=label(100)), cutoff=label(100))["main_values"]
    a, b, net = independent_oracle(prices)
    assert got["rv_1_same"] == pytest.approx(a, rel=1e-12)
    assert got["rv_5"] == pytest.approx(b, rel=1e-12)
    assert got["net_log_change"] == pytest.approx(net, rel=1e-12)
    assert got["sensitivity_ratio"] == pytest.approx(a/b, rel=1e-12)
    assert got["n_returns_1"] == 100 and got["n_returns_5"] == 20
    assert 0 <= got["rv_5"] <= 5 * got["rv_1_same"]


def test_every_cutoff_uses_expected_anchor_and_known_future_does_not_change_numbers():
    prices = [100, 110, 95, 130, 110, 105, 100, 115, 97, 101, 113, 120, 117, 130, 105, 101]
    q = source(prices)
    d = descriptor(q, last=label(15))
    for k in range(16):
        got = segment(q, d, cutoff=label(k))
        m = 5*(k//5)
        assert got["k"] == k and got["m"] == m
        if m < 5:
            assert got["main_values"] is None
        else:
            expected = independent_oracle(prices[:m+1])
            values = got["main_values"]
            assert (values["rv_1_same"], values["rv_5"], values["net_log_change"]) == pytest.approx(expected)
            assert got["comparison_start_label"] == label(0)
            assert got["comparison_end_label"] == label(m)
        changed = deepcopy(q)
        for row in changed["rows"][k+1:]:
            row["values"]["close"] = "0"
            row["checks"] = [dict(name="source_code", outcome="fail")]
        assert segment(changed, d, cutoff=label(k))["main_values"] == got["main_values"]


def test_missing_expected_coarse_endpoint_cannot_fall_back_to_prior_grid():
    q = source()
    q["rows"].pop()
    got = segment(q)
    assert got["main_values"] is None
    assert got["located_subset_values"] is None
    assert got["coverage_status"] == "incomplete_declared_grid"
    assert got["m"] == 10 and got["comparison_end_label"] == label(10)
    assert got["counts"]["expected_slots"] == 11
    assert got["counts"]["missing_slots"] == 1


def test_tail_bad_price_and_negative_closure_cannot_poison_common_interval():
    q = source()
    before = segment(q, cutoff=label(9))
    q["rows"][8]["values"]["close"] = "0"
    after = segment(q, cutoff=label(9), closure=unclosed(9))
    assert after["main_values"] == before["main_values"]
    assert after["main_values"] is not None
    assert after["closure_status"] == "unknown"


@pytest.mark.parametrize("date", [None, "20261008", "2026/10/08", "20260230"])
def test_unlocatable_current_or_unknown_date_disables_main_not_same_grid_subset(date):
    q = source()
    expected = segment(q)["main_values"]
    add_unknown(q, date=date)
    got = segment(q)
    assert got["main_values"] is None
    assert numbers(got["located_subset_values"]) == numbers(expected)
    assert got["located_subset_values"]["estimate_scope"] == "located_source_subset"
    assert got["coverage_status"] == "unknown"


@pytest.mark.parametrize("date", ["20261007", "20261009", "2026/10/09"])
def test_reliably_other_date_unlocated_row_does_not_poison_current_day(date):
    q = source()
    expected = segment(q)["main_values"]
    add_unknown(q, date=date)
    got = segment(q)
    assert got["main_values"] == expected
    assert got["located_subset_values"] is None
    assert got["coverage_status"] == "complete_declared_grid"


@pytest.mark.parametrize("date", ["20261007", "20261009"])
def test_other_day_unlocatable_conflict_is_outside_selected_date_not_global_rejection(date):
    q = source()
    expected = segment(q)["main_values"]
    add_unknown(q, date=date)
    q["unlocated"][0]["checks"] = [dict(name="source_code", outcome="fail")]
    assert segment(q)["main_values"] == expected


def test_unlocatable_identity_conflict_with_unknown_date_is_rejected_globally():
    q = source()
    add_unknown(q)
    q["unlocated"][0]["checks"] = [dict(name="source_code", outcome="fail")]
    with pytest.raises(ValueError):
        report(q)


def test_incomplete_known_grid_cannot_acquire_subset_value_from_unknown_row():
    q = source()
    q["rows"].pop(2)
    add_unknown(q)
    got = segment(q)
    assert got["main_values"] is None and got["located_subset_values"] is None
    assert got["coverage_status"] == "incomplete_declared_grid"


def test_batch_unknown_without_details_cannot_be_silently_erased():
    q = source()
    expected = segment(q)["main_values"]
    q["counts"]["batch_unlocated_rows"] = 1
    got = segment(q)
    assert got["main_values"] is None
    assert numbers(got["located_subset_values"]) == numbers(expected)
    assert got["coverage_status"] == "unknown"


@pytest.mark.parametrize("field", ["quarantined", "negative_batch_check"])
def test_known_negative_source_cannot_use_conditional_subset_channel(field):
    q = source()
    add_unknown(q)
    if field == "quarantined":
        q["metadata"]["quarantined"] = True
    else:
        q["batch_checks"].append(dict(name="known_negative_sample", outcome="fail"))
    with pytest.raises(ValueError, match="known_negative_source"):
        report(q)


@pytest.mark.parametrize("name", ["source_code", "source_adjustflag", "source_adjustment"])
def test_conflicting_source_check_invalidates_slot_even_if_ohlc_is_valid(name):
    q = source()
    q["rows"][3]["checks"].append(dict(name=name, outcome="fail"))
    got = segment(q)
    assert got["main_values"] is None and got["located_subset_values"] is None


def test_known_unclosed_common_member_is_a_negative_gate_not_qualification():
    q = source()
    got = segment(q, closure=unclosed(4))
    assert got["main_values"] is None and got["located_subset_values"] is None
    assert got["closure_status"] == "unclosed"
    assert report(q)["mode"] == "retrospective"
    assert report(q)["scope"] == "source_template_only"


def test_arbitrary_positive_row_closure_cannot_certify_finality():
    q = source()
    for row in q["rows"]:
        row["closed"] = True
    assert segment(q)["closure_status"] == "unknown"


@pytest.mark.parametrize("closure", [
    {"1": dict(status="closed", evidence_refs=evidence())},
    {"1": dict(status="verified", evidence_refs=evidence())},
    {"1": dict(status="unclosed", evidence_refs=[])},
    {"01": dict(status="unclosed", evidence_refs=evidence())},
    {"0": dict(status="unclosed", evidence_refs=evidence())},
    {"999": dict(status="unclosed", evidence_refs=evidence())},
    {True: dict(status="unclosed", evidence_refs=evidence())},
])
def test_closure_mapping_rejects_unbound_or_positive_evidence(closure):
    with pytest.raises(ValueError):
        report(source(), closure=closure)


@pytest.mark.parametrize("cutoff", ["2026-10-08", "2026-10-08 09:41", "2026-10-08T9:41",
                                    "2026-10-08T09:41:00", "2026-10-08T09:41Z",
                                    "2026-10-09T09:41", "2026-02-30T09:41"])
def test_cutoff_never_accepts_implicit_clock_or_other_date(cutoff):
    with pytest.raises(ValueError):
        report(source(), cutoff=cutoff)


@pytest.mark.parametrize("key", ["ordinal_start", "ordinal_end"])
def test_ordinal_clipping_is_rejected_even_when_all_required_prices_remain(key):
    q = source()
    q["selection"][key] = 1 if key == "ordinal_start" else 11
    with pytest.raises(ValueError, match="ordinal_window_not_supported"):
        report(q)


def test_explicit_query_cutoff_mismatch_is_rejected():
    q = source()
    q["selection"]["cutoff"] = label(9)
    with pytest.raises(ValueError, match="input_cutoff_mismatch"):
        report(q)


def test_function_preserves_query_descriptor_and_closure_inputs():
    q = source()
    d = descriptor(q)
    closure = unclosed(11)
    before = deepcopy((q, d, closure))
    got = report(q, d, cutoff=label(9), closure=closure)
    assert (q, d, closure) == before
    json.dumps(got, allow_nan=False)


def test_auxiliary_budget_rejects_before_treating_huge_evidence_as_trust():
    q = source()
    d = descriptor(q)
    d["evidence_refs"][0]["source_id"] = "x" * 17000
    with pytest.raises(ValueError):
        report(q, d)


@pytest.mark.parametrize("target", ["timezone_status", "stage", "stage_status", "declared_by"])
def test_wrong_descriptor_enum_type_has_stable_validation_error(target):
    q = source()
    d = descriptor(q)
    if target == "timezone_status":
        d["timezone"]["evidence_status"] = []
    elif target == "stage":
        d["segments"][0]["stage"] = {}
    elif target == "stage_status":
        d["segments"][0]["stage_evidence_status"] = []
    else:
        d["evidence_refs"][0]["declared_by"] = []
    with pytest.raises(ValueError):
        report(q, d)


def test_too_many_segments_is_rejected_even_when_all_prices_exist():
    q = source()
    d = descriptor(q)
    d["segments"] = [dict(d["segments"][0], segment_id=f"one-{i}", first_label=label(i),
                          last_label=label(i)) for i in range(9)]
    with pytest.raises(ValueError):
        report(q, d)


@pytest.mark.parametrize("kind", ["duplicate_id", "overlap", "different_date", "nonminute_step"])
def test_invalid_declared_grid_is_rejected_instead_of_reinterpreted(kind):
    q = source()
    d = descriptor(q)
    if kind in {"duplicate_id", "overlap"}:
        other = deepcopy(d["segments"][0])
        if kind == "duplicate_id":
            other.update(first_label=label(11), last_label=label(12))
        else:
            other.update(segment_id="another")
        d["segments"].append(other)
    elif kind == "different_date":
        d["segments"][0]["last_label"] = "2026-10-09T09:41"
    else:
        d["segments"][0]["step_seconds"] = 300
    with pytest.raises(ValueError):
        report(q, d)


def test_all_day_maximum_expected_grid_is_finite_without_filling_source_gaps():
    midnight = datetime(2026, 10, 8)
    q = source(range(100, 1540), start=midnight)
    d = descriptor(q, first=f"{DAY}T00:00", last=f"{DAY}T23:59")
    got = report(q, d, cutoff=f"{DAY}T23:59")
    assert len(got["slot_trace"]) == 1440
    assert got["segments"][0]["main_values"]["n_returns_1"] == 1435
    assert got["segments"][0]["main_values"]["n_returns_5"] == 287
    assert len(json.dumps(got).encode()) < 400_000


def test_resource_limit_includes_unlocated_rows_not_only_good_prices():
    q = source()
    q["unlocated"] = [dict(ordinal=100+i, label=None, tokens={}, values={}, checks=[])
                       for i in range(20001)]
    with pytest.raises(ValueError):
        report(q)


def test_precision_loss_does_not_fabricate_a_zero_volatility_constant_price():
    q = source(["1", "1.000000000000000001", "1", "1", "1", "1"])
    d = descriptor(q, last=label(5))
    got = segment(q, d, cutoff=label(5))
    assert got["main_values"] is None and got["located_subset_values"] is None
    assert "precision_loss" in json.dumps(got)


def test_missing_volume_and_bad_amount_do_not_block_a_price_only_comparison():
    q = source()
    expected = segment(q)["main_values"]
    for row in q["rows"]:
        row["values"].update(volume=None, amount="not-an-amount")
    assert segment(q)["main_values"] == expected


def test_full_120_close_segment_reports_115_fine_23_coarse_returns_and_four_tail_intervals():
    q = source(range(100, 220))
    d = descriptor(q, last=label(119))
    got = segment(q, d, cutoff=label(119))
    assert (got["k"], got["m"]) == (119, 115)
    assert got["comparison_end_label"] == "2026-10-08T11:26"
    assert got["main_values"]["n_returns_1"] == 115
    assert got["main_values"]["n_returns_5"] == 23
    assert got["tail"]["counts"]["expected_slots"] == 4


def test_noon_price_jump_never_enters_independent_afternoon_segment():
    q = source(range(100, 106))
    afternoon = source(range(10000, 10006), start=datetime(2026, 10, 8, 13, 1))["rows"]
    for row in afternoon:
        row["ordinal"] += 6
    q["rows"].extend(afternoon)
    d = descriptor(q, last=label(5))
    other = deepcopy(d["segments"][0])
    other.update(segment_id="afternoon", first_label=f"{DAY}T13:01", last_label=f"{DAY}T13:06")
    d["segments"].append(other)
    got = report(q, d, cutoff=f"{DAY}T13:06")
    assert len(got["segments"]) == 2
    for result, prices in zip(got["segments"], [range(100, 106), range(10000, 10006)]):
        expected = independent_oracle(prices)
        values = result["main_values"]
        assert (values["rv_1_same"], values["rv_5"], values["net_log_change"]) == pytest.approx(expected)
        assert values["n_returns_1"] == 5 and values["n_returns_5"] == 1


def test_identity_binds_cutoff_descriptor_evidence_stage_timezone_query_and_closure():
    q = source()
    d = descriptor(q)
    baseline = report(q, d, cutoff=label(9))
    identities = {baseline["analysis_id"]}
    variants = []
    for modify in (lambda x: x["evidence_refs"][0].update(version="2"),
                   lambda x: x["segments"][0].update(last_label=label(11)),
                   lambda x: x["segments"][0].update(stage="mixed"),
                   lambda x: x["timezone"].update(name="Asia/Shanghai", evidence_status="declared",
                                                 evidence_refs=evidence())):
        changed = deepcopy(d)
        modify(changed)
        variants.append(report(q, changed, cutoff=label(9)))
    variants.append(report(q, d, cutoff=label(8)))
    changed = deepcopy(q)
    changed["query_id"] = "c" * 64
    variants.append(report(changed, d, cutoff=label(9)))
    variants.extend(report(q, d, cutoff=label(9), closure=unclosed(11, version=v)) for v in ["1", "2"])
    for result in variants:
        assert result["segments"][0]["main_values"] == baseline["segments"][0]["main_values"]
        assert result["analysis_id"] not in identities
        identities.add(result["analysis_id"])


def test_declared_timezone_metadata_does_not_require_host_tz_database(monkeypatch):
    import zoneinfo
    import anatrading.intraday_sampling as module

    def no_database(*args, **kwargs):
        raise zoneinfo.ZoneInfoNotFoundError("simulated unavailable time-zone database")

    monkeypatch.setattr(zoneinfo, "ZoneInfo", no_database)
    if hasattr(module, "ZoneInfo"):
        monkeypatch.setattr(module, "ZoneInfo", no_database)
    q = source()
    d = descriptor(q)
    baseline = segment(q)["main_values"]
    d["timezone"].update(name="Asia/Shanghai", evidence_status="declared", evidence_refs=evidence())
    got = report(q, d)
    assert got["segments"][0]["main_values"] == baseline
    assert got["descriptor"]["timezone"]["name"] == "Asia/Shanghai"
    assert got["scope"] == "source_template_only"


def test_finite_estimates_and_exact_source_values_do_not_depend_on_decimal_context():
    q = source(["0.000000000000000001", "99999999999999999999", "2", "1", "11", "5"])
    d = descriptor(q, last=label(5))
    expected = report(q, d, cutoff=label(5))
    before = deepcopy(q)
    with localcontext() as ctx:
        ctx.prec = 2
        actual = report(q, d, cutoff=label(5))
    assert actual == expected and q == before
    json.dumps(actual, allow_nan=False)


def test_source_order_does_not_change_numbers_or_identity():
    q = source()
    expected = report(q)
    q["rows"].reverse()
    actual = report(q)
    assert actual["analysis_id"] == expected["analysis_id"]
    assert actual["segments"] == expected["segments"]


def imported_http_query(tmp_path, *, malformed_last_clock=False, interpretation=None):
    """Build bytes independently and exercise the actual parser/store boundary."""
    from anatrading.store import EvidenceStore
    prices = ["10", "11", "9", "10", "12", "11"]
    times = ["093100", "093200", "093300", "093400", "093500", "093600"]
    if malformed_last_clock:
        times[-1] = "093601"
    request = dict(id=42, method="get_market_data", params=dict(stock_list=[SYMBOL], period="1m",
                   end_time="20261008150000", count=6, dividend_type="none", fill_data=False))
    columns = dict(ErrorId="0", Date=["20261008"] * 6, Time=times,
                   Open=prices, High=prices, Low=prices, Close=prices,
                   Volume=["0"] * 6, Amount=["0"] * 6)
    response = dict(id=42, result=dict(ErrorId="0", Value={SYMBOL: columns}))
    payload = json.dumps(dict(request_utf8=json.dumps(request), response_utf8=json.dumps(response))).encode()
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(payload, "tdx-http-market-v1", interpretation=interpretation)["snapshot_id"]
        return store.query(sid, cutoff=label(5))


def test_real_importer_shape_preserves_source_unknowns_and_exact_query(tmp_path):
    q = imported_http_query(tmp_path)
    before = deepcopy(q)
    got = report(q, descriptor(q, last=label(5)), cutoff=label(5))
    assert got["segments"][0]["main_values"] is not None
    assert got["segments"][0]["closure_status"] == "unknown"
    assert got["mode"] == "retrospective" and got["scope"] == "source_template_only"
    assert q == before


def test_importer_unlocatable_clock_is_not_repaired_into_complete_last_slot(tmp_path):
    q = imported_http_query(tmp_path, malformed_last_clock=True)
    assert len(q["unlocated"]) == 1
    got = segment(q, descriptor(q, last=label(5)), cutoff=label(5))
    assert got["main_values"] is None and got["located_subset_values"] is None
    assert got["counts"]["missing_slots"] == 1


def test_imported_conflicting_identity_declaration_cannot_be_ignored(tmp_path):
    q = imported_http_query(tmp_path, interpretation=dict(instrument="000001.SZ", venue="SZ"))
    assert any(c["name"] == "declared_instrument" and c["outcome"] == "fail" for c in q["batch_checks"])
    with pytest.raises(ValueError):
        report(q, descriptor(q, last=label(5)), cutoff=label(5))
