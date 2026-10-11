"""Strictly prior, paired one-step errors of fixed daily source-price models.

The empirical absolute-error quantile has no future coverage guarantee. Results
describe frozen source observations, not latent trends, PIT data or returns.
The caller supplies a same-cutoff full prefix from the existing verified Store.
"""
from collections import deque
from math import fsum, isfinite, log, sqrt
import re

from . import signal_research as signal
from .models import VALUE_FIELDS
from .pair_research import symbol_identity
from .research_series import MAX_RESEARCH_ROWS, daily_bars, daily_coverage, source_rejection, strict_date
from .store import _identity


_METHOD = "daily-one-step-source-diagnostic-v1"
_MODELS = ("kalman", "last_close", "lagged_ema")
_WINDOW = 60
_RANK = 54
_ORIGIN_MIN = 21
_ID = re.compile(r"[0-9a-f]{64}\Z")
_MODEL_FIELDS = ("prediction_log", "error_log", "abs_error_quantile", "lower_log", "upper_log",
                 "position", "mae_pre", "rmse_pre")
_LIMITATIONS = (
    "retrospective_source_version", "calendar_and_corporate_actions_unverified",
    "adjustment_basis_unverified", "historical_availability_unverified", "bar_closure_unverified",
    "source_identity_not_security_master_verified", "fixed_engineering_parameters_not_calibrated",
    "empirical_quantile_without_coverage_guarantee", "no_prediction_alpha_or_trading_return_claim",
    "one_step_observation_target_not_latent_trend",
    "display_endpoints_rounded_position_uses_residual_domain",
)


def _validate_query(query, cutoff):
    if not isinstance(cutoff, str) or len(cutoff) != 10:
        raise ValueError("invalid_cutoff")
    strict_date(cutoff, "invalid_cutoff")
    required = {"snapshot_id", "batch_id", "query_id", "selection", "manifest", "metadata",
                "rows", "unlocated", "counts", "batch_checks"}
    if not isinstance(query, dict) or not required <= query.keys():
        raise ValueError("invalid_forecast_query")
    if (any(not isinstance(query[key], dict) for key in ("selection", "manifest", "metadata", "counts"))
            or any(not isinstance(query[key], (list, tuple)) for key in ("rows", "unlocated", "batch_checks"))):
        raise ValueError("invalid_forecast_query")
    if len(query["rows"]) + len(query["unlocated"]) > MAX_RESEARCH_ROWS:
        raise ValueError("research_row_limit")
    selection, manifest = query["selection"], query["manifest"]
    if selection.get("cutoff") != cutoff:
        raise ValueError("research_cutoff_mismatch")
    if selection.get("ordinal_start") is not None or selection.get("ordinal_end") is not None:
        raise ValueError("ordinal_window_not_supported")
    if (selection.get("mode") != "retrospective" or selection.get("fields") != list(VALUE_FIELDS)
            or "versions" not in manifest or selection.get("versions") != manifest["versions"]
            or not {"ordinal_start", "ordinal_end"} <= selection.keys()):
        raise ValueError("invalid_forecast_selection")
    ids = [query[key] for key in ("snapshot_id", "batch_id", "query_id")]
    ids += [manifest.get(key) for key in ("raw_sha256", "source_contract_id")]
    count = query["counts"].get("batch_unlocated_rows")
    if (any(not isinstance(value, str) or _ID.fullmatch(value) is None for value in ids)
            or selection.get("snapshot_id") != query["snapshot_id"]
            or type(count) is not int or count < 0
            or "read_projection" in query and query["read_projection"] != "daily_ohlc_input_v1"):
        raise ValueError("invalid_forecast_query")
    if query["query_id"] != _identity(selection):
        raise ValueError("invalid_forecast_query")
    if query["metadata"].get("period") != "1d":
        raise ValueError("unsupported_period")
    return symbol_identity(query)


def _mean_nonnegative(terms):
    """Report arithmetic failure without turning a positive mean into zero."""
    try:
        total = fsum(terms)
    except OverflowError:
        return None, "numerical_failure"
    if not isfinite(total):
        return None, "numerical_failure"
    if total < 0:
        raise RuntimeError("forecast_internal_invariant")
    mean = total / _WINDOW
    if total > 0 and mean == 0:
        return None, "numerical_underflow"
    return (mean, None) if isfinite(mean) else (None, "numerical_failure")


def _losses(errors):
    """Fixed-window loss arithmetic; defensive extremes are not source prices."""
    if len(errors) != _WINDOW or not all(map(isfinite, errors)):
        raise RuntimeError("forecast_internal_invariant")
    reasons = {}
    mae, reason = _mean_nonnegative(abs(error) for error in errors)
    if reason:
        reasons["mae_pre"] = reason
    squares = []
    rmse = None
    for error in errors:
        square = error * error
        if not isfinite(square):
            reasons["rmse_pre"] = "numerical_failure"
            break
        if error != 0 and square == 0:
            reasons["rmse_pre"] = "numerical_underflow"
            break
        squares.append(square)
    else:
        mean, reason = _mean_nonnegative(squares)
        if reason:
            reasons["rmse_pre"] = reason
        else:
            rmse = sqrt(mean)
            if not isfinite(rmse):
                rmse, reasons["rmse_pre"] = None, "numerical_failure"
    return mae, rmse, reasons


def _window_summary(evidence):
    """Freeze only a requested pre-observation window, never the current error."""
    if len(evidence) > _WINDOW:
        raise RuntimeError("forecast_internal_invariant")
    evidence = [dict(item) for item in evidence]
    first, last = (evidence[0], evidence[-1]) if evidence else (None, None)
    window = dict(expected_count=_WINDOW, actual_count=len(evidence),
                  start_date=first["observation_date"] if first else None,
                  end_date=last["observation_date"] if last else None,
                  origin_start_date=first["origin_date"] if first else None,
                  origin_end_date=last["origin_date"] if last else None,
                  window_unit="source_observation_intervals")
    models = []
    for model in _MODELS:
        if len(evidence) == _WINDOW:
            errors = [item[f"{model}_error_log"] for item in evidence]
            mae, rmse, reasons = _losses(errors)
            quantile = sorted(abs(error) for error in errors)[_RANK - 1]
            if not isfinite(quantile) or quantile < 0:
                raise RuntimeError("forecast_internal_invariant")
        else:
            quantile = mae = rmse = None
            reasons = dict.fromkeys(("abs_error_quantile", "mae_pre", "rmse_pre"),
                                    "calibration_history_insufficient")
        models.append(dict(model_id=model, abs_error_quantile=quantile,
                           mae_pre=mae, rmse_pre=rmse, field_reasons=reasons))
    return dict(window=window, evidence=evidence, models=models)


def _position(error, quantile):
    if not isfinite(error) or not isfinite(quantile) or quantile < 0:
        raise RuntimeError("forecast_internal_invariant")
    return "below" if error < -quantile else "above" if error > quantile else "inside"


def _model_result(summary, prediction, error):
    result = dict(summary, prediction_log=prediction, error_log=error,
                  lower_log=None, upper_log=None, position=None,
                  field_reasons=dict(summary["field_reasons"]))
    quantile = summary["abs_error_quantile"]
    if quantile is None:
        result["field_reasons"].update(dict.fromkeys(("lower_log", "upper_log", "position"),
                                                    "calibration_history_insufficient"))
    else:
        result["position"] = _position(error, quantile)
        for field, value in (("lower_log", prediction - quantile), ("upper_log", prediction + quantile)):
            if isfinite(value):
                result[field] = value
            else:
                result["field_reasons"][field] = "price_range_numerical_failure"
    return result


def _comparisons(models):
    comparisons = {}
    for loss in ("mae_pre", "rmse_pre"):
        result = dict(K_minus_R=None, K_minus_E=None, field_reasons={})
        for key, baseline in (("K_minus_R", models[1]), ("K_minus_E", models[2])):
            kalman = models[0]
            reason = kalman["field_reasons"].get(loss) or baseline["field_reasons"].get(loss)
            if reason:
                result["field_reasons"][key] = reason
            else:
                delta = kalman[loss] - baseline[loss]
                if isfinite(delta):
                    result[key] = delta
                else:
                    result["field_reasons"][key] = "numerical_failure"
        comparisons[loss] = result
    return comparisons


def _unavailable(reasons):
    return dict(calculation_status="unavailable", reasons=sorted(set(reasons)),
                current=None, window=None, models=None, prior_scales=None, comparisons=None,
                evidence=[], cohort_counts=None, diagnostic_block=None)


class _DiagnosticCollector:
    """Only the last 60 common errors and constant-size current state are held."""
    __slots__ = ("ring", "counts", "prefix_start", "segment_start", "previous_close", "previous_float",
                 "previous_log", "block", "row", "prior", "errors", "reason", "status")

    def __init__(self, prefix_start):
        self.ring = deque(maxlen=_WINDOW)
        self.counts = dict(total_groups=0, forecast_origin_warmup=0, common_errors=0,
                           source_or_state_unavailable=0, pre_window_insufficient=0, pre_window_complete=0)
        self.prefix_start = prefix_start
        self.segment_start = self.previous_close = self.previous_float = self.previous_log = None
        self.block = self.row = self.prior = self.errors = self.reason = self.status = None

    def freeze(self):
        return _window_summary(self.ring)

    def observe(self, bar, row, prior):
        self.row, self.prior, self.errors = row, prior, None
        self.counts["total_groups"] += 1
        self.reason = row["reason"]
        if self.reason is not None:
            self.ring.clear()
            self.block = self.segment_start = self.previous_close = self.previous_float = self.previous_log = None
            self.status = "unavailable"
            self.counts["source_or_state_unavailable"] += 1
            return
        if row["segment_observations"] == 1:
            self.segment_start = bar["date"]
        value = float(bar["close"])
        y = log(value)
        if (self.block is None and self.previous_close is not None and bar["close"] != self.previous_close
                and (value == self.previous_float or y == self.previous_log)):
            self.block = dict(date=bar["date"], ordinal=bar["ordinal"], reason="precision_loss_state_dependency")
            self.ring.clear()
        self.previous_close, self.previous_float, self.previous_log = bar["close"], value, y
        if self.block is not None:
            self.reason, self.status = self.block["reason"], "unavailable"
            self.counts["source_or_state_unavailable"] += 1
            return
        if prior is None or prior.origin_observations < _ORIGIN_MIN:
            self.reason, self.status = "forecast_origin_warmup", "warming_up"
            self.counts["forecast_origin_warmup"] += 1
            return
        self.errors = (y - prior.mK, y - prior.mR, y - prior.mE)
        if not all(map(isfinite, self.errors)):
            raise RuntimeError("forecast_internal_invariant")
        complete = len(self.ring) == _WINDOW
        self.status = "computed" if complete else "history_insufficient"
        self.reason = None if complete else "calibration_history_insufficient"
        self.counts["common_errors"] += 1
        self.counts["pre_window_complete" if complete else "pre_window_insufficient"] += 1
        self.ring.append(dict(origin_date=prior.origin_date, origin_ordinal=prior.origin_ordinal,
                              observation_date=bar["date"], observation_ordinal=bar["ordinal"],
                              segment_id=prior.model_segment_id, origin_observations=prior.origin_observations,
                              kalman_error_log=self.errors[0], last_close_error_log=self.errors[1],
                              lagged_ema_error_log=self.errors[2]))

    def result(self, summary):
        row = self.row
        result = _unavailable([self.reason] if self.reason else [])
        result.update(calculation_status=self.status, cohort_counts=dict(self.counts),
                      diagnostic_block=dict(self.block) if self.block else None,
                      current=dict(requested_date=row["date"], date=row["date"], ordinal=row["ordinal"],
                                   close=row["close"], segment_id=row["segment_id"],
                                   segment_observations=row["segment_observations"],
                                   source_prefix_start=self.prefix_start, state_segment_start=self.segment_start))
        if self.status == "unavailable":
            return result
        if self.status == "warming_up":
            models = [dict(model_id=model, **dict.fromkeys(_MODEL_FIELDS),
                           field_reasons=dict.fromkeys(_MODEL_FIELDS, self.reason)) for model in _MODELS]
        else:
            predictions = (self.prior.mK, self.prior.mR, self.prior.mE)
            models = [_model_result(model, prediction, error)
                      for model, prediction, error in zip(summary["models"], predictions, self.errors)]
            result["prior_scales"] = dict(model_innovation_variance_pre=self.prior.S,
                                           rw_ewma_variance_pre=self.prior.v_pre,
                                           origin_date=self.prior.origin_date,
                                           origin_ordinal=self.prior.origin_ordinal,
                                           origin_observations=self.prior.origin_observations)
        result.update(models=models, comparisons=_comparisons(models),
                      window=summary["window"], evidence=summary["evidence"])
        return result


def forecast_diagnostic_report(query, *, cutoff):
    """A single-cutoff pure report; no I/O, event study, model fit or UI policy."""
    identity = _validate_query(query, cutoff)
    parameters = dict(cutoff=cutoff, base_model=signal.fixed_parameters(), window=_WINDOW,
                      absolute_error_quantile=0.9, order_rank=_RANK,
                      quantile_method="nearest-rank-no-interpolation", forecast_origin_min_observations=_ORIGIN_MIN,
                      policies=dict(source_window="daily-source-date-groups-v1",
                                    predictor="pre-update-private-prior-v1",
                                    calibration="common-lagged-errors-60-v1",
                                    comparison="binary64-residual-domain-v1",
                                    precision="collision-blocks-existing-segment-v1"))
    source = dict(batch_id=query["batch_id"], raw_sha256=query["manifest"]["raw_sha256"],
                  source_contract_id=query["manifest"]["source_contract_id"], identity=identity, period="1d")
    report = dict(method_id=_METHOD, inputs=[dict(snapshot_id=query["snapshot_id"], query_id=query["query_id"])],
                  parameters=parameters, source=source)
    report["analysis_id"] = _identity(report)
    report.update(mode="retrospective", source_qualification="conditional_frozen_source_observations",
                  historical_availability="unverified", limitations=list(_LIMITATIONS),
                  units=dict(log_coordinate="ln_source_price_numeric_value", error_and_loss="natural_log_ratio",
                             variance="natural_log_ratio_squared"))
    bars = daily_bars(query)
    coverage = daily_coverage(query, bars)
    reasons = []
    rejected = source_rejection(query)
    if rejected:
        reasons.append(rejected)
    if not coverage["coverage_known"]:
        reasons.append("date_set_integrity_unknown")
    if not bars or bars[-1]["date"] != cutoff:
        reasons.append("cutoff_missing")
    if reasons:
        result = _unavailable(reasons)
    else:
        collector = _DiagnosticCollector(bars[0]["date"])
        iterator = signal._causal_rows(bars, capture_prior=True)
        for bar in bars:
            # This must precede next(): yielding the old row already absorbs y.
            if bar["date"] == cutoff:
                summary = collector.freeze()
            row, prior = next(iterator)
            collector.observe(bar, row, prior)
        result = collector.result(summary)
    result["coverage"] = coverage
    report["result"] = result
    return report
