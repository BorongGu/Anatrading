"""Bounded in-memory HTTP budget simulations; no Store, original data or browser.

The simulated catalog reports 20,001 rows but holds at most two fabricated rows.
This exercises real routes and _bounded_query, not import/materialization capacity,
algorithm effectiveness, real-source qualification, or Store behavior.
"""
import asyncio
from copy import deepcopy

import httpx
import pytest

import anatrading.workbench as workbench


class ForbiddenRoot:
    def __fspath__(self):
        raise AssertionError("This simulation must never resolve a Store root")


def row(ordinal, label):
    return dict(ordinal=ordinal, label=label, source_label=label, locator=f"synthetic:{ordinal}",
                values=dict(open="10", high="11", low="9", close="10", volume="100", amount="1000"),
                tokens={}, checks=[dict(name=name, outcome="pass") for name in ("ohlc_bounds", "nonnegative_prices")])


class MemoryCatalog:
    def __init__(self):
        self.calls = []
        self.sources = {
            "large-minute": (20_001, "1m", [row(1, "2026-09-29T09:31"), row(2, "2026-09-30T09:31")], []),
            "large-daily": (20_001, "1d", [row(1, "2026-09-28"), row(2, "2026-09-29")], []),
            "small-daily": (2, "1d", [row(1, "2026-09-28"), row(2, "2026-09-29")], []),
            "unlocated-large": (20_001, "1m", [], [row(1, None)]),
        }

    def snapshot_catalog(self, snapshot_id):
        count, period, _, _ = self.sources[snapshot_id]
        self.calls.append(("catalog", snapshot_id))
        return [dict(row_count=count, metadata=dict(period=period,
                     interpretation=dict(instrument="600059.SH", venue="SH", asset_type="stock")))]

    def query(self, snapshot_id, **selection):
        self.calls.append(("query", snapshot_id, deepcopy(selection)))
        count, period, rows, unlocated = self.sources[snapshot_id]
        chosen = dict(cutoff=None, ordinal_start=None, ordinal_end=None, mode="retrospective")
        chosen.update(selection)

        def includes(item):
            return ((chosen["ordinal_start"] is None or item["ordinal"] >= chosen["ordinal_start"])
                    and (chosen["ordinal_end"] is None or item["ordinal"] <= chosen["ordinal_end"])
                    and (chosen["cutoff"] is None or item["label"] is None or item["label"] <= chosen["cutoff"]))

        return dict(snapshot_id=snapshot_id, batch_id=snapshot_id, selection=chosen,
                    query_id=workbench._identity(dict(snapshot_id=snapshot_id, selection=chosen)),
                    metadata=dict(period=period), manifest=dict(qualification="synthetic_unverified"),
                    counts=dict(batch_rows=count), rows=deepcopy([item for item in rows if includes(item)]),
                    unlocated=deepcopy([item for item in unlocated if includes(item)]))

    def label_navigation(self, *_args, **_kwargs):
        return []


@pytest.fixture
def memory_app(monkeypatch):
    # Guard both construction routes before create_app: no real Store may open,
    # and even an attempted use of this root as a filesystem path must fail.
    def forbid_store(*_args, **_kwargs):
        raise AssertionError("A real or existing Store must not be accessed")

    monkeypatch.setattr(workbench.EvidenceStore, "__init__", forbid_store)
    catalog, root = MemoryCatalog(), ForbiddenRoot()

    class MemoryOwner:
        def __init__(self, received_root):
            assert received_root is root

        async def open(self):
            pass

        async def close(self):
            pass

        async def call(self, operation):
            return workbench._safe_store_call(lambda: operation(catalog))

    monkeypatch.setattr(workbench, "_StoreThread", MemoryOwner)
    return workbench.create_app(root), catalog


async def display(client, snapshot, selection):
    response = await client.get(f"/api/query/{snapshot}", params=selection)
    assert response.status_code == 200, response.text
    return response.json()["query"]


def assert_limit(response):
    assert response.status_code == 400, response.text
    assert response.json() == {"error": "query_row_limit"}
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("route,snapshot,parameter,values", [
    ("volume", "large-minute", "lookback", [20, 2]),
    ("price-channel", "large-daily", "lookback", [20, 2]),
    ("true-range", "large-daily", "period", [14, 1]),
    ("daily-volume", "large-daily", "lookback", [20, 2]),
    ("path-efficiency", "large-daily", "lookback", [10, 2]),
    ("source-pivots", "large-daily", "radius", [2, 1]),
    ("source-gaps", "large-daily", None, [None]),
    ("source-pivots", "large-minute", "radius", [2, 1]),
    ("source-gaps", "large-minute", None, [None]),
])
def test_narrow_display_and_earlier_cutoff_cannot_lower_full_catalog_budget(memory_app, route, snapshot, parameter, values):
    app, catalog = memory_app

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                early_label = catalog.sources[snapshot][2][0]["label"]
                for selection in (dict(ordinal_start=1, ordinal_end=2),
                                  dict(ordinal_start=1, ordinal_end=1, cutoff=early_label)):
                    query = await display(client, snapshot, selection)
                    assert query["counts"]["batch_rows"] == 20_001
                    assert len(query["rows"]) == selection["ordinal_end"]
                    for value in values:
                        params = dict(selection)
                        if parameter:
                            params[parameter] = value
                        if route in {"source-pivots", "source-gaps"}:
                            params["query_id"] = query["query_id"]
                        catalog.calls.clear()
                        assert_limit(await client.get(f"/api/{route}/{snapshot}", params=params))
                        assert catalog.calls == [("catalog", snapshot), ("query", snapshot, selection), ("catalog", snapshot)]
    asyncio.run(scenario())


@pytest.mark.parametrize("route", ["source-pivots", "source-gaps"])
@pytest.mark.parametrize("snapshot,selection,unlocated", [
    ("large-minute", dict(ordinal_start=1, ordinal_end=1, cutoff="2026-01-01"), 0),
    ("unlocated-large", dict(ordinal_start=1, ordinal_end=1), 1),
])
def test_pivots_and_gaps_reuse_empty_located_selection_without_context_read(memory_app, route, snapshot, selection, unlocated):
    app, catalog = memory_app

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                query = await display(client, snapshot, selection)
                assert query["rows"] == [] and len(query["unlocated"]) == unlocated
                catalog.calls.clear()
                response = await client.get(f"/api/{route}/{snapshot}", params={**selection, "query_id": query["query_id"]})
                assert response.status_code == 200, response.text
                assert response.json()["context_query_id"] == query["query_id"]
                assert catalog.calls == [("catalog", snapshot), ("query", snapshot, selection)]
    asyncio.run(scenario())


@pytest.mark.parametrize("route,parameter", [
    ("volume", "lookback"), ("price-channel", "lookback"), ("true-range", "period"),
    ("daily-volume", "lookback"), ("path-efficiency", "lookback"),
])
def test_automatic_indicators_still_request_context_for_empty_display(memory_app, route, parameter):
    app, catalog = memory_app
    snapshot = "large-minute" if route == "volume" else "large-daily"

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                selection = dict(ordinal_start=1, ordinal_end=1, cutoff="2026-01-01")
                assert (await display(client, snapshot, selection))["rows"] == []
                catalog.calls.clear()
                assert_limit(await client.get(f"/api/{route}/{snapshot}", params={**selection, parameter: 2}))
                assert catalog.calls == [("catalog", snapshot), ("query", snapshot, selection), ("catalog", snapshot)]
    asyncio.run(scenario())


def test_background_and_reconciliation_reject_large_daily_independently(memory_app):
    app, catalog = memory_app

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                selection = dict(ordinal_start=1, ordinal_end=1)
                query = await display(client, "large-minute", selection)
                assert len(query["rows"]) == 1
                for ordinal in (2, 1):
                    for window in ("all", "60", "1"):
                        catalog.calls.clear()
                        assert_limit(await client.get("/api/daily-background/large-minute", params=dict(
                            daily_snapshot="large-daily", ordinal=ordinal, window=window)))
                        assert [call for call in catalog.calls if call[0] == "query"] == [
                            ("query", "large-minute", dict(ordinal_start=ordinal, ordinal_end=ordinal))]
                        assert catalog.calls[-1] == ("catalog", "large-daily")
                # This route runs on its own; a successful background response is not required.
                catalog.calls.clear()
                assert_limit(await client.get("/api/minute-daily-reconciliation/large-minute", params=dict(
                    **selection, daily_snapshot="large-daily", query_id=query["query_id"])))
                assert [call for call in catalog.calls if call[0] == "query"] == [("query", "large-minute", selection)]
                assert catalog.calls[-1] == ("catalog", "large-daily")
                # Replacing only the paired daily version passes this budget; it does not certify source quality.
                background = await client.get("/api/daily-background/large-minute", params=dict(daily_snapshot="small-daily", ordinal=1, window=60))
                assert background.status_code == 200, background.text
                assert background.json()["pairing_status"] == "assumed_text_match"
                reconciled = await client.get("/api/minute-daily-reconciliation/large-minute", params=dict(
                    **selection, daily_snapshot="small-daily", query_id=query["query_id"]))
                assert reconciled.status_code == 200, reconciled.text
                assert reconciled.json()["qualification"] == "retrospective_source_arithmetic"
    asyncio.run(scenario())


def test_reconciliation_same_code_can_reject_minute_selection_before_daily_read(memory_app):
    app, catalog = memory_app

    async def scenario():
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                query = await display(client, "large-minute", dict(ordinal_start=1, ordinal_end=1))
                for selection in ({}, dict(ordinal_start=1, ordinal_end=20_001)):
                    catalog.calls.clear()
                    assert_limit(await client.get("/api/minute-daily-reconciliation/large-minute", params=dict(
                        **selection, daily_snapshot="small-daily", query_id=query["query_id"])))
                    assert not any(call[0] == "query" for call in catalog.calls)
                    assert catalog.calls[-1] == ("catalog", "large-minute")
    asyncio.run(scenario())
