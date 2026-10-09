"""Exact selected-label aggregation, with partial observations kept separate."""
from .candle_geometry import ohlc_values
from .numeric import NumericError, decimal_text, decimal_value, exact_sum, integer_value
from .store import _identity
from .volume_at_time import _CLOCKS, _source_date


_METHOD = "selected-minute-label-aggregation-v1"
_TEMPLATE = "observed-600059-240-clocks-v1"
_POSITIONS = {clock: index for index, clock in enumerate(_CLOCKS)}


def _observed(rows, duplicate):
    values = dict.fromkeys(("open", "high", "low", "close", "volume", "amount"))
    reasons = dict.fromkeys(("ohlc", "volume", "amount"), "duplicate_label" if duplicate else "no_members" if not rows else None)
    if duplicate or not rows:
        return values, reasons
    prices = [ohlc_values(row) for row in rows]
    reasons["ohlc"] = next((reason for _, reason in prices if reason), None)
    if reasons["ohlc"] is None:
        prices = [price for price, _ in prices]
        values.update(open=decimal_text(prices[0][0]), high=decimal_text(max(p[1] for p in prices)),
                      low=decimal_text(min(p[2] for p in prices)), close=decimal_text(prices[-1][3]))
    for field in ("volume", "amount"):
        numbers = []
        for row in rows:
            token = row["values"].get(field)
            try:
                if token is None:
                    reasons[field] = "missing_field"
                    break
                number = integer_value(token) if field == "volume" else decimal_value(token)
                if number < 0:
                    raise NumericError("negative_field")
                numbers.append(number)
            except NumericError:
                reasons[field] = "invalid_field"
                break
        if reasons[field] is None:
            values[field] = str(sum(numbers)) if field == "volume" else decimal_text(exact_sum(numbers))
    return values, reasons


def aggregation_report(query, target_minutes=5):
    if type(target_minutes) is not int or target_minutes not in {5, 15, 30, 60}:
        raise ValueError("invalid_target_minutes")
    labels = [row["label"] for row in query["rows"]]
    asof = max(labels) if labels else None
    cutoff = query.get("selection", {}).get("cutoff")
    if asof is not None and cutoff is not None:
        asof = min(asof, cutoff)
    supported = query["metadata"].get("period") == "1m"
    days, excluded, unknown_dates, unknown_days = {}, [], [], set()
    for row in (*query["rows"], *query["unlocated"]):
        label = row["label"]
        reason = "unsupported_period" if not supported else None
        if reason is None and label is None:
            day = _source_date(row)
            if day is None:
                unknown_dates.append(row["ordinal"])
            elif asof is None or day <= asof[:10]:
                unknown_days.add(day)
            reason = "outside_asof_date" if day is not None and asof is not None and day > asof[:10] else "unlocated_label"
        elif reason is None:
            if asof is not None and label > asof:
                reason = "outside_asof"
            elif len(label) != 16 or label[10] != "T" or label[11:] not in _POSITIONS:
                reason = "outside_observed_template"
            else:
                days.setdefault(label[:10], {}).setdefault(_POSITIONS[label[11:]], []).append(row)
        if reason:
            excluded.append(dict(ordinal=row["ordinal"], label=label, reason=reason))
    bucket_count = sum(max(slots) // target_minutes - min(slots) // target_minutes + 1 for slots in days.values())
    if bucket_count > 20000:
        raise ValueError("aggregation_bucket_limit")
    buckets = []
    for day, slots in sorted(days.items()):
        for position in range(min(slots) // target_minutes, max(slots) // target_minutes + 1):
            indexes = range(position * target_minutes, (position + 1) * target_minutes)
            expected = [day + "T" + _CLOCKS[i] for i in indexes]
            members = sorted((row for i in indexes for row in slots.get(i, [])), key=lambda row: (row["label"], row["ordinal"]))
            missing = [day + "T" + _CLOCKS[i] for i in indexes if i not in slots]
            duplicates = [day + "T" + _CLOCKS[i] for i in indexes if len(slots.get(i, [])) > 1]
            future = [label for label in expected if asof is not None and label > asof]
            membership_reason = ("duplicate_label" if duplicates else "unlocated_membership_unknown" if unknown_dates or day in unknown_days else
                                 "not_in_selected_records" if any(label not in future for label in missing) else
                                 "right_labels_not_observed" if future else None)
            observed, observed_reasons = _observed(members, duplicates)
            values = dict.fromkeys(observed) if membership_reason else observed.copy()
            reasons = {field: membership_reason or reason for field, reason in observed_reasons.items()}
            prices = [decimal_value(values[key]) for key in ("open", "high", "low", "close") if values[key] is not None]
            precision_lost = any(a != b and float(a) == float(b) for i, a in enumerate(prices) for b in prices[i + 1:])
            direction = "unknown" if len(prices) != 4 else "up" if prices[3] > prices[0] else "down" if prices[3] < prices[0] else "equal"
            bucket_identity = dict(method_id=_METHOD, snapshot_id=query["snapshot_id"], template_id=_TEMPLATE,
                                   target_minutes=target_minutes, end_label=expected[-1])
            buckets.append(dict(bucket_id=_identity(bucket_identity), first_label=expected[0], end_label=expected[-1],
                segment="morning_labels" if position * target_minutes < 120 else "afternoon_labels",
                expected_labels=expected, members=[dict(ordinal=row["ordinal"], label=row["label"]) for row in members],
                missing_labels=missing, duplicate_labels=duplicates, future_labels=future,
                last_observed_label=members[-1]["label"] if members else None,
                template_complete=membership_reason is None, membership_reason=membership_reason,
                values=values, reasons=reasons, observed_values=observed, observed_reasons=observed_reasons,
                display=dict(direction=direction, ohlc_drawable=len(prices) == 4 and not precision_lost, precision_lost=precision_lost)))
    identity = dict(method_id=_METHOD, query_id=query["query_id"], template_id=_TEMPLATE,
                    target_minutes=target_minutes, as_of_label=asof)
    return dict(**identity, aggregation_id=_identity(identity), snapshot_id=query["snapshot_id"],
                qualification="conditional_source_values", source_qualification=query["manifest"]["qualification"],
                member_scope="selected_records_only", bucket_label_semantics="nominal_last_template_label",
                completeness_semantics="selected_template_members_present_not_market_bar_closed",
                assumptions=["fixed_observed_clock_template", "constant_field_scales", "comparable_price_basis"],
                unknowns=["calendar", "trade_coverage", "bar_intervals", "bar_closure", "known_at", "trade_phase", "source_units"],
                unknown_date_ordinals=unknown_dates, unknown_clock_dates=sorted(unknown_days), excluded=excluded, buckets=buckets)
