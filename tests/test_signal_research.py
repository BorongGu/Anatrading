"""Independent matrix and hand arithmetic for causal fixed-parameter estimates."""
from copy import deepcopy
import json
import math

import pytest

from anatrading.signal_research import signal_report
from test_research_series import source_query, source_row


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(len(b)))
             for j in range(len(b[0]))] for i in range(len(a))]


def add(a, b):
    return [[x + y for x, y in zip(ar, br)] for ar, br in zip(a, b)]


def transpose(a):
    return list(map(list, zip(*a)))


def independent_filter(prices):
    f, h = [[1., 1.], [0., 1.]], [[1., 0.]]
    q, r = [[1e-6, 0.], [0., 1e-8]], [[1e-4]]
    x, p = [[math.log(float(prices[0]))], [0.]], [[1e-4, 0.], [0., 1e-4]]
    result = [(x, p, None, None)]
    for price in prices[1:]:
        prediction = matmul(f, x)
        predicted_p = add(matmul(matmul(f, p), transpose(f)), q)
        error = math.log(float(price)) - matmul(h, prediction)[0][0]
        variance = add(matmul(matmul(h, predicted_p), transpose(h)), r)[0][0]
        gain = [[value[0] / variance] for value in matmul(predicted_p, transpose(h))]
        x = add(prediction, [[gain[0][0] * error], [gain[1][0] * error]])
        a = [[1. - gain[0][0], 0.], [-gain[1][0], 1.]]
        p = add(matmul(matmul(a, predicted_p), transpose(a)), matmul(matmul(gain, r), transpose(gain)))
        result.append((x, p, error, variance))
    return result


def test_first_initializes_second_hand_calculation_and_ewma_pre_post():
    rows = signal_report(source_query([1, 2, 8]), lookback=2)["series"]
    a, b, c = rows
    assert a["kalman_level"] == 0 and a["kalman_slope"] == 0
    assert a["variance_level"] == a["variance_slope"] == 1e-4
    assert a["innovation"] is None and a["ewma_variance_post"] is None
    assert b["innovation_variance"] == pytest.approx(.000301)
    assert b["kalman_level"] == pytest.approx((.000201 / .000301) * math.log(2))
    assert b["kalman_slope"] == pytest.approx((.0001 / .000301) * math.log(2))
    assert b["ema_log"] == pytest.approx((1 - 2 ** (-1/10)) * math.log(2))
    assert b["ewma_variance_post"] == pytest.approx(math.log(2) ** 2)
    assert b["return_shock"] is None and b["return_shock_reason"] == "no_prior_variance"
    assert c["return_shock"] == pytest.approx(2)
    lam = 2 ** (-1/20)
    assert c["ewma_variance_pre"] == b["ewma_variance_post"]
    assert c["ewma_variance_post"] == pytest.approx(lam * math.log(2)**2 + (1-lam)*math.log(4)**2)


def test_independent_matrix_reference_covariance_psd_and_constant():
    prices = [10 + i / 10 + math.sin(i) for i in range(100)]
    prices = [f"{p:.8f}" for p in prices]
    actual = signal_report(source_query(prices))["series"]
    for row, (x, p, error, variance) in zip(actual, independent_filter(prices)):
        assert row["kalman_level"] == pytest.approx(x[0][0], rel=1e-12)
        assert row["kalman_slope"] == pytest.approx(x[1][0], abs=1e-14)
        assert row["variance_level"] == pytest.approx(p[0][0], rel=1e-12)
        assert row["covariance_level_slope"] == pytest.approx(p[0][1], rel=1e-12)
        assert row["variance_slope"] == pytest.approx(p[1][1], rel=1e-12)
        assert row["variance_level"] * row["variance_slope"] >= row["covariance_level_slope"] ** 2
        assert row["innovation"] == pytest.approx(error) if error is not None else row["innovation"] is None
        assert row["innovation_variance"] == pytest.approx(variance) if variance else row["innovation_variance"] is None
    flat = signal_report(source_query([10] * 30))["series"]
    assert all(row["kalman_slope"] == 0 for row in flat)
    assert flat[2]["return_shock"] is None and flat[2]["return_shock_reason"] == "zero_scale"
    assert flat[2]["ewma_variance_post"] == 0
    assert all(row["warmup"] for row in flat[:20]) and flat[20]["warmup"] is False


def test_all_prefixes_and_future_perturbation_preserve_every_past_signal():
    prices = [10 + i for i in range(30)]
    query = source_query(prices)
    full = signal_report(query, lookback=2)["series"]
    for n in range(1, len(prices) + 1):
        assert signal_report(source_query(prices[:n]), lookback=2)["series"] == full[:n]
    changed = deepcopy(query)
    for row in changed["rows"][15:]:
        row["values"] = dict.fromkeys(("open", "high", "low", "close"), "9999")
    assert signal_report(changed, lookback=2)["series"][:15] == full[:15]


def test_bad_slot_restarts_all_models_without_calendar_gap_inference():
    query = source_query([10, 11, 0, 30, 31, 32])
    query["rows"][4]["label"] = "2026-03-04"
    query["rows"][5]["label"] = "2026-05-06"
    actual = signal_report(query)["series"]
    assert actual[2]["status"] == "invalid" and actual[2]["reason"] == "invalid_price"
    assert actual[3]["segment_id"] == 2 and actual[3]["reset_reason"] == "invalid_price"
    assert actual[3]["innovation"] is None and actual[3]["log_return"] is None
    assert actual[3]["ema_log"] == actual[3]["kalman_level"] == math.log(30)
    assert actual[5]["segment_observations"] == 3 and actual[5]["reset_reason"] is None
    independent = signal_report(source_query([30, 31, 32]))["series"]
    for a, b in zip(actual[3:], independent):
        for field in ("kalman_level", "kalman_slope", "ema_log", "ewma_variance_post", "return_shock"):
            assert a[field] == b[field]


def test_duplicate_and_unlocated_qualification():
    query = source_query([10, 11, 12])
    query["rows"].append(source_row(1, "11", ordinal=4))
    query["unlocated"] = [source_row(5, label=None)]
    result = signal_report(query)
    assert result["series"][1]["reason"] == "duplicate_date"
    assert result["series"][2]["reset_reason"] == "duplicate_date"
    assert result["qualification"] == "source_coverage_unknown"
    assert result["coverage"]["coverage_known"] is False
    json.dumps(result, allow_nan=False)


def test_scaled_prices_preserve_slope_return_and_shock():
    a = signal_report(source_query([10, 11, 9, 12, 13]))["series"]
    b = signal_report(source_query([100, 110, 90, 120, 130]))["series"]
    for x, y in zip(a, b):
        assert y["kalman_level"] - x["kalman_level"] == pytest.approx(math.log(10))
        for field in ("kalman_slope", "log_return", "return_shock", "model_deviation"):
            assert x[field] == pytest.approx(y[field]) if x[field] is not None else y[field] is None


@pytest.mark.parametrize("kwargs,code", [(dict(lookback=True), "invalid_lookback"),
    (dict(lookback=1), "invalid_lookback"), (dict(lookback=253), "invalid_lookback"),
    (dict(horizon=True), "invalid_horizon"), (dict(horizon=2), "invalid_horizon"),
    (dict(horizon="5"), "invalid_horizon"), (dict(test_start="20260101"), "invalid_test_start")])
def test_invalid_parameters(kwargs, code):
    with pytest.raises(ValueError, match=code):
        signal_report(source_query([10]), **kwargs)


def test_large_valid_price_jump_enters_raw_risk_and_models_are_not_clipped():
    rows = signal_report(source_query([10, 10, 1000, 1000]))["series"]
    assert rows[2]["log_return"] == pytest.approx(math.log(100))
    assert rows[2]["return_shock_reason"] == "zero_scale"
    assert rows[2]["ewma_variance_post"] > 0
    assert rows[2]["kalman_price"] > 10 and rows[2]["status"] == "warming_up"
    assert rows[3]["return_shock"] == 0


def test_numerical_failure_stops_chain_and_next_valid_value_reinitializes(monkeypatch):
    import anatrading.signal_research as module
    original = module._update
    calls = 0

    def fail_once(*args):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ArithmeticError("numerical_failure")
        return original(*args)

    monkeypatch.setattr(module, "_update", fail_once)
    rows = signal_report(source_query([10, 11, 12, 13]))["series"]
    assert rows[1]["reason"] == "numerical_failure"
    assert rows[1]["kalman_level"] is None and rows[1]["status"] == "invalid"
    assert rows[2]["reset_reason"] == "numerical_failure" and rows[2]["segment_id"] == 2
    assert rows[2]["kalman_level"] == math.log(12) and rows[2]["innovation"] is None
    assert rows[3]["segment_observations"] == 2


def test_price_display_overflow_does_not_destroy_log_estimate():
    from anatrading.signal_research import _price_scale
    assert _price_scale(1000) == (None, "price_scale_out_of_range")
    assert _price_scale(-1000) == (None, "price_scale_out_of_range")
    assert _price_scale(0) == (1., None)


def test_empty_single_report_and_decimal_context_have_stable_parameters():
    from decimal import localcontext
    from anatrading.signal_research import fixed_parameters
    empty = signal_report(source_query([]))
    assert empty["series"] == [] and empty["events"]["rows"] == []
    assert empty["events"]["evaluation_as_of"] is None
    params = fixed_parameters()
    assert params["kalman_r"] == 1e-4 and params["kalman_q_level"] == 1e-6
    assert params["kalman_q_slope"] == 1e-8 and params["warmup_observations"] == 20
    params["kalman_r"] = 99
    assert fixed_parameters()["kalman_r"] == 1e-4
    query = source_query(["10.123456789123456789", "10.223456789123456789", "10.323456789123456789"])
    normal = signal_report(query, lookback=2, horizon=1)
    with localcontext() as context:
        context.prec = 3
        assert signal_report(query, lookback=2, horizon=1) == normal
