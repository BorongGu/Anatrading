"""Fixed prior-high events and descriptive, non-trading source-price labels."""
from collections import deque
from fractions import Fraction
from math import floor, fsum, isfinite

from .numeric import decimal_text
from .research_series import MAX_RESEARCH_ROWS, strict_date


HORIZONS = (1, 5, 10, 20)


def validate_event_parameters(lookback, horizon, test_start):
    if type(lookback) is not int or not 2 <= lookback <= 252:
        raise ValueError("invalid_lookback")
    if type(horizon) is not int or horizon not in HORIZONS:
        raise ValueError("invalid_horizon")
    if test_start is not None:
        strict_date(test_start, "invalid_test_start")


def _summary(values):
    ordered = sorted(values)
    size = len(ordered)

    def quantile(probability):
        if not size:
            return None
        position = (size - 1) * probability
        left = floor(position)
        weight = position - left
        return ordered[left] if weight == 0 else ordered[left] * (1 - weight) + ordered[left + 1] * weight

    positive = sum(value > 0 for value in ordered)
    return dict(count=size, mean=fsum(ordered) / size if size else None,
                median=quantile(.5), q05=quantile(.05), q25=quantile(.25),
                q75=quantile(.75), q95=quantile(.95), positive_count=positive,
                zero_count=sum(value == 0 for value in ordered),
                negative_count=sum(value < 0 for value in ordered),
                positive_fraction=positive / size if size else None)


def _new_group():
    return dict(counts=dict(candidate_dates=0, rule_computable=0, raw_events=0,
                           overlap_excluded=0, selected_events=0, valid=0,
                           immature=0, invalid=0, purged=0),
                _values=[],
                baseline=dict(counts=dict(candidate_dates=0, valid=0, immature=0, invalid=0, purged=0),
                              _values=[]))


def _finish(group):
    group["statistics"] = _summary(group.pop("_values"))
    group["baseline"]["statistics"] = _summary(group["baseline"].pop("_values"))
    return group


def event_report(bars, lookback=20, horizon=5, test_start=None, evaluation_as_of=None):
    """Evaluate one horizon without choosing events using their future labels.

    bars are ascending daily_bars() slots. Selection is greedy across the full
    event sequence before partitioning, so splitting cannot erase overlap.
    The baseline includes event dates and keeps overlapping labels.
    """
    validate_event_parameters(lookback, horizon, test_start)
    if len(bars) > MAX_RESEARCH_ROWS:
        raise ValueError("research_row_limit")
    if evaluation_as_of is not None:
        strict_date(evaluation_as_of, "invalid_evaluation_as_of")
        bars = [bar for bar in bars if bar["date"] <= evaluation_as_of]
    elif bars:
        evaluation_as_of = bars[-1]["date"]
    bad_prefix = [0]
    for bar in bars:
        bad_prefix.append(bad_prefix[-1] + (bar["reason"] is not None))
    groups = {name: _new_group() for name in (("descriptive",) if test_start is None else ("train", "test"))}
    total = _new_group()
    maxima, signals, events = deque(), [], []
    last_selected = None

    def label_at(index):
        end = index + horizon
        if end >= len(bars):
            return dict(label_status="immature", label_reason="insufficient_future_records",
                        label_end=None, price_change=None)
        label_end = bars[end]["date"]
        if bad_prefix[end + 1] != bad_prefix[index]:
            return dict(label_status="invalid", label_reason="invalid_label_window",
                        label_end=label_end, price_change=None)
        # Fraction uses exact source decimals even if adjacent prices round to
        # the same binary64 value; only the derived ratio becomes an estimate.
        change = float(Fraction(bars[end]["close"]) / Fraction(bars[index]["close"]) - 1)
        if not isfinite(change):
            return dict(label_status="invalid", label_reason="numerical_failure",
                        label_end=label_end, price_change=None)
        return dict(label_status="valid", label_reason=None, label_end=label_end, price_change=change)

    for index, bar in enumerate(bars):
        while maxima and maxima[0] < index - lookback:
            maxima.popleft()
        history_reason = ("history_insufficient" if index < lookback else
                          "invalid_history_window" if bad_prefix[index] != bad_prefix[index-lookback] else None)
        upper = bars[maxima[0]]["high"] if history_reason is None else None
        reason = bar["reason"] or history_reason
        breakout = bar["close"] > upper if reason is None else None
        signal = dict(date=bar["date"], ordinal=bar["ordinal"], prior_high=decimal_text(upper) if upper is not None else None,
                      breakout=breakout, reason=reason)
        signals.append(signal)
        partition = "descriptive" if test_start is None else "train" if bar["date"] < test_start else "test"
        affected = (total, groups[partition])
        for group in affected:
            group["counts"]["candidate_dates"] += 1
        if reason is None:
            label = label_at(index)
            purged = partition == "train" and label["label_end"] is not None and label["label_end"] >= test_start
            baseline_status = "purged" if purged else label["label_status"]
            for group in affected:
                group["counts"]["rule_computable"] += 1
                group["baseline"]["counts"]["candidate_dates"] += 1
                group["baseline"]["counts"][baseline_status] += 1
                if baseline_status == "valid":
                    group["baseline"]["_values"].append(label["price_change"])
            if breakout:
                selected = last_selected is None or index > last_selected + horizon
                if selected:
                    last_selected = index
                status = baseline_status if selected else "overlap_excluded"
                event = dict(date=bar["date"], ordinal=bar["ordinal"], index=index,
                             partition=partition, selected=selected, evaluation_status=status,
                             signal_as_of=bar["date"], evaluation_as_of=evaluation_as_of,
                             start_close=decimal_text(bar["close"]),
                             end_close=decimal_text(bars[index+horizon]["close"])
                             if index+horizon < len(bars) and bars[index+horizon]["close"] is not None else None,
                             **label)
                events.append(event)
                for group in affected:
                    group["counts"]["raw_events"] += 1
                    group["counts"]["selected_events"] += selected
                    group["counts"][status] += 1
                    if status == "valid":
                        group["_values"].append(label["price_change"])
        # Only now insert today's high, never into today's historical threshold.
        if bar["reason"] is None:
            while maxima and bars[maxima[-1]]["high"] <= bar["high"]:
                maxima.pop()
            maxima.append(index)
    result = _finish(total)
    result.update(signals=signals, rows=events, partitions={name: _finish(group) for name, group in groups.items()},
                  lookback=lookback, horizon=horizon, test_start=test_start,
                  evaluation_as_of=evaluation_as_of, mode="descriptive" if test_start is None else "time_split_descriptive",
                  rule="close_strictly_above_prior_source_highs", horizon_unit="source_date_groups",
                  overlap_policy="greedy_next_start_strictly_after_previous_end",
                  baseline_policy="all_rule_computable_dates_including_events_with_overlapping_labels",
                  quantile_method="type_7", label_meaning="ex_post_source_close_change_not_trading_return",
                  numeric_kind="estimate_float64")
    return result
