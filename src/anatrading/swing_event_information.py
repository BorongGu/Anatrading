"""Fixed breakout events joined once to exact, lagged source-path context.

This pure, single-source report accepts trusted Store queries. It describes
frozen source prices, not historical availability, executions or trade returns.
"""
from calendar import monthrange
from datetime import date, timedelta
from fractions import Fraction
from math import isfinite

from .event_study import _summary, event_report
from .numeric import decimal_text
from .pair_research import symbol_identity
from .research_series import (MAX_RESEARCH_ROWS, daily_bars, daily_coverage,
                              source_rejection, strict_date)
from .store import _identity


_METHOD = "source-breakout-lagged-er-v1"
_PROTOCOL = "035-er-half-lag1-v1"
_EVALUATIONS = ("valid", "immature", "invalid", "purged", "overlap_excluded")
_QUALIFICATIONS = ("admitted", "source_unavailable", "internal_failure")


def _request(query, report_start, test_start, cutoff):
    # Store already verifies raw bytes. These are safety/identity references,
    # not a second generic query-schema or source-authentication layer.
    if not isinstance(query, dict) or any(
        not isinstance(query.get(key), dict) for key in ("selection", "metadata", "manifest")
    ) or any(not isinstance(query.get(key), (list, tuple)) for key in ("rows", "unlocated")):
        raise ValueError("invalid_swing_query")
    selection, manifest = query["selection"], query["manifest"]
    references = [query.get(key) for key in ("snapshot_id", "batch_id", "query_id")]
    references += [manifest.get(key) for key in ("raw_sha256", "source_contract_id")]
    if any(not isinstance(value, str) or not value for value in references) or selection.get("mode") != "retrospective":
        raise ValueError("invalid_swing_query")
    if len(query["rows"]) + len(query["unlocated"]) > MAX_RESEARCH_ROWS:
        raise ValueError("research_row_limit")
    for value in (report_start, test_start, cutoff):
        strict_date(value, "invalid_swing_dates")
    first, last = date.fromisoformat(report_start), date.fromisoformat(cutoff)
    quarters = (last.year - first.year) * 4 + (last.month - 1) // 3 - (first.month - 1) // 3 + 1
    if not report_start < test_start <= cutoff or quarters > 9:
        raise ValueError("invalid_swing_dates")
    if selection.get("cutoff") != cutoff:
        raise ValueError("research_cutoff_mismatch")
    if any(selection.get(key) is not None for key in ("ordinal_start", "ordinal_end")):
        raise ValueError("ordinal_window_not_supported")
    if query["metadata"].get("period") != "1d":
        raise ValueError("unsupported_period")
    return symbol_identity(query)


def _fraction(value, *, estimate=False):
    result = dict(numerator=str(value.numerator), denominator=str(value.denominator))
    if estimate:
        result["estimate"] = float(value)
    return result


def _ratio(numerator, denominator):
    return _fraction(Fraction(numerator, denominator), estimate=True) if denominator else None


class _ConnectionError(ArithmeticError):
    """An impossible join/sign within the declared, normalized price domain."""


def _connect(event, signals, bars):
    index = event["index"]
    if type(index) is not int or not 20 <= index < len(bars):
        raise _ConnectionError("event_index_mismatch")
    current, signal = bars[index], signals[index]
    if (event["date"] != current["date"] or event["ordinal"] != current["ordinal"]
            or event["start_close"] != decimal_text(current["close"])
            or signal["date"] != current["date"] or signal["ordinal"] != current["ordinal"]
            or signal["breakout"] is not True or signal["prior_high"] is None):
        raise _ConnectionError("event_source_join_mismatch")
    # A valid B already certifies its preceding twenty slots. The connection
    # uses only eleven of them, never current/future prices, for ten changes.
    window = bars[index - 11:index]
    if any(bar["reason"] is not None or bar["close"] is None for bar in window):
        raise _ConnectionError("event_background_mismatch")
    values = [Fraction(bar["close"]) for bar in window]
    net = values[-1] - values[0]
    path = sum((abs(b - a) for a, b in zip(values, values[1:])), Fraction(0))
    background = dict(start_date=window[0]["date"], end_date=window[-1]["date"],
                      start_index=index - 11, end_index=index - 1,
                      start_ordinal=window[0]["ordinal"], end_ordinal=window[-1]["ordinal"],
                      net=_fraction(net), path=_fraction(path),
                      er=_fraction(abs(net) / path if path else Fraction(0)),
                      direction_up=net > 0, efficient=path > 0 and 2 * abs(net) >= path,
                      reason=None if path else "zero_path_convention")
    label_sign = None
    if event["label_status"] == "valid":
        end = index + 5
        if (end >= len(bars) or event["label_end"] != bars[end]["date"]
                or event["end_close"] != decimal_text(bars[end]["close"])
                or any(bar["reason"] is not None for bar in bars[index:end + 1])):
            raise _ConnectionError("event_label_join_mismatch")
        sign = (bars[end]["close"] > current["close"]) - (bars[end]["close"] < current["close"])
        estimate = event["price_change"]
        # Exact ratio-minus-one in the bounded Decimal source domain cannot
        # under/overflow or lose a nonzero sign. A negative value may round -1.
        if (not isinstance(estimate, (int, float)) or not isfinite(estimate)
                or (estimate > 0) - (estimate < 0) != sign):
            raise _ConnectionError("event_label_sign_mismatch")
        label_sign = {1: "positive", 0: "zero", -1: "negative"}[sign]
    return dict(event, prior_high=signal["prior_high"], background=background,
                label_sign=label_sign, comparison_status=("comparable" if event["evaluation_status"] == "valid"
                                                         else event["evaluation_status"]))


def _period(events, start, end, qualification):
    members = [event for event in events if start <= event["date"] <= end]
    old = dict(raw_events=len(members), overlap_excluded=0, selected_events=0,
               valid=0, immature=0, invalid=0, purged=0)
    labels = {label: dict.fromkeys(_EVALUATIONS, 0) for label in ("valid", "immature", "invalid")}
    qualifications = {status: dict.fromkeys(_QUALIFICATIONS, 0) for status in _EVALUATIONS}
    for event in members:
        old["selected_events"] += event["selected"]
        old[event["evaluation_status"]] += 1
        labels[event["label_status"]][event["evaluation_status"]] += 1
        qualifications[event["evaluation_status"]][qualification] += 1
    admitted = qualification == "admitted"
    selection = dict(comparable=old["valid"] if admitted else 0,
                     source_unavailable_valid=old["valid"] if qualification == "source_unavailable" else 0,
                     internal_failure_valid=old["valid"] if qualification == "internal_failure" else 0,
                     condition_computed=old["selected_events"] if admitted else 0,
                     condition_source_unavailable=old["selected_events"] if qualification == "source_unavailable" else 0,
                     condition_internal_failure=old["selected_events"] if qualification == "internal_failure" else 0)
    result = dict(start=start, end=end, old_counts=old, label_evaluation_counts=labels,
                  qualification_counts=qualifications, selection_qualification=selection,
                  condition_counts=None, groups=None, costs=None, delta=None, distinct_signal_dates=None)
    if not admitted:
        return result
    conditions = dict(D_true=0, D_false=0, E_true=0, E_false=0)
    groups = {name: [] for name in ("a0", "a1", "e_true", "e_false")}
    for event in members:
        background = event["background"]
        direction, efficient = background["direction_up"], background["efficient"]
        if event["selected"]:
            conditions["D_true" if direction else "D_false"] += 1
            if direction:
                conditions["E_true" if efficient else "E_false"] += 1
        if event["evaluation_status"] == "valid":
            groups["a0"].append(event)
            if direction:
                groups["a1"].append(event)
                groups["e_true" if efficient else "e_false"].append(event)
    statistics = {name: _summary([event["price_change"] for event in group]) for name, group in groups.items()}
    yes, no = statistics["e_true"], statistics["e_false"]
    delta = (Fraction(yes["zero_count"] + yes["negative_count"], yes["count"])
             - Fraction(no["zero_count"] + no["negative_count"], no["count"])) if yes["count"] and no["count"] else None
    result.update(condition_counts=conditions, groups=statistics,
                  costs=dict(retention=_ratio(yes["count"], statistics["a1"]["count"]),
                             missed_positive_count=no["positive_count"],
                             missed_positive_fraction=_ratio(no["positive_count"], statistics["a1"]["positive_count"])),
                  delta=_fraction(delta, estimate=True) if delta is not None else None,
                  distinct_signal_dates={name: len({event["date"] for event in group}) for name, group in groups.items()})
    return result


def _period_ranges(report_start, test_start, cutoff):
    ranges = dict(primary=(test_start, cutoff),
                  development=(report_start, (date.fromisoformat(test_start) - timedelta(days=1)).isoformat()),
                  full=(report_start, cutoff))
    first, last = date.fromisoformat(report_start), date.fromisoformat(cutoff)
    quarter = first.year * 4 + (first.month - 1) // 3
    final = last.year * 4 + (last.month - 1) // 3
    for value in range(quarter, final + 1):
        year, q = divmod(value, 4)
        begin, month = date(year, q * 3 + 1, 1), q * 3 + 3
        finish = date(year, month, monthrange(year, month)[1])
        ranges[f"{year:04d}-Q{q + 1}"] = (max(begin, first).isoformat(), min(finish, last).isoformat())
    return ranges


def swing_event_report(query, *, report_start, test_start, cutoff):
    """Join the fixed 20/5 breakout to a lag-one, ten-change ER >= 1/2.

    All B events, selection and old labels are retained. A connection invariant
    failure closes this entire source's new comparison, never just one event.
    """
    identity = _request(query, report_start, test_start, cutoff)
    parameters = dict(report_start=report_start, test_start=test_start, cutoff=cutoff,
                      lookback=20, horizon=5, efficiency_lookback=10, lag=1,
                      efficiency_threshold=_fraction(Fraction(1, 2)),
                      primary_period="internal_2026" if (report_start, test_start, cutoff) ==
                      ("2024-10-11", "2026-01-01", "2026-10-09") else "internal_test_period")
    bound = dict(method_id=_METHOD, protocol_version=_PROTOCOL,
                 inputs=[dict(snapshot_id=query["snapshot_id"], query_id=query["query_id"])],
                 source=dict(batch_id=query["batch_id"], raw_sha256=query["manifest"]["raw_sha256"],
                             source_contract_id=query["manifest"]["source_contract_id"], identity=identity, period="1d"),
                 parameters=parameters)
    bars = daily_bars(query)
    coverage = daily_coverage(query, bars)
    rejection = source_rejection(query)
    reasons = ([rejection] if rejection else []) + ([] if coverage["coverage_known"] else ["unknown_source_coverage"])
    qualification = "source_unavailable" if reasons else "admitted"
    result = dict(**bound, analysis_id=_identity(bound), mode="retrospective",
                  source_qualification="source_unavailable" if reasons else "conditional_frozen_source_observations",
                  historical_availability="unverified",
                  limitations=["source_price_labels_not_execution_returns", "adjustment_unverified",
                               "corporate_actions_unverified", "historical_availability_unverified",
                               "source_steps_not_calendar_days", "overlapping_cross_security_dates",
                               "distribution_estimates_float64"],
                  coverage=coverage, calculation_status="source_unavailable" if reasons else "computed",
                  reasons=reasons, full_prefix=dict(start=bars[0]["date"] if bars else None,
                                                   end=bars[-1]["date"] if bars else None),
                  legacy=None, events=None, periods=None)
    try:
        old = event_report(bars, 20, 5, test_start, cutoff)
    except ArithmeticError as exc:
        result.update(calculation_status="legacy_event_failure", reasons=reasons + [f"legacy_event_failure:{type(exc).__name__}"])
        return result
    result["legacy"] = {key: old[key] for key in ("counts", "partitions")}
    events = None
    if qualification == "admitted":
        try:
            events = [_connect(event, old["signals"], bars) for event in old["rows"]]
        except (_ConnectionError, KeyError, IndexError, TypeError) as exc:
            qualification = "internal_failure"
            result.update(calculation_status="connection_invariant_failure",
                          reasons=reasons + [f"connection_invariant_failure:{exc}"])
    if events is None:
        # Even on join failure no old field is rewritten or dropped. Retrieving
        # a prior threshold is optional if the old index itself was corrupted.
        events = []
        for event in old["rows"]:
            index = event.get("index")
            signal = old["signals"][index] if type(index) is int and 0 <= index < len(old["signals"]) else {}
            prior_high = (signal.get("prior_high") if signal.get("date") == event.get("date")
                          and signal.get("ordinal") == event.get("ordinal") else None)
            events.append(dict(event, prior_high=prior_high, background=None,
                               label_sign=None, comparison_status=qualification))
    result["events"] = events
    result["periods"] = {name: _period(events, start, end, qualification)
                         for name, (start, end) in _period_ranges(report_start, test_start, cutoff).items()}
    return result
