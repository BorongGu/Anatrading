import asyncio

import httpx

from anatrading.store import EvidenceStore
from anatrading.workbench import create_app
from test_formats import bao_payload


def test_api_full_history_cutoff_selection_and_parameter_validation(tmp_path):
    root = tmp_path / "store"
    data = bao_payload([[f"2026-09-{day}", "sh.600059", opening, high, low, close, "100", "1000", "3"]
                        for day, opening, high, low, close in [
                            (28, "10", "12", "8", "11"), (29, "11", "13", "9", "12"),
                            (30, "12", "14", "7", "13")]], code="sh.600059")
    with EvidenceStore(root) as store:
        sid = store.import_bytes(data, "baostock-decoded-v0.9.4")["snapshot_id"]

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                path = "/api/price-channel/" + sid
                default = (await client.get(path)).json()
                assert default["lookback"] == 20 and default["rows"][-1]["reason"] == "history_insufficient"
                params = dict(ordinal_start=3, ordinal_end=3, cutoff="2026-09-30")
                q = (await client.get("/api/query/" + sid, params=params)).json()["query"]
                response = await client.get(path, params={**params, "lookback": 2})
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                result = response.json()
                assert result["query_id"] == q["query_id"] and result["context_query_id"] != q["query_id"]
                assert len(result["rows"]) == 1
                value = result["rows"][0]
                assert (value["upper"], value["lower"], value["range_relation"], value["close_relation"]) == ("13", "8", "both", "touch_upper")
                assert [m["ordinals"] for m in value["members"]] == [[1], [2]]
                truncated = (await client.get(path, params=dict(cutoff="2026-09-29", lookback=2))).json()
                assert len(truncated["rows"]) == 2 and all(r["reason"] == "history_insufficient" for r in truncated["rows"])
                for bad in ("1", "253", "two", "2.0"):
                    assert (await client.get(path, params=dict(lookback=bad))).status_code == 400
                for suffix in ("?lookback=2&lookback=3", "?unknown=1", "?mode=point-in-time"):
                    assert (await client.get(path + suffix)).status_code == 400
    asyncio.run(scenario())
