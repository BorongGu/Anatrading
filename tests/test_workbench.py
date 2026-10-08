"""Single-snapshot HTTP boundaries use local ASGI and synthetic source bytes only."""
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import threading

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import anatrading.workbench as module
from anatrading.formats import FORMAT_IDS
from anatrading.store import EvidenceStore
from anatrading.workbench import create_app


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows store locks")
ORIGIN = "http://127.0.0.1:8765"
TEXT = FORMAT_IDS[0]
PRIVATE = "SYNTHETIC_PRIVATE_PAYLOAD_NOT_FOR_LOGS"


def source(*rows):
    lines = ["601577 合成验收 1分钟线 不复权", "日期\t时间\t开盘\t最高\t最低\t收盘\t成交量\t成交额"]
    lines.extend(",".join(row) for row in rows)
    return ("\r\n".join([*lines, "数据来源:通达信"]) + "\r\n").encode("gbk")


def row(time="0931", opening="10", high="11", low="9", close="10", volume="100", amount="1000"):
    return ["2021/02/26", time, opening, high, low, close, volume, amount]


@asynccontextmanager
async def running(root):
    web = root.parent / "web"
    web.mkdir(exist_ok=True)
    (web / "index.html").write_text("<!doctype html><title>Local fixture</title>", encoding="utf-8")
    app = create_app(root, web_directory=web)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            token = (await client.get("/api/config")).json()["csrf_token"]
            yield app, client, {"Origin": ORIGIN, "X-Anatrading-Token": token}


async def upload(client, headers, raw, **params):
    return await client.post("/api/import", params={"format_id": TEXT, "filename": "synthetic.txt", **params},
                             headers={**headers, "Content-Type": "application/octet-stream"}, content=raw)


async def asgi_request(app, *, path="/api/import", headers=(), chunks=(), disconnect=False, receive_error=None):
    sent, reads = [], []
    pending = list(chunks)

    async def receive():
        reads.append(True)
        if receive_error is not None:
            raise receive_error
        if pending:
            return {"type": "http.request", "body": pending.pop(0), "more_body": bool(pending) or disconnect}
        return {"type": "http.disconnect"} if disconnect else {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    await app({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
               "scheme": "http", "path": path, "raw_path": path.encode(),
               "query_string": b"format_id=tdx-public-text-v1&filename=synthetic.txt",
               "headers": list(headers), "client": ("127.0.0.1", 1234), "server": ("127.0.0.1", 8765)}, receive, send)
    return sent, len(reads)


@pytest.mark.parametrize("bad", ["host", "origin", "missing_origin", "token", "duplicate_host"])
def test_security_rejects_before_body_and_store_attempt(tmp_path, bad):
    async def scenario():
        async with running(tmp_path / "root") as (app, client, auth):
            headers = [(b"host", b"127.0.0.1:8765"), (b"origin", ORIGIN.encode()),
                       (b"x-anatrading-token", auth["X-Anatrading-Token"].encode()),
                       (b"content-type", b"application/octet-stream")]
            if bad == "host": headers[0] = (b"host", b"evil.test")
            if bad == "origin": headers[1] = (b"origin", b"http://evil.test")
            if bad == "missing_origin": headers.pop(1)
            if bad == "token": headers[2] = (b"x-anatrading-token", PRIVATE.encode())
            if bad == "duplicate_host": headers.append((b"host", b"evil.test"))
            messages, reads = await asgi_request(app, headers=headers, chunks=[PRIVATE.encode()])
            assert messages[0]["status"] == 403
            assert reads == 0
            assert PRIVATE.encode() not in b"".join(m.get("body", b"") for m in messages)
            assert (await client.get("/api/attempts")).json() == {"attempts": []}
    asyncio.run(scenario())


@pytest.mark.parametrize("format_id", FORMAT_IDS)
def test_cross_format_control_never_reaches_raw_or_temporary_files(tmp_path, capsys, format_id):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            raw = ("00.9.10\x0101\x010000000001\x010\x01login\x01" + PRIVATE).encode()
            response = await upload(client, auth, raw, format_id=format_id)
            assert response.status_code == 200
            attempt = response.json()["attempt"]
            assert attempt["status"] == "rejected" and attempt["error_code"] == "non_market_payload"
            assert attempt["raw_sha256"] is None
            assert (await client.get("/api/snapshots")).json() == {"snapshots": []}
    asyncio.run(scenario())
    output = capsys.readouterr()
    assert PRIVATE not in output.out + output.err
    for path in (tmp_path / "root").rglob("*"):
        if path.is_file(): assert PRIVATE.encode() not in path.read_bytes()


def test_stream_limit_and_incomplete_upload_make_no_attempt(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (app, client, auth):
            headers = [(b"host", b"127.0.0.1:8765"), (b"origin", ORIGIN.encode()),
                       (b"x-anatrading-token", auth["X-Anatrading-Token"].encode()),
                       (b"content-type", b"application/octet-stream")]
            messages, _ = await asgi_request(app, headers=headers, chunks=[b"x" * (16 * 1024 * 1024), b"x"])
            assert messages[0]["status"] == 413
            messages, _ = await asgi_request(app, headers=headers, chunks=[source(row())], disconnect=True)
            assert messages[0]["status"] == 400
            assert (await client.get("/api/attempts")).json() == {"attempts": []}
            assert not list((tmp_path / "root").glob("raw/**/*"))
    asyncio.run(scenario())


def test_oversized_content_length_and_nonempty_export_body_are_rejected_before_store(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (app, client, auth):
            headers = [(b"host", b"127.0.0.1:8765"), (b"origin", ORIGIN.encode()),
                       (b"x-anatrading-token", auth["X-Anatrading-Token"].encode()),
                       (b"content-type", b"application/octet-stream"), (b"content-length", b"9" * 5000)]
            messages, reads = await asgi_request(app, headers=headers, chunks=[PRIVATE.encode()])
            assert messages[0]["status"] == 413 and reads == 0
            response = await client.post("/api/export/" + "0" * 64, params={"format": "json", "query_id": "0" * 64},
                                         headers=auth, content=PRIVATE)
            assert response.status_code == 400 and response.json() == {"error": "invalid_request"}
            assert (await client.get("/api/attempts")).json() == {"attempts": []}
    asyncio.run(scenario())


def test_unexpected_body_read_error_is_safe_and_releases_upload_slot(tmp_path, capsys, caplog):
    async def scenario():
        async with running(tmp_path / "root") as (app, client, auth):
            headers = [(b"host", b"127.0.0.1:8765"), (b"origin", ORIGIN.encode()),
                       (b"x-anatrading-token", auth["X-Anatrading-Token"].encode()),
                       (b"content-type", b"application/octet-stream")]
            messages, _ = await asgi_request(app, headers=headers, receive_error=RuntimeError(PRIVATE))
            assert messages[0]["status"] == 500
            assert json.loads(b"".join(message.get("body", b"") for message in messages)) == {"error": "internal_error"}
            assert (await client.get("/api/attempts")).json() == {"attempts": []}
            assert (await upload(client, auth, source(row()))).json()["attempt"]["status"] == "committed"
    asyncio.run(scenario())
    output = capsys.readouterr()
    assert PRIVATE not in output.out + output.err + caplog.text


@pytest.mark.parametrize("params", [{"path": PRIVATE}, {"sql": PRIVATE}, {"format_id": "unknown"},
                                    {"instrument": ["one", "two"]}])
def test_import_spec_rejects_unknown_or_duplicate_parameters_without_echo(tmp_path, params):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            response = await upload(client, auth, source(row()), **params)
            assert response.status_code == 400
            assert set(response.json()) == {"error"}
            assert PRIVATE not in response.text
            assert (await client.get("/api/attempts")).json() == {"attempts": []}
    asyncio.run(scenario())


def test_config_and_static_are_local_and_api_is_uncached(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            response = await client.get("/api/config")
            assert response.headers["cache-control"] == "no-store"
            assert response.json() == {"csrf_token": auth["X-Anatrading-Token"], "formats": list(FORMAT_IDS),
                                       "max_upload_bytes": 16777216, "max_query_rows": 20000, "mode": "retrospective",
                                       "data_root_id": hashlib.sha256(str((tmp_path / "root").resolve()).casefold().encode()).hexdigest()}
            assert (await client.get("/")).status_code == 200
            assert (await client.get("/docs")).status_code == 404
            assert (await client.get("/openapi.json")).status_code == 404
            response = await client.get("/api/config", headers={"Origin": "http://evil.test"})
            assert response.status_code == 403
            assert auth["X-Anatrading-Token"] not in response.text
    asyncio.run(scenario())


def test_native_asgi_startup_does_not_configure_telemetry_from_environment(tmp_path, monkeypatch):
    from fastapi.telemetry import _runtime
    calls = []
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://telemetry.invalid")

    def forbidden_export(signal):
        calls.append(signal)
        raise AssertionError("No automatic export may be configured")

    monkeypatch.setattr(_runtime, "_export_endpoint", forbidden_export)

    async def scenario():
        app = create_app(tmp_path / "root")
        received = iter([{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}])
        sent = []

        async def receive():
            return next(received)

        async def send(message):
            sent.append(message)

        await app({"type": "lifespan", "asgi": {"version": "3.0"}, "state": {}}, receive, send)
        assert [message["type"] for message in sent] == ["lifespan.startup.complete", "lifespan.shutdown.complete"]
        assert calls == []
        assert all(app._telemetry[key] is False for key in ("tracing", "metrics", "logs", "operation_spans", "auto_configure"))
    asyncio.run(scenario())


def test_query_exact_values_navigation_and_both_export_scopes(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            response = await upload(client, auth, source(row("0932", volume="9007199254740993"),
                row("2500", volume="bad"), row(), row(volume="0", amount="0"), row("0933")))
            snapshot = response.json()["attempt"]["snapshot_id"]
            catalog = (await client.get("/api/snapshots")).json()["snapshots"]
            assert len(catalog) == 1 and catalog[0]["row_count"] == 5
            assert set(catalog[0]) == {"snapshot_id", "batch_id", "row_count", "manifest", "metadata"}
            selection = {"cutoff": "2021-02-26T09:32", "ordinal_start": 1, "ordinal_end": 4}
            response = await client.get("/api/query/" + snapshot, params=selection)
            assert response.status_code == 200
            view = response.json(); query = view["query"]
            assert [r["ordinal"] for r in query["rows"]] == [3, 4, 1]
            assert [r["ordinal"] for r in query["unlocated"]] == [2]
            assert query["rows"][-1]["values"]["volume"] == "9007199254740993"
            assert query["rows"][1]["values"]["volume"] == "0"
            assert view["navigation"] == {"previous_label": "2021-02-26T09:31", "next_label": None}
            assert [r["ordinal"] for r in view["display"]] == [3, 4, 1]
            for kind in ("json", "parquet"):
                exported = await client.post("/api/export/" + snapshot, params={**selection, "format": kind,
                                              "query_id": query["query_id"]}, headers=auth)
                assert exported.status_code == 200
                assert exported.headers["x-query-id"] == query["query_id"]
                assert hashlib.sha256(exported.content).hexdigest() == exported.headers["x-content-sha256"]
                assert "attachment;" in exported.headers["content-disposition"]
                if kind == "json": assert exported.json() == query
                else:
                    table = pq.read_table(pa.BufferReader(exported.content))
                    assert [r["scope"] for r in table.to_pylist()] == ["rows", "rows", "rows", "unlocated"]
                    assert json.loads(table.schema.metadata[b"anatrading_query"])["query_id"] == query["query_id"]
            mismatch = await client.post("/api/export/" + snapshot, params={**selection, "format": "json", "query_id": "0" * 64}, headers=auth)
            assert mismatch.status_code == 409 and mismatch.json() == {"error": "query_id_mismatch"}
            empty = (await client.get("/api/query/" + snapshot, params={"cutoff": "2020-01-01T00:00"})).json()
            assert empty["query"]["rows"] == [] and len(empty["query"]["unlocated"]) == 1
            assert empty["navigation"] == {"previous_label": None, "next_label": "2021-02-26T09:31"}
    asyncio.run(scenario())


def test_decimal_direction_and_drawability_are_independent_of_float_rounding(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            rows = [row(opening="9007199254740992", high="9007199254740994", low="9007199254740992", close="9007199254740993"),
                    row("0932", opening="11", close="10"), row("0933", opening="", close="10"),
                    row("0934", opening="10", high="9", low="11"), row("0935", opening="-1", low="-2"), row("0936")]
            snapshot = (await upload(client, auth, source(*rows))).json()["attempt"]["snapshot_id"]
            view = (await client.get("/api/query/" + snapshot)).json()
            assert [r["direction"] for r in view["display"]] == ["up", "down", "unknown", "equal", "up", "equal"]
            assert [r["ohlc_drawable"] for r in view["display"]] == [False, True, False, False, False, True]
            assert [r["precision_lost"] for r in view["display"]] == [True, False, False, False, False, False]
            assert view["navigation"] == {"previous_label": "2021-02-26T09:35", "next_label": None}
    asyncio.run(scenario())


def test_total_row_budget_includes_unlocated_and_explicit_window(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            snapshot = (await upload(client, auth, source(*([row("2500")] * 20001)))).json()["attempt"]["snapshot_id"]
            path = "/api/query/" + snapshot
            for selection in ({}, {"ordinal_start": 1}, {"ordinal_start": 1, "ordinal_end": 20001}):
                response = await client.get(path, params=selection)
                assert response.status_code == 400 and response.json() == {"error": "query_row_limit"}
            result = (await client.get(path, params={"ordinal_start": 1, "ordinal_end": 2, "cutoff": "2020-01-01T00:00"})).json()
            assert result["query"]["counts"]["unlocated_rows"] == 2
            assert result["query"]["counts"]["batch_unlocated_rows"] == 20001
            assert result["query"]["rows"] == [] and result["display"] == []
    asyncio.run(scenario())


def test_broken_raw_blocks_query_and_export(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            attempt = (await upload(client, auth, source(row()))).json()["attempt"]
            path = "/api/query/" + attempt["snapshot_id"]
            query = (await client.get(path)).json()["query"]
            raw = tmp_path / "root/raw" / attempt["raw_sha256"][:2] / attempt["raw_sha256"]
            raw.write_bytes(b"changed")
            for response in (await client.get(path), await client.post("/api/export/" + attempt["snapshot_id"],
                             params={"format": "json", "query_id": query["query_id"]}, headers=auth)):
                assert response.status_code == 409 and response.json() == {"error": "raw_object_corrupt"}
    asyncio.run(scenario())


def test_navigation_keeps_core_semantics_for_large_positive_ordinal_bounds(tmp_path):
    async def scenario():
        async with running(tmp_path / "root") as (_, client, auth):
            snapshot = (await upload(client, auth, source(row(), row("0932")))).json()["attempt"]["snapshot_id"]
            for selection, count, previous in (({"ordinal_start": 10**100}, 0, None),
                                               ({"ordinal_end": 10**100}, 2, "2021-02-26T09:31"),
                                               ({"ordinal_start": 10**100, "ordinal_end": 10**100}, 0, None)):
                response = await client.get("/api/query/" + snapshot, params=selection)
                assert response.status_code == 200
                view = response.json()
                assert len(view["query"]["rows"]) == count
                assert view["navigation"] == {"previous_label": previous, "next_label": None}
    asyncio.run(scenario())


def test_cancelled_startup_closes_a_store_created_after_cancellation(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    class DelayedStore(EvidenceStore):
        def __init__(self, root):
            calls.append(("open", threading.get_ident()))
            entered.set()
            assert release.wait(3)
            super().__init__(root)

        def close(self):
            calls.append(("close", threading.get_ident()))
            super().close()

    monkeypatch.setattr(module, "EvidenceStore", DelayedStore)

    async def scenario():
        app = create_app(tmp_path / "root")
        startup = asyncio.create_task(app.router.lifespan_context(app).__aenter__())
        assert await asyncio.to_thread(entered.wait, 2)
        startup.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError): await startup
        assert [name for name, _ in calls] == ["open", "close"]
        assert len({thread for _, thread in calls}) == 1
    try: asyncio.run(scenario())
    finally: release.set()
    with EvidenceStore(tmp_path / "root"):
        pass


def test_cancelled_http_wait_retains_import_and_shutdown_drains_owner_thread(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls = []

    class TrackedStore(EvidenceStore):
        def __init__(self, root):
            calls.append(("open", threading.get_ident()))
            super().__init__(root)

        def import_bytes(self, *args, **kwargs):
            calls.append(("import", threading.get_ident()))
            entered.set()
            assert release.wait(5)
            return super().import_bytes(*args, **kwargs)

        def close(self):
            calls.append(("close", threading.get_ident()))
            super().close()

    monkeypatch.setattr(module, "EvidenceStore", TrackedStore)

    async def scenario():
        loop_thread = threading.get_ident()
        app = create_app(tmp_path / "root")
        lifespan = app.router.lifespan_context(app)
        await lifespan.__aenter__()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=ORIGIN) as client:
            auth = {"Origin": ORIGIN, "X-Anatrading-Token": (await client.get("/api/config")).json()["csrf_token"]}
            task = asyncio.create_task(upload(client, auth, source(row())))
            assert await asyncio.to_thread(entered.wait, 3)
            task.cancel()
            with pytest.raises(asyncio.CancelledError): await task
            duplicate = await upload(client, auth, source(row()))
            assert duplicate.status_code == 409 and duplicate.json() == {"error": "upload_in_progress"}
            closing = asyncio.create_task(lifespan.__aexit__(None, None, None))
            await asyncio.sleep(0)
            assert not closing.done()
            response = await client.get("/api/attempts")
            assert response.status_code == 503
            release.set()
            await asyncio.wait_for(closing, 5)
        assert len({thread for _, thread in calls}) == 1
        assert calls[0][1] != loop_thread and [name for name, _ in calls] == ["open", "import", "close"]
    try: asyncio.run(scenario())
    finally: release.set()
    with EvidenceStore(tmp_path / "root") as store:
        assert store.attempts()[0]["status"] == "committed"


def test_queue_is_bounded_without_cancelling_already_accepted_work(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    monkeypatch.setattr(module, "_MAX_PENDING", 2)

    class BlockedStore(EvidenceStore):
        def attempts(self):
            entered.set()
            assert release.wait(5)
            return super().attempts()

    monkeypatch.setattr(module, "EvidenceStore", BlockedStore)

    async def scenario():
        async with running(tmp_path / "root") as (_, client, _):
            first = asyncio.create_task(client.get("/api/attempts"))
            assert await asyncio.to_thread(entered.wait, 3)
            second = asyncio.create_task(client.get("/api/attempts"))
            await asyncio.sleep(0)
            rejected = await client.get("/api/attempts")
            assert rejected.status_code == 503 and rejected.json() == {"error": "service_busy"}
            release.set()
            assert (await first).status_code == (await second).status_code == 200
    try: asyncio.run(scenario())
    finally: release.set()
