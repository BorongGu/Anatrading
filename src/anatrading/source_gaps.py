"""Exact gaps between located source ranges and subsequent extremum observations."""
from heapq import heappop, heappush

from .candle_geometry import ohlc_values
from .numeric import decimal_text, exact_sum
from .store import _identity


_METHOD = "source-price-gaps-v1"


def gap_report(query, context):
    if query["snapshot_id"] != context["snapshot_id"]:
        raise ValueError("context_snapshot_mismatch")
    labels = [row["label"] for row in query["rows"]]
    asof = max(labels) if labels else None
    cutoff = query.get("selection", {}).get("cutoff")
    if asof is not None and cutoff is not None:
        asof = min(asof, cutoff)
    supported = query["metadata"].get("period") in {"1d", "1m"}
    selected = {row["ordinal"] for row in query["rows"]}
    groups = {}
    for row in context["rows"]:
        if asof is not None and row["label"] <= asof:
            groups.setdefault(row["label"], []).append(row)
    calculated, active = {}, {}
    queues = {(direction, boundary): [] for direction in ("up", "down") for boundary in ("near", "far")}
    previous = None

    def blank(row, reason=None):
        return dict(ordinal=row["ordinal"], label=row["label"], previous_label=None,
                    previous_ordinals=[], open_close_change=None, gap=None, reason=reason)

    for label, rows in sorted(groups.items()) if supported else ():
        prices, reason = (None, "duplicate_label") if len(rows) != 1 else ohlc_values(rows[0])
        member = dict(label=label, ordinals=[row["ordinal"] for row in rows], prices=prices, reason=reason)
        if reason:
            stop = dict(label=label, ordinals=member["ordinals"], reason=reason)
            for gap in active.values():
                gap["interrupted_at"] = stop
            active.clear()
            for queue in queues.values():
                queue.clear()
        else:
            opening, high, low, close = prices
            for (direction, boundary), queue in queues.items():
                extreme = low if direction == "up" else high
                key = extreme.copy_negate() if direction == "up" else extreme
                while queue and queue[0][0] <= key:
                    threshold_key, ordinal = heappop(queue)
                    gap = active[ordinal]
                    threshold = threshold_key.copy_negate() if direction == "up" else threshold_key
                    lower, upper = gap["_bounds"]
                    gap[boundary + "_event"] = dict(ordinal=rows[0]["ordinal"], label=label,
                        extreme=decimal_text(extreme), relation="equal" if extreme == threshold else "beyond",
                        contains_boundary=low <= threshold <= high,
                        range_relation="overlaps_interval" if low <= upper and high >= lower else "passed_without_overlap")
                    if boundary == "far":
                        active.pop(ordinal)
        for row in rows:
            if row["ordinal"] not in selected:
                continue
            value = blank(row, reason)
            if previous is not None:
                value.update(previous_label=previous["label"], previous_ordinals=previous["ordinals"])
            if reason is None:
                value["reason"] = "no_previous_source_bar" if previous is None else (
                    "previous_bar_unavailable" if previous["reason"] else None)
                if value["reason"] is None:
                    prior = previous["prices"]
                    value["open_close_change"] = decimal_text(exact_sum((opening, prior[3].copy_negate())))
                    direction = "up" if low > prior[1] else "down" if high < prior[2] else None
                    if direction:
                        lower, upper = (prior[1], low) if direction == "up" else (high, prior[2])
                        gap = dict(gap_id=_identity(dict(method_id=_METHOD, snapshot_id=query["snapshot_id"],
                            previous_ordinal=previous["ordinals"][0], ordinal=row["ordinal"])),
                            direction=direction, lower=decimal_text(lower), upper=decimal_text(upper),
                            width=decimal_text(exact_sum((upper, lower.copy_negate()))),
                            near_event=None, far_event=None, interrupted_at=None, _bounds=(lower, upper))
                        value["gap"] = gap
                        active[row["ordinal"]] = gap
                        near, far = (upper, lower) if direction == "up" else (lower, upper)
                        for boundary, threshold in (("near", near), ("far", far)):
                            key = threshold.copy_negate() if direction == "up" else threshold
                            heappush(queues[direction, boundary], (key, row["ordinal"]))
            calculated[row["ordinal"]] = value
        previous = member

    values = [calculated.get(row["ordinal"], blank(row, "context_row_unavailable" if supported else "unsupported_period"))
              for row in query["rows"]]
    for value in values:
        gap = value["gap"]
        if gap:
            gap.pop("_bounds")
            gap["state"] = ("far_boundary_observed" if gap["far_event"] else "observation_interrupted" if gap["interrupted_at"] else
                            "near_boundary_observed" if gap["near_event"] else "not_observed_before_asof")
    identity = dict(method_id=_METHOD, query_id=query["query_id"], context_query_id=context["query_id"], as_of_label=asof)
    return dict(**identity, gaps_id=_identity(identity), qualification="conditional_source_values",
                source_qualification=query["manifest"]["qualification"], origin_scope="selected_source_rows",
                observation_scope="full_source_context_to_asof", adjacency="adjacent_located_labels",
                first_event_scope="first_unique_valid_located_before_interruption",
                context_unlocated_rows=len(context["unlocated"]),
                coverage_reason="unknown_adjacency_and_first_observation_coverage" if context["unlocated"] else None,
                assumptions=["constant_price_scale", "comparable_adjustment_basis"],
                unknowns=["calendar", "coverage", "bar_closure", "adjustment", "known_at", "intrabar_path"],
                rows=values, unlocated=[blank(row, "unlocated_label") for row in query["unlocated"]])
