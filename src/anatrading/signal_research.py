"""Causal daily log-price estimates with frozen engineering parameters.

Filtered estimates condition on a frozen source prefix. They establish neither
historical source availability nor prediction, execution or strategy returns.
"""
from math import exp, isfinite, log, sqrt
from typing import NamedTuple

from .event_study import event_report, validate_event_parameters
from .numeric import decimal_text
from .research_series import daily_bars, daily_coverage, source_rejection


_R = 1e-4
_Q_LEVEL = 1e-6
_Q_SLOPE = 1e-8
_EMA_ALPHA = 1 - 2 ** (-1 / 10)
_EWMA_DECAY = 2 ** (-1 / 20)
_WARMUP = 20
_ESTIMATES = ("kalman_level", "kalman_slope", "kalman_price", "ema_log", "ema_price",
              "innovation", "innovation_variance", "model_deviation", "variance_level",
              "variance_slope", "covariance_level_slope", "log_return", "ewma_variance_pre",
              "ewma_variance_post", "ewma_volatility", "return_shock")


def fixed_parameters():
    """A fresh serializable description, not a public tuning API."""
    return dict(period="1d", kalman_r=_R, kalman_q_level=_Q_LEVEL, kalman_q_slope=_Q_SLOPE,
                kalman_p0_level=_R, kalman_p0_slope=_R, kalman_initial_slope=0,
                ema_half_life=10, ewma_half_life=20, ema_alpha=_EMA_ALPHA,
                ewma_decay=_EWMA_DECAY, warmup_observations=_WARMUP,
                reset_policy="invalid_or_duplicate_date_group", initialization="full_source_prefix")


def _price_scale(value):
    try:
        price = exp(value)
        return (price, None) if isfinite(price) and price > 0 else (None, "price_scale_out_of_range")
    except OverflowError:
        return None, "price_scale_out_of_range"


def _update(level, slope, p00, p01, p11, y):
    predicted_level = level + slope
    a = p00 + 2 * p01 + p11 + _Q_LEVEL
    b, c = p01 + p11, p11 + _Q_SLOPE
    innovation = y - predicted_level
    variance = a + _R
    if not all(map(isfinite, (predicted_level, a, b, c, innovation, variance))) or variance <= 0:
        raise ArithmeticError("numerical_failure")
    k0, k1 = a / variance, b / variance
    level, slope = predicted_level + k0 * innovation, slope + k1 * innovation
    # Joseph form: (I-KH) P_pred (I-KH)' + K R K'. Symmetric
    # off-diagonal stored once, no silent clamp of negative variance.
    p00 = (1-k0)**2 * a + k0*k0*_R
    p01 = (1-k0) * (b-k1*a) + k0*k1*_R
    p11 = c - 2*k1*b + k1*k1*a + k1*k1*_R
    determinant = p00*p11 - p01*p01
    if (not all(map(isfinite, (level, slope, p00, p01, p11, determinant)))
            or p00 < 0 or p11 < 0 or determinant < -1e-12 * max(p00*p11, 1e-30)):
        raise ArithmeticError("numerical_failure")
    return level, slope, p00, p01, p11, innovation, variance


class _Prior(NamedTuple):
    origin_date: str
    origin_ordinal: int
    origin_observations: int
    model_segment_id: int
    mK: float
    mR: float
    mE: float
    S: float
    v_pre: float | None


def _capture_prior(origin_date, origin_ordinal, observations, segment_id,
                   level, slope, p00, p01, p11, ema, previous_y, variance_post):
    """An immutable snapshot made before reading the current observation."""
    return _Prior(origin_date, origin_ordinal, observations, segment_id,
                  level + slope, previous_y, ema,
                  (p00 + 2 * p01 + p11 + _Q_LEVEL) + _R, variance_post)


def _causal_rows(bars, *, capture_prior=False):
    """The legacy scalar recurrence; optional priors never enter its catch."""
    active = False
    segment_id, observations = 0, 0
    origin_date = origin_ordinal = None
    next_reset_reason = "initial_observation"
    level = slope = p00 = p01 = p11 = ema = previous_y = variance_post = None
    for bar in bars:
        # Even a bad current bar cannot change the preceding active state.
        # Capture is outside the legacy numeric catch and is off by default.
        prior = (_capture_prior(origin_date, origin_ordinal, observations, segment_id,
                                level, slope, p00, p01, p11, ema, previous_y, variance_post)
                 if capture_prior and active else None)
        row = dict(date=bar["date"], ordinal=bar["ordinal"],
                   close=decimal_text(bar["close"]) if bar["close"] is not None else None,
                   segment_id=None, segment_observations=0, warmup=False, status="invalid",
                   reason=bar["reason"], reset_reason=None, return_shock_reason=None,
                   kalman_price_reason=None, ema_price_reason=None, **dict.fromkeys(_ESTIMATES))
        if bar["reason"] is not None:
            active = False
            next_reset_reason = bar["reason"]
            yield row, prior
            continue
        try:
            value = float(bar["close"])
            if not isfinite(value) or value <= 0:
                raise ArithmeticError("numerical_failure")
            y = log(value)
            if not active:
                segment_id += 1
                observations = 1
                level, slope, p00, p01, p11, ema = y, 0., _R, 0., _R, y
                variance_post = None
                row.update(reset_reason=next_reset_reason, return_shock_reason="no_return")
                active = True
            else:
                level, slope, p00, p01, p11, innovation, innovation_variance = _update(level, slope, p00, p01, p11, y)
                ema = (1 - _EMA_ALPHA) * ema + _EMA_ALPHA * y
                raw_return = y - previous_y
                variance_pre = variance_post
                shock = None
                if variance_pre is None:
                    shock_reason = "no_prior_variance"
                    variance_post = raw_return * raw_return
                else:
                    if variance_pre > 0:
                        shock = raw_return / sqrt(variance_pre)
                        shock_reason = None if isfinite(shock) else "numerical_failure"
                        if shock_reason:
                            shock = None
                    else:
                        shock_reason = "zero_scale"
                    variance_post = _EWMA_DECAY * variance_pre + (1-_EWMA_DECAY) * raw_return * raw_return
                if not all(map(isfinite, (ema, raw_return, variance_post))) or variance_post < 0:
                    raise ArithmeticError("numerical_failure")
                row.update(innovation=innovation, innovation_variance=innovation_variance,
                           model_deviation=innovation/sqrt(innovation_variance), log_return=raw_return,
                           ewma_variance_pre=variance_pre, ewma_variance_post=variance_post,
                           ewma_volatility=sqrt(variance_post), return_shock=shock, return_shock_reason=shock_reason)
                observations += 1
            previous_y = y
            warmup = observations <= _WARMUP
            row.update(segment_id=segment_id, segment_observations=observations, warmup=warmup,
                       status="warming_up" if warmup else "computed", reason=None,
                       kalman_level=level, kalman_slope=slope, variance_level=p00,
                       variance_slope=p11, covariance_level_slope=p01, ema_log=ema)
            row["kalman_price"], row["kalman_price_reason"] = _price_scale(level)
            row["ema_price"], row["ema_price_reason"] = _price_scale(ema)
        except (ArithmeticError, OverflowError, ValueError):
            active = False
            next_reset_reason = "numerical_failure"
            row.update(**dict.fromkeys(_ESTIMATES), reason="numerical_failure", status="invalid",
                       segment_id=None, segment_observations=0, warmup=False)
        if capture_prior and row["reason"] is None:
            origin_date, origin_ordinal = bar["date"], bar["ordinal"]
        yield row, prior


def _causal_series(bars):
    return [row for row, _ in _causal_rows(bars)]


def signal_report(query, lookback=20, horizon=5, test_start=None):
    """Compact full-prefix result; API supplies the identity and access envelope."""
    validate_event_parameters(lookback, horizon, test_start)
    bars = daily_bars(query)
    coverage = daily_coverage(query, bars)
    evaluation_as_of = (query.get("selection") or {}).get("cutoff")
    events = event_report(bars, lookback, horizon, test_start, evaluation_as_of)
    series = _causal_series(bars)
    for row, signal in zip(series, events.pop("signals")):
        row.update(prior_high=signal["prior_high"], breakout=signal["breakout"], breakout_reason=signal["reason"])
    return dict(series=series, events=events, coverage=coverage,
                parameters=dict(**fixed_parameters(), lookback=lookback, horizon=horizon, test_start=test_start),
                numeric_kind="estimate_float64", source_numeric_kind="exact_decimal_text",
                qualification=("source_rejected" if source_rejection(query) else
                               "conditional_source_observations" if coverage["coverage_known"] else "source_coverage_unknown"),
                units=dict(level="log_price", slope="log_price_per_source_observation",
                           volatility="log_return_per_source_observation", price_change="simple_source_close_change"),
                limitations=["retrospective_source_version", "calendar_and_coverage_unverified",
                             "adjustment_and_corporate_actions_unverified", "historical_availability_unverified",
                             "fixed_engineering_parameters_not_calibrated", "no_prediction_or_trading_return_claim"])
