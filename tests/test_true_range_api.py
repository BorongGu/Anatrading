import asyncio

import httpx

from anatrading.store import EvidenceStore
from anatrading.workbench import create_app
from test_formats import bao_payload


def test_range_api_keeps_seed_history_under_cutoff_and_display_selection(tmp_path):
    root = tmp_path / "store"
    raw = bao_payload([[f"2026-09-{day:02d}", "sh.600059", close, high, low, close, "100", "1000", "3"]
                       for day, high, low, close in [(1, "10", "8", "9"), (2, "13", "11", "12"),
                                                    (3, "12", "8", "9"), (4, "15", "14", "14")]], code="sh.600059")
    with EvidenceStore(root) as store:
        sid = store.import_bytes(raw, "baostock-decoded-v0.9.4")["snapshot_id"]

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                path = "/api/true-range/" + sid
                all_values = (await client.get(path, params=dict(period=2))).json()
                params = dict(ordinal_start=4, ordinal_end=4, cutoff="2026-09-04")
                q = (await client.get("/api/query/" + sid, params=params)).json()["query"]
                response = await client.get(path, params={**params, "period": 2})
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                report = response.json()
                assert report["query_id"] == q["query_id"] and report["context_query_id"] != q["query_id"]
                assert report["rows"] == all_values["rows"][-1:]
                assert report["rows"][0]["atr"]["value"] == "5"
                assert report["seed_dates"] == ["2026-09-02", "2026-09-03"]
                earlier = (await client.get(path, params=dict(period=2, cutoff="2026-09-03"))).json()
                assert earlier["rows"] == all_values["rows"][:3]
                assert (await client.get(path)).json()["period"] == 14
                for bad in ("0", "253", "two", "2.0"):
                    assert (await client.get(path, params=dict(period=bad))).status_code == 400
                for suffix in ("?period=2&period=3", "?unknown=1", "?mode=point-in-time"):
                    assert (await client.get(path + suffix)).status_code == 400
    asyncio.run(scenario())
