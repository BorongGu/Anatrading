"""Local single-snapshot HTTP adapter; all Store work has one owning thread."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from decimal import Decimal
import hashlib
from pathlib import Path
import re
import secrets

import duckdb
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.requests import ClientDisconnect
from starlette.responses import JSONResponse, Response
from starlette.staticfiles import StaticFiles

from .formats import FORMAT_IDS
from .models import DecodeError
from .numeric import NumericError
from .store import EvidenceStore, StoreError


_MAX_UPLOAD = 16 * 1024 * 1024
_MAX_ROWS = 20000
_MAX_PENDING = 32
_DECLARATIONS = {"instrument", "venue", "asset_type", "volume_unit", "amount_unit"}
_SELECTION = {"cutoff", "ordinal_start", "ordinal_end", "mode"}
_STORE_CODES = {
    "windows_required", "data_directory_busy", "destination_exists", "restore_incomplete",
    "unrecognized_database", "unsupported_schema", "invalid_object_id", "raw_reference_outside_root",
    "raw_object_missing", "raw_object_corrupt", "staging_outside_root", "raw_write_mismatch",
    "import_outcome_unavailable", "invalid_import_spec", "unverified_normalization", "mode_not_supported",
    "invalid_snapshot_id", "invalid_ordinal_range", "snapshot_not_found", "invalid_label_cutoff",
    "non_market_payload", "unsupported_format", "invalid_text_encoding", "invalid_text_structure",
    "invalid_text_row_width", "invalid_day_length", "unsupported_known_minute_binary", "unsupported_bao_period",
    "invalid_bao_fields", "invalid_bao_records", "invalid_bao_cells", "invalid_interpretation", "invalid_raw_type",
    "numeric_type", "invalid_decimal", "nonfinite", "decimal_scale", "decimal_range", "integer_fraction",
    "integer_range", "sum_precision", "sum_range", "storage_io_error", "database_error", "internal_error",
    "process_interrupted",
}


class _RequestError(Exception):
    def __init__(self, code, status=400):
        self.code, self.status = code, status
        super().__init__(code)


def _safe_store_call(operation):
    try:
        return operation()
    except _RequestError:
        raise
    except (StoreError, DecodeError, NumericError) as error:
        code = error.code if error.code in _STORE_CODES else "internal_error"
    except OSError:
        code = "storage_io_error"
    except duckdb.Error:
        code = "database_error"
    except Exception:
        code = "internal_error"
    status = 404 if code == "snapshot_not_found" else 400 if code.startswith("invalid_") or code == "mode_not_supported" else 409
    if code in {"storage_io_error", "database_error", "internal_error"}:
        status = 500
    raise _RequestError(code, status)


class _StoreThread:
    def __init__(self, root):
        self.root = root
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="anatrading-store")
        self.store = None
        self.accepting = False
        self.pending = 0

    async def open(self):
        def open_store():
            self.store = EvidenceStore(self.root)

        future = asyncio.wrap_future(self.executor.submit(_safe_store_call, open_store))
        future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            await asyncio.shield(future)
            self.accepting = True
        except BaseException:
            self.executor.submit(lambda: self.store.close() if self.store is not None else None)
            self.executor.shutdown(wait=True)
            raise

    def submit(self, operation):
        if not self.accepting:
            raise _RequestError("service_closing", 503)
        if self.pending >= _MAX_PENDING:
            raise _RequestError("service_busy", 503)
        self.pending += 1
        future = asyncio.wrap_future(self.executor.submit(_safe_store_call, lambda: operation(self.store)))

        def finished(done):
            self.pending -= 1
            if not done.cancelled():
                done.exception()  # Consume orphaned errors when an HTTP waiter disconnects.

        future.add_done_callback(finished)
        return future

    async def call(self, operation):
        return await asyncio.shield(self.submit(operation))

    async def close(self):
        self.accepting = False
        try:
            if self.store is not None:
                future = asyncio.wrap_future(self.executor.submit(_safe_store_call, self.store.close))
                future.add_done_callback(lambda done: None if done.cancelled() else done.exception())
                await asyncio.shield(future)
        finally:
            self.executor.shutdown(wait=True)


class _LocalBoundary:
    def __init__(self, app, *, port, token):
        self.app, self.token = app, token
        self.host = f"127.0.0.1:{port}".encode("ascii")
        self.origin = b"http://" + self.host

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = scope["headers"]

        def values(name):
            return [value for key, value in headers if key.lower() == name]

        code = None
        if values(b"host") != [self.host]:
            code = "invalid_host"
        elif values(b"origin") and values(b"origin") != [self.origin]:
            code = "invalid_origin"
        elif scope["method"] == "POST":
            supplied = values(b"x-anatrading-token")
            if values(b"origin") != [self.origin]:
                code = "invalid_origin"
            elif len(supplied) != 1 or not secrets.compare_digest(supplied[0], self.token.encode("ascii")):
                code = "invalid_token"

        started = False

        async def uncached(message):
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            if message["type"] == "http.response.start" and scope["path"].startswith("/api/"):
                message = {**message, "headers": [*message.get("headers", []), (b"cache-control", b"no-store")]}
            await send(message)

        if code:
            await JSONResponse({"error": code}, status_code=403)(scope, receive, uncached)
        else:
            try:
                await self.app(scope, receive, uncached)
                return
            except Exception:
                pass
            if started:
                raise RuntimeError("response_interrupted")
            await JSONResponse({"error": "internal_error"}, status_code=500)(scope, receive, uncached)


def _parameters(request, allowed, required=()):
    items = list(request.query_params.multi_items())
    result = dict(items)
    if len(items) != len(result) or set(result) - allowed or any(not result.get(key) for key in required):
        raise _RequestError("invalid_request")
    return result


def _selection(parameters):
    selection = {key: value for key, value in parameters.items() if key in _SELECTION}
    for key in ("ordinal_start", "ordinal_end"):
        if key in selection:
            try:
                selection[key] = int(selection[key])
            except ValueError:
                raise _RequestError("invalid_ordinal_range") from None
            if selection[key] < 1:
                raise _RequestError("invalid_ordinal_range")
    if ("ordinal_start" in selection and "ordinal_end" in selection
            and selection["ordinal_start"] > selection["ordinal_end"]):
        raise _RequestError("invalid_ordinal_range")
    if selection.get("mode", "retrospective") != "retrospective":
        raise _RequestError("mode_not_supported")
    return selection


def _bounded_query(store, snapshot_id, selection):
    count = store.snapshot_catalog(snapshot_id)[0]["row_count"]
    start, end = selection.get("ordinal_start"), selection.get("ordinal_end")
    if ((count > _MAX_ROWS and (start is None or end is None))
            or (start is not None and end is not None and end - start + 1 > _MAX_ROWS)):
        raise _RequestError("query_row_limit")
    query = store.query(snapshot_id, **selection)
    if len(query["rows"]) + len(query["unlocated"]) > _MAX_ROWS:
        raise _RequestError("query_row_limit")
    return query


def _display(row):
    values = [None if row["values"][key] is None else Decimal(row["values"][key]) for key in ("open", "high", "low", "close")]
    opening, _, _, close = values
    direction = "unknown" if opening is None or close is None else "up" if close > opening else "down" if close < opening else "equal"
    known = [value for value in values if value is not None]
    precision_lost = any(a != b and float(a) == float(b) for i, a in enumerate(known) for b in known[i + 1:])
    checks = {check["name"]: check["outcome"] for check in row["checks"]}
    drawable = all(value is not None for value in values) and not precision_lost
    drawable = drawable and all(checks.get(name) == "pass" for name in ("ohlc_bounds", "nonnegative_prices"))
    return dict(ordinal=row["ordinal"], direction=direction, ohlc_drawable=drawable, precision_lost=precision_lost)


def _query_view(store, snapshot_id, selection):
    query = _bounded_query(store, snapshot_id, selection)
    navigation = store.label_navigation(query["batch_id"], **{key: selection.get(key) for key in ("cutoff", "ordinal_start", "ordinal_end")})
    return dict(query=query, display=[_display(row) for row in query["rows"]], navigation=navigation)


def _export(store, snapshot_id, selection, kind, expected_id):
    query = _bounded_query(store, snapshot_id, selection)
    if query["query_id"] != expected_id:
        raise _RequestError("query_id_mismatch", 409)
    exporter = store.export_json if kind == "json" else store.export_parquet
    result = exporter(snapshot_id, **selection)
    content = Path(result["path"]).read_bytes()
    if result["query_id"] != expected_id or hashlib.sha256(content).hexdigest() != result["sha256"]:
        raise _RequestError("export_integrity_error", 409)
    return content, result["sha256"]


def create_app(root, *, port=8765, web_directory=None):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid_port")
    token = secrets.token_urlsafe(32)
    owner = _StoreThread(root)
    upload_busy = False

    @asynccontextmanager
    async def lifespan(app):
        await owner.open()
        try:
            yield
        finally:
            await owner.close()

    app = FastAPI(lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None,
                  telemetry={"tracing": False, "metrics": False, "logs": False,
                             "operation_spans": False, "auto_configure": False})
    app.add_middleware(_LocalBoundary, port=port, token=token)

    @app.exception_handler(_RequestError)
    async def request_error(request, error):
        return JSONResponse({"error": error.code}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        return JSONResponse({"error": "invalid_request"}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse({"error": "not_found" if error.status_code == 404 else "invalid_request"}, status_code=error.status_code)

    @app.get("/api/config")
    async def config(request: Request):
        _parameters(request, set())
        return dict(csrf_token=token, formats=list(FORMAT_IDS), max_upload_bytes=_MAX_UPLOAD,
                    max_query_rows=_MAX_ROWS, mode="retrospective")

    @app.get("/api/snapshots")
    async def snapshots(request: Request):
        _parameters(request, set())
        return {"snapshots": await owner.call(lambda store: store.snapshot_catalog())}

    @app.get("/api/attempts")
    async def attempts(request: Request):
        _parameters(request, set())
        return {"attempts": await owner.call(lambda store: store.attempts())}

    @app.post("/api/import")
    async def ingest(request: Request):
        nonlocal upload_busy
        parameters = _parameters(request, {"format_id", "filename", *_DECLARATIONS}, ("format_id", "filename"))
        if parameters["format_id"] not in FORMAT_IDS:
            raise _RequestError("invalid_import_spec")
        if request.headers.get("content-type") != "application/octet-stream":
            raise _RequestError("invalid_content_type", 415)
        if not owner.accepting:
            raise _RequestError("service_closing", 503)
        if upload_busy:
            raise _RequestError("upload_in_progress", 409)
        declared = request.headers.get("content-length")
        if declared is not None:
            if not re.fullmatch("[0-9]+", declared):
                raise _RequestError("invalid_request")
            declared = declared.lstrip("0") or "0"
            if len(declared) > len(str(_MAX_UPLOAD)) or (len(declared) == len(str(_MAX_UPLOAD)) and declared > str(_MAX_UPLOAD)):
                raise _RequestError("upload_too_large", 413)
            declared = int(declared)
        upload_busy, submitted = True, False

        def finished(future):
            nonlocal upload_busy
            upload_busy = False

        try:
            raw = bytearray()
            try:
                async for chunk in request.stream():
                    if len(raw) + len(chunk) > _MAX_UPLOAD:
                        raise _RequestError("upload_too_large", 413)
                    raw.extend(chunk)
            except ClientDisconnect:
                raise _RequestError("upload_incomplete") from None
            if declared is not None and len(raw) != declared:
                raise _RequestError("upload_incomplete")
            content = bytes(raw)
            future = owner.submit(lambda store: store.import_bytes(content, parameters["format_id"], filename=parameters["filename"],
                                   interpretation={key: value for key, value in parameters.items() if key in _DECLARATIONS}))
            future.add_done_callback(finished)
            submitted = True
            attempt = await asyncio.shield(future)
            if attempt.get("error_code") is not None and attempt["error_code"] not in _STORE_CODES:
                attempt = {**attempt, "error_code": "internal_error"}
            return {"attempt": attempt}
        finally:
            if not submitted:
                upload_busy = False

    @app.get("/api/query/{snapshot_id}")
    async def query(snapshot_id: str, request: Request):
        selection = _selection(_parameters(request, _SELECTION))
        return JSONResponse(await owner.call(lambda store: _query_view(store, snapshot_id, selection)))

    @app.post("/api/export/{snapshot_id}")
    async def export(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "format", "query_id"}, ("format", "query_id"))
        kind, expected = parameters["format"], parameters["query_id"]
        if kind not in {"json", "parquet"} or not re.fullmatch("[0-9a-f]{64}", expected):
            raise _RequestError("invalid_request")
        selection = _selection(parameters)
        try:
            async for chunk in request.stream():
                if chunk:
                    raise _RequestError("invalid_request")
        except ClientDisconnect:
            raise _RequestError("upload_incomplete") from None
        content, digest = await owner.call(lambda store: _export(store, snapshot_id, selection, kind, expected))
        return Response(content, media_type="application/json" if kind == "json" else "application/vnd.apache.parquet",
                        headers={"X-Query-Id": expected, "X-Content-SHA256": digest,
                                 "Content-Disposition": f'attachment; filename="anatrading-{expected}.{kind}"'})

    directory = Path(web_directory) if web_directory is not None else Path(__file__).resolve().parents[2] / "web/dist"
    if directory.is_dir():
        app.mount("/", StaticFiles(directory=directory, html=True))
    else:
        @app.get("/")
        async def missing_web():
            raise _RequestError("web_not_built", 503)
    return app
