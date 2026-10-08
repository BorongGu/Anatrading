"""Owned shutdown accepts no new Store work and survives response delivery errors."""
import asyncio
from contextlib import asynccontextmanager
import os
import threading

import httpx
import pytest

import anatrading.workbench as module
from anatrading.store import EvidenceStore
from test_workbench import row, source, upload


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows Store ownership")
ORIGIN = "http://127.0.0.1:8765"


@asynccontextmanager
async def running(root, callback=None):
    app = module.create_app(root, on_shutdown=callback)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            token = (await client.get("/api/config")).json()["csrf_token"]
            yield app, client, {"Origin": ORIGIN, "X-Anatrading-Token": token}


async def raw_shutdown(app, auth, *, query=b"", chunks=(), disconnect=False, headers=None,
                       send_fault=None, send_cancel=False, trace=None):
    pending, messages, reads = list(chunks), [], []
    async def receive():
        reads.append(True)
        if pending:
            return {"type": "http.request", "body": pending.pop(0), "more_body": bool(pending) or disconnect}
        return {"type": "http.disconnect"} if disconnect else {"type": "http.request", "body": b"", "more_body": False}
    async def send(message):
        messages.append(message)
        if trace is not None:
            trace.append(message["type"])
        if message["type"] == send_fault:
            if send_cancel:
                raise asyncio.CancelledError
            raise OSError("synthetic response delivery failure")
    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
               "scheme": "http", "path": "/api/shutdown", "raw_path": b"/api/shutdown", "query_string": query,
               "headers": headers if headers is not None else [(b"host", b"127.0.0.1:8765"),
                   (b"origin", auth["Origin"].encode()), (b"x-anatrading-token", auth["X-Anatrading-Token"].encode())],
               "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8765)}, receive, send)
    return messages, len(reads)


def test_missing_shutdown_callback_keeps_store_accepting(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            reply = await client.post("/api/shutdown", headers=auth)
            assert reply.status_code == 503 and reply.json() == {"error": "shutdown_unavailable"}
            assert (await client.get("/api/attempts")).status_code == 200
    asyncio.run(scenario())


class AsyncCallback:
    async def __call__(self):
        pass


async def async_callback():
    pass


@pytest.mark.parametrize("callback", [False, 1, "exit", object(), async_callback, AsyncCallback()])
def test_invalid_callback_rejected_without_opening_store(tmp_path, callback):
    with pytest.raises(ValueError, match="^invalid_shutdown_callback$"):
        module.create_app(tmp_path / "unused", on_shutdown=callback)
    assert not (tmp_path / "unused").exists()


@pytest.mark.parametrize("query,chunks,disconnect", [
    (b"pid=1234", (), False), (b"x=1&x=2", (), False),
    (b"", (b"nonempty",), False), (b"", (b"", b"nonempty"), False),
    (b"", (), True), (b"", (b"",), True),
])
def test_invalid_request_or_disconnect_keeps_store_accepting(tmp_path, query, chunks, disconnect):
    calls = []
    async def scenario():
        async with running(tmp_path / "root", lambda: calls.append("exit")) as (app, client, auth):
            messages, _ = await raw_shutdown(app, auth, query=query, chunks=chunks, disconnect=disconnect)
            assert 400 <= messages[0]["status"] < 500 and calls == []
            assert (await client.get("/api/attempts")).status_code == 200
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["http.response.start", "http.response.body"])
def test_response_cancellation_still_requests_owned_exit_once(tmp_path, fault):
    calls = []
    async def scenario():
        async with running(tmp_path / "root", lambda: calls.append("exit")) as (app, client, auth):
            with pytest.raises(asyncio.CancelledError):
                await raw_shutdown(app, auth, send_fault=fault, send_cancel=True)
            assert calls == ["exit"]
            assert (await client.get("/api/attempts")).status_code == 503
            assert (await client.post("/api/shutdown", headers=auth)).status_code == 202
            assert calls == ["exit"]
    asyncio.run(scenario())


def test_shutdown_ack_and_callback_order_and_repetition(tmp_path):
    trace, calls = [], []
    async def scenario():
        loop_thread = threading.get_ident()
        def callback():
            calls.append((threading.get_ident(), tuple(trace)))
        async with running(tmp_path / "root", callback) as (app, client, auth):
            messages, _ = await raw_shutdown(app, auth, trace=trace)
            assert messages[0]["status"] == 202
            assert calls == [(loop_thread, ("http.response.start", "http.response.body"))]
            repeated = await asyncio.gather(*(client.post("/api/shutdown", headers=auth) for _ in range(3)))
            expected = {"status": "shutdown_requested", "data_root_id": module.data_root_id(tmp_path / "root")}
            assert all(r.status_code == 202 and r.json() == expected and r.headers["cache-control"] == "no-store" for r in repeated)
            assert len(calls) == 1
            for path in ("/api/attempts", "/api/snapshots", "/api/query/" + "0" * 64):
                reply = await client.get(path)
                assert reply.status_code == 503 and reply.json() == {"error": "service_closing"}
            assert (await upload(client, auth, source(row()))).status_code == 503
    asyncio.run(scenario())


def test_response_construction_failure_does_not_half_close_owner(tmp_path, monkeypatch):
    calls = []
    async def scenario():
        async with running(tmp_path / "root", lambda: calls.append("exit")) as (_, client, auth):
            def failed(root):
                raise OSError("synthetic root identity failure")
            monkeypatch.setattr(module, "data_root_id", failed)
            assert (await client.post("/api/shutdown", headers=auth)).status_code == 500
            assert calls == [] and (await client.get("/api/attempts")).status_code == 200
    asyncio.run(scenario())


def test_upload_started_before_shutdown_is_rejected_after_body_completes(tmp_path, monkeypatch):
    owners = []
    class Owner(module._StoreThread):
        def __init__(self, root):
            super().__init__(root)
            owners.append(self)
    monkeypatch.setattr(module, "_StoreThread", Owner)
    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        async def body():
            entered.set()
            await release.wait()
            yield source(row())
        async with running(tmp_path / "root", lambda: None) as (_, client, auth):
            request = asyncio.create_task(client.post("/api/import", params={"format_id": "tdx-public-text-v1", "filename": "synthetic.txt"},
                headers={**auth, "Content-Type": "application/octet-stream"}, content=body()))
            try:
                await asyncio.wait_for(entered.wait(), 2)
                assert owners[0].pending == 0
                assert (await client.post("/api/shutdown", headers=auth)).status_code == 202
                release.set()
                reply = await asyncio.wait_for(request, 2)
                assert reply.status_code == 503 and reply.json() == {"error": "service_closing"}
            finally:
                release.set()
                if not request.done():
                    await request
    asyncio.run(scenario())
    with EvidenceStore(tmp_path / "root") as store:
        assert store.attempts() == []


def test_accepted_import_and_queued_query_drain_after_http_cancellation(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls, owners = [], []
    class TrackedStore(EvidenceStore):
        def __init__(self, root):
            calls.append(("open", threading.get_ident()))
            super().__init__(root)
        def import_bytes(self, *args, **kwargs):
            calls.append(("import", threading.get_ident()))
            entered.set()
            assert release.wait(5)
            return super().import_bytes(*args, **kwargs)
        def attempts(self):
            calls.append(("query", threading.get_ident()))
            return super().attempts()
        def close(self):
            calls.append(("close", threading.get_ident()))
            super().close()
    class Owner(module._StoreThread):
        def __init__(self, root):
            super().__init__(root)
            owners.append(self)
        def submit(self, operation):
            future = super().submit(operation)
            if self.pending == 2:
                queued.set()
            return future
    monkeypatch.setattr(module, "EvidenceStore", TrackedStore)
    monkeypatch.setattr(module, "_StoreThread", Owner)
    async def scenario():
        nonlocal queued
        queued = asyncio.Event()
        app = module.create_app(tmp_path / "root", on_shutdown=lambda: None)
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
                auth = {"Origin": ORIGIN, "X-Anatrading-Token": (await client.get("/api/config")).json()["csrf_token"]}
                importing = asyncio.create_task(upload(client, auth, source(row())))
                assert await asyncio.to_thread(entered.wait, 2)
                reading = asyncio.create_task(client.get("/api/attempts"))
                await asyncio.wait_for(queued.wait(), 2)
                importing.cancel()
                with pytest.raises(asyncio.CancelledError): await importing
                assert (await client.post("/api/shutdown", headers=auth)).status_code == 202
                assert owners[0].accepting is False
                closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
                await asyncio.sleep(0)
                assert not closing.done()
                assert (await client.get("/api/attempts")).status_code == 503
                release.set()
                assert (await reading).json()["attempts"][0]["status"] == "committed"
                await asyncio.wait_for(closing, 3)
        finally:
            release.set()
            await lifespan.__aexit__(None, None, None)
    queued = None
    try: asyncio.run(scenario())
    finally: release.set()
    assert [name for name, _ in calls] == ["open", "import", "query", "close"]
    assert len({thread for _, thread in calls}) == 1
    with EvidenceStore(tmp_path / "root") as store:
        assert store.attempts()[0]["status"] == "committed"


@pytest.mark.parametrize("bad", ["host", "origin", "missing_origin", "token", "duplicate_host", "duplicate_origin", "duplicate_token"])
def test_shutdown_authentication_failure_has_no_action_or_body_read(tmp_path, bad):
    calls = []
    async def scenario():
        async with running(tmp_path / "root", lambda: calls.append("exit")) as (app, client, auth):
            headers = [(b"host", b"127.0.0.1:8765"), (b"origin", ORIGIN.encode()),
                       (b"x-anatrading-token", auth["X-Anatrading-Token"].encode())]
            if bad == "host": headers[0] = (b"host", b"elsewhere.test")
            if bad == "origin": headers[1] = (b"origin", b"http://elsewhere.test")
            if bad == "missing_origin": headers.pop(1)
            if bad == "token": headers[2] = (b"x-anatrading-token", b"invalid")
            if bad.startswith("duplicate_"):
                headers.append(headers[{"duplicate_host": 0, "duplicate_origin": 1, "duplicate_token": 2}[bad]])
            messages, reads = await raw_shutdown(app, auth, chunks=[b"private body"], headers=headers)
            assert messages[0]["status"] == 403 and reads == 0 and calls == []
            assert (await client.get("/api/attempts")).status_code == 200
    asyncio.run(scenario())


@pytest.mark.parametrize("fault", ["http.response.start", "http.response.body"])
def test_response_delivery_failure_still_requests_owned_exit_once(tmp_path, fault):
    calls = []
    async def scenario():
        async with running(tmp_path / "root", lambda: calls.append("exit")) as (app, client, auth):
            with pytest.raises((OSError, RuntimeError)):
                await raw_shutdown(app, auth, send_fault=fault)
            assert calls == ["exit"]
            assert (await client.get("/api/attempts")).status_code == 503
            repeated = await client.post("/api/shutdown", headers=auth)
            assert repeated.status_code == 202 and calls == ["exit"]
    asyncio.run(scenario())
