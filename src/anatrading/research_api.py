"""Bounded, read-only adapters for retrospective stock research.

All store work stays on the application's existing owner thread. Numerical
reports are pure functions; this module alone binds them to source identities.
"""
from datetime import date
import re

from fastapi import Request
from starlette.responses import JSONResponse

from .store import _identity

MAX_SERIES_ROWS = 20_000
MAX_TOTAL_ROWS = 200_000
MAX_MEMBERS = 50
_METHODS = {
    "single": "daily-causal-research-v1",
    "pair": "paired-daily-research-v1",
    "universe": "selected-universe-research-v1",
    "path-match": "historical-source-path-retrieval-v1",
}
_LIMITATIONS = [
    "retrospective_source_version", "adjustment_basis_unverified",
    "historical_availability_unverified", "calendar_and_bar_closure_unverified",
    "descriptive_estimates_not_trading_returns",
]
_SAFE_ERRORS = {
    "unsupported_period", "invalid_lookback", "invalid_horizon", "invalid_test_start",
    "duplicate_instrument", "unknown_instrument", "incompatible_market", "unknown_market",
    "same_instrument", "same_snapshot", "invalid_cutoff", "invalid_series",
    "invalid_parameters", "invalid_universe", "invalid_member_count",
    "research_market_unknown", "research_identity_conflict", "research_duplicate_symbol",
    "research_identity_unknown", "research_market_mismatch",
    "research_identity_unavailable", "research_duplicate_snapshot", "research_cutoff_mismatch",
    "research_invalid_member_count", "research_total_row_limit", "research_row_limit",
    "invalid_label_cutoff",
}


def _day(value, error):
    try:
        if not isinstance(value, str) or len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError
    except ValueError:
        raise error("invalid_research_date") from None
    return value


def _identifier(value, error):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise error("invalid_snapshot_id")
    return value


def _window(value, lower, error):
    if not isinstance(value, str) or re.fullmatch(r"[0-9]{1,3}", value) is None:
        raise error("invalid_lookback")
    number = int(value)
    if not lower <= number <= 252:
        raise error("invalid_lookback")
    return number


def _research_budget(store, ids, cutoff, error):
    # Every count completes before checking limits; no source has been loaded.
    counts = [store.query_row_count(sid, cutoff=cutoff) for sid in ids]
    if any(n > MAX_SERIES_ROWS for n in counts) or sum(counts) > MAX_TOTAL_ROWS:
        raise error("research_row_limit")


def _load(store, ids, cutoff, error):
    _research_budget(store, ids, cutoff, error)
    queries = [store._research_query(sid, cutoff=cutoff) for sid in ids]
    if any(q["metadata"].get("period") != "1d" for q in queries):
        raise error("unsupported_period")
    return queries


def _research_call(operation, error):
    try:
        return operation()
    except ValueError as exc:
        code = str(exc)
        raise error(code if code in _SAFE_ERRORS else "invalid_research_input") from None


def _filter_call(operation, error):
    from .stock_filters import FILTER_ERRORS

    try:
        return operation()
    except ValueError as exc:
        code = str(exc)
        if code in _SAFE_ERRORS or code in FILTER_ERRORS:
            raise error(code) from None
        raise  # Unknown failures retain the owner's controlled mapping.


def _envelope(kind, queries, parameters, result):
    inputs = [dict(snapshot_id=q["snapshot_id"], query_id=q["query_id"]) for q in queries]
    parameters = {**parameters, "model": result.get("parameters", {})}
    identity = dict(method_id=_METHODS[kind], inputs=inputs, parameters=parameters)
    return dict(**identity, analysis_id=_identity(identity), mode="retrospective",
                limitations=[*_LIMITATIONS, *(["current_selected_membership"] if kind == "universe" else [])], result=result)


def _calculate(kind, queries, parameters, error):
    # Lazy imports keep the HTTP shell independent of optional analysis modules
    # during module initialization, and avoid any Store dependency in formulas.
    from .signal_research import signal_report
    from .pair_research import pair_report
    from .universe_research import universe_report

    def calculate():
        if kind == "single":
            return signal_report(queries[0], lookback=parameters["lookback"],
                                 horizon=parameters["horizon"], test_start=parameters["test_start"])
        if kind == "pair":
            return pair_report(queries[0], queries[1], lookback=parameters["lookback"])
        return universe_report(queries, cutoff=parameters["cutoff"], lookback=parameters["lookback"])

    result = _research_call(calculate, error)
    # Source/envelope identities stay outside the calculation ValueError guard.
    return _envelope(kind, queries, parameters, result)


def _capture_preparation(operation, guard, error, safe_store_call):
    """Retain only the existing boundary's safe code/status, never an exception."""
    try:
        return safe_store_call(lambda: guard(operation, error)), None
    except error as exc:
        return None, (exc.code, exc.status)


def _prepare_source(store, sid, cutoff, lookback, guard, error, safe_store_call):
    from .universe_research import _at_cutoff, _prepare_window

    # Read errors bypass deferred preparation entirely, including bad JSON.
    query = store._research_query(sid, cutoff=cutoff)
    header = {key: query[key] for key in (
        "snapshot_id", "batch_id", "query_id", "selection", "manifest", "metadata",
        "batch_checks", "counts", "read_projection") if key in query}
    selected, selection_error = _capture_preparation(
        lambda: _at_cutoff(query, cutoff), guard, error, safe_store_call)
    result = dict(header=header, selected_count=None, selection_error=selection_error,
                  prepared=None, preparation_error=None)
    if selection_error is None:
        result["selected_count"] = len(selected["rows"]) + len(selected.get("unlocated", []))
        result["prepared"], result["preparation_error"] = _capture_preparation(
            lambda: _prepare_window(selected, cutoff, lookback), guard, error, safe_store_call)
    # This function ends before the next source read. No full rows escape.
    return result


def _load_universe(store, ids, cutoff, lookback, guard, error, safe_store_call):
    _research_budget(store, ids, cutoff, error)
    prepared = [_prepare_source(store, sid, cutoff, lookback, guard, error, safe_store_call) for sid in ids]
    if any(item["header"]["metadata"].get("period") != "1d" for item in prepared):
        raise error("unsupported_period")
    return prepared


def _prepared_evaluation(prepared, cutoff, lookback, error, *, with_evidence=False):
    from .universe_research import _universe_identities, _evaluate_members

    headers = [item["header"] for item in prepared]
    identities = _universe_identities(headers, cutoff, lookback)
    for item in prepared:
        if item["selection_error"] is not None:
            raise error(*item["selection_error"])
    if sum(item["selected_count"] for item in prepared) > MAX_TOTAL_ROWS:
        raise ValueError("research_total_row_limit")

    def windows():
        for item in prepared:
            if item["preparation_error"] is not None:
                raise error(*item["preparation_error"])
            yield item["prepared"]

    return _evaluate_members(headers, identities, windows(), cutoff, lookback,
                             with_evidence=with_evidence)


def _calculate_universe(store, ids, parameters, error, safe_store_call):
    cutoff, lookback = parameters["cutoff"], parameters["lookback"]
    prepared = _load_universe(store, ids, cutoff, lookback, _research_call, error, safe_store_call)
    result = _research_call(lambda: _prepared_evaluation(prepared, cutoff, lookback, error)[0], error)
    return _envelope("universe", [item["header"] for item in prepared], parameters, result)


def _calculate_filter(store, ids, cutoff, lookback, rule, error, safe_store_call):
    from .stock_filters import _filter_inputs, _assemble_filter

    prepared = _load_universe(store, ids, cutoff, lookback, _filter_call, error, safe_store_call)

    def calculate():
        canonical, headers = _filter_inputs([item["header"] for item in prepared], cutoff, rule)
        universe, evidence = _prepared_evaluation(prepared, cutoff, lookback, error, with_evidence=True)
        return _assemble_filter(headers, cutoff, lookback, canonical, universe, evidence)

    return _filter_call(calculate, error)


def _calculate_path(store, sid, cutoff, error):
    from .historical_path_retrieval import (
        MAX_RESULT_BYTES, PATH_ERRORS, _json_bytes, historical_path_report,
    )

    queries = _load(store, [sid], cutoff, error)
    try:
        result = historical_path_report(queries[0], cutoff)
    except ValueError as exc:
        code = str(exc)
        raise error(code if code in _SAFE_ERRORS or code in PATH_ERRORS else "invalid_research_input") from None
    envelope = _envelope("path-match", queries, dict(cutoff=cutoff), result)
    if len(_json_bytes(envelope)) > MAX_RESULT_BYTES:
        raise error("path_result_limit")
    return envelope


def register_research_routes(app, owner, parse_parameters, error, safe_store_call):
    """Reuse the established local HTTP boundary and error mapping."""
    @app.get("/api/research/peer-neighbors")
    async def peer_neighbors(request: Request):
        from .peer_neighbor_research import peer_neighbor_report, ERRORS
        p = parse_parameters(request, {"snapshot_ids", "target_snapshot_id", "cutoff"},
                             ("snapshot_ids", "target_snapshot_id", "cutoff"))
        if len(p["snapshot_ids"]) > MAX_MEMBERS * 65:
            raise error("research_member_limit")
        ids = [_identifier(sid, error) for sid in p["snapshot_ids"].split(",")]
        if not 2 <= len(ids) <= MAX_MEMBERS:
            raise error("research_member_limit")
        if len(set(ids)) != len(ids):
            raise error("duplicate_snapshot")
        target = _identifier(p["target_snapshot_id"], error)
        if target not in ids:
            raise error("invalid_target")
        cutoff = _day(p["cutoff"], error)
        ids.sort()
        def calculate(store):
            _research_budget(store, ids, None, error)
            queries = [store._research_query(sid, cutoff=None) for sid in ids]
            try:
                return peer_neighbor_report(queries, target, cutoff)
            except ValueError as exc:
                code = str(exc)
                raise error(code if code in ERRORS else "invalid_research_input") from None
        return JSONResponse(await owner.call(lambda store: safe_store_call(lambda: calculate(store))))

    @app.get("/api/research/group-endpoints")
    async def group_endpoints(request: Request):
        from .peer_relative_research import group_endpoint_report, GROUP_ERRORS
        p = parse_parameters(request, {"snapshot_ids", "start_date", "end_date"},
                             ("snapshot_ids", "start_date", "end_date"))
        if len(p["snapshot_ids"]) > MAX_MEMBERS * 65:
            raise error("research_member_limit")
        ids = [_identifier(sid, error) for sid in p["snapshot_ids"].split(",")]
        if not 4 <= len(ids) <= MAX_MEMBERS:
            raise error("research_member_limit")
        if len(set(ids)) != len(ids):
            raise error("duplicate_snapshot")
        ids.sort()
        start, end = _day(p["start_date"], error), _day(p["end_date"], error)
        if start >= end:
            raise error("invalid_dates")
        def calculate(store):
            _research_budget(store, ids, None, error)
            queries = [store._research_query(sid, cutoff=None) for sid in ids]
            try:
                return group_endpoint_report(queries, start, end)
            except ValueError as exc:
                code = str(exc)
                raise error(code if code in GROUP_ERRORS else "invalid_research_input") from None
        return JSONResponse(await owner.call(lambda store: safe_store_call(lambda: calculate(store))))

    @app.get("/api/research/two-group-explanation")
    async def two_group_explanation(request: Request):
        from .two_group_explanation import two_group_report, ERRORS
        p = parse_parameters(request, {"snapshot_ids", "group_a", "group_b", "current_start", "current_end"},
                             ("snapshot_ids", "group_a", "group_b", "current_start", "current_end"))
        if any(len(p[key]) > MAX_MEMBERS * 65 for key in ("snapshot_ids", "group_a", "group_b")):
            raise error("research_member_limit")
        ids = [_identifier(sid, error) for sid in p["snapshot_ids"].split(",")]
        groups = {key: [_identifier(sid, error) for sid in p[name].split(",")]
                  for key, name in (("A", "group_a"), ("B", "group_b"))}
        if not 4 <= len(ids) <= MAX_MEMBERS:
            raise error("research_member_limit")
        if len(set(ids)) != len(ids):
            raise error("duplicate_snapshot")
        if (any(len(group) < 2 for group in groups.values()) or
                len(set(groups["A"] + groups["B"])) != len(groups["A"] + groups["B"]) or
                set(groups["A"] + groups["B"]) != set(ids)):
            raise error("invalid_groups")
        start, end = _day(p["current_start"], error), _day(p["current_end"], error)
        if start >= end:
            raise error("invalid_dates")
        def calculate(store):
            queries = _load(store, ids, None, error)
            try:
                return two_group_report(queries, groups, start, end)
            except ValueError as exc:
                code = str(exc)
                raise error(code if code in ERRORS or code in _SAFE_ERRORS else "invalid_research_input") from None
        return JSONResponse(await owner.call(lambda store: safe_store_call(lambda: calculate(store))))

    @app.get("/api/research/path-match/{snapshot_id}")
    async def path_match(snapshot_id: str, request: Request):
        sid = _identifier(snapshot_id, error)
        p = parse_parameters(request, {"cutoff"}, ("cutoff",))
        cutoff = _day(p["cutoff"], error)
        try:
            result = await owner.call(lambda store: _calculate_path(store, sid, cutoff, error))
        except error as exc:
            if exc.code != "path_result_limit":
                raise
            return JSONResponse(dict(error=exc.code, method_id=_METHODS["path-match"],
                                     snapshot_id=sid, cutoff=cutoff), status_code=exc.status)
        return JSONResponse(result)

    @app.get("/api/research/single/{snapshot_id}")
    async def single(snapshot_id: str, request: Request):
        sid = _identifier(snapshot_id, error)
        p = parse_parameters(request, {"cutoff", "lookback", "horizon", "test_start"})
        cutoff = _day(p["cutoff"], error) if "cutoff" in p else None
        split = _day(p["test_start"], error) if "test_start" in p else None
        if split is not None and cutoff is not None and split > cutoff:
            raise error("invalid_test_start")
        lookback = _window(p.get("lookback", "20"), 2, error)
        horizon_text = p.get("horizon", "5")
        if horizon_text not in {"1", "5", "10", "20"}:
            raise error("invalid_horizon")
        params = dict(cutoff=cutoff, lookback=lookback, horizon=int(horizon_text), test_start=split)
        return JSONResponse(await owner.call(
            lambda store: _calculate("single", _load(store, [sid], cutoff, error), params, error)))

    @app.get("/api/research/pair")
    async def pair(request: Request):
        p = parse_parameters(request, {"left", "right", "cutoff", "lookback"}, ("left", "right", "cutoff"))
        ids = [_identifier(p[name], error) for name in ("left", "right")]
        if ids[0] == ids[1]:
            raise error("duplicate_snapshot")
        cutoff = _day(p["cutoff"], error)
        params = dict(cutoff=cutoff, lookback=_window(p.get("lookback", "20"), 5, error))
        return JSONResponse(await owner.call(
            lambda store: _calculate("pair", _load(store, ids, cutoff, error), params, error)))

    @app.get("/api/research/universe")
    async def universe(request: Request):
        p = parse_parameters(request, {"snapshot_ids", "cutoff", "lookback"}, ("snapshot_ids", "cutoff"))
        if len(p["snapshot_ids"]) > MAX_MEMBERS * 65:
            raise error("research_member_limit")
        ids = [_identifier(sid, error) for sid in p["snapshot_ids"].split(",")]
        if not 2 <= len(ids) <= MAX_MEMBERS:
            raise error("research_member_limit")
        if len(set(ids)) != len(ids):
            raise error("duplicate_snapshot")
        ids.sort()  # Membership identity and tie ordering are request-order invariant.
        cutoff = _day(p["cutoff"], error)
        params = dict(cutoff=cutoff, lookback=_window(p.get("lookback", "20"), 2, error))
        return JSONResponse(await owner.call(
            lambda store: _calculate_universe(store, ids, params, error, safe_store_call)))

    @app.get("/api/research/universe-filter")
    async def universe_filter(request: Request):
        from .stock_filters import FILTER_ERRORS, parse_rule

        p = parse_parameters(request, {"snapshot_ids", "cutoff", "lookback", "rule"},
                             ("snapshot_ids", "cutoff", "rule"))
        # Reject rule size/shape before any Store call; do not fall back to an
        # unfiltered universe when a supplied rule is invalid.
        try:
            rule = parse_rule(p["rule"])
        except ValueError as exc:
            raise error(str(exc) if str(exc) in FILTER_ERRORS else "invalid_filter_rule") from None
        if len(p["snapshot_ids"]) > MAX_MEMBERS * 65:
            raise error("research_member_limit")
        ids = [_identifier(sid, error) for sid in p["snapshot_ids"].split(",")]
        if not 2 <= len(ids) <= MAX_MEMBERS:
            raise error("research_member_limit")
        if len(set(ids)) != len(ids):
            raise error("duplicate_snapshot")
        ids.sort()
        cutoff = _day(p["cutoff"], error)
        lookback = _window(p.get("lookback", "20"), 2, error)

        return JSONResponse(await owner.call(
            lambda store: _calculate_filter(store, ids, cutoff, lookback, rule, error, safe_store_call)))
