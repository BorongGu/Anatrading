"""036 independent source fixtures, exact arithmetic and presentation oracles.

Expected values never use a product normalizer, fit, score or display helper.
Ideal Fraction vectors are identified separately from finite-decimal source data.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import (
    Decimal, getcontext, localcontext, ROUND_DOWN, InvalidOperation,
    DivisionByZero, Overflow, Underflow, Subnormal, Clamped, FloatOperation,
    Rounded, Inexact,
)
from fractions import Fraction
import hashlib
import json
from math import gcd
import sys

import pytest

from anatrading.pair_stability_research import (
    pair_fixed_change_report, _exact_fit, _exact_evaluate, _scalar,
)


F = Fraction
FIELDS = ("open", "high", "low", "close", "volume", "amount")
PRICE = FIELDS[:4]
SIGNALS = (InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal,
           Clamped, FloatOperation, Rounded, Inexact)
DAYS = [(date(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(90)]
FIT_END, CUTOFF = DAYS[60], DAYS[80]
LOSS_KEYS = ("P", "M", "U", "delta_PM", "delta_PU")


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def recount(query):
    located, unknown = len(query["rows"]), len(query["unlocated"])
    query["counts"] = dict(selected_rows=located, unlocated_rows=unknown,
                           batch_rows=located + unknown, batch_unlocated_rows=unknown)


def source(prices, symbol, *, days=None, projection=True):
    """Construct an independent synthetic DTO in the documented Store shape."""
    days = DAYS[:len(prices)] if days is None else days
    snap, raw = digest("snapshot:" + symbol), digest("raw:" + symbol)
    versions = {"schema": "1", "decode": "1"}
    code, venue = symbol.split(".")
    rows = []
    for ordinal, (day, price) in enumerate(zip(days, prices, strict=True), 1):
        token = None if price is None else str(price)
        rows.append(dict(ordinal=ordinal, label=day,
            tokens={"source_date": day, **dict.fromkeys(PRICE, token)},
            values={**dict.fromkeys(PRICE, token), "volume": None, "amount": None},
            checks=[]))
    query = dict(snapshot_id=snap, batch_id=digest("batch:" + symbol),
        query_id=digest("query:" + symbol),
        selection=dict(snapshot_id=snap, mode="retrospective", cutoff=None,
                       ordinal_start=None, ordinal_end=None, fields=list(FIELDS), versions=versions),
        manifest=dict(raw_sha256=raw, source_contract_id=digest("contract:" + symbol),
            versions=versions, qualification="source_evidence_retrospective_only",
            contract=dict(format_id="tencent-daily-capture-v1", version="1",
                capture_version="public-market-capture-v1",
                source_token_mapping={"source_date": "source_date"},
                source_semantics={"fields": {"price_unit": {"value": "unknown"},
                                             "adjustment": {"value": "unknown"}}})),
        metadata=dict(raw_sha256=raw, source="tencent", period="1d", requested_period="1d",
            requested_symbol=symbol, source_code=symbol, source_venue=venue,
            source_symbol=venue.lower() + code, requested_adjustment="none", response_branch="day"),
        rows=rows, unlocated=[], counts={}, batch_checks=[])
    if projection:
        query["read_projection"] = "daily_ohlc_input_v1"
    else:
        query.update(quality=[], unlocated_quality=[], totals={})
    recount(query)
    return query


def pair(*, stable=False, future=0):
    left = ["100" if i % 2 == 0 else "102" if i <= 60 or stable else "100.5"
            for i in range(81 + future)]
    right = ["100" if i % 2 == 0 else "101" for i in range(81 + future)]
    return source(left, "600123.SH"), source(right, "000456.SZ")


def report(left, right, *, cutoff=CUTOFF, fit_end=FIT_END):
    return pair_fixed_change_report(left, right, fit_end=fit_end, evaluation_cutoff=cutoff)


def from_token(token):
    """Independent source decimal decomposition, with no product parser."""
    sign, digits, exponent = Decimal(token).as_tuple()
    integer = 0
    for digit in digits:
        integer = 10 * integer + digit
    integer = -integer if sign else integer
    return F(integer * 10**exponent) if exponent >= 0 else F(integer, 10**-exponent)


def source_vectors(left, right):
    """Independent union grid for the valid-source numeric fixtures."""
    maps = []
    for query in (left, right):
        mapping = {}
        for row in (*query["rows"], *query["unlocated"]):
            label, raw_day = row["label"], row["tokens"].get("source_date")
            assert label == raw_day and date.fromisoformat(label).isoformat() == label
            assert label not in mapping
            mapping[label] = from_token(row["tokens"]["close"])
        maps.append(mapping)
    dates = sorted(set(maps[0]) | set(maps[1]))
    split = dates.index(FIT_END)
    dates = dates[split - 60:split + 21]
    assert len(dates) == 81 and all(set(dates) <= set(m) for m in maps)
    changes = [[m[b] / m[a] - 1 for a, b in zip(dates, dates[1:])] for m in maps]
    return changes[1][:60], changes[0][:60], changes[1][60:], changes[0][60:]


def fit_oracle(x, y):
    n = len(x)
    sx, sy = sum(x, F()), sum(y, F())
    q = n * sum((a * a for a in x), F()) - sx * sx
    k = n * sum((a * b for a, b in zip(x, y, strict=True)), F()) - sx * sy
    beta = k / q if q else None
    alpha = (sy - beta * sx) / n if beta is not None else None
    return dict(mx=sx / n, my=sy / n, Sxx=q / n, alpha=alpha, beta=beta)


def evaluation_oracle(fit, x, y):
    rows = []
    for a, b in zip(x, y, strict=True):
        p = fit["alpha"] + fit["beta"] * a if fit["beta"] is not None else None
        m, u = fit["my"], a
        ep, em, eu = None if p is None else b - p, b - m, b - u
        rows.append(dict(x=a, y=b, P=p, M=m, U=u, eP=ep, eM=em, eU=eu,
            squared_delta_PM=None if ep is None else ep**2 - em**2,
            squared_delta_PU=None if ep is None else ep**2 - eu**2,
            absolute_delta_PM=None if ep is None else abs(ep) - abs(em),
            absolute_delta_PU=None if ep is None else abs(ep) - abs(eu)))
    summaries = {}
    for name, loss in (("mse", lambda e: e * e), ("mae", abs)):
        summary = dict.fromkeys(LOSS_KEYS)
        if len(rows) == 20:
            for model in ("P", "M", "U"):
                residuals = [r["e" + model] for r in rows]
                if all(e is not None for e in residuals):
                    summary[model] = sum((loss(e) for e in residuals), F()) / 20
            if summary["P"] is not None:
                summary["delta_PM"] = summary["P"] - summary["M"]
                summary["delta_PU"] = summary["P"] - summary["U"]
        summaries[name] = summary
    return dict(rows=rows, **summaries)


def scalar_oracle(value):
    """Integer-only scientific display; product uses Decimal division."""
    if value is None:
        return None
    if not value:
        return {"display": "0", "sign": 0}
    numerator, denominator = abs(value.numerator), value.denominator
    lower, upper = -31000, 31000
    def reaches(exponent):
        return (numerator >= denominator * 10**exponent if exponent >= 0 else
                numerator * 10**-exponent >= denominator)
    assert reaches(lower) and not reaches(upper)
    while lower + 1 < upper:
        middle = (lower + upper) // 2
        if reaches(middle):
            lower = middle
        else:
            upper = middle
    exponent = lower
    shift = 11 - exponent
    if shift >= 0:
        numerator *= 10**shift
    else:
        denominator *= 10**-shift
    digits, remainder = divmod(numerator, denominator)
    if 2 * remainder > denominator or 2 * remainder == denominator and digits % 2:
        digits += 1
    if digits == 10**12:
        digits //= 10
        exponent += 1
    text = str(digits)
    assert len(text) == 12
    sign = -1 if value < 0 else 1
    return {"display": ("-" if sign < 0 else "") + text[0] + "." + text[1:] + f"e{exponent:+d}",
            "sign": sign}


def assert_core(actual, expected):
    assert actual == expected
    def visit(value):
        if isinstance(value, F):
            assert value.numerator.bit_length() <= 110000
            assert value.denominator.bit_length() <= 110000
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(actual)


def assert_public_numbers(result, fit, evaluation):
    for key, value in fit.items():
        assert result["fit"][key] == scalar_oracle(value)
    for metric in ("mse", "mae"):
        for key, value in evaluation[metric].items():
            assert result["evaluation"][metric][key] == scalar_oracle(value)
    for actual, expected in zip(result["evaluation"]["rows"], evaluation["rows"], strict=True):
        for key, value in expected.items():
            assert actual[key] == scalar_oracle(value)


def mutate_price(query, index, token):
    query["rows"][index]["values"].update(dict.fromkeys(PRICE, token))
    query["rows"][index]["tokens"].update(dict.fromkeys(PRICE, token))


def test_independent_source_counterexample_all_exact_values_and_public_display():
    left, right = pair()
    original = deepcopy((left, right))
    x, y, ex, ey = source_vectors(left, right)
    fit = fit_oracle(x, y)
    assert fit == dict(mx=F(1, 20200), my=F(1, 5100), Sxx=fit["Sxx"],
                       alpha=F(1, 10251), beta=F(20402, 10251))
    expected = evaluation_oracle(fit, ex, ey)
    assert expected["mse"] == dict(P=F(205083001, 934071120000), M=F(4653449, 186814224000),
        U=F(812130601, 32970448080000), delta_PM=F(226139, 1161780000),
        delta_PU=F(385021963, 1975219630000))
    actual_fit = _exact_fit(x, y)
    assert_core(actual_fit, fit)
    assert_core(_exact_evaluate(actual_fit, ex, ey), expected)
    result = report(left, right)
    assert result["status"] == "source_description_complete"
    assert result["fit"]["planned_intervals"] == 60
    assert result["evaluation"]["observed"] == result["evaluation"]["eligible"] == 20
    assert len(result["trace"]) == 81
    assert_public_numbers(result, fit, expected)
    assert (left, right) == original
    assert len(json.dumps(result, sort_keys=True, ensure_ascii=False, separators=(",", ":"),
                          allow_nan=False).encode()) <= 262144
    for key in ("economic_return", "prediction", "causal_attribution", "stability_certified"):
        assert result["limitations"][key] is False


@pytest.mark.parametrize("kind", ["same", "negative", "flat_y", "tiny_nonzero_x", "mixed"])
def test_actual_exact_kernel_against_independent_noncentered_matrix(kind):
    x = [F((i * 17) % 29 - 14, 1000 + i) for i in range(60)]
    y = [F((i * 7) % 13 - 6, 300 + i) for i in range(60)]
    if kind == "same":
        y = list(x)
    elif kind == "negative":
        y = [F(3, 1000) - 2 * a for a in x]
    elif kind == "flat_y":
        y = [F(0)] * 60
    elif kind == "tiny_nonzero_x":
        x = [F(i % 2, 10**38) for i in range(60)]
    expected = fit_oracle(x, y)
    frozen = deepcopy((x, y))
    fit = _exact_fit(x, y)
    assert_core(fit, expected)
    ex, ey = [F((i * 3) % 7 - 3, 201) for i in range(20)], [F(i % 5 - 2, 103) for i in range(20)]
    assert_core(_exact_evaluate(fit, ex, ey), evaluation_oracle(expected, ex, ey))
    assert (x, y) == frozen


@pytest.mark.parametrize("constant", [F(0), F(1, 100)])
def test_zero_sxx_keeps_only_complete_baseline_comparisons(constant):
    x, y = [constant] * 60, [F(i % 3, 100) for i in range(60)]
    fit = _exact_fit(x, y)
    assert_core(fit, fit_oracle(x, y))
    assert fit["alpha"] is fit["beta"] is None
    ex, ey = [F(1, 200)] * 20, [F(i % 2, 100) for i in range(20)]
    assert_core(_exact_evaluate(fit, ex, ey), evaluation_oracle(fit_oracle(x, y), ex, ey))


@pytest.mark.parametrize("count", [0, 1, 19])
def test_private_partial_evaluation_never_returns_a_complete_block(count):
    fit = fit_oracle([F(i % 2, 100) for i in range(60)], [F(i % 2, 50) for i in range(60)])
    x, y = [F(1, 100)] * count, [F(1, 200)] * count
    assert_core(_exact_evaluate(fit, x, y), evaluation_oracle(fit, x, y))


@pytest.mark.parametrize("direction", [-1, 1])
def test_loss_difference_sign_is_exact_when_rounded_losses_are_equal(direction):
    # Ideal kernel vector only: no claim that this is a finite-decimal source fixture.
    beta = direction * F(1, 10**6000)
    fit = dict(mx=F(0), my=F(0), Sxx=F(1), alpha=F(0), beta=beta)
    actual = _exact_evaluate(fit, [F(1)] * 20, [F(1)] * 20)
    expected = evaluation_oracle(fit, [F(1)] * 20, [F(1)] * 20)
    assert_core(actual, expected)
    assert _scalar(actual["mse"]["P"])["display"] == _scalar(actual["mse"]["M"])["display"]
    assert _scalar(actual["mse"]["delta_PM"])["sign"] == -direction


@pytest.mark.parametrize("value", [F(0), F(1, 3), -F(2, 7), F(1, 10**6000), -F(1, 10**6000),
    F(10**30646), -F(1, 10**30646), F(9999999999995, 10**12),
    F(1234567890125, 10**12), F(1234567890135, 10**12),
    F(1234567890125, 10**12) + F(1, 10**6000),
    F(1234567890125, 10**12) - F(1, 10**6000)], ids=lambda value: None)
def test_scalar_integer_oracle_and_external_context_isolation(value):
    expected = scalar_oracle(value)
    original_limit = sys.get_int_max_str_digits()
    with localcontext() as outer:
        outer.prec = 2
        outer.rounding = ROUND_DOWN
        outer.Emin, outer.Emax = -9, 9
        outer.traps[Inexact] = True
        outer.flags[Rounded] = True
        before = (outer.prec, outer.rounding, outer.Emin, outer.Emax, outer.capitals, outer.clamp,
                  tuple(outer.traps[s] for s in SIGNALS), tuple(outer.flags[s] for s in SIGNALS))
        assert _scalar(value) == expected
        after = getcontext()
        assert (after.prec, after.rounding, after.Emin, after.Emax, after.capitals, after.clamp,
                tuple(after.traps[s] for s in SIGNALS), tuple(after.flags[s] for s in SIGNALS)) == before
    assert sys.get_int_max_str_digits() == original_limit
    assert len(expected["display"]) <= 21


def test_scalar_null_and_no_precision_floor_for_a_legal_source_movement():
    assert _scalar(None) is None
    left, right = pair()
    for i in range(len(right["rows"])):
        mutate_price(right, i, "1" if i % 2 == 0 else "1.000000000000000001")
    x, y, ex, ey = source_vectors(left, right)
    assert 0 < fit_oracle(x, y)["Sxx"] < F(1, 10**16)
    result = report(left, right)
    assert result["fit"]["status"] == "ready"
    assert_public_numbers(result, fit_oracle(x, y), evaluation_oracle(fit_oracle(x, y), ex, ey))


@pytest.mark.parametrize("observed", [0, 1, 19, 20, 21])
def test_maturity_uses_first_twenty_source_intervals(observed):
    left, right = pair(future=2)
    cutoff = DAYS[60 + observed] if observed else (date.fromisoformat(FIT_END) + timedelta(days=1)).isoformat()
    if observed == 0:
        # First available source label after d0 is later than this cutoff.
        for query in (left, right):
            query["rows"] = [r for r in query["rows"] if r["label"] != DAYS[61]]
            recount(query)
    result = report(left, right, cutoff=cutoff)
    assert result["fit"]["status"] == "ready"
    assert result["evaluation"]["observed"] == min(observed, 20)
    if observed < 20:
        assert result["status"] == "incomplete" and result["evaluation"]["status"] == "pending"
        assert all(v is None for v in result["evaluation"]["mse"].values())
    else:
        assert result["status"] == "source_description_complete"
        assert result["evaluation"]["end"] == DAYS[80]


@pytest.mark.parametrize("issue", ["missing", "duplicate", "bad_price", "unknown_check", "identity", "bad_label"])
def test_evaluation_local_failure_blocks_two_intervals_without_retraining(issue):
    left, right = pair()
    normal = report(left, right)
    row = left["rows"][65]
    if issue == "missing":
        left["rows"].pop(65)
    elif issue == "duplicate":
        duplicate = deepcopy(row)
        duplicate["ordinal"] = 900
        left["rows"].append(duplicate)
    elif issue == "bad_price":
        mutate_price(left, 65, "0")
    elif issue == "unknown_check":
        row["checks"] = [{"name": "new_unsupported_price_evidence", "outcome": "fail"}]
    elif issue == "identity":
        row["tokens"]["code"] = "600999.SH"
    else:
        left["rows"].pop(65)
        row["label"] = None
        left["unlocated"].append(row)
    recount(left)
    result = report(left, right)
    assert result["fit"] == normal["fit"]
    assert result["status"] == "unavailable" and result["evaluation"]["status"] == "invalid"
    assert result["evaluation"]["observed"] == 20 and result["evaluation"]["eligible"] == 18
    assert len(result["evaluation"]["rows"]) == 20
    assert all(v is None for v in result["evaluation"]["mse"].values())
    assert result["evaluation"]["rows"][4]["P"] is None
    assert result["evaluation"]["rows"][5]["P"] is None
    assert result["evaluation"]["rows"][6]["P"] == normal["evaluation"]["rows"][6]["P"]


def test_shared_anchor_and_unknown_position_do_not_become_future_local_errors():
    for mode in ("bad_anchor", "unknown_future"):
        left, right = pair(future=3)
        if mode == "bad_anchor":
            mutate_price(left, 60, "0")
        else:
            left["rows"][-1]["tokens"]["source_date"] = DAYS[84]
        result = report(left, right)
        assert result["fit"]["status"] == "unavailable"
        assert result["status"] == "unavailable"
        assert all(v is None for v in result["evaluation"]["mse"].values())


def test_missing_anchor_never_falls_back_and_both_sides_missing_stays_unknown_calendar():
    left, right = pair()
    for query in (left, right):
        query["rows"].pop(60)
        recount(query)
    result = report(left, right)
    assert "anchor_missing" in result["reasons"]
    assert result["trace"] == result["evaluation"]["rows"] == []
    assert result["evaluation"]["observed"] is None
    left, right = pair()
    for query in (left, right):
        query["rows"].pop(65)
        recount(query)
    result = report(left, right)
    assert result["evaluation"]["observed"] == 19
    assert result["evaluation"]["status"] == "pending"
    assert result["limitations"]["calendar"] == "unknown"


def test_future_source_mutation_and_evaluation_cutoff_preserve_frozen_calculation():
    left, right = pair(future=3)
    original = report(left, right)
    mutate_price(left, 81, "0")
    left["rows"][82]["checks"] = [{"name": "future_unknown_fail", "outcome": "fail"}]
    changed = report(left, right, cutoff=DAYS[83])
    assert changed["fit"] == original["fit"]
    assert changed["evaluation"] == original["evaluation"]
    assert changed["analysis_id"] != original["analysis_id"]


def test_changed_first_e_close_affects_only_two_rows_and_never_the_fit():
    left, right = pair()
    original = report(left, right)
    mutate_price(left, 61, "103")
    changed = report(left, right)
    assert changed["fit"] == original["fit"]
    assert changed["evaluation"]["rows"][0] != original["evaluation"]["rows"][0]
    assert changed["evaluation"]["rows"][1] != original["evaluation"]["rows"][1]
    assert changed["evaluation"]["rows"][2:] == original["evaluation"]["rows"][2:]


def test_reliable_future_unlocated_label_does_not_hide_or_poison_selected_prices():
    left, right = pair()
    expected = report(left, right)
    row = deepcopy(left["rows"][-1])
    row.update(ordinal=1000, label=None)
    row["tokens"]["source_date"] = DAYS[85]
    left["unlocated"].append(row)
    recount(left)
    actual = report(left, right)
    assert actual["fit"] == expected["fit"]
    assert actual["evaluation"] == expected["evaluation"]


def test_training_failure_does_not_fit_a_cleaner_target_only_baseline():
    left, right = pair()
    mutate_price(right, 10, "0")
    result = report(left, right)
    assert result["fit"]["status"] == "unavailable"
    assert result["evaluation"]["eligible"] == 20
    assert result["evaluation"]["status"] == "complete"
    for row in result["evaluation"]["rows"]:
        assert row["x"] is not None and row["y"] is not None
        assert row["P"] is row["M"] is row["U"] is None


def test_constant_training_source_keeps_baselines_and_perfect_fit_is_not_rejected():
    left, right = pair(stable=True)
    result = report(left, right)
    assert result["evaluation"]["mse"]["P"] == {"display": "0", "sign": 0}
    for i in range(len(right["rows"])):
        mutate_price(right, i, "100")
    result = report(left, right)
    assert result["status"] == "baseline_only"
    assert result["fit"]["beta"] is None
    assert result["evaluation"]["mse"]["P"] is None
    assert result["evaluation"]["mse"]["M"] is not None
    assert result["evaluation"]["mse"]["U"] is not None


@pytest.mark.parametrize("field,value,reason", [("quarantined", True, "known_negative_source"),
    ("requested_adjustment", "qfq", "source_adjustment_conflict"),
    ("daily_label_basis", "US_exchange_date", "scope_conflict")])
def test_existing_global_source_rejections_are_not_weakened(field, value, reason):
    left, right = pair()
    left["metadata"][field] = value
    with pytest.raises(ValueError, match="^" + reason + "$"):
        report(left, right)


@pytest.mark.parametrize("field", ["cutoff", "ordinal_start", "ordinal_end"])
def test_full_source_required_and_rows_budget_precedes_any_derived_scan(field):
    left, right = pair()
    left["selection"][field] = DAYS[10] if field == "cutoff" else 1
    with pytest.raises(ValueError, match="^full_query_required$"):
        report(left, right)
    oversized = {"rows": [None] * 20001, "unlocated": []}
    with pytest.raises(ValueError, match="^research_row_limit$"):
        report(oversized, right)


def test_role_swap_is_a_new_fit_and_input_order_is_not_a_new_model():
    left, right = pair()
    x, y, ex, ey = source_vectors(right, left)
    reverse = report(right, left)
    assert_public_numbers(reverse, fit_oracle(x, y), evaluation_oracle(fit_oracle(x, y), ex, ey))
    original = report(left, right)
    left["rows"].reverse()
    right["rows"].reverse()
    assert report(left, right) == original


def test_quantity_errors_and_unknown_adjustment_remain_source_descriptions():
    left, right = pair()
    original = report(left, right)
    left["rows"][65]["checks"] = [{"name": "numeric.volume", "outcome": "fail"},
                                    {"name": "source_order", "outcome": "fail"}]
    actual = report(left, right)
    assert actual["fit"] == original["fit"]
    assert actual["evaluation"]["mse"] == original["evaluation"]["mse"]
    assert actual["limitations"]["corporate_action_coverage"] == "unknown"
    assert actual["limitations"]["adjustment"] == "request_declared_semantics_unverified"


def test_exact_positive_price_rescaling_and_hostile_outer_decimal_context():
    left, right = pair()
    expected = report(left, right)
    for query, scale in ((left, F(1, 10)), (right, F(3))):
        for index, row in enumerate(query["rows"]):
            scaled = from_token(row["tokens"]["close"]) * scale * 10**18
            assert scaled.denominator == 1
            integer, fraction = divmod(scaled.numerator, 10**18)
            mutate_price(query, index, f"{integer}.{fraction:018d}")
    with localcontext() as outer:
        outer.prec = 2
        outer.Emin, outer.Emax = -9, 9
        outer.rounding = ROUND_DOWN
        outer.traps[Inexact] = True
        actual = report(left, right)
    assert actual["fit"] == expected["fit"]
    assert actual["evaluation"] == expected["evaluation"]


def test_bounded_duplicate_trace_does_not_change_comparison_denominator():
    left, right = pair()
    seed = left["rows"][65]
    for i in range(400):
        row = deepcopy(seed)
        row["ordinal"] = 1000 + i
        left["rows"].append(row)
    recount(left)
    result = report(left, right)
    def dictionaries(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from dictionaries(child)
        elif isinstance(value, list):
            for child in value:
                yield from dictionaries(child)
    matches = [d for d in dictionaries(result["trace"]) if d.get("candidate_count") == 401]
    assert len(matches) == 1 and matches[0]["omitted_candidates"] == 398
    assert len(result["evaluation"]["rows"]) == 20
    assert result["evaluation"]["eligible"] == 18
    assert result["evaluation"]["mse"]["P"] is None
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 262144


def test_legal_domain_and_coprime_denominators_match_exact_oracle_without_long_integer_export():
    # One deterministic arithmetic correctness case, with no timing or memory measurement.
    selected = []
    for candidate in range(10**37 + 1, 10**37 + 100001):
        if all(gcd(candidate, prior) == 1 for prior in selected):
            selected.append(candidate)
            if len(selected) == 158:
                break
    assert len(selected) == 158
    def prices(numbers):
        result = []
        for integer in [1, 10**38 - 1, *numbers]:
            whole, fraction = divmod(integer, 10**18)
            result.append(f"{whole}.{fraction:018d}")
        return result
    left = source(prices(selected[::2]), "600123.SH")
    right = source(prices(selected[1::2]), "000456.SZ")
    x, y, ex, ey = source_vectors(left, right)
    expected_fit = fit_oracle(x, y)
    expected_evaluation = evaluation_oracle(expected_fit, ex, ey)
    fit = _exact_fit(x, y)
    assert_core(fit, expected_fit)
    assert_core(_exact_evaluate(fit, ex, ey), expected_evaluation)
    result = report(left, right)
    for metric in ("mse", "mae"):
        for key, value in expected_evaluation[metric].items():
            assert result["evaluation"][metric][key] == scalar_oracle(value)
    assert len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) <= 262144


@pytest.mark.parametrize("legacy", [False, True])
def test_synthetic_capture_decoder_store_paths_have_identical_reports(tmp_path, legacy):
    from anatrading.public_market import build_request, build_capture, build_legacy_capture
    from anatrading.store import EvidenceStore
    left, right = pair()
    with EvidenceStore(tmp_path / "audit-store") as store:
        snapshots = []
        for query in (left, right):
            symbol = query["metadata"]["source_code"]
            request = build_request("tencent", symbol, "1d", start=DAYS[0], end=CUTOFF, count=640)
            rows = [[r["label"], *(r["tokens"][k] for k in ("open", "close", "high", "low")),
                     "invalid-volume", {}, "0", "0", "0", "0"] for r in query["rows"]]
            data = {"code": 0, "msg": "", "data": {query["metadata"]["source_symbol"]: {"day": rows}}}
            body = (request["parameters"]["_var"] + "=" + json.dumps(data, separators=(",", ":"))).encode()
            common = dict(status=200, response_url=request["url"], body=body)
            if legacy:
                capture = build_legacy_capture("tencent", request, **common,
                    selected_headers={"content-type": "text/html; charset=UTF-8", "content-encoding": ""},
                    provenance={"capture_mode": "legacy_reconstruction", "header_cardinality": "unrecorded",
                        "transport_evidence": "not_established", "original_manifest_sha256": digest("manifest"),
                        "capture_script_sha256": digest("script")})
            else:
                capture = build_capture("tencent", request, **common,
                    response_headers=[("Content-Type", "text/html; charset=UTF-8")])
            snapshots.append(store.import_bytes(capture, "tencent-daily-capture-v1")["snapshot_id"])
        full = [store.query(sid) for sid in snapshots]
        compact = [store._research_query(sid) for sid in snapshots]
        a, b = report(*full), report(*compact)
        assert a == b and a["status"] == "source_description_complete"
        x, y, ex, ey = source_vectors(left, right)
        assert_public_numbers(a, fit_oracle(x, y), evaluation_oracle(fit_oracle(x, y), ex, ey))
