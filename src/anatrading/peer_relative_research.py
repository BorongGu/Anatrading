"""Exact, bounded peer context from complete retrospective Store queries.

This trusts the Store's immutable source IDs, not caller-generated hashes. It
neither loads raw objects nor certifies asset class, currency, or economic return.
See docs/plans/2026-10-11-peer-relative.md for the approved single-interval scope.
"""
from decimal import Decimal
from fractions import Fraction
import hashlib
import json
import re

from .models import VALUE_FIELDS
from .numeric import NumericError, decimal_text, decimal_value
from .pair_research import symbol_identity
from .research_series import source_rejection, strict_date


METHOD_ID = "peer-relative-source-v1"
RULE_VERSION = "peer-relative-eligibility-v1"
MAX_MEMBERS = 50
MAX_SOURCE_ROWS = 20_000
MAX_TOTAL_ROWS = 200_000
MAX_AUXILIARY_BYTES = 16_384
_PRICE = ("open", "high", "low", "close")
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_IDENTITY = {"source_code", "instrument_identity", "declared_instrument", "declared_venue"}
_ADJUSTMENT = {"source_adjustflag", "source_adjustment", "declared_adjustment"}
_PRICE_CHECKS = {"ohlc_bounds", "nonnegative_prices", *("numeric." + key for key in _PRICE)}
_POSITION = {"label", "duplicate_label", "source_date_range"}
_QUANTITY = {"numeric.volume", "numeric.amount", "source_quantity_decimal", "nonnegative_amount",
             "zero_volume_amount", "conditional_price_bounds", "conditional_price_bounds_cent",
             "standard_units", "source_units_and_coverage"}
_KNOWN_CHECKS = _IDENTITY | _ADJUSTMENT | _PRICE_CHECKS | _POSITION | _QUANTITY | {
    "structure", "source_order", "known_negative_sample"}
_REASONS = ("local_source_conflict", "unclassified_source_failure", "endpoint_integrity_unknown",
            "duplicate_endpoint", "unlocated_endpoint", "missing_endpoint", "missing_ohlc",
            "invalid_price", "invalid_ohlc", "endpoint_price_check_failed",
            "corporate_action_unresolved", "halted_endpoint_source_value")
_DIAGNOSTIC = {"corporate_action_unresolved", "halted_endpoint_source_value"}
_ADJUSTED = {"qfq", "hfq", "forward", "backward", "adjusted", "前复权", "后复权"}


def _keys(value, expected, code="invalid_descriptor"):
    if type(value) is not dict or set(value) != set(expected):
        raise ValueError(code)


def _text(value):
    return type(value) is str and bool(value.strip())


def _enum(value, choices):
    return type(value) is str and value in choices


def _hash(value):
    return type(value) is str and _HEX.fullmatch(value) is not None


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def _auxiliary(value):
    """Bound only the small external descriptor, never recursively rehash rows."""
    active = set()
    nodes = 0

    def check(item, depth):
        nonlocal nodes
        # Every expanded JSON node costs at least one encoded byte. Charge on
        # entry so shared acyclic containers cannot expand before the byte gate.
        nodes += 1
        if depth > 8 or nodes > MAX_AUXILIARY_BYTES:
            raise ValueError("auxiliary_input_limit")
        if type(item) is str:
            if len(item) > 1024:
                raise ValueError("auxiliary_input_limit")
        elif type(item) in (dict, list):
            identity = id(item)
            if identity in active or len(item) > 64:
                raise ValueError("auxiliary_input_limit")
            active.add(identity)
            if type(item) is dict:
                for key, child in item.items():
                    if type(key) is not str:
                        raise ValueError("invalid_descriptor")
                    check(key, depth + 1)
                    check(child, depth + 1)
            else:
                for child in item:
                    check(child, depth + 1)
            active.remove(identity)
        elif item is not None and type(item) not in (int, bool):
            raise ValueError("invalid_descriptor")
        elif type(item) is int and abs(item) > 2**63 - 1:
            raise ValueError("invalid_descriptor")

    check(value, 0)
    size = 0
    try:
        for chunk in json.JSONEncoder(sort_keys=True, ensure_ascii=False, allow_nan=False,
                                      separators=(",", ":")).iterencode(value):
            size += len(chunk.encode("utf-8"))
            if size > MAX_AUXILIARY_BYTES:
                raise ValueError("auxiliary_input_limit")
    except UnicodeError:
        raise ValueError("invalid_descriptor") from None


def _refs(refs):
    if type(refs) is not list or not 1 <= len(refs) <= 16:
        raise ValueError("invalid_descriptor")
    normalized = []
    for ref in refs:
        _keys(ref, ("source_id", "version", "declared_by"))
        if not _text(ref["source_id"]) or not _text(ref["version"]) or not _enum(
                ref["declared_by"], {"selection_record", "source_document", "user_declaration", "project_test"}):
            raise ValueError("invalid_descriptor")
        normalized.append(dict(ref))
    serialized = [_json(ref) for ref in normalized]
    if len(set(serialized)) != len(serialized):
        raise ValueError("invalid_descriptor")
    return sorted(normalized, key=_json)


def _descriptor(value, identities, target, a, b):
    _keys(value, ("schema_version", "group_name", "group_axis", "selection_date", "membership",
                  "selection_basis", "scope", "evidence_refs", "members", "events"))
    if (type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not _text(value["group_name"]) or not _text(value["selection_basis"])
            or not _enum(value["group_axis"], {"business_peers", "listing_board", "explicit_sample"})
            or value["membership"] != "current_members_retrospective"):
        raise ValueError("invalid_descriptor")
    strict_date(value["selection_date"], "invalid_descriptor")
    scope = value["scope"]
    expected = dict(asset_type="stock", share_class="A_share", price_currency="CNY", daily_label_basis="CN_exchange_date")
    _keys(scope, expected)
    for name, required in expected.items():
        _keys(scope[name], ("value", "evidence_status"))
        if not _enum(scope[name]["evidence_status"], {"declared", "assumed"}):
            raise ValueError("invalid_descriptor")
        if scope[name]["value"] != required:
            raise ValueError("scope_conflict")
    members = value["members"]
    if type(members) is not list or len(members) != len(identities):
        raise ValueError("descriptor_source_mismatch")
    found = {}
    for member in members:
        _keys(member, ("symbol", "snapshot_id", "query_id"))
        symbol = member["symbol"]
        if not _text(symbol):
            raise ValueError("invalid_descriptor")
        if symbol in found:
            raise ValueError("duplicate_member")
        if symbol not in identities or member != identities[symbol]:
            raise ValueError("descriptor_source_mismatch")
        found[symbol] = dict(member)
    if target not in found:
        raise ValueError("invalid_target")
    events = value["events"]
    if type(events) is not list or len(events) > 64:
        raise ValueError("invalid_descriptor")
    normalized_events = []
    for event in events:
        _keys(event, ("symbol", "snapshot_id", "start_date", "end_date", "kind", "evidence_refs"))
        if not _text(event["symbol"]) or event["symbol"] not in found:
            raise ValueError("descriptor_source_mismatch")
        if event["snapshot_id"] != found[event["symbol"]]["snapshot_id"]:
            raise ValueError("descriptor_source_mismatch")
        first = strict_date(event["start_date"], "invalid_descriptor")
        last = strict_date(event["end_date"], "invalid_descriptor")
        if first > last or last < a or first > b or not _enum(
                event["kind"], {"halt", "corporate_action_unresolved", "scope_conflict"}):
            raise ValueError("invalid_descriptor")
        if event["kind"] == "scope_conflict":
            raise ValueError("scope_conflict")
        normalized_events.append({**event, "evidence_refs": _refs(event["evidence_refs"])})
    if len({_json(event) for event in normalized_events}) != len(normalized_events):
        raise ValueError("invalid_descriptor")
    return {**value, "scope": {key: dict(scope[key]) for key in scope},
            "evidence_refs": _refs(value["evidence_refs"]),
            "members": [found[symbol] for symbol in sorted(found)], "events": sorted(normalized_events, key=_json)}


def _checks(checks):
    if type(checks) not in (list, tuple):
        raise ValueError("invalid_source_checks")
    failed = set()
    for check in checks:
        if type(check) is not dict or not _text(check.get("name")) or not _enum(
                check.get("outcome"), {"pass", "fail", "not_evaluated"}):
            raise ValueError("invalid_source_checks")
        if check["outcome"] == "fail":
            failed.add(check["name"])
    return failed


def _source(query):
    """Validate only necessary Store structure and source qualification."""
    required = {"snapshot_id", "batch_id", "query_id", "selection", "manifest", "metadata", "rows",
                "unlocated", "counts", "batch_checks"}
    extras = ({"read_projection"} if "read_projection" in query else {"quality", "unlocated_quality", "totals"})
    _keys(query, required | extras, "invalid_query")
    if "read_projection" in query and query["read_projection"] != "daily_ohlc_input_v1":
        raise ValueError("invalid_query")
    selection, manifest, metadata = (query[key] for key in ("selection", "manifest", "metadata"))
    _keys(selection, ("snapshot_id", "mode", "cutoff", "ordinal_start", "ordinal_end", "fields", "versions"),
          "invalid_selection")
    if (selection["mode"] != "retrospective" or any(selection[key] is not None for key in
            ("cutoff", "ordinal_start", "ordinal_end"))):
        raise ValueError("full_query_required")
    if type(manifest) is not dict or type(metadata) is not dict or type(manifest.get("contract")) is not dict:
        raise ValueError("invalid_query")
    for field in ("snapshot_id", "batch_id", "query_id"):
        if not _hash(query[field]):
            raise ValueError("invalid_source_id")
    if not all(_hash(manifest.get(key)) for key in ("raw_sha256", "source_contract_id")):
        raise ValueError("invalid_source_id")
    if (selection["snapshot_id"] != query["snapshot_id"]
            or type(selection["versions"]) is not dict or selection["versions"] != manifest.get("versions")
            or metadata.get("raw_sha256") != manifest["raw_sha256"]
            or selection["fields"] != list(VALUE_FIELDS)):
        raise ValueError("source_identity_mismatch")
    if manifest.get("qualification") != "source_evidence_retrospective_only":
        raise ValueError("unsupported_source")
    counts = query["counts"]
    _keys(counts, ("selected_rows", "unlocated_rows", "batch_rows", "batch_unlocated_rows"), "invalid_counts")
    expected = (len(query["rows"]), len(query["unlocated"]), len(query["rows"]) + len(query["unlocated"]), len(query["unlocated"]))
    if any(type(counts[key]) is not int or counts[key] != count for key, count in zip(
            ("selected_rows", "unlocated_rows", "batch_rows", "batch_unlocated_rows"), expected)):
        raise ValueError("invalid_counts")
    failed = _checks(query["batch_checks"])
    if source_rejection(query):
        raise ValueError("known_negative_source")
    if failed & _IDENTITY:
        raise ValueError("source_identity_conflict")
    if failed & _ADJUSTMENT:
        raise ValueError("source_adjustment_conflict")
    if "structure" in failed:
        raise ValueError("source_structure_failed")
    if failed - (_IDENTITY | _ADJUSTMENT | _QUANTITY | {"structure", "known_negative_sample"}):
        raise ValueError("unsupported_source_check")
    try:
        identity = symbol_identity(query)
    except ValueError as error:
        raise ValueError("source_identity_conflict" if str(error) == "research_identity_conflict" else "invalid_source_id") from None
    if identity["venue"] not in {"SH", "SZ"}:
        raise ValueError("scope_conflict")
    for key in ("requested_symbol", "source_code"):
        if metadata.get(key) != identity["symbol"]:
            raise ValueError("source_identity_conflict")
    if metadata.get("source_symbol") != identity["venue"].lower() + identity["code"]:
        raise ValueError("source_identity_conflict")
    declaration = metadata.get("interpretation", {})
    for obj in (metadata, declaration):
        for key, required_value in (("asset_type", "stock"), ("share_class", "A_share"),
                                    ("price_currency", "CNY"), ("currency", "CNY"),
                                    ("daily_label_basis", "CN_exchange_date")):
            if obj.get(key) not in (None, "unknown", required_value):
                raise ValueError("scope_conflict")
    contract = manifest["contract"]
    semantics = contract.get("source_semantics", {}).get("fields", {}) if type(contract.get("source_semantics")) is dict else {}
    if type(semantics) is not dict:
        raise ValueError("invalid_query")
    for name, expected_value in (("price_unit", "CNY"), ("adjustment", "none")):
        field = semantics.get(name, {})
        if type(field) is not dict:
            raise ValueError("invalid_query")
        if field.get("value") not in (None, "unknown", expected_value, "unadjusted" if name == "adjustment" else "CNY"):
            raise ValueError("source_adjustment_conflict" if name == "adjustment" else "scope_conflict")
    if metadata.get("requested_adjustment") != "none" or _enum(metadata.get("source_adjustment"), _ADJUSTED):
        raise ValueError("source_adjustment_conflict")
    mapping = contract.get("source_token_mapping")
    if (contract.get("format_id") != "tencent-daily-capture-v1" or contract.get("version") != "1"
            or not _enum(contract.get("capture_version"), {"public-market-capture-v1", "public-market-legacy-reconstruction-v1"})
            or metadata.get("source") != "tencent" or metadata.get("response_branch") != "day"
            or type(mapping) is not dict or mapping.get("source_date") != "source_date"):
        raise ValueError("unsupported_source")
    if metadata.get("period") != "1d" or metadata.get("requested_period") != "1d":
        raise ValueError("unsupported_period")
    ordinals = set()
    for rows, unlocated in ((query["rows"], False), (query["unlocated"], True)):
        for row in rows:
            if type(row) is not dict or not {"ordinal", "label", "tokens", "values", "checks"} <= row.keys():
                raise ValueError("invalid_query")
            ordinal = row["ordinal"]
            if type(ordinal) is not int or ordinal <= 0 or ordinal in ordinals:
                raise ValueError("invalid_source_ordinal")
            ordinals.add(ordinal)
            if ((row["label"] is None) != unlocated or row["label"] is not None and type(row["label"]) is not str
                    or type(row["tokens"]) is not dict or type(row["values"]) is not dict
                    or not set(_PRICE) <= row["values"].keys()):
                raise ValueError("invalid_query")
            if any(row["values"][key] is not None and type(row["values"][key]) not in (str, Decimal, int) for key in _PRICE):
                raise ValueError("invalid_query")
            _checks(row["checks"])
    return identity


def _day(value):
    try:
        return strict_date(value)
    except ValueError:
        return None


def _position(row):
    label, token = _day(row["label"]), _day(row["tokens"].get("source_date"))
    if label is not None:
        return (label, True) if label == token else (None, False)
    return token, False


def _row_conflict(row, failed, identity):
    if failed & (_IDENTITY | _ADJUSTMENT | {"structure", "known_negative_sample", "source_date_range"}):
        return True
    for key in ("code", "source_code"):
        if row["tokens"].get(key) is not None:
            try:
                observed = symbol_identity({"metadata": {"source_code": row["tokens"][key], "source_venue": identity["venue"]}})
            except ValueError:
                return True
            if observed["symbol"] != identity["symbol"]:
                return True
    return any(type(row["tokens"].get(key)) is str and row["tokens"][key] in _ADJUSTED
               for key in ("adjustflag", "source_adjustment"))


def _price(value):
    if (type(value) is str and len(value) > 128 or type(value) is int and value.bit_length() > 426
            or type(value) is Decimal and (len(value.as_tuple().digits) > 128
                or type(value.as_tuple().exponent) is not int or abs(value.as_tuple().exponent) > 128)):
        raise NumericError("decimal_range")
    return decimal_value(value)


def _ordered(reasons):
    return [reason for reason in _REASONS if reason in reasons]


def _endpoint(day, candidates):
    output = dict(date=day, ordinal=None, close_token=None, close_exact=None, reasons=[])
    reasons = set()
    if not candidates:
        output["reasons"] = ["missing_endpoint"]
        return output, None
    if len(candidates) > 1:
        reasons.add("duplicate_endpoint")
    if any(not located or "label" in _checks(row["checks"]) for row, located in candidates):
        reasons.add("unlocated_endpoint")
    if len(candidates) != 1:
        output["reasons"] = _ordered(reasons)
        return output, None
    row, _ = candidates[0]
    output["ordinal"] = row["ordinal"]
    failed, values = _checks(row["checks"]), {}
    if "duplicate_label" in failed:
        reasons.add("duplicate_endpoint")
    if failed & _PRICE_CHECKS:
        reasons.add("endpoint_price_check_failed")
    for key in _PRICE:
        raw = row["values"][key]
        if raw is None:
            reasons.add("missing_ohlc")
            continue
        try:
            values[key] = _price(raw)
            if values[key] <= 0:
                reasons.add("invalid_price")
        except NumericError:
            reasons.add("invalid_price")
        if key in row["tokens"]:
            try:
                if _price(row["tokens"][key]) != values.get(key):
                    reasons.add("endpoint_price_check_failed")
            except (NumericError, TypeError):
                reasons.add("endpoint_price_check_failed")
    if len(values) == 4 and not (values["low"] <= values["open"] <= values["high"]
                               and values["low"] <= values["close"] <= values["high"]):
        reasons.add("invalid_ohlc")
    if type(row["tokens"].get("close")) is str and len(row["tokens"]["close"]) <= 128:
        output["close_token"] = row["tokens"]["close"]
    if "close" in values:
        output["close_exact"] = decimal_text(values["close"])
    output["reasons"] = _ordered(reasons)
    return output, None if reasons else values["close"]


def _exact(value, unit="ratio"):
    return dict(numerator=str(value.numerator), denominator=str(value.denominator), unit=unit)


def _member(query, identity, target, a, b, events):
    candidates, reasons, anomalies = {a: [], b: []}, set(), []
    for rows in (query["rows"], query["unlocated"]):
        for row in rows:
            day, located = _position(row)
            failed = _checks(row["checks"])
            scope = "unknown" if day is None else "inside_interval" if a <= day <= b else "outside_interval"
            codes = set(failed)
            if day is None:
                reasons.add("endpoint_integrity_unknown")
                codes.add("endpoint_integrity_unknown")
            elif day in candidates:
                candidates[day].append((row, located))
            if _row_conflict(row, failed, identity):
                codes.add("local_source_conflict")
                if scope != "outside_interval":
                    reasons.add("local_source_conflict")
            if failed - _KNOWN_CHECKS:
                codes.add("unclassified_source_failure")
                if scope != "outside_interval":
                    reasons.add("unclassified_source_failure")
            if not located:
                codes.add("unlocated_label")
            if codes:
                anomalies.append(dict(ordinal=row["ordinal"], scope=scope, codes=sorted(codes)))
    start, left = _endpoint(a, candidates[a])
    end, right = _endpoint(b, candidates[b])
    reasons.update(start["reasons"])
    reasons.update(end["reasons"])
    for event in events:
        if event["symbol"] != identity["symbol"]:
            continue
        if event["kind"] == "corporate_action_unresolved":
            reasons.add("corporate_action_unresolved")
        elif event["kind"] == "halt" and any(close is not None and event["start_date"] <= day <= event["end_date"]
                                             for day, close in ((a, left), (b, right))):
            reasons.add("halted_endpoint_source_value")
    valid = left is not None and right is not None and not (reasons - _DIAGNOSTIC)
    change = Fraction(right) / Fraction(left) - 1 if valid else None
    return dict(symbol=identity["symbol"], role="target" if identity["symbol"] == target else "peer",
                snapshot_id=query["snapshot_id"], batch_id=query["batch_id"], query_id=query["query_id"],
                endpoints=dict(start=start, end=end), source_change=_exact(change) if change is not None else None,
                reasons=_ordered(reasons), anomalies=sorted(anomalies, key=lambda item: item["ordinal"])), change


def peer_relative_report(queries, group_descriptor, target, start_date, end_date):
    """Return one exact fixed-member comparison, or a structured unavailable report.

Only unmodified, complete Store source queries/projections are trusted inputs.
Structural/global source failures raise stable ValueError codes. Missing/bad
endpoints never roll back dates or silently shrink the selected peer group.
"""
    if type(queries) not in (list, tuple):
        raise ValueError("invalid_queries")
    if not 4 <= len(queries) <= MAX_MEMBERS:
        raise ValueError("member_limit")
    total = 0
    for query in queries:
        if type(query) is not dict or any(type(query.get(key)) not in (list, tuple) for key in ("rows", "unlocated")):
            raise ValueError("invalid_query")
        count = len(query["rows"]) + len(query["unlocated"])
        if count > MAX_SOURCE_ROWS:
            raise ValueError("research_row_limit")
        total += count
    if total > MAX_TOTAL_ROWS:
        raise ValueError("universe_row_limit")
    a, b = strict_date(start_date, "invalid_dates"), strict_date(end_date, "invalid_dates")
    if a >= b:
        raise ValueError("invalid_dates")
    if not _text(target):
        raise ValueError("invalid_target")
    _auxiliary(group_descriptor)
    sources, identities, snapshots = {}, {}, set()
    for query in queries:
        identity = _source(query)
        symbol = identity["symbol"]
        if symbol in sources or query["snapshot_id"] in snapshots:
            raise ValueError("duplicate_member")
        sources[symbol] = (query, identity)
        identities[symbol] = dict(symbol=symbol, snapshot_id=query["snapshot_id"], query_id=query["query_id"])
        snapshots.add(query["snapshot_id"])
    descriptor = _descriptor(group_descriptor, identities, target, a, b)
    members, changes = [], {}
    for symbol in sorted(sources):
        query, identity = sources[symbol]
        member, change = _member(query, identity, target, a, b, descriptor["events"])
        members.append(member)
        changes[symbol] = change
    all_reasons = _ordered({reason for member in members for reason in member["reasons"]})
    valid_count = sum(value is not None for value in changes.values())
    comparison = None
    if valid_count == len(members):
        peers = sorted(value for symbol, value in changes.items() if symbol != target)
        size = len(peers)
        median = peers[size // 2] if size % 2 else (peers[size // 2 - 1] + peers[size // 2]) / 2
        mean = sum(peers, Fraction()) / size
        d_median, d_mean = 100 * (changes[target] - median), 100 * (changes[target] - mean)
        comparison = dict(peer_median=_exact(median), peer_mean=_exact(mean),
                          median_difference_pp=_exact(d_median, "percentage_point"),
                          mean_difference_pp=_exact(d_mean, "percentage_point"),
                          strict_sign_disagreement=d_median * d_mean < 0)
    parameters = dict(target=target, start_date=a, end_date=b)
    identity_input = dict(method_id=METHOD_ID, rule_version=RULE_VERSION, parameters=parameters,
                          group=descriptor, sources=[identities[symbol] for symbol in sorted(identities)])
    return dict(method_id=METHOD_ID, analysis_id=hashlib.sha256(_json(identity_input).encode("utf-8")).hexdigest(),
                parameters=parameters, group=descriptor, members=members,
                coverage=dict(selected_member_count=len(members), selected_peer_count=len(members) - 1,
                              valid_member_endpoint_count=valid_count,
                              valid_peer_endpoint_count=valid_count - (changes[target] is not None),
                              target_endpoints_valid=changes[target] is not None),
                comparison=comparison, status="unavailable" if comparison is None else
                "diagnostic_only" if set(all_reasons) & _DIAGNOSTIC else "source_price_comparison_only",
                reasons=all_reasons, limitations=dict(economic_return_qualified=False, total_return_qualified=False,
                    historical_availability="unverified", closure="unknown", trading_calendar="unknown",
                    corporate_action_coverage="unknown", adjustment="request_declared_semantics_unverified",
                    source_integrity="trusted_store_boundary", membership="current_members_retrospective",
                    source_semantics="unverified", statistical_or_trading_advantage="not_evaluated"))
