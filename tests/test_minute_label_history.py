"""Synthetic endpoint records; no live database or market qualification."""
from copy import deepcopy
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from fractions import Fraction

import pytest

from anatrading.minute_label_history import endpoint_selection, minute_label_history, signed_fraction


def row(day, clock, close="10", ordinal=1, **tokens):
    label = f"2026-09-{day:02d}T{clock}" if clock else None
    return dict(ordinal=ordinal, label=label, source_label=label, locator=f"row:{ordinal}",
                tokens=dict(source_date=f"202609{day:02d}", **tokens),
                values=dict(open=None, high=None, low=None, close=close, volume=None, amount=None),
                checks=[], volume_shares=None, amount_cny=None)


def query(rows, unlocated=()):
    return dict(snapshot_id="a" * 64, batch_id="b" * 64, query_id="c" * 64,
                metadata=dict(period="1m"), manifest=dict(raw_sha256="d" * 64, versions=dict(parser="v1"),
                    contract=dict(temporal_semantics=dict(status="unknown"))), batch_checks=[],
                selection=dict(cutoff=None, ordinal_start=None, ordinal_end=None),
                rows=rows, unlocated=list(unlocated))


def sample():
    return query([row(day, clock, close, (day-20)*2+i)
                  for day in range(21, 29) for i, (clock, close) in enumerate((("14:57", "10"), ("15:00", "9")))])


def report(context=None, selected=None, **kwargs):
    context = context if context is not None else sample()
    return minute_label_history(selected if selected is not None else context, context,
                                kwargs.get("day", "2026-09-28"), kwargs.get("start", "14:57"), kwargs.get("end", "15:00"))


def test_explicit_endpoints_signed_hand_calculation_and_immutable_source():
    context = sample(); before = deepcopy(context)
    result = report(context)
    assert result["nominal_minutes"] == 3
    assert result["history_dates"] == [f"2026-09-{d}" for d in range(23, 28)]
    assert result["window_status"] == "complete" and result["missing_history_dates"] == 0
    assert result["days"][0]["kind"] == "current" and len(result["days"]) == 6
    for member in result["days"]:
        assert member["change"] == dict(numerator="-1", denominator="10", display="-0.10000000")
        assert member["magnitude"] == dict(numerator="1", denominator="10", display="0.10000000")
        assert member["reason"] is None
        assert member["start"][0]["values"]["close"] == "10"
    assert result["contract"]["temporal_semantics"]["status"] == "unknown"
    assert result["raw_sha256"] == context["manifest"]["raw_sha256"]
    assert result["versions"] == context["manifest"]["versions"]
    assert context == before and report(context) == result


@pytest.mark.parametrize("value", [Fraction(-1, 3), Fraction(1, 3), Fraction(-1, 200_000_000),
    Fraction(-3, 200_000_000), Fraction(1, 200_000_000), Fraction(3, 200_000_000),
    Fraction(-1234567891, 10_000_000_000), Fraction(0)])
def test_signed_rounding_against_independent_decimal_quantize(value):
    with localcontext() as context:
        context.prec = 100
        expected = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_EVEN)
    if expected == 0:
        expected = abs(expected)
    assert signed_fraction(value)["display"] == format(expected, ".8f")
    assert signed_fraction(value)["numerator"] == str(value.numerator)


def test_long_decimal_endpoints_do_not_use_current_decimal_division_context():
    context = sample()
    context["rows"][-2]["values"]["close"] = "10.000000000000000001"
    context["rows"][-1]["values"]["close"] = "10.000000000000000002"
    with localcontext() as precision:
        precision.prec = 3
        current = report(context)["days"][0]
    assert current["change"]["numerator"] == "1"
    assert current["change"]["denominator"] == "10000000000000000001"
    assert current["change"]["display"] == "0.00000000"
    assert current["magnitude"] == current["change"]


def test_no_grid_or_internal_path_requirement_and_lunch_nominal_span():
    context = query([row(28, "11:30"), row(28, "13:01", "12", 2)])
    result = report(context, start="11:30", end="13:01")
    assert result["nominal_minutes"] == 91 and result["days"][0]["change"]["numerator"] == "1"
    assert result["window_status"] == "insufficient" and result["missing_history_dates"] == 5


@pytest.mark.parametrize("problem,reason", [("missing", "missing_endpoint"), ("duplicate", "duplicate_endpoint"),
    (None, "missing_close"), ("NaN", "invalid_close"), ("junk", "invalid_close"),
    ("0", "nonpositive_close"), ("-1", "nonpositive_close"), (True, "invalid_close")])
def test_bad_historical_day_keeps_place_and_all_candidates(problem, reason):
    context = sample()
    target = next(r for r in context["rows"] if r["label"] == "2026-09-27T15:00")
    if problem == "missing": context["rows"].remove(target)
    elif problem == "duplicate": context["rows"].append({**target, "ordinal": 999})
    else: target["values"]["close"] = problem
    result = report(context)
    member = result["days"][-1]
    assert member["source_date"] == "2026-09-27" and member["reason"] == reason
    assert member["change"] is None and member["magnitude"] is None
    assert result["history_dates"][0] == "2026-09-23"
    if problem == "duplicate": assert [r["ordinal"] for r in member["end"]] == [15, 999]


def test_readable_bad_clock_date_occupies_window_and_uniqueness_not_assumed():
    context = sample()
    context["rows"] = [r for r in context["rows"] if r["label"][:10] != "2026-09-27"]
    context["unlocated"] = [row(27, None, ordinal=999)]
    result = report(context)
    assert result["window_status"] == "complete"
    assert result["days"][-1]["reason"] == "endpoint_uniqueness_unknown"
    assert result["days"][-1]["unknown_clock_ordinals"] == [999]
    context["unlocated"] = [row(28, None, ordinal=998)]
    assert report(context)["days"][0]["reason"] == "endpoint_uniqueness_unknown"


def test_unreadable_date_degrades_window_but_retains_literal_located_values():
    context = sample()
    bad = row(28, None, ordinal=999); bad["tokens"]["source_date"] = "unreadable"
    context["unlocated"] = [bad]
    result = report(context)
    assert result["window_status"] == "unresolved_dates" and result["missing_history_dates"] is None
    assert result["unknown_date_ordinals"] == [999]
    assert result["days"][0]["change"] is not None
    assert len(result["history_dates"]) == 5  # expressly only the readable subset


def test_future_known_rows_and_outside_window_failures_do_not_change_fixed_result():
    context = sample(); original = report(context)
    context["rows"].extend([row(29, "14:57", "999", 998), row(29, "15:00", "1", 999)])
    context["unlocated"].extend([row(29, None, ordinal=1000), row(21, None, ordinal=1001)])
    context["rows"][0]["checks"] = [dict(name="source_code", outcome="fail")]
    assert report(context) == original
    future_bad = row(29, None, ordinal=1002); future_bad["tokens"] = {}
    context["unlocated"].append(future_bad)
    assert report(context)["window_status"] == "unresolved_dates"


def test_visible_ordinal_selection_cannot_shorten_source_history():
    context = sample(); selected = deepcopy(context)
    selected["rows"] = [context["rows"][-1]]
    selected["selection"].update(ordinal_start=17, ordinal_end=17)
    selected["query_id"] = "e" * 64
    result = report(context, selected)
    assert len(result["history_dates"]) == 5 and result["context_query_id"] != result["query_id"]
    context["selection"]["ordinal_start"] = 17
    with pytest.raises(ValueError, match="incomplete_source_context"): report(context, selected)


@pytest.mark.parametrize("name,reason", [("source_code", "source_identity_conflict"), ("declared_venue", "source_identity_conflict"),
    ("source_adjustflag", "source_adjustment_check_failed"), ("price_scaling", "price_scale_conflict"),
    ("label_semantics", "source_label_conflict"), ("structure", "source_structure_failed"),
    ("numeric.close", "invalid_close")])
@pytest.mark.parametrize("scope", ["row", "batch"])
def test_known_checks_block_close_ratio(name, reason, scope):
    context = sample(); check = dict(name=name, outcome="fail")
    if scope == "row": context["rows"][-1]["checks"].append(check)
    else: context["batch_checks"].append(check)
    current = report(context)["days"][0]
    assert current["reason"] == reason and current["change"] is None


def test_metadata_conflicts_and_quarantine_block_even_with_valid_endpoints():
    context = sample()
    context["metadata"].update(source_code="600059.SH", source_venue="SH", interpretation=dict(instrument="000001.SZ", venue="SZ"))
    assert report(context)["days"][0]["reason"] == "source_identity_conflict"
    context["metadata"] = dict(period="1m", quarantined=True)
    assert report(context)["days"][0]["reason"] == "source_quarantined"
    context["metadata"] = dict(period="1m")
    context["manifest"]["contract"]["price_scaling"] = dict(status="conflict")
    assert report(context)["days"][0]["reason"] == "price_scale_conflict"


@pytest.mark.parametrize("token,reason", [("price_scale", "price_scale_conflict"), ("adjustflag", "source_adjustment_conflict"), ("label_semantics", "source_label_conflict")])
def test_known_intraday_claim_change_blocks_only_that_day(token, reason):
    context = sample()
    context["rows"][-2]["tokens"][token] = "a"
    context["rows"][-1]["tokens"][token] = "b"
    result = report(context)
    assert result["days"][0]["reason"] == reason
    assert all(r["change"] is not None for r in result["days"][1:])


def test_close_only_ignores_unrelated_quantity_and_ohlc_failures():
    context = sample()
    for scope in (context["batch_checks"], context["rows"][-1]["checks"]):
        scope.extend(dict(name=name, outcome="fail") for name in ("numeric.volume", "numeric.open", "ohlc_bounds", "nonnegative_prices"))
    assert report(context)["days"][0]["change"]["numerator"] == "-1"
    context["rows"].append(row(28, "14:58", "bad", 999))
    assert report(context)["days"][0]["reason"] is None


def test_price_common_scale_invariance_and_zero_change():
    context = sample(); original = report(context)
    for row_ in context["rows"]: row_["values"]["close"] = str(int(row_["values"]["close"]) * 7)
    assert [r["change"] for r in report(context)["days"]] == [r["change"] for r in original["days"]]
    context["rows"][-1]["values"]["close"] = context["rows"][-2]["values"]["close"]
    assert report(context)["days"][0]["change"] == dict(numerator="0", denominator="1", display="0.00000000")


@pytest.mark.parametrize("args", [("20260928", "14:57", "15:00"), ("2026-09-28", "14:57", "14:57"),
    ("2026-09-28", "15:00", "14:57"), ("2026-09-28", "9:31", "15:00"), ("2026-09-28", "14:57", "25:00")])
def test_selection_is_explicit_canonical_and_ordered(args):
    with pytest.raises(ValueError, match="invalid_endpoint_selection"): endpoint_selection(*args)


def test_cutoff_before_endpoint_and_wrong_context_or_period_are_rejected():
    context = sample(); context["selection"]["cutoff"] = "2026-09-28T14:59"
    with pytest.raises(ValueError, match="invalid_endpoint_selection"): report(context)
    context = sample(); selected = deepcopy(context); selected["snapshot_id"] = "f" * 64
    with pytest.raises(ValueError, match="context_source_mismatch"): report(context, selected)
    context["metadata"]["period"] = "1d"
    with pytest.raises(ValueError, match="unsupported_period"): report(context)
    context["metadata"]["period"] = "5m"
    assert report(context)["days"][0]["change"] is not None


def test_row_and_response_budgets_have_stable_failure_not_truncation():
    context = sample(); context["rows"] *= 1251
    with pytest.raises(ValueError, match="query_row_limit"): report(context)
    context = sample(); context["rows"][-1]["tokens"]["large_original"] = "字" * 700_000
    with pytest.raises(ValueError, match="response_limit"): report(context)


def test_known_label_convention_change_across_dates_is_not_qualified_matching():
    context = sample()
    for row_ in context["rows"]:
        row_["tokens"]["label_semantics"] = "end" if row_["label"].startswith("2026-09-28") else "start"
    result = report(context)
    assert result["days"][0]["change"] is not None
    assert all(item["reason"] == "source_label_conflict" and item["change"] is None for item in result["days"][1:])
    assert all(item["start"] and item["end"] for item in result["days"])


def test_scientific_close_strings_and_tiny_negative_rounding_keep_exact_sign():
    context = query([row(28, "14:57", "2E-18"), row(28, "15:00", "1E-18", 2)])
    assert report(context)["days"][0]["change"] == dict(numerator="-1", denominator="2", display="-0.50000000")
    context["rows"][0]["values"]["close"] = "10.000000000000000002"
    context["rows"][1]["values"]["close"] = "10.000000000000000001"
    value = report(context)["days"][0]["change"]
    assert value["numerator"] == "-1" and value["denominator"] == "10000000000000000002"
    assert value["display"] == "0.00000000"


def test_every_fixed_prefix_endpoint_and_date_membership_survives_future_changes():
    context = sample()
    for day in range(21, 29):
        old = report(context, day=f"2026-09-{day}")
        changed = deepcopy(context)
        for row_ in changed["rows"]:
            if row_["label"][:10] > f"2026-09-{day}":
                row_["values"]["close"] = "bad"
                row_["checks"].append(dict(name="source_code", outcome="fail"))
        assert report(changed, day=f"2026-09-{day}") == old


@pytest.mark.parametrize("start_tokens,end_tokens", [
    ({"code": "600000.SH"}, {"code": "000001.SZ"}),
    ({"source_code": "600000.SH"}, {"source_code": "000001.SZ"}),
    ({"code": "600000.SH"}, {"source_code": "000001.SZ"}),
    ({"venue": "SH"}, {"venue": "SZ"}),
    ({"source_venue": "SH"}, {"source_venue": "SZ"}),
    ({"venue": "SH"}, {"source_venue": "SZ"}),
    ({"code": "600000.SH", "source_code": "000001.SZ"}, {}),
    ({"code": "600000.SH", "venue": "SZ"}, {}),
])
def test_explicit_row_identity_conflicts_block_without_batch_identity(start_tokens, end_tokens):
    context = sample()
    context["rows"][-2]["tokens"].update(start_tokens)
    context["rows"][-1]["tokens"].update(end_tokens)
    current = report(context)["days"][0]
    assert current["reason"] == "source_identity_conflict" and current["change"] is None
    assert current["start"] and current["end"]


@pytest.mark.parametrize("token,value", [("source_code", "000001.SZ"), ("code", "000001.SZ"),
                                         ("source_venue", "SZ"), ("venue", "SZ")])
def test_each_row_identity_alias_is_checked_against_batch_claim(token, value):
    context = sample(); context["metadata"].update(source_code="600000.SH", source_venue="SH")
    context["rows"][-1]["tokens"][token] = value
    assert report(context)["days"][0]["reason"] == "source_identity_conflict"


def test_matching_identity_aliases_and_unknown_shared_identity_remain_conditional():
    context = sample()
    assert report(context)["days"][0]["change"] is not None
    context["metadata"].update(source_code="600000.SH", source_venue="SSE",
                               interpretation=dict(instrument="sh.600000", venue="XSHG"))
    context["rows"][-2]["tokens"].update(code="SH600000", source_venue="SH")
    context["rows"][-1]["tokens"].update(source_code="600000", venue="XSHG")
    assert report(context)["days"][0]["reason"] is None
    context["metadata"] = dict(period="1m")
    assert report(context)["days"][0]["change"] is not None


def test_outside_window_identity_conflict_is_scoped_to_its_day():
    context = sample(); original = report(context)
    context["rows"][0]["tokens"]["code"] = "600000.SH"
    context["rows"][1]["tokens"]["code"] = "000001.SZ"
    assert report(context) == original
