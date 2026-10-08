"""The page reads minutes through the existing Store owner."""
import asyncio
import threading

import httpx
import pytest

from anatrading import workbench
from anatrading.tdx_acquisition import AcquireError
from test_tdx_http_format import capture, encoded


def test_read_imports_and_reuses_same_snapshot(tmp_path, monkeypatch):
    async def scenario():
        calls = []
        def read(client, symbol, **kwargs):
            calls.append((symbol, kwargs))
            return encoded(capture())
        monkeypatch.setattr(workbench, "read_minutes", read, raising=False)
        app = workbench.create_app(tmp_path / "store")
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                config = (await client.get("/api/config")).json()
                headers = {"Origin": "http://127.0.0.1:8765", "X-Anatrading-Token": config["csrf_token"]}
                url = "/api/read-tdx-minutes?symbol=600059.SH&count=720&end_time=20260930150000"
                first = await client.post(url, headers=headers)
                assert first.status_code == 200
                attempt = first.json()["attempt"]
                assert attempt["status"] == "committed"
                second = await client.post(url, headers=headers)
                assert second.json()["attempt"]["snapshot_id"] == attempt["snapshot_id"]
                query = (await client.get("/api/query/" + attempt["snapshot_id"])).json()
                assert query["query"]["rows"][0]["tokens"]["source_time"] == "93100"
                assert query["query"]["rows"][0]["values"]["volume"] == "9007199254740993"
                assert calls == [("600059.SH", {"count": 720, "end_time": "20260930150000"})] * 2
                assert len((await client.get("/api/snapshots")).json()["snapshots"]) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("case", ["token", "count", "body", "failure"])
def test_failed_read_does_not_create_snapshot(tmp_path, monkeypatch, case):
    async def scenario():
        calls = []
        def read(*args, **kwargs):
            calls.append(1)
            raise AcquireError("client_identity_unavailable")
        monkeypatch.setattr(workbench, "read_minutes", read, raising=False)
        app = workbench.create_app(tmp_path / "store")
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                token = (await client.get("/api/config")).json()["csrf_token"]
                headers = {"Origin": "http://127.0.0.1:8765", "X-Anatrading-Token": "wrong" if case == "token" else token}
                count = "0" if case == "count" else "720"
                response = await client.post(f"/api/read-tdx-minutes?symbol=600059.SH&count={count}",
                                             headers=headers, content=b"unexpected" if case == "body" else b"")
                assert response.status_code in (400, 403, 409)
                if case == "failure": assert response.json() == {"error": "client_identity_unavailable"}
                assert calls == ([1] if case == "failure" else [])
                assert (await client.get("/api/snapshots")).json()["snapshots"] == []
    asyncio.run(scenario())


def test_duplicate_click_is_rejected_while_read_is_active(tmp_path, monkeypatch):
    async def scenario():
        started, release = threading.Event(), threading.Event()
        def read(*args, **kwargs):
            started.set()
            assert release.wait(5)
            return encoded(capture())
        monkeypatch.setattr(workbench, "read_minutes", read, raising=False)
        app = workbench.create_app(tmp_path / "store")
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                token = (await client.get("/api/config")).json()["csrf_token"]
                headers = {"Origin": "http://127.0.0.1:8765", "X-Anatrading-Token": token}
                url = "/api/read-tdx-minutes?symbol=600059.SH&count=720"
                first = asyncio.create_task(client.post(url, headers=headers))
                try:
                    assert await asyncio.to_thread(started.wait, 2)
                    duplicate = await client.post(url, headers=headers)
                    assert duplicate.status_code == 409
                    assert duplicate.json() == {"error": "upload_in_progress"}
                    assert (await client.get("/api/config")).status_code == 200
                finally:
                    release.set()
                    await first
    asyncio.run(scenario())
