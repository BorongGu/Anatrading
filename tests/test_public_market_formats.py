"""Synthetic capture counterexamples; these do not qualify a real data source."""
import base64
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path

import pytest

from anatrading.formats import decode, preflight
from anatrading.models import DecodeError, NonMarketPayload, VERSIONS
from anatrading.public_market import (
    CAPTURE_VERSION, MAX_BODY_BYTES, MAX_CAPTURE_BYTES, PUBLIC_FORMAT_IDS,
    build_capture, build_request, canonical_json, decoder_identity,
    preflight_capture, public_contract, validate_capture,
)
from anatrading.research_series import daily_bars
from anatrading.store import EvidenceStore


TX, SINA = PUBLIC_FORMAT_IDS
SYMBOL = "600111.SH"
SINA_PREFIX = b"/*<script>location.href='//sina.com';</script>*/\n=("


def tx_row(day="2024-12-31", volume="123.4500", **values):
    row = [day, "12.3400", "12.5000", "13.0000", "12.0000", volume,
           {"x": "uninterpreted"}, "0.123", "456.7800", "7", "8"]
    for key, value in values.items():
        row[int(key)] = value
    return row


def sina_row(day="2050-01-03 09:31:00", volume="123.4500"):
    return dict(day=day, open="12.3400", close="12.5000", high="13.0000",
                low="12.0000", volume=volume, amount="456.7800")


def tx_capture(rows=None, *, request=None, extra=None, symbol="sh600111", body=None, **overrides):
    request = request or build_request("tencent", SYMBOL, "1d", start="2024-12-30", end="2025-01-03", count=640)
    stock = {"day": [tx_row()] if rows is None else rows, "qt": {"unrelated": ["current quote"]}}
    stock.update(extra or {})
    payload = {"code": 0, "msg": "", "data": {symbol: stock}}
    if body is None:
        body = request["parameters"]["_var"].encode() + b"=" + canonical_json(payload)
    args = dict(status=200, response_url=request["url"],
                response_headers=[("Content-Type", "text/html; charset=UTF-8")], body=body)
    args.update(overrides)
    return build_capture("tencent", request, **args)


def sina_capture(rows=None, *, request=None, body=None, **overrides):
    request = request or build_request("sina", SYMBOL, "1m", count=1970)
    if body is None:
        body = SINA_PREFIX + canonical_json([sina_row()] if rows is None else rows) + b");"
    args = dict(status=200, response_url=request["url"],
                response_headers=[("Content-Type", "application/javascript; charset=GBK")], body=body)
    args.update(overrides)
    return build_capture("sina", request, **args)


def mutate_capture(raw, mutate):
    obj = json.loads(raw)
    mutate(obj)
    return canonical_json(obj)


def mutate_body(raw, change):
    def mutate(obj):
        body = change(base64.b64decode(obj["body_base64"]))
        obj["body_base64"] = base64.b64encode(body).decode()
        obj["body_sha256"] = hashlib.sha256(body).hexdigest()
    return mutate_capture(raw, mutate)


def check(row, name):
    return next(item for item in row.checks if item.name == name)


@pytest.mark.parametrize("start,end,accepted", [
    ("2024-01-01", "2024-12-31", True),
    ("2024-01-01", "2025-01-01", False),
    ("2024-10-11", "2025-10-10", True),
    ("2025-01-02", "2025-01-01", False),
    ("2024-02-30", "2024-03-01", False),
    ("20241230", "2025-01-01", False),
])
def test_request_calendar_bounds_are_pure(start, end, accepted):
    if not accepted:
        with pytest.raises(DecodeError):
            build_request("tencent", SYMBOL, "1d", start=start, end=end, count=640)
    else:
        req = build_request("tencent", SYMBOL, "1d", start=start, end=end, count=640)
        assert req["parameters"]["_var"] == "kline_day" + start[:4]
        assert req["parameters"]["param"].endswith(",640,")


@pytest.mark.parametrize("source,period,kwargs", [
    ("tencent", "1d", {"start": "2024-12-30", "end": "2025-01-03", "count": v})
    for v in (0, 641, -1, True, "64", 1.5)
] + [("sina", "1m", {"count": v}) for v in (0, 1971, -1, False, "1970")]
  + [("sina", "15m", {}), ("sina", "1m", {"start": "2024-01-01"}),
     ("tencent", "1m", {"start": "2024-01-01", "end": "2024-01-03"})])
def test_request_bad_types_and_out_of_scope_combinations(source, period, kwargs):
    with pytest.raises(DecodeError):
        build_request(source, SYMBOL, period, **kwargs)


@pytest.mark.parametrize("symbol", ["600111.BJ", "sh600111", "600111", "600111.SH@secret", "600111.sh"])
def test_symbol_mapping_is_exact(symbol):
    with pytest.raises(DecodeError):
        build_request("sina", symbol, "1m")


@pytest.mark.parametrize("mutate", [
    lambda x: x.update(extra="forbidden"),
    lambda x: x.update(body_sha256="0" * 64),
    lambda x: x.update(body_sha256=x["body_sha256"].upper()),
    lambda x: x.update(request_sha256="0" * 64),
    lambda x: x.update(response_headers_sha256="0" * 64),
    lambda x: x.update(source="sina"),
    lambda x: x.update(capture_version="future"),
    lambda x: x.update(body_base64=x["body_base64"] + "\n"),
    lambda x: x["response"].update(status=True),
    lambda x: x["response"].update(url="https://localhost/secret"),
    lambda x: x["request"].update(method="POST"),
    lambda x: x["request"].update(url=x["request"]["url"] + "#x"),
    lambda x: x["request"]["headers"].update(Authorization="SECRET"),
])
def test_capture_mutations_rejected_before_store(mutate, tmp_path):
    raw = mutate_capture(tx_capture(), mutate)
    with pytest.raises(DecodeError):
        preflight(raw, TX)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["status"] == "rejected"
        assert result["raw_sha256"] is None
        assert store.list_snapshots() == []


@pytest.mark.parametrize("change", [
    lambda raw: raw + b"\n",
    lambda raw: b"\xef\xbb\xbf" + raw,
    lambda raw: raw.replace(b'"source":"tencent"', b'"source":"tencent","source":"tencent"'),
    lambda raw: raw.replace(b'"status":200', b'"status":NaN'),
    lambda raw: raw.replace(b'"status":200', b'"status":200.0'),
])
def test_noncanonical_duplicate_and_nonfinite_envelopes(change):
    with pytest.raises(DecodeError):
        validate_capture(change(tx_capture()), TX)


@pytest.mark.parametrize("headers", [
    [], [("Content-Type", "text/html")],
    [("Content-Type", "text/html; charset=UTF-8; charset=GBK")],
    [("Content-Type", "text/html; charset=UTF-8"), ("content-type", "text/html; charset=UTF-8")],
    [("Content-Type", "text/html; charset=UTF-8"), ("Content-Encoding", "gzip")],
    [("Content-Type", "text/html; charset=UTF-8"), ("Content-Length", "1"), ("Content-Length", "2")],
    [("Content-Type", "text/html; charset=UTF-8"), ("Content-Length", "1"), ("Transfer-Encoding", "chunked")],
])
def test_response_header_ambiguity_rejected(headers):
    with pytest.raises(DecodeError):
        tx_capture(response_headers=headers)


@pytest.mark.parametrize("prefix,suffix", [
    (b"alert('x');", b""), (b" ", b""), (b"", b";"), (b"", b"//x"),
])
def test_tencent_script_drift_is_nonmarket(prefix, suffix):
    raw = tx_capture()
    changed = mutate_body(raw, lambda body: prefix + body + suffix)
    with pytest.raises(DecodeError):
        preflight_capture(changed, TX)


@pytest.mark.parametrize("change", [
    lambda b: b.replace(b"kline_day2024", b"kline_day2025"),
    lambda b: b.replace(b'"code":0', b'"code":false'),
    lambda b: b.replace(b'"msg":""', b'"msg":"source error"'),
    lambda b: b.replace(b'"day":', b'"qfqday":'),
    lambda b: b.replace(b'"sh600111":', b'"sz600111":'),
    lambda b: b.replace(b'"day":', b'"day":[],"day":'),
    lambda b: b.replace(b'"x":"uninterpreted"', b'"x":NaN'),
    lambda b: b.replace(b'"x":"uninterpreted"', b'"x":"\\ud800"'),
])
def test_source_json_and_identity_rejections(change):
    with pytest.raises(DecodeError):
        preflight_capture(mutate_body(tx_capture(), change), TX)


@pytest.mark.parametrize("body", [b"", b"<html>SECRET CAPTCHA</html>", b"=([1]);", SINA_PREFIX + b"[]);alert(1)"])
def test_sina_signature_drift_never_becomes_raw(body, tmp_path):
    raw = sina_capture(body=body)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, SINA)
        assert result["status"] == "rejected" and result["raw_sha256"] is None


@pytest.mark.parametrize("rows", [[tx_row("2025-01-04")], [tx_row("2024-02-30")],
                                   [tx_row(**{"6": []})], [tx_row(**{"1": 12.34})]])
def test_recognized_invalid_market_retains_capture_without_snapshot(rows, tmp_path):
    raw = tx_capture(rows)
    assert len(preflight_capture(raw, TX).payload) == len(rows)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["status"] == "rejected"
        assert result["raw_sha256"] == hashlib.sha256(raw).hexdigest()
        assert store.list_snapshots() == []


@pytest.mark.parametrize("day", ["2025-01-03 09:31:01", "2025-01-03T09:31:00", "2025-02-30 09:31:00"])
def test_sina_label_shape_rejected(day):
    with pytest.raises(DecodeError):
        validate_capture(sina_capture([sina_row(day)]), SINA)


@pytest.mark.parametrize("raw,fmt", [(tx_capture, TX), (sina_capture, SINA)])
def test_empty_capture_has_no_empty_snapshot(raw, fmt, tmp_path):
    capture = raw([])
    assert validate_capture(capture, fmt).payload == []
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(capture, fmt)
        assert result["status"] == "rejected" and result["error_code"] == "empty_public_market_result"
        assert store.list_snapshots() == []


@pytest.mark.parametrize("volume,outcome,reason", [
    ("123.4500", "pass", None), ("123", "pass", None), ("0", "pass", None),
    ("", "not_evaluated", "missing"), ("bad", "fail", "invalid_decimal"),
    ("-1", "fail", "negative_source_quantity"), ("NaN", "fail", "nonfinite"),
    ("1e-19", "fail", "decimal_scale"), ("1e20", "fail", "decimal_range"),
])
@pytest.mark.parametrize("fmt", [TX, SINA])
def test_quantity_is_exact_unstandardized_and_never_integer_fraction(volume, outcome, reason, fmt):
    raw = tx_capture([tx_row(volume=volume)]) if fmt == TX else sina_capture([sina_row(volume=volume)])
    result = decode(raw, fmt)
    row = result.rows[0]
    assert row.tokens["volume"] == volume
    assert row.values["volume"] is row.volume_shares is row.amount_cny is None
    assert check(row, "source_quantity_decimal").outcome == outcome
    assert check(row, "source_quantity_decimal").reason == reason
    assert all(c.reason != "integer_fraction" for c in row.checks)
    if outcome == "pass":
        assert check(row, "numeric.volume").outcome == "not_evaluated"
        assert check(row, "numeric.volume").reason == "source_quantity_not_normalized"
    for key in ("zero_volume_amount", "conditional_price_bounds", "conditional_price_bounds_cent"):
        assert check(row, key).outcome == "not_evaluated"
        assert check(row, key).reason == "source_quantity_not_normalized"
    assert row.tokens["open"] == "12.3400"
    assert row.values["open"] == Decimal("12.34")
    assert row.values["amount"] == Decimal("456.78")


def test_older_context_and_saturation_retained_without_coverage_claim():
    request = build_request("tencent", SYMBOL, "1d", start="2024-12-31", end="2025-01-03", count=3)
    rows = [tx_row("2023-01-03"), tx_row("2024-12-31"), tx_row("2025-01-03")]
    result = decode(tx_capture(rows, request=request), TX, {"instrument": SYMBOL, "venue": "SH", "asset_type": "stock"})
    assert len(result.rows) == 3
    assert result.metadata["before_start_count"] == 1
    assert result.metadata["in_request_count"] == 2
    assert result.metadata["after_end_count"] == 0
    assert result.metadata["request_range_mismatch"] is True
    assert result.metadata["count_saturated"] is True
    assert result.metadata["truncated_possible"] is True
    assert result.metadata["coverage"] == "unverified"
    assert result.metadata["source_code"] == SYMBOL
    assert result.metadata["source_symbol"] == "sh600111"
    assert check(result.rows[0], "label").outcome == "pass"
    assert next(c for c in result.checks if c.name == "declared_instrument").outcome == "pass"


def test_duplicate_and_inverse_rows_are_preserved_with_checks():
    result = decode(tx_capture([tx_row("2025-01-02"), tx_row(), tx_row()]), TX)
    assert [r.ordinal for r in result.rows] == [1, 2, 3]
    assert check(result.rows[1], "source_order").outcome == "fail"
    assert check(result.rows[1], "duplicate_label").outcome == "fail"
    assert check(result.rows[2], "duplicate_label").outcome == "fail"


def test_sina_request_only_identity_and_clock_free_decode(monkeypatch):
    import anatrading.public_market as module
    class ClockForbiddenDate(date):
        @classmethod
        def today(cls):
            raise AssertionError("pure decoder read clock")
    class ClockForbiddenDatetime(datetime):
        @classmethod
        def now(cls, *args, **kwargs):
            raise AssertionError("pure decoder read clock")
    raw = sina_capture()
    expected = asdict(decode(raw, SINA))
    monkeypatch.setattr(module, "date", ClockForbiddenDate)
    monkeypatch.setattr(module, "datetime", ClockForbiddenDatetime)
    result = decode(raw, SINA)
    assert asdict(result) == expected
    assert result.metadata["response_identity"] == "absent"
    assert result.metadata.get("source_code") is None
    assert result.metadata.get("source_venue") is None
    assert result.metadata.get("source_adjustment") is None
    assert result.metadata["requested_symbol"] == SYMBOL
    assert result.metadata["period_evidence"] == "request_declared"
    assert result.metadata["instrument_id"] is None


@pytest.mark.parametrize("symbol", ["000001.SH", "510300.SH"])
def test_syntax_does_not_qualify_asset_type(symbol):
    request = build_request("sina", symbol, "1m")
    result = decode(sina_capture(request=request), SINA, {"instrument": symbol, "venue": "SH", "asset_type": "stock"})
    assert result.metadata["interpretation_status"] == "assumed"
    assert result.metadata["instrument_id"] is None
    assert next(c for c in result.checks if c.name == "instrument_identity").outcome == "not_evaluated"


@pytest.mark.parametrize("interpretation", [{"instrument": "600112.SH"}, {"venue": "SZ"},
                                             {"asset_type": "index"}, {"volume_unit": "shares"}])
def test_conflicting_public_interpretation_is_rejected(interpretation):
    with pytest.raises(DecodeError):
        decode(tx_capture(), TX, interpretation)


@pytest.mark.parametrize("fmt,raw", [(TX, tx_capture), (SINA, sina_capture)])
def test_contract_identity_is_static_and_matches_decoder(fmt, raw):
    result = decode(raw(), fmt)
    assert result.contract == public_contract(fmt)
    identity = decoder_identity(fmt)
    assert identity == dict(format_id=fmt, capture_version=CAPTURE_VERSION, decode_contract_version="1",
                            source_contract_id=hashlib.sha256(canonical_json(result.contract)).hexdigest(),
                            versions=VERSIONS)


def test_store_query_exports_idempotency_and_price_research(tmp_path):
    raw = tx_capture([tx_row("2024-12-30"), tx_row("2024-12-31")])
    with EvidenceStore(tmp_path / "store") as store:
        first = store.import_bytes(raw, TX)
        again = store.import_bytes(raw, TX)
        assert first["status"] == again["status"] == "committed"
        assert first["snapshot_id"] == again["snapshot_id"]
        assert again["reused"] is True
        result = store.query(first["snapshot_id"])
        assert [r["values"]["volume"] for r in result["rows"]] == [None, None]
        assert [r["tokens"]["volume"] for r in result["rows"]] == ["123.4500", "123.4500"]
        assert all(bar["reason"] is None for bar in daily_bars(result))
        exported = store.export_json(first["snapshot_id"])
        assert json.loads(Path(exported["path"]).read_bytes()) == result
        parquet = store.export_parquet(first["snapshot_id"])
        assert Path(parquet["path"]).is_file()
        changed = tx_capture([tx_row("2024-12-30"), tx_row("2024-12-31")], extra={"qt": {"new": "quote"}})
        other = store.import_bytes(changed, TX)
        assert other["snapshot_id"] != first["snapshot_id"]
        assert store.query(first["snapshot_id"]) == result


def test_size_and_deep_json_boundaries():
    with pytest.raises(DecodeError):
        validate_capture(b" " * (MAX_CAPTURE_BYTES + 1), TX)
    with pytest.raises(DecodeError):
        tx_capture(body=b"x" * (MAX_BODY_BYTES + 1))
    raw = mutate_body(tx_capture(), lambda b: b.replace(b'"x":"uninterpreted"',
                      b'"x":' + b"[" * 33 + b"0" + b"]" * 33))
    with pytest.raises(DecodeError):
        preflight_capture(raw, TX)


@pytest.mark.parametrize("count,accepted", [(640, True), (641, False)])
def test_full_tencent_row_bound(count, accepted):
    from datetime import timedelta
    rows = [tx_row((date(2023, 1, 1) + timedelta(days=i)).isoformat()) for i in range(count)]
    request = build_request("tencent", SYMBOL, "1d", start="2024-01-01", end="2024-12-31", count=640)
    raw = tx_capture(rows, request=request)
    if accepted:
        result = decode(raw, TX)
        assert len(result.rows) == 640
        assert result.metadata["before_start_count"] == 365
    else:
        with pytest.raises(DecodeError, match="^public_row_limit$"):
            decode(raw, TX)


def test_full_sina_1970_is_a_valid_saturated_recent_window():
    from datetime import timedelta
    rows = [sina_row((datetime(2025, 1, 3, 9, 31) + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"))
            for i in range(1970)]
    result = decode(sina_capture(rows), SINA)
    assert len(result.rows) == 1970
    assert result.metadata["count_saturated"] is True
    assert result.metadata["window_kind"] == "recent_window"
    assert result.metadata["coverage"] == "unverified"
    with pytest.raises(DecodeError, match="^public_row_limit$"):
        decode(sina_capture([*rows, sina_row()]), SINA)


def test_constructor_and_request_validation_types_are_stable():
    from anatrading.public_market import validate_request
    request = build_request("sina", SYMBOL, "1m")
    assert validate_request(request, "sina") == dict(source="sina", symbol=SYMBOL, period="1m", count=10,
                                                    start=None, end=None)
    for source in ([], {}, None, False):
        with pytest.raises(DecodeError):
            build_capture(source, request, status=200, response_url=request["url"], response_headers=[], body=b"")
        with pytest.raises(DecodeError):
            validate_request(request, source)


def test_literal_canonical_request_grammar_cannot_be_resigned_around():
    raw = tx_capture()
    for path, value in (("url", "https://user@proxy.finance.qq.com/a"), ("method", "get")):
        def mutate(obj):
            obj["request"][path] = value
            obj["request_sha256"] = hashlib.sha256(canonical_json(obj["request"])).hexdigest()
        with pytest.raises(DecodeError):
            validate_capture(mutate_capture(raw, mutate), TX)
    for token in ("0640", "+640", "640.0", "640e0"):
        obj = json.loads(raw)
        request = obj["request"]
        request["parameters"]["param"] = request["parameters"]["param"].replace(",640,", f",{token},")
        from urllib.parse import urlencode
        request["url"] = request["url"].split("?")[0] + "?" + urlencode(
            [(key, request["parameters"][key]) for key in ("_var", "param", "r")])
        obj["request_sha256"] = hashlib.sha256(canonical_json(request)).hexdigest()
        with pytest.raises(DecodeError):
            validate_capture(canonical_json(obj), TX)


def test_quantity_unavailable_research_is_not_zero_volume(tmp_path):
    from anatrading.daily_volume import daily_volume_report
    with EvidenceStore(tmp_path / "store") as store:
        imported = store.import_bytes(tx_capture([tx_row("2024-12-30"), tx_row("2024-12-31")]), TX)
        query = store.query(imported["snapshot_id"])
        report = daily_volume_report(query, query, lookback=2)
        assert all(row["reason"] == "missing_quantity" for row in report["rows"])
        assert all(row["current"] is None and row["ratio"] is None for row in report["rows"])
        import pyarrow.parquet as pq
        exported = store.export_parquet(imported["snapshot_id"])
        columns = pq.read_table(exported["path"]).to_pydict()
        assert columns["source_volume"] == [None, None]
        assert columns["volume_shares"] == [None, None]
        assert columns["amount_cny"] == [None, None]


def test_new_formats_are_readable_in_existing_http_and_research_routes(tmp_path):
    import asyncio
    import httpx
    from anatrading.workbench import create_app
    root = tmp_path / "store"
    with EvidenceStore(root) as store:
        daily = store.import_bytes(tx_capture([tx_row("2024-12-30"), tx_row("2024-12-31")]), TX)["snapshot_id"]
        minute = store.import_bytes(sina_capture(), SINA)["snapshot_id"]

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                for snapshot in (daily, minute):
                    response = await client.get("/api/query/" + snapshot)
                    assert response.status_code == 200, response.text
                    rows = response.json()["query"]["rows"]
                    assert all(row["values"]["volume"] is None for row in rows)
                    assert all(row["tokens"]["volume"] == "123.4500" for row in rows)
                response = await client.get("/api/research/single/" + daily, params={"lookback": "2"})
                assert response.status_code == 200, response.text
                assert response.json()["mode"] == "retrospective"
                response = await client.get("/api/volume/" + minute)
                assert response.status_code == 200, response.text
                assert response.json()["rows"][0]["regular"]["reason"] == "missing_quantity"
    asyncio.run(scenario())


@pytest.mark.parametrize("fmt,raw", [
    (SINA, lambda: sina_capture([{"token": "PRIVATE_MARKER", "message": "login required"}])),
    (TX, lambda: tx_capture([{"token": "PRIVATE_MARKER"}])),
    (TX, lambda: tx_capture([tx_row()[:-1]])),
])
def test_control_arrays_never_persist_as_recognized_market(fmt, raw, tmp_path):
    capture = raw()
    with pytest.raises(NonMarketPayload, match="^non_market_payload$"):
        preflight_capture(capture, fmt)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(capture, fmt)
        assert result["status"] == "rejected" and result["raw_sha256"] is None
        assert store.list_snapshots() == []


def test_business_error_is_distinct_safe_and_never_archived(tmp_path):
    raw = mutate_body(tx_capture(), lambda body: body.replace(b'"code":0', b'"code":-1').replace(
        b'"msg":""', b'"msg":"PRIVATE_MARKER source error"'))
    with pytest.raises(NonMarketPayload, match="^public_source_error$"):
        preflight_capture(raw, TX)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["error_code"] == "public_source_error"
        assert result["raw_sha256"] is None
        assert "PRIVATE_MARKER" not in json.dumps(store.attempts())
