"""Independent workbench boundaries; synthetic inputs and local ASGI only."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import inspect
import os
import threading

import httpx
import pytest

import anatrading.workbench as module
from anatrading.store import EvidenceStore, StoreError


ORIGIN = "http://127.0.0.1:8765"
TEXT = "tdx-public-text-v1"
PRIVATE = "SYNTHETIC_HTTP_PRIVATE_MARKER_813"


def source(*times):
    lines = ["601577 独立边界 1分钟线 不复权", "日期\t时间\t开盘\t最高\t最低\t收盘\t成交量\t成交额"]
    lines.extend(f"2021/02/26,{stamp},10,11,9,10,100,1000" for stamp in times)
    return ("\r\n".join([*lines, "数据来源:通达信"]) + "\r\n").encode("gbk")


@asynccontextmanager
async def native_lifespan(app):
    """Exercise FastAPI.__call__, including its native lifespan wrapper."""
    incoming, outgoing = asyncio.Queue(), asyncio.Queue()
    task = asyncio.create_task(app(
        {"type": "lifespan", "asgi": {"version": "3.0", "spec_version": "2.0"}, "state": {}},
        incoming.get, outgoing.put,
    ))
    await incoming.put({"type": "lifespan.startup"})
    first = await asyncio.wait_for(outgoing.get(), 10)
    assert first["type"] == "lifespan.startup.complete", first["type"]
    try:
        yield
    finally:
        await incoming.put({"type": "lifespan.shutdown"})
        last = await asyncio.wait_for(outgoing.get(), 10)
        assert last["type"] == "lifespan.shutdown.complete", last["type"]
        await asyncio.wait_for(task, 10)


@asynccontextmanager
async def running(root):
    app = module.create_app(root)
    async with native_lifespan(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            config = await client.get("/api/config")
            assert config.status_code == 200
            auth = {"Origin": ORIGIN, "X-Anatrading-Token": config.json()["csrf_token"]}
            yield app, client, auth


async def upload(client, auth, raw):
    response = await client.post(
        "/api/import", params={"format_id": TEXT, "filename": "synthetic.txt"}, content=raw,
        headers={**auth, "Content-Type": "application/octet-stream"},
    )
    assert response.status_code == 200, response.text
    attempt = response.json()["attempt"]
    assert attempt["status"] == "committed", attempt
    return attempt


def test_every_store_operation_and_close_uses_one_non_http_thread(tmp_path, monkeypatch):
    calls = []

    def observed(name, original):
        def invoke(self, *args, **kwargs):
            calls.append((name, threading.get_ident()))
            return original(self, *args, **kwargs)
        return invoke

    methods = {name: observed(name, function) for name, function in vars(EvidenceStore).items()
               if inspect.isfunction(function) and (name == "__init__" or not name.startswith("_"))}
    monkeypatch.setattr(module, "EvidenceStore", type("ObservedStore", (EvidenceStore,), methods))

    async def scenario():
        http_thread = threading.get_ident()
        async with running(tmp_path / "root") as (_, client, auth):
            attempt = await upload(client, auth, source("0931", "0932"))
            snapshot = attempt["snapshot_id"]
            assert (await client.get("/api/snapshots")).status_code == 200
            assert (await client.get("/api/attempts")).status_code == 200
            query = (await client.get("/api/query/" + snapshot)).json()["query"]
            for kind in ("json", "parquet"):
                response = await client.post("/api/export/" + snapshot, headers=auth,
                                             params={"format": kind, "query_id": query["query_id"]})
                assert response.status_code == 200
        names = [name for name, _ in calls]
        assert names[0] == "__init__" and names[-1] == "close"
        assert {"import_bytes", "snapshot_catalog", "label_navigation", "attempts", "query",
                "export_json", "export_parquet", "close"} <= set(names)
        owners = {thread for _, thread in calls}
        assert len(owners) == 1 and http_thread not in owners

    asyncio.run(scenario())
    with EvidenceStore(tmp_path / "root") as reopened:
        assert len(reopened.list_snapshots()) == 1


def test_cancelled_http_wait_keeps_an_import_queued_behind_another_operation(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    events = []

    class QueuedStore(EvidenceStore):
        def __init__(self, root):
            events.append(("open", threading.get_ident()))
            super().__init__(root)

        def snapshot_catalog(self, *args, **kwargs):
            events.append(("blocked_read", threading.get_ident()))
            entered.set()
            assert release.wait(8), "bounded test gate expired"
            return super().snapshot_catalog(*args, **kwargs)

        def import_bytes(self, *args, **kwargs):
            events.append(("import", threading.get_ident()))
            return super().import_bytes(*args, **kwargs)

        def close(self):
            events.append(("close", threading.get_ident()))
            super().close()

    monkeypatch.setattr(module, "EvidenceStore", QueuedStore)

    async def scenario():
        app = module.create_app(tmp_path / "root")
        lifespan = native_lifespan(app)
        await lifespan.__aenter__()
        closing = None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            auth = {"Origin": ORIGIN, "X-Anatrading-Token": (await client.get("/api/config")).json()["csrf_token"]}
            first = asyncio.create_task(client.get("/api/snapshots"))
            assert await asyncio.to_thread(entered.wait, 3)
            consumed = asyncio.Event()

            async def body():
                yield source("0931")
                consumed.set()

            pending = asyncio.create_task(client.post(
                "/api/import", params={"format_id": TEXT, "filename": "queued.txt"}, content=body(),
                headers={**auth, "Content-Type": "application/octet-stream"},
            ))
            try:
                await asyncio.wait_for(consumed.wait(), 3)
                await asyncio.sleep(0)
                assert "import" not in [name for name, _ in events]
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending
                busy = await client.post("/api/import", params={"format_id": TEXT, "filename": "second.txt"},
                                         content=source("0932"), headers={**auth, "Content-Type": "application/octet-stream"})
                assert busy.status_code == 409 and busy.json() == {"error": "upload_in_progress"}
                closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
                await asyncio.sleep(0)
                # Delivering native lifespan.shutdown requires another event-loop turn.
                await asyncio.sleep(0)
                assert not closing.done() and "close" not in [name for name, _ in events]
                with pytest.raises(StoreError, match="data_directory_busy"):
                    EvidenceStore(tmp_path / "root")
                rejected = await asyncio.wait_for(client.get("/api/attempts"), 3)
                assert rejected.status_code == 503
            finally:
                release.set()
                if not pending.done():
                    pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
                await asyncio.wait_for(first, 5)
                if closing is None:
                    closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
                await asyncio.wait_for(closing, 5)
        assert [name for name, _ in events] == ["open", "blocked_read", "import", "close"]
        assert len({thread for _, thread in events}) == 1

    try:
        asyncio.run(scenario())
    finally:
        release.set()
    with EvidenceStore(tmp_path / "root") as store:
        attempts = store.attempts()
        assert len(attempts) == 1 and attempts[0]["status"] == "committed"
        assert len(store.list_snapshots()) == 1


@pytest.mark.parametrize("bad", ["foreign_origin", "null_origin", "missing_token", "duplicate_token"])
def test_export_write_gate_rejects_before_consuming_body_or_creating_a_file(tmp_path, bad):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            attempt = await upload(client, auth, source("0931"))
            snapshot = attempt["snapshot_id"]
            query = (await client.get("/api/query/" + snapshot)).json()["query"]
            headers = list(auth.items())
            if bad == "foreign_origin":
                headers[0] = ("Origin", "http://outside.invalid")
            elif bad == "null_origin":
                headers[0] = ("Origin", "null")
            elif bad == "missing_token":
                headers = headers[:1]
            else:
                headers.append(("X-Anatrading-Token", PRIVATE))
            consumed = []

            async def body():
                consumed.append(True)
                yield PRIVATE.encode()

            response = await client.post("/api/export/" + snapshot, headers=headers, content=body(),
                                         params={"format": "json", "query_id": query["query_id"]})
            assert response.status_code == 403
            assert set(response.json()) == {"error"} and PRIVATE not in response.text
            assert consumed == []
            assert response.headers["cache-control"] == "no-store"
            assert not list((tmp_path / "root/exports").rglob("*"))
    asyncio.run(scenario())


def test_write_token_from_a_previous_service_instance_is_not_accepted(tmp_path):
    async def scenario():
        async with running(tmp_path / "first") as (_, _, old):
            old_token = old["X-Anatrading-Token"]
        async with running(tmp_path / "second") as (_, client, current):
            assert current["X-Anatrading-Token"] != old_token
            response = await client.post("/api/import", content=source("0931"),
                                         params={"format_id": TEXT, "filename": "source.txt"},
                                         headers={"Origin": ORIGIN, "X-Anatrading-Token": old_token,
                                                  "Content-Type": "application/octet-stream"})
            assert response.status_code == 403
            assert (await client.get("/api/attempts")).json() == {"attempts": []}
    asyncio.run(scenario())


@pytest.mark.parametrize("damage", ["missing", "corrupt"])
def test_existing_export_files_cannot_bypass_a_later_raw_integrity_failure(tmp_path, damage):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            raw = source("0931", "2500", "0932")
            attempt = await upload(client, auth, raw)
            snapshot = attempt["snapshot_id"]
            path = "/api/query/" + snapshot
            query = (await client.get(path)).json()["query"]
            selections = [{"format": kind, "query_id": query["query_id"]} for kind in ("json", "parquet")]
            for selection in selections:
                response = await client.post("/api/export/" + snapshot, headers=auth, params=selection)
                assert response.status_code == 200
                assert hashlib.sha256(response.content).hexdigest() == response.headers["x-content-sha256"]
            original = tmp_path / "root/raw" / attempt["raw_sha256"][:2] / attempt["raw_sha256"]
            if damage == "missing":
                original.unlink()
            else:
                original.write_bytes(b"damaged synthetic copy")
            expected = "raw_object_missing" if damage == "missing" else "raw_object_corrupt"
            try:
                for response in [await client.get(path), *[
                    await client.post("/api/export/" + snapshot, headers=auth, params=selection)
                    for selection in selections
                ]]:
                    assert response.status_code == 409 and response.json() == {"error": expected}
                    assert "x-content-sha256" not in response.headers
            finally:
                original.write_bytes(raw)
            restored = await client.get(path)
            assert restored.status_code == 200 and restored.json()["query"] == query
    asyncio.run(scenario())


@pytest.mark.parametrize("operation", ["query", "json", "parquet"])
def test_post_query_budget_counts_unlocated_even_if_catalogue_count_is_stale(tmp_path, monkeypatch, operation):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            attempt = await upload(client, auth, source("0931", "2500", "2501"))
            snapshot = attempt["snapshot_id"]
            query = (await client.get("/api/query/" + snapshot)).json()["query"]
            assert len(query["rows"]) == 1 and len(query["unlocated"]) == 2
            original = EvidenceStore.snapshot_catalog

            def stale_count(self, *args, **kwargs):
                return [{**item, "row_count": 1} for item in original(self, *args, **kwargs)]

            monkeypatch.setattr(EvidenceStore, "snapshot_catalog", stale_count)
            monkeypatch.setattr(module, "_MAX_ROWS", 2)
            if operation == "query":
                response = await client.get("/api/query/" + snapshot)
            else:
                response = await client.post("/api/export/" + snapshot, headers=auth,
                                             params={"format": operation, "query_id": query["query_id"]})
            assert response.status_code == 400 and response.json() == {"error": "query_row_limit"}
            assert not list((tmp_path / "root/exports").rglob("*"))
    asyncio.run(scenario())


def test_snapshot_directory_never_queries_full_snapshot_rows(tmp_path, monkeypatch):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            await upload(client, auth, source("0931"))
            await upload(client, auth, source("0932"))

            def forbidden(*args, **kwargs):
                pytest.fail("directory listing must not query full records")

            monkeypatch.setattr(EvidenceStore, "query", forbidden)
            response = await client.get("/api/snapshots")
            assert response.status_code == 200 and len(response.json()["snapshots"]) == 2
            assert all(set(item) == {"snapshot_id", "batch_id", "row_count", "manifest", "metadata"}
                       for item in response.json()["snapshots"])
    asyncio.run(scenario())


def test_native_lifespan_and_rejected_input_do_not_enter_telemetry_paths(tmp_path, monkeypatch, capsys, caplog):
    from fastapi.telemetry import _asgi, _runtime

    def forbidden_environment(*args, **kwargs):
        pytest.fail("environment telemetry configuration must stay disabled")

    async def forbidden_payload(*args, **kwargs):
        pytest.fail("native request telemetry must stay disabled")

    monkeypatch.setattr(_runtime, "_export_endpoint", forbidden_environment)
    monkeypatch.setattr(_asgi.NativeTelemetry, "__call__", forbidden_payload)

    async def scenario():
        async with running(tmp_path / "root") as (app, client, _):
            for setting in ("tracing", "metrics", "logs", "operation_spans", "auto_configure"):
                assert app._telemetry[setting] is False
            response = await client.get("/api/query/" + "0" * 64, params={"ordinal_start": PRIVATE})
            assert response.status_code == 400 and set(response.json()) == {"error"}
            assert PRIVATE not in response.text
    asyncio.run(scenario())
    captured = capsys.readouterr()
    assert PRIVATE not in captured.out + captured.err + caplog.text
