import asyncio
import json

import httpx

from anatrading.store import EvidenceStore
from anatrading.workbench import create_app
from test_tdx_http_format import capture, encoded


def test_volume_window_preserves_history_and_matches_query_identity(tmp_path):
    root = tmp_path / "store"
    bundle = capture()
    response = json.loads(bundle["response_utf8"])
    stock = response["result"]["Value"]["600059.SH"]
    for key in ("Date", "Time", "Open", "High", "Low", "Close", "Volume", "Amount", "ForwardFactor"):
        stock[key] *= 3
    stock["Date"] = ["20260928", "20260929", "20260930"]
    stock["Volume"] = ["10", "30", "50"]
    bundle["response_utf8"] = json.dumps(response)
    with EvidenceStore(root) as store:
        snapshot = store.import_bytes(encoded(bundle), "tdx-http-market-v1")["snapshot_id"]

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                path = "/api/volume/" + snapshot
                default = (await client.get(path)).json()
                assert default["lookback"] == 20 and default["rows"][-1]["regular"]["reason"] == "history_insufficient"
                params = dict(ordinal_start=3, ordinal_end=3, cutoff="2026-09-30T09:31")
                q = (await client.get("/api/query/" + snapshot, params=params)).json()["query"]
                response = await client.get(path, params={**params, "lookback": 2})
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                result = response.json()
                assert result["query_id"] == q["query_id"]
                assert result["context_query_id"] != q["query_id"]
                assert len(result["rows"]) == 1
                assert result["rows"][0]["history_dates"] == ["2026-09-28", "2026-09-29"]
                assert result["rows"][0]["regular"]["ratio"]["display"] == "2.5000"
                for bad in ("1", "253", "two", "2.0"):
                    assert (await client.get(path, params=dict(lookback=bad))).status_code == 400
                assert (await client.get(path + "?lookback=2&lookback=3")).status_code == 400
    asyncio.run(scenario())
