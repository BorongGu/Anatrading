"""Strict source-window extrema, with anchor and right-window observation kept separate."""
from .candle_geometry import ohlc_values
from .numeric import decimal_text
from .store import _identity


_METHOD = "source-window-pivots-v1"


def pivot_report(query, context, radius=2):
    if type(radius) is not int or not 1 <= radius <= 20:
        raise ValueError("invalid_radius")
    if query["snapshot_id"] != context["snapshot_id"]:
        raise ValueError("context_snapshot_mismatch")
    labels = [row["label"] for row in query["rows"]]
    asof = max(labels) if labels else None
    cutoff = query.get("selection", {}).get("cutoff")
    if asof is not None and cutoff is not None:
        asof = min(asof, cutoff)
    supported = query["metadata"].get("period") in {"1d", "1m"}
    groups, members, prices = {}, {}, {}
    for row in context["rows"] if supported else ():
        if asof is not None and row["label"] <= asof:
            groups.setdefault(row["label"], []).append(row)
    dates = sorted(groups)
    positions = {label: i for i, label in enumerate(dates)}
    for label in dates:
        rows = groups[label]
        values, reason = (None, "duplicate_label") if len(rows) != 1 else ohlc_values(rows[0])
        prices[label] = values
        members[label] = dict(label=label, ordinals=[r["ordinal"] for r in rows], reason=reason,
                             high=None if reason else decimal_text(values[1]), low=None if reason else decimal_text(values[2]))
    events = []

    def calculate(row):
        label = row["label"]
        result = dict(ordinal=row["ordinal"], label=label, left_count=0, right_count=0, window_labels=[],
                      confirmation_label=None, confirmation_ordinal=None, reason=None,
                      high=dict(is_pivot=None, reason=None, pivot_id=None), low=dict(is_pivot=None, reason=None, pivot_id=None))
        reason = "unsupported_period" if not supported else "unlocated_label" if label is None else (
            "context_row_unavailable" if label not in positions else None)
        if reason:
            result["reason"] = reason
            return result
        position = positions[label]
        window = dates[max(0, position - radius):position + radius + 1]
        left, right = min(radius, position), min(radius, len(dates) - position - 1)
        reason = members[label]["reason"] or ("history_insufficient" if left < radius else
                  "pending_right_window" if right < radius else next((members[d]["reason"] for d in window if members[d]["reason"]), None))
        result.update(window_labels=window, left_count=left, right_count=right, reason=reason)
        if reason:
            return result
        confirmation = window[-1]
        result.update(confirmation_label=confirmation, confirmation_ordinal=members[confirmation]["ordinals"][0])
        for kind, column in (("high", 1), ("low", 2)):
            value = prices[label][column]
            others = [prices[d][column] for d in window if d != label]
            outside = any(value < other if kind == "high" else value > other for other in others)
            reason = ("not_high" if kind == "high" else "not_low") if outside else (
                "tied_not_strict" if value in others else None)
            decision = result[kind]
            decision.update(is_pivot=reason is None, reason=reason)
            if reason is None:
                decision["pivot_id"] = _identity(dict(method_id=_METHOD, snapshot_id=query["snapshot_id"],
                                                      radius=radius, ordinal=row["ordinal"], kind=kind))
                events.append(dict(pivot_id=decision["pivot_id"], kind=kind, price=decimal_text(value),
                    anchor_ordinal=row["ordinal"], anchor_label=label, confirmation_label=confirmation,
                    confirmation_ordinal=result["confirmation_ordinal"], delay_source_labels=radius))
        return result

    rows = [calculate(row) for row in query["rows"]]
    unlocated = [calculate(row) for row in query["unlocated"]]
    events.sort(key=lambda event: (event["confirmation_label"], event["anchor_ordinal"], event["kind"]))
    identity = dict(method_id=_METHOD, query_id=query["query_id"], context_query_id=context["query_id"], radius=radius, as_of_label=asof)
    return dict(**identity, pivots_id=_identity(identity), qualification="conditional_source_values",
                source_qualification=query["manifest"]["qualification"], anchor_scope="selected_source_rows",
                window_unit="located_source_labels", tie_policy="strict_no_ties",
                confirmation_semantics="right_source_window_present", context_unlocated_rows=len(context["unlocated"]),
                coverage_reason="unknown_source_window_coverage" if context["unlocated"] else None,
                assumptions=["constant_price_scale", "comparable_adjustment_basis"],
                unknowns=["calendar", "coverage", "bar_closure", "adjustment", "known_at", "intrabar_path"],
                members=[members[d] for d in dates], rows=rows, unlocated=unlocated, events=events)
