"""Read native daily caches and publish a current source pool one file at a time."""
import hashlib
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
import uuid

from . import tdx_acquisition as acquisition


def read_daily_cache(client_directory, symbol):
    if not isinstance(symbol, str) or not re.fullmatch(r"[0-9]{6}\.(?:SH|SZ|BJ)", symbol):
        raise acquisition.AcquireError("invalid_tdx_symbol")
    client = Path(client_directory).resolve()
    code, venue = symbol.split(".")
    market = venue.lower()
    path = acquisition._inside(client / "vipdoc" / market / "lday" / f"{market}{code}.day", client)
    raw = acquisition._capture(path)
    if raw is None:
        raise acquisition.AcquireError("daily_cache_missing")
    return raw


def current_symbols(client_directory):
    acquisition._client_identity(Path(client_directory).resolve())
    request = dict(id=1, method="get_stock_list", params=dict(market="5", list_type=0))
    body = json.dumps(request, separators=(",", ":")).encode("utf-8")
    status, raw = acquisition._http(17709, "POST", "/", body, {"Content-Type": "application/json"}, budget=10)
    response = acquisition._decode_json(raw)
    result = response.get("result") if isinstance(response, dict) else None
    values = result.get("Value") if isinstance(result, dict) else None
    if (status != 200 or not isinstance(response, dict) or type(response.get("id")) is not int or response["id"] != 1
            or result is None or result.get("ErrorId") != "0" or type(values) is not list or not 1 <= len(values) <= 25000
            or any(type(value) is not str or not re.fullmatch(r"[0-9]{6}\.(?:SH|SZ|BJ)", value) for value in values)
            or len(set(values)) != len(values)):
        raise acquisition.AcquireError("invalid_stock_list")
    return values, dict(request_utf8=body.decode("utf-8"), response_utf8=raw.decode("utf-8"))


def import_current_caches(root, client_directory, *, port=8765, start_at=None):
    root = Path(root).resolve()
    config = acquisition._config(root, port)
    symbols, capture = current_symbols(client_directory)
    pool_size = len(symbols)
    if start_at is not None and start_at not in symbols:
        raise acquisition.AcquireError("invalid_tdx_symbol")
    skipped_prefix = symbols.index(start_at) if start_at is not None else 0
    symbols = symbols[skipped_prefix:]
    directory = root / "acquisition" / "daily-cache" / uuid.uuid4().hex
    directory.mkdir(parents=True)
    (directory / "catalog.json").write_text(json.dumps(capture, ensure_ascii=False), encoding="utf-8")
    report = dict(status="running", coverage="partial", expected=len(symbols), processed=0,
                  committed=0, missing=0, failed=0, source_rows=0, evidence_directory=str(directory),
                  pool_sha256=hashlib.sha256(capture["response_utf8"].encode("utf-8")).hexdigest(),
                  pool_semantics="current_source_market_5_not_historical_universe", current_symbol=None,
                  pool_size=pool_size, skipped_prefix=skipped_prefix)

    def save():
        path = directory / "progress.json"
        temporary = directory / "progress.tmp"
        temporary.write_text(json.dumps(report, ensure_ascii=False), encoding="utf-8")
        for attempt in range(10):
            try:
                temporary.replace(path)
                break
            except OSError as error:
                # Windows readers without delete sharing briefly block replacement.
                if getattr(error, "winerror", None) not in {5, 32, 33} or attempt == 9:
                    raise
                time.sleep(0.05)

    def record(outcome):
        with (directory / "outcomes.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(outcome, ensure_ascii=False) + "\n")
        report["processed"] += 1
        save()

    save()
    try:
        for symbol in symbols:
            report["current_symbol"] = symbol
            save()
            try:
                raw = read_daily_cache(client_directory, symbol)
            except acquisition.AcquireError as error:
                state = "missing" if error.code == "daily_cache_missing" else "failed"
                report[state] += 1
                record(dict(symbol=symbol, status=state, error_code=error.code))
                continue
            sha = hashlib.sha256(raw).hexdigest()
            parameters = urlencode(dict(format_id="tdx-public-day-v1", filename=f"{symbol}.day",
                                         instrument=symbol, venue=symbol[-2:]))
            headers = {"Origin": f"http://127.0.0.1:{port}", "X-Anatrading-Token": config["csrf_token"],
                       "Content-Type": "application/octet-stream"}
            try:
                status, reply = acquisition._http(port, "POST", f"/api/import?{parameters}", raw, headers, budget=30)
                response = acquisition._decode_json(reply)
                attempt = response.get("attempt") if isinstance(response, dict) else None
                if status != 200 or not isinstance(attempt, dict) or attempt.get("raw_sha256") != sha:
                    raise acquisition.AcquireError("http_result_unknown")
                if attempt.get("status") == "committed" and isinstance(attempt.get("snapshot_id"), str) and re.fullmatch(r"[0-9a-f]{64}", attempt["snapshot_id"]):
                    report["committed"] += 1
                    report["source_rows"] += len(raw) // 32
                else:
                    report["failed"] += 1
                record(dict(symbol=symbol, **attempt))
            except acquisition.AcquireError as error:
                report["failed"] += 1
                record(dict(symbol=symbol, status="publication_unknown", raw_sha256=sha, error_code=error.code))
                report["status"] = "failed"
                break
        else:
            report["status"] = "completed"
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        save()
        raise
    except OSError:
        report.update(status="failed", error_code="storage_io_error")
        try:
            save()
        except OSError:
            pass
        raise
    if report["committed"] == report["expected"]:
        report["coverage"] = "selected_current_list_cache_files" if skipped_prefix else "all_current_list_cache_files"
    report["current_symbol"] = None
    save()
    return report
