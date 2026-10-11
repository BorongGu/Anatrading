"""One frozen source-change mapping, one fixed subsequent block, no forecasts.

Inputs are complete, unmodified retrospective Store queries. Source qualification
is inherited from the reviewed peer helpers; this module does no I/O and certifies
neither economic returns nor a stable relationship. See research 036 and its plan.
"""
from decimal import (
    Decimal, Context, localcontext, ROUND_HALF_EVEN, InvalidOperation,
    DivisionByZero, Overflow, Underflow, Subnormal, Clamped, FloatOperation,
    Rounded, Inexact,
)
from fractions import Fraction
import hashlib
from heapq import nsmallest
import json

from .peer_relative_research import (
    _source, _position, _endpoint, _row_conflict, _checks, _KNOWN_CHECKS,
)
from .research_series import strict_date


METHOD_ID = "pair-fixed-source-change-audit-v1"
RULE_VERSION = "pair-fixed-source-change-eligibility-v1"
FIT_INTERVALS = 60
EVALUATION_INTERVALS = 20
MAX_SOURCE_ROWS = 20_000
MAX_REPORT_BYTES = 262_144
MAX_EXACT_BITS = 110_000
_LOSSES = ("P", "M", "U", "delta_PM", "delta_PU")
_NUMBERS = ("x", "y", "P", "M", "U", "eP", "eM", "eU", "squared_delta_PM",
            "squared_delta_PU", "absolute_delta_PM", "absolute_delta_PU")
_REASONS = (
    "position_integrity_unknown", "anchor_missing", "anchor_invalid", "history_insufficient",
    "local_source_conflict", "unclassified_source_failure", "duplicate_endpoint",
    "unlocated_endpoint", "missing_endpoint", "endpoint_price_check_failed", "missing_ohlc",
    "invalid_price", "invalid_ohlc", "constant_training_x", "evaluation_incomplete",
)


def _ordered(reasons):
    return [reason for reason in _REASONS if reason in reasons]


def _bounded(value):
    """The fixed Decimal(38,18), 60/20 proof bounds reduced exact scalars."""
    if value is not None and (value.numerator.bit_length() > MAX_EXACT_BITS
                              or value.denominator.bit_length() > MAX_EXACT_BITS):
        raise ArithmeticError("exact_size_invariant")
    return value


def _scalar(value):
    if value is None:
        return None
    _bounded(value)
    if not value:
        return dict(display="0", sign=0)
    traps = {signal: True for signal in (InvalidOperation, DivisionByZero, Overflow,
             Underflow, Subnormal, Clamped, FloatOperation)}
    traps.update({Rounded: False, Inexact: False})
    context = Context(prec=12, rounding=ROUND_HALF_EVEN, Emin=-40000, Emax=40000,
                      capitals=0, clamp=0, flags=[], traps=traps)
    with localcontext(context):
        number = Decimal(value.numerator) / Decimal(value.denominator)
        display = format(number, ".11e")
    if len(display) > 21 or number.is_zero():
        raise ArithmeticError("display_invariant")
    return dict(display=display, sign=1 if value > 0 else -1)


def _exact_fit(x, y):
    """Actual production kernel; independent tests inspect these Fractions."""
    if len(x) != FIT_INTERVALS or len(y) != FIT_INTERVALS:
        raise ValueError("invalid_fit_size")
    mx, my = sum(x, Fraction()) / FIT_INTERVALS, sum(y, Fraction()) / FIT_INTERVALS
    xx = sum(((a - mx) ** 2 for a in x), Fraction())
    xy = sum(((a - mx) * (b - my) for a, b in zip(x, y)), Fraction())
    beta = xy / xx if xx else None
    alpha = my - beta * mx if beta is not None else None
    return {name: _bounded(value) for name, value in
            dict(mx=mx, my=my, Sxx=xx, alpha=alpha, beta=beta).items()}


def _exact_evaluate(fit, x, y):
    """Keep missing positions, and aggregate only one complete 20-interval block."""
    if len(x) != len(y) or len(x) > EVALUATION_INTERVALS:
        raise ValueError("invalid_evaluation_size")
    rows = []
    for a, b in zip(x, y):
        row = dict.fromkeys(_NUMBERS)
        if a is not None and b is not None:
            row.update(x=a, y=b)
            if fit is not None:
                p = (fit["my"] + fit["beta"] * (a - fit["mx"])
                     if fit["beta"] is not None else None)
                m, u = fit["my"], a
                ep, em, eu = None if p is None else b - p, b - m, b - u
                row.update(P=p, M=m, U=u, eP=ep, eM=em, eU=eu)
                if ep is not None:
                    row.update(squared_delta_PM=ep**2 - em**2, squared_delta_PU=ep**2 - eu**2,
                               absolute_delta_PM=abs(ep) - abs(em), absolute_delta_PU=abs(ep) - abs(eu))
        rows.append({name: _bounded(value) for name, value in row.items()})
    result = dict(rows=rows)
    for name, loss in (("mse", lambda e: e * e), ("mae", abs)):
        summary = dict.fromkeys(_LOSSES)
        if len(rows) == EVALUATION_INTERVALS:
            for model in ("P", "M", "U"):
                errors = [row["e" + model] for row in rows]
                if all(error is not None for error in errors):
                    summary[model] = sum((loss(error) for error in errors), Fraction()) / EVALUATION_INTERVALS
            if summary["P"] is not None:
                summary["delta_PM"] = summary["P"] - summary["M"]
                summary["delta_PU"] = summary["P"] - summary["U"]
        result[name] = {key: _bounded(value) for key, value in summary.items()}
    return result


def _group(query):
    grouped, unknown = {}, 0
    for rows in (query["rows"], query["unlocated"]):
        for row in rows:
            day, located = _position(row)
            if day is None:
                unknown += 1
            else:
                grouped.setdefault(day, []).append((row, located))
    return grouped, unknown


def _selected_endpoint(day, candidates, identity):
    result, price = _endpoint(day, candidates)
    reasons, source_failures = set(result["reasons"]), set()
    for row, _ in candidates:
        failed = _checks(row["checks"])
        source_failures.update(failed & _KNOWN_CHECKS)
        if _row_conflict(row, failed, identity):
            reasons.add("local_source_conflict")
        if failed - _KNOWN_CHECKS:
            reasons.add("unclassified_source_failure")
    result.update(candidate_count=len(candidates),
                  candidate_ordinals=nsmallest(3, (row["ordinal"] for row, _ in candidates)),
                  omitted_candidates=max(0, len(candidates) - 3),
                  reasons=_ordered(reasons), source_failures=sorted(source_failures))
    return result, None if reasons else Fraction(price)


def _range(values):
    if not values or any(value is None for value in values):
        return dict(min=None, max=None, constant=None)
    low, high = min(values), max(values)
    return dict(min=_scalar(low), max=_scalar(high), constant=low == high)


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def pair_fixed_change_report(left_query, right_query, *, fit_end, evaluation_cutoff):
    """Describe a fixed mapping's subsequent error, without refitting or I/O.

    Known global source failures raise the existing helper's ValueError. Local
    failures preserve their union-grid positions and never shrink denominators.
    """
    fit_end = strict_date(fit_end, "invalid_dates")
    evaluation_cutoff = strict_date(evaluation_cutoff, "invalid_dates")
    if fit_end >= evaluation_cutoff:
        raise ValueError("invalid_dates")
    queries = (left_query, right_query)
    for query in queries:
        if type(query) is not dict or any(type(query.get(key)) not in (list, tuple)
                                          for key in ("rows", "unlocated")):
            raise ValueError("invalid_query")
        if len(query["rows"]) + len(query["unlocated"]) > MAX_SOURCE_ROWS:
            raise ValueError("research_row_limit")
    identities = [_source(query) for query in queries]
    if identities[0]["symbol"] == identities[1]["symbol"]:
        raise ValueError("research_duplicate_symbol")
    if left_query["snapshot_id"] == right_query["snapshot_id"]:
        raise ValueError("research_duplicate_snapshot")
    grouped = [_group(query) for query in queries]
    days = sorted(set(grouped[0][0]) | set(grouped[1][0]))
    unknown = any(item[1] for item in grouped)
    parameters = dict(fit_end=fit_end, evaluation_cutoff=evaluation_cutoff,
                      fit_intervals=FIT_INTERVALS, evaluation_intervals=EVALUATION_INTERVALS,
                      transform="simple_source_relative_change", Y="left", X="right",
                      primary_loss="mse", sensitivity_loss="mae", display_digits=12,
                      rounding="ROUND_HALF_EVEN", information_timing="contemporaneous_source_endpoints",
                      mode="retrospective", units=dict(change="source_relative_change",
                          mse="source_relative_change_squared", beta="source_change_beta"))
    sources = []
    for role, query, identity, (groups, count) in zip(("left", "right"), queries, identities, grouped):
        sources.append(dict(role=role, symbol=identity["symbol"], snapshot_id=query["snapshot_id"],
            batch_id=query["batch_id"], query_id=query["query_id"],
            qualification=query["manifest"]["qualification"],
            capture_version=query["manifest"]["contract"]["capture_version"],
            row_count=len(query["rows"]) + len(query["unlocated"]),
            source_start=min(groups) if groups else None, source_end=max(groups) if groups else None,
            unlocated_rows=len(query["unlocated"]), unknown_positions=count))
    identity = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, parameters=parameters,
                    sources=[{key: source[key] for key in ("role", "symbol", "snapshot_id", "query_id")}
                             for source in sources])
    result = dict(method_id=METHOD_ID, rule_version=RULE_VERSION,
        analysis_id=hashlib.sha256(_json(identity).encode()).hexdigest(), parameters=parameters,
        sources=sources, status="unavailable", reasons=[], grid_defined=fit_end in days,
        fit=dict(status="unavailable", planned_intervals=60, observed_intervals=None,
                 start=None, end=None, **dict.fromkeys(("mx", "my", "Sxx", "alpha", "beta")), x_range=_range([])),
        evaluation=dict(status="not_located", planned=20, observed=None, eligible=None,
                        start=None, end=None, mse=dict.fromkeys(_LOSSES), mae=dict.fromkeys(_LOSSES),
                        x_range=_range([]), outside_fit_range_count=None, rows=[]), trace=[],
        limitations=dict(economic_return=False, total_return=False, prediction=False,
            causal_attribution=False, stability_certified=False, historical_availability="unverified",
            calendar="unknown", closure="unknown", corporate_action_coverage="unknown",
            adjustment="request_declared_semantics_unverified", current_selection_retrospective=True))
    reasons = {"position_integrity_unknown"} if unknown else set()
    if not result["grid_defined"]:
        reasons.add("anchor_missing")
        result["reasons"] = _ordered(reasons)
        return _finish(result)
    split = days.index(fit_end)
    fit_days = days[max(0, split - FIT_INTERVALS):split + 1]
    eval_days = [day for day in days[split + 1:]
                 if day <= evaluation_cutoff][:EVALUATION_INTERVALS]
    selected = fit_days + eval_days
    endpoints = {}
    for day in selected:
        sides, prices = {}, []
        for role, (groups, _), identity in zip(("left", "right"), grouped, identities):
            detail, price = _selected_endpoint(day, groups.get(day, []), identity)
            sides[role] = detail
            prices.append(price)
            reasons.update(detail["reasons"])
        result["trace"].append(dict(date=day, **sides))
        endpoints[day] = (sides, prices)
    if any(price is None for price in endpoints[fit_end][1]):
        reasons.add("anchor_invalid")

    def changes(path):
        x, y, failures = [], [], []
        for start, end in zip(path, path[1:]):
            codes = set()
            for day in (start, end):
                for side in endpoints[day][0].values():
                    codes.update(side["reasons"])
            failures.append(_ordered(codes))
            if codes:
                x.append(None); y.append(None)
            else:
                a0, b0 = endpoints[start][1]
                a1, b1 = endpoints[end][1]
                x.append(_bounded(b1 / b0 - 1)); y.append(_bounded(a1 / a0 - 1))
        return x, y, failures

    fx, fy, _ = changes(fit_days)
    ex, ey, eval_failures = changes([fit_end] + eval_days)
    if len(fx) < FIT_INTERVALS:
        reasons.add("history_insufficient")
    fit = None
    if not unknown and len(fx) == FIT_INTERVALS and all(value is not None for value in fx):
        fit = _exact_fit(fx, fy)
        result["fit"].update({key: _scalar(value) for key, value in fit.items()})
        result["fit"].update(status="ready" if fit["Sxx"] else "constant_x", x_range=_range(fx))
        if not fit["Sxx"]:
            reasons.add("constant_training_x")
    result["fit"].update(observed_intervals=len(fx), start=fit_days[0], end=fit_end)
    evaluation = _exact_evaluate(fit, ex, ey)
    eligible = sum(value is not None for value in ex)
    if len(ex) < EVALUATION_INTERVALS:
        reasons.add("evaluation_incomplete")
    eval_status = ("invalid" if unknown or eligible != len(ex) else
                   "pending" if len(ex) < EVALUATION_INTERVALS else "complete")
    result["evaluation"].update(status=eval_status, observed=len(ex), eligible=eligible,
                                 start=fit_end, end=eval_days[-1] if eval_days else fit_end)
    for name in ("mse", "mae"):
        result["evaluation"][name] = {key: _scalar(value) for key, value in evaluation[name].items()}
    if eval_status == "complete":
        result["evaluation"]["x_range"] = _range(ex)
        if fit is not None:
            low, high = min(fx), max(fx)
            result["evaluation"]["outside_fit_range_count"] = sum(value < low or value > high for value in ex)
    for i, (row, codes) in enumerate(zip(evaluation["rows"], eval_failures)):
        result["evaluation"]["rows"].append(dict(index=i + 1, start=fit_end if i == 0 else eval_days[i - 1],
            end=eval_days[i], reasons=codes, **{key: _scalar(value) for key, value in row.items()}))
    if fit is None or eval_status == "invalid":
        result["status"] = "unavailable"
    elif eval_status == "pending":
        result["status"] = "incomplete"
    else:
        result["status"] = "source_description_complete" if fit["Sxx"] else "baseline_only"
    result["reasons"] = _ordered(reasons)
    return _finish(result)


def _finish(result):
    if len(_json(result).encode("utf-8")) > MAX_REPORT_BYTES:
        raise ArithmeticError("report_size_invariant")
    return result
