"""Synthetic temporary Store and in-process HTTP only; no external reads."""
import asyncio
import hashlib
import json

import httpx

from anatrading.store import EvidenceStore
from anatrading.workbench import create_app
from test_tdx_http_format import capture, encoded


def synthetic_bundle():
    bundle = capture()
    response = json.loads(bundle["response_utf8"])
    stock = response["result"]["Value"]["600059.SH"]
    size = 16
    for key in ("Date", "Time", "Open", "High", "Low", "Close", "Volume", "Amount", "ForwardFactor"):
        stock[key] *= size
    stock["Date"] = [f"202609{day}" for day in range(21, 29) for _ in range(2)]
    stock["Time"] = ["145700", "150000"] * 8
    stock["Close"] = ["11.30", "11.20"] * 8
    bundle["response_utf8"] = json.dumps(response)
    return bundle


def test_api_full_context_binding_cutoff_and_strict_parameters(tmp_path):
    root = tmp_path / "synthetic-store"
    raw = encoded(synthetic_bundle())
    with EvidenceStore(root) as store:
        snapshot = store.import_bytes(raw, "tdx-http-market-v1")["snapshot_id"]

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                path = "/api/minute-label-history/" + snapshot
                selection = dict(ordinal_start=16, ordinal_end=16, cutoff="2026-09-28T15:00", mode="retrospective")
                query = (await client.get("/api/query/" + snapshot, params=selection)).json()["query"]
                params = dict(**selection, query_id=query["query_id"], source_date="2026-09-28", start_clock="14:57", end_clock="15:00")
                response = await client.get(path, params=params)
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                result = response.json()
                assert result["query_id"] == query["query_id"] and result["context_query_id"] != query["query_id"]
                assert result["raw_sha256"] == hashlib.sha256(raw).hexdigest()
                assert result["batch_id"] == query["batch_id"] and result["versions"] == query["manifest"]["versions"]
                assert result["metadata"] == query["metadata"] and result["contract"] == query["manifest"]["contract"]
                assert result["nominal_minutes"] == 3 and result["window_status"] == "complete"
                assert result["history_dates"] == [f"2026-09-{d}" for d in range(23, 28)]
                current = result["days"][0]
                assert current["start"][0]["ordinal"] == 15 and current["end"][0] == query["rows"][0]
                assert current["change"]["numerator"] == "-1" and current["change"]["denominator"] == "113"
                assert current["start"][0]["tokens"]["close"] == "11.30"
                full = (await client.get("/api/query/" + snapshot, params=dict(cutoff="2026-09-28T15:00", mode="retrospective"))).json()["query"]
                assert result["context_query_id"] == full["query_id"]
                again = await client.get(path, params=params)
                assert again.json() == result
                assert (await client.get(path, params={**params, "query_id": "f" * 64})).status_code == 409
                for changes in ({"start_clock": "9:31"}, {"start_clock": "15:00"}, {"end_clock": "14:00"},
                                {"source_date": "2026-09-29"}, {"cutoff": "2026-09-28T14:59"},
                                {"source_date": "20260928"}, {"mode": "live"}, {"unexpected": "1"}):
                    assert (await client.get(path, params={**params, **changes})).status_code == 400
                assert (await client.get(path, params={k: v for k, v in params.items() if k != "start_clock"})).status_code == 400
                assert (await client.get(path, params=[*params.items(), ("start_clock", "14:55")])).status_code == 400
    asyncio.run(scenario())


def test_api_rejects_oversized_full_context_before_materializing_it(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-store"
    with EvidenceStore(root) as store:
        snapshot = store.import_bytes(encoded(synthetic_bundle()), "tdx-http-market-v1")["snapshot_id"]
        original = store.query(snapshot, ordinal_start=16, ordinal_end=16)
    catalog = EvidenceStore.snapshot_catalog
    query = EvidenceStore.query
    reads = []

    def oversized(self, *args, **kwargs):
        result = catalog(self, *args, **kwargs)
        for item in result: item["row_count"] = 20_001
        return result

    def track(self, *args, **kwargs):
        reads.append(kwargs)
        return query(self, *args, **kwargs)

    monkeypatch.setattr(EvidenceStore, "snapshot_catalog", oversized)
    monkeypatch.setattr(EvidenceStore, "query", track)

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                response = await client.get("/api/minute-label-history/" + snapshot,
                    params=dict(query_id=original["query_id"], ordinal_start=16, ordinal_end=16,
                                source_date="2026-09-28", start_clock="14:57", end_clock="15:00"))
                assert response.status_code == 400 and response.json()["error"] == "query_row_limit"
    asyncio.run(scenario())
    assert reads == [dict(ordinal_start=16, ordinal_end=16)]


def test_api_response_limit_is_a_stable_failure(tmp_path, monkeypatch):
    import anatrading.minute_label_history as helper
    root = tmp_path / "synthetic-store"
    with EvidenceStore(root) as store:
        snapshot = store.import_bytes(encoded(synthetic_bundle()), "tdx-http-market-v1")["snapshot_id"]
        query = store.query(snapshot)
    monkeypatch.setattr(helper, "MAX_RESPONSE_BYTES", 100)

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                response = await client.get("/api/minute-label-history/" + snapshot,
                    params=dict(query_id=query["query_id"], source_date="2026-09-28", start_clock="14:57", end_clock="15:00"))
                assert response.status_code == 400 and response.json()["error"] == "response_limit"
    asyncio.run(scenario())
