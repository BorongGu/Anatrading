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


def _load(store, ids, cutoff, error):
    # Reject budgets before loading any source rows or constructing a report.
    counts = [store.query_row_count(sid, cutoff=cutoff) for sid in ids]
    if any(n > MAX_SERIES_ROWS for n in counts) or sum(counts) > MAX_TOTAL_ROWS:
        raise error("research_row_limit")
    queries = [store.query(sid, cutoff=cutoff) for sid in ids]
    if any(q["metadata"].get("period") != "1d" for q in queries):
        raise error("unsupported_period")
    return queries


def _calculate(kind, queries, parameters, error):
    # Lazy imports keep the HTTP shell independent of optional analysis modules
    # during module initialization, and avoid any Store dependency in formulas.
    from .signal_research import signal_report
    from .pair_research import pair_report
    from .universe_research import universe_report

    try:
        if kind == "single":
            result = signal_report(queries[0], lookback=parameters["lookback"],
                                   horizon=parameters["horizon"], test_start=parameters["test_start"])
        elif kind == "pair":
            result = pair_report(queries[0], queries[1], lookback=parameters["lookback"])
        else:
            result = universe_report(queries, cutoff=parameters["cutoff"], lookback=parameters["lookback"])
    except ValueError as exc:
        code = str(exc)
        raise error(code if code in _SAFE_ERRORS else "invalid_research_input") from None
    inputs = [dict(snapshot_id=q["snapshot_id"], query_id=q["query_id"]) for q in queries]
    parameters = {**parameters, "model": result.get("parameters", {})}
    identity = dict(method_id=_METHODS[kind], inputs=inputs, parameters=parameters)
    return dict(**identity, analysis_id=_identity(identity), mode="retrospective",
                limitations=[*_LIMITATIONS, *(["current_selected_membership"] if kind == "universe" else [])], result=result)


def register_research_routes(app, owner, parse_parameters, error):
    """Reuse the established local HTTP boundary and error mapping."""
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
            lambda store: _calculate("universe", _load(store, ids, cutoff, error), params, error)))
