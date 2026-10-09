"""Local single-snapshot HTTP adapter; all Store work has one owning thread."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import inspect
import json
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
from .candle_geometry import geometry_report
from .models import DecodeError
from .numeric import NumericError
from .store import EvidenceStore, StoreError, _identity
from .tdx_acquisition import AcquireError, data_root_id
from .tdx_market import read_minutes
from .tdx_daily import read_daily_cache
from .volume_at_time import volume_report
from .price_channel import channel_report
from .true_range import range_report
from .daily_volume import daily_volume_report
from .path_efficiency import efficiency_report
from .tdx_reference import read_reference
from .daily_coverage import collection_runs, coverage_report
from .daily_screen import screen_report
from .minute_daily_reconciliation import reconciliation_report
from .source_actions import action_captures, action_window, captured_actions


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
    "invalid_tdx_http_capture", "invalid_tdx_http_response", "invalid_tdx_http_rows",
    "client_fingerprint_changed", "client_architecture_changed", "client_identity_unavailable",
    "source_path_outside_client", "source_file_limit", "http_result_unknown", "response_limit", "invalid_response",
    "invalid_tdx_symbol", "daily_cache_missing", "cache_unstable", "invalid_day_capture",
    "invalid_tdx_reference_request", "invalid_tdx_reference_response", "tdx_reference_unavailable",
    "invalid_daily_cache_runs", "daily_cache_evidence_mismatch",
    "invalid_daily_screen",
    "invalid_daily_followup",
    "followup_screen_mismatch",
    "invalid_reference_capture", "reference_capture_mismatch", "reference_capture_unavailable",
    "reference_capture_not_actions", "invalid_action_window", "action_reference_window_unavailable",
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
    except (StoreError, DecodeError, NumericError, AcquireError) as error:
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
    return dict(query=query, geometry=geometry_report(query), display=[_display(row) for row in query["rows"]], navigation=navigation)


def _pair_claim(metadata):
    interpretation = metadata.get("interpretation", {})
    codes, venues = set(), set()
    for token in (metadata.get("source_code"), interpretation.get("instrument")):
        if token is None:
            continue
        match = re.fullmatch(r"(?:(SH|SZ|BJ)\.)?([0-9]{6})(?:\.(SH|SZ|BJ))?", token.upper())
        if match is None:
            raise _RequestError("background_symbol_unavailable", 409)
        codes.add(match[2])
        venues.update(value for value in (match[1], match[3]) if value)
    venues.update(str(value).upper() for value in (metadata.get("source_venue"), interpretation.get("venue")) if value)
    if len(codes) > 1 or len(venues) > 1:
        raise _RequestError("background_symbol_mismatch", 409)
    if len(codes) != 1 or len(venues) != 1 or not venues <= {"SH", "SZ", "BJ"}:
        raise _RequestError("background_symbol_unavailable", 409)
    return next(iter(codes)), next(iter(venues))


def _paired_sources(store, minute_snapshot, daily_snapshot):
    minute_meta = store.snapshot_catalog(minute_snapshot)[0]["metadata"]
    daily_meta = store.snapshot_catalog(daily_snapshot)[0]["metadata"]
    if minute_meta.get("period") != "1m" or daily_meta.get("period") != "1d":
        raise _RequestError("background_period_mismatch", 409)
    if _pair_claim(minute_meta) != _pair_claim(daily_meta):
        raise _RequestError("background_symbol_mismatch", 409)
    if (minute_meta.get("instrument_id") and daily_meta.get("instrument_id")
            and minute_meta["instrument_id"] != daily_meta["instrument_id"]):
        raise _RequestError("background_symbol_mismatch", 409)
    assets = {meta.get("interpretation", {}).get("asset_type") for meta in (minute_meta, daily_meta)} - {None}
    if len(assets) > 1:
        raise _RequestError("background_symbol_mismatch", 409)


def _daily_background(store, minute_snapshot, daily_snapshot, ordinal, window=60):
    if type(ordinal) is not int or ordinal < 1:
        raise _RequestError("invalid_request")
    if window is not None and (type(window) is not int or not 1 <= window <= _MAX_ROWS):
        raise _RequestError("invalid_request")
    _paired_sources(store, minute_snapshot, daily_snapshot)
    anchor_query = _bounded_query(store, minute_snapshot, dict(ordinal_start=ordinal, ordinal_end=ordinal))
    if not anchor_query["rows"]:
        raise _RequestError("background_anchor_unlocated")
    anchor_row = anchor_query["rows"][0]
    anchor_date = date.fromisoformat(anchor_row["label"][:10])
    cutoff = (anchor_date - timedelta(days=1)).isoformat()
    selection = dict(cutoff=cutoff)
    context = _bounded_query(store, daily_snapshot, selection)
    if window is not None and len(context["rows"]) > window:
        first_date = context["rows"][-window]["label"]
        ordinals = [row["ordinal"] for row in context["rows"] if row["label"] >= first_date]
        selection.update(ordinal_start=min(ordinals), ordinal_end=max(ordinals))
    daily = _query_view(store, daily_snapshot, selection)
    latest = daily["query"]["rows"][-1]["label"] if daily["query"]["rows"] else None
    anchor = dict(snapshot_id=minute_snapshot, ordinal=ordinal, label=anchor_row["label"])
    identity = dict(method_id="prior-source-date-background-v1", anchor=anchor, daily_query_id=daily["query"]["query_id"])
    return dict(**identity, background_id=_identity(identity), daily=daily,
                pairing_status="assumed_text_match", qualification="source_date_retrospective_only",
                requested_rows=window, context_unlocated_rows=len(context["unlocated"]),
                latest_source_date=latest,
                calendar_gap_days=None if latest is None else (anchor_date - date.fromisoformat(latest)).days)


def _geometry_export(store, snapshot_id, selection, expected_query, expected_geometry):
    query = _bounded_query(store, snapshot_id, selection)
    if query["query_id"] != expected_query:
        raise _RequestError("query_id_mismatch", 409)
    geometry = geometry_report(query)
    if geometry["geometry_id"] != expected_geometry:
        raise _RequestError("geometry_id_mismatch", 409)
    content = json.dumps(dict(query=query, geometry=geometry), ensure_ascii=False,
                         allow_nan=False, separators=(",", ":")).encode("utf-8")
    return content, hashlib.sha256(content).hexdigest()


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


class _ShutdownResponse(JSONResponse):
    def __init__(self, content, callback):
        super().__init__(content, status_code=202)
        self.callback = callback

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.callback()


def create_app(root, *, port=8765, web_directory=None, on_shutdown=None):
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("invalid_port")
    if on_shutdown is not None and (not callable(on_shutdown) or inspect.iscoroutinefunction(on_shutdown)
                                   or inspect.iscoroutinefunction(getattr(on_shutdown, "__call__", None))):
        raise ValueError("invalid_shutdown_callback")
    token = secrets.token_urlsafe(32)
    owner = _StoreThread(root)
    upload_busy = False
    callback_called = False

    def request_exit():
        nonlocal callback_called
        if not callback_called:
            callback_called = True
            on_shutdown()

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
                    max_query_rows=_MAX_ROWS, mode="retrospective", data_root_id=data_root_id(root))

    @app.post("/api/shutdown")
    async def shutdown(request: Request):
        _parameters(request, set())
        try:
            async for chunk in request.stream():
                if chunk:
                    raise _RequestError("invalid_request")
        except ClientDisconnect:
            raise _RequestError("upload_incomplete") from None
        if on_shutdown is None:
            raise _RequestError("shutdown_unavailable", 503)
        response = _ShutdownResponse(dict(status="shutdown_requested", data_root_id=data_root_id(root)), request_exit)
        owner.accepting = False
        return response

    @app.get("/api/snapshots")
    async def snapshots(request: Request):
        _parameters(request, set())
        return {"snapshots": await owner.call(lambda store: store.snapshot_catalog())}

    @app.get("/api/attempts")
    async def attempts(request: Request):
        _parameters(request, set())
        return {"attempts": await owner.call(lambda store: store.attempts())}

    @app.get("/api/action-captures")
    async def saved_action_captures(request: Request):
        _parameters(request, set())
        return {"captures": await owner.call(lambda store: action_captures(root))}

    @app.get("/api/action-window/{snapshot_id}")
    async def saved_action_window(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "capture_id", "query_id", "start", "end"},
                                 ("capture_id", "query_id", "start", "end"))
        selection = _selection(parameters)

        def calculate(store):
            query = _bounded_query(store, snapshot_id, selection)
            if query["query_id"] != parameters["query_id"]:
                raise _RequestError("query_id_mismatch", 409)
            reference = captured_actions(root, parameters["capture_id"])
            if _pair_claim(query["metadata"]) != _pair_claim(dict(source_code=reference["target"])):
                raise _RequestError("background_symbol_mismatch", 409)
            return action_window(query, reference, parameters["start"], parameters["end"])

        return JSONResponse(await owner.call(calculate))

    @app.get("/api/daily-cache-runs")
    async def daily_cache_runs(request: Request):
        _parameters(request, set())
        return {"runs": await owner.call(lambda store: collection_runs(root))}

    @app.get("/api/daily-cache-coverage")
    async def daily_cache_coverage(request: Request):
        parameters = _parameters(request, {"run_ids"}, ("run_ids",))
        return {"coverage": await owner.call(lambda store: coverage_report(
            root, store.snapshot_catalog(), parameters["run_ids"].split(",")))}

    @app.get("/api/daily-screen")
    async def daily_screen(request: Request):
        parameters = _parameters(request, {"run_ids", "source_date", "channel_lookback", "volume_lookback",
            "efficiency_lookback", "channel_relation", "minimum_volume", "minimum_efficiency", "direction"},
            ("run_ids", "source_date"))
        run_ids = parameters.pop("run_ids").split(",")
        try:
            for name in ("channel_lookback", "volume_lookback", "efficiency_lookback"):
                if name in parameters:
                    parameters[name] = int(parameters[name])
        except ValueError:
            raise _RequestError("invalid_daily_screen") from None
        return {"screen": await owner.call(lambda store: screen_report(root, store.snapshot_catalog(), run_ids, **parameters))}

    @app.get("/api/daily-followup")
    async def daily_followup(request: Request):
        parameters = _parameters(request, {"run_ids", "source_date", "evaluation_date", "screen_id", "channel_lookback", "volume_lookback",
            "efficiency_lookback", "channel_relation", "minimum_volume", "minimum_efficiency", "direction"},
            ("run_ids", "source_date", "evaluation_date"))
        run_ids = parameters.pop("run_ids").split(",")
        expected_screen_id = parameters.pop("screen_id", None)
        try:
            for name in ("channel_lookback", "volume_lookback", "efficiency_lookback"):
                if name in parameters:
                    parameters[name] = int(parameters[name])
        except ValueError:
            raise _RequestError("invalid_daily_screen") from None
        return {"followup": await owner.call(lambda store: screen_report(
            root, store.snapshot_catalog(), run_ids, expected_screen_id=expected_screen_id, **parameters))}

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

    @app.post("/api/read-tdx-minutes")
    async def read_tdx_minutes(request: Request):
        nonlocal upload_busy
        parameters = _parameters(request, {"symbol", "count", "end_time"}, ("symbol",))
        try:
            count = int(parameters.get("count", "720"))
        except ValueError:
            raise _RequestError("invalid_request") from None
        if not 1 <= count <= _MAX_ROWS:
            raise _RequestError("invalid_request")
        async for chunk in request.stream():
            if chunk:
                raise _RequestError("invalid_request")
        if not owner.accepting:
            raise _RequestError("service_closing", 503)
        if upload_busy:
            raise _RequestError("upload_in_progress", 409)
        symbol = parameters["symbol"]

        def operation(store):
            raw = read_minutes(Path(r"D:\tdx_64"), symbol, count=count, end_time=parameters.get("end_time", ""))
            return store.import_bytes(raw, "tdx-http-market-v1", filename=f"{symbol}.http.json",
                                      interpretation={"instrument": symbol, "venue": symbol[-2:], "asset_type": "stock"})

        def finished(future):
            nonlocal upload_busy
            upload_busy = False

        upload_busy, submitted = True, False
        try:
            future = owner.submit(operation)
            future.add_done_callback(finished)
            submitted = True
            return {"attempt": await asyncio.shield(future)}
        finally:
            if not submitted:
                upload_busy = False

    @app.post("/api/read-tdx-daily-cache")
    async def read_tdx_daily_cache(request: Request):
        nonlocal upload_busy
        parameters = _parameters(request, {"symbol"}, ("symbol",))
        async for chunk in request.stream():
            if chunk:
                raise _RequestError("invalid_request")
        if not owner.accepting:
            raise _RequestError("service_closing", 503)
        if upload_busy:
            raise _RequestError("upload_in_progress", 409)
        symbol = parameters["symbol"]

        def operation(store):
            raw = read_daily_cache(Path(r"D:\tdx_64"), symbol)
            return store.import_bytes(raw, "tdx-public-day-v1", filename=f"{symbol}.day",
                                      interpretation={"instrument": symbol, "venue": symbol[-2:]})

        def finished(future):
            nonlocal upload_busy
            upload_busy = False

        upload_busy, submitted = True, False
        try:
            future = owner.submit(operation)
            future.add_done_callback(finished)
            submitted = True
            return {"attempt": await asyncio.shield(future)}
        finally:
            if not submitted:
                upload_busy = False

    @app.post("/api/read-tdx-reference")
    async def read_tdx_reference(request: Request):
        parameters = _parameters(request, {"kind", "target", "start", "end"}, ("kind", "target", "start", "end"))
        async for chunk in request.stream():
            if chunk:
                raise _RequestError("invalid_request")
        return {"reference": await owner.call(lambda store: read_reference(
            root, Path(r"D:\tdx_64"), **parameters))}

    @app.get("/api/query/{snapshot_id}")
    async def query(snapshot_id: str, request: Request):
        selection = _selection(_parameters(request, _SELECTION))
        return JSONResponse(await owner.call(lambda store: _query_view(store, snapshot_id, selection)))

    @app.get("/api/volume/{snapshot_id}")
    async def volume(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "lookback"})
        selection = _selection(parameters)
        try:
            lookback = int(parameters.get("lookback", "20"))
        except ValueError:
            raise _RequestError("invalid_request") from None
        if not 2 <= lookback <= 252:
            raise _RequestError("invalid_request")

        def calculate(store):
            query = _bounded_query(store, snapshot_id, selection)
            context = _bounded_query(store, snapshot_id, {key: value for key, value in selection.items()
                                                        if key in {"cutoff", "mode"}})
            return volume_report(query, context, lookback)

        return JSONResponse(await owner.call(calculate))

    @app.get("/api/price-channel/{snapshot_id}")
    async def price_channel(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "lookback"})
        selection = _selection(parameters)
        try:
            lookback = int(parameters.get("lookback", "20"))
        except ValueError:
            raise _RequestError("invalid_request") from None
        if not 2 <= lookback <= 252:
            raise _RequestError("invalid_request")

        def calculate(store):
            query = _bounded_query(store, snapshot_id, selection)
            context = _bounded_query(store, snapshot_id, {key: value for key, value in selection.items()
                                                        if key in {"cutoff", "mode"}})
            return channel_report(query, context, lookback)

        return JSONResponse(await owner.call(calculate))

    @app.get("/api/daily-volume/{snapshot_id}")
    async def daily_volume(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "lookback"})
        selection = _selection(parameters)
        try:
            lookback = int(parameters.get("lookback", "20"))
        except ValueError:
            raise _RequestError("invalid_request") from None
        if not 2 <= lookback <= 252:
            raise _RequestError("invalid_request")

        def calculate(store):
            query = _bounded_query(store, snapshot_id, selection)
            context = _bounded_query(store, snapshot_id, {key: value for key, value in selection.items()
                                                        if key in {"cutoff", "mode"}})
            return daily_volume_report(query, context, lookback)

        return JSONResponse(await owner.call(calculate))

    @app.get("/api/path-efficiency/{snapshot_id}")
    async def path_efficiency(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "lookback"})
        selection = _selection(parameters)
        try:
            lookback = int(parameters.get("lookback", "10"))
        except ValueError:
            raise _RequestError("invalid_request") from None
        if not 2 <= lookback <= 252:
            raise _RequestError("invalid_request")

        def calculate(store):
            query = _bounded_query(store, snapshot_id, selection)
            context = _bounded_query(store, snapshot_id, {key: value for key, value in selection.items()
                                                        if key in {"cutoff", "mode"}})
            return efficiency_report(query, context, lookback)

        return JSONResponse(await owner.call(calculate))

    @app.get("/api/true-range/{snapshot_id}")
    async def true_range(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "period"})
        selection = _selection(parameters)
        try:
            period = int(parameters.get("period", "14"))
        except ValueError:
            raise _RequestError("invalid_request") from None
        if not 1 <= period <= 252:
            raise _RequestError("invalid_request")

        def calculate(store):
            query = _bounded_query(store, snapshot_id, selection)
            context = _bounded_query(store, snapshot_id, {key: value for key, value in selection.items()
                                                        if key in {"cutoff", "mode"}})
            return range_report(query, context, period)

        return JSONResponse(await owner.call(calculate))

    @app.get("/api/daily-background/{snapshot_id}")
    async def daily_background(snapshot_id: str, request: Request):
        parameters = _parameters(request, {"daily_snapshot", "ordinal", "window"}, ("daily_snapshot", "ordinal"))
        try:
            ordinal = int(parameters["ordinal"])
            window = None if parameters.get("window") == "all" else int(parameters.get("window", "60"))
        except ValueError:
            raise _RequestError("invalid_request") from None
        return JSONResponse(await owner.call(lambda store: _daily_background(store, snapshot_id, parameters["daily_snapshot"], ordinal, window)))

    @app.get("/api/minute-daily-reconciliation/{snapshot_id}")
    async def minute_daily_reconciliation(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "daily_snapshot", "query_id", "amount_multiplier"},
                                 ("daily_snapshot", "query_id"))
        selection = _selection(parameters)
        multiplier = parameters.get("amount_multiplier")
        if multiplier is not None and multiplier not in {"1", "10000"}:
            raise _RequestError("invalid_request")

        def calculate(store):
            _paired_sources(store, snapshot_id, parameters["daily_snapshot"])
            minute = _bounded_query(store, snapshot_id, selection)
            if minute["query_id"] != parameters["query_id"]:
                raise _RequestError("query_id_mismatch", 409)
            daily = _bounded_query(store, parameters["daily_snapshot"], {})
            return reconciliation_report(minute, daily, None if multiplier is None else int(multiplier))

        return JSONResponse(await owner.call(calculate))

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

    @app.post("/api/geometry-export/{snapshot_id}")
    async def geometry_export(snapshot_id: str, request: Request):
        parameters = _parameters(request, {*_SELECTION, "query_id", "geometry_id"}, ("query_id", "geometry_id"))
        query_id, geometry_id = parameters["query_id"], parameters["geometry_id"]
        if any(not re.fullmatch("[0-9a-f]{64}", value) for value in (query_id, geometry_id)):
            raise _RequestError("invalid_request")
        selection = _selection(parameters)
        try:
            async for chunk in request.stream():
                if chunk:
                    raise _RequestError("invalid_request")
        except ClientDisconnect:
            raise _RequestError("upload_incomplete") from None
        content, digest = await owner.call(lambda store: _geometry_export(store, snapshot_id, selection, query_id, geometry_id))
        return Response(content, media_type="application/json",
                        headers={"X-Query-Id": query_id, "X-Geometry-Id": geometry_id, "X-Content-SHA256": digest,
                                 "Content-Disposition": f'attachment; filename="anatrading-{geometry_id}.json"'})

    directory = Path(web_directory) if web_directory is not None else Path(__file__).resolve().parents[2] / "web/dist"
    if directory.is_dir():
        app.mount("/", StaticFiles(directory=directory, html=True))
    else:
        @app.get("/")
        async def missing_web():
            raise _RequestError("web_not_built", 503)
    return app
