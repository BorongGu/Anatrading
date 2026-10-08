"""Received HTTP values stay separate from binary-cache approximations."""
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from anatrading.formats import decode, preflight
from anatrading.models import DecodeError, NonMarketPayload


FORMAT = "tdx-http-market-v1"
FIELDS = ("Date", "Time", "Open", "High", "Low", "Close", "Volume", "Amount")


def capture(*, time="93100", opening="11.20", volume="9007199254740993", method="get_market_data"):
    request = dict(id=401, method=method, params=dict(stock_list=["600059.SH"], period="1m",
                   end_time="20260930150000", count=720, dividend_type="none", fill_data=False))
    stock = dict(ErrorId="0", Date=["20260928"], Time=[time], Open=[opening], High=["11.85"],
                 Low=["11.10"], Close=["11.30"], Volume=[volume], Amount=["37.02"], ForwardFactor=["1.000000"])
    response = dict(id=401, result=dict(ErrorId="0", Value={"600059.SH": stock}))
    return dict(request_utf8=json.dumps(request), response_utf8=json.dumps(response))


def encoded(bundle):
    return json.dumps(bundle).encode("utf-8")


def test_capture_keeps_original_strings_and_derived_minute_label():
    bundle = capture()
    data = decode(encoded(bundle), FORMAT)
    row = data.rows[0]
    assert row.label == "2026-09-28T09:31"
    assert row.tokens["source_time"] == "93100"
    assert row.tokens["open"] == "11.20"
    assert row.values["open"] == Decimal("11.20")
    assert row.values["volume"] == 9007199254740993
    assert row.locator == "response:$.result.Value.600059.SH:index:0"
    assert row.volume_shares is None and row.amount_cny is None
    assert data.metadata["response_sha256"] == hashlib.sha256(bundle["response_utf8"].encode()).hexdigest()
    assert data.contract["raw_kind"] == "http_capture_bundle"
    assert data.contract["source_semantics"]["fields"]["adjustment"]["status"] == "assumed"


@pytest.mark.parametrize("time,label", [("130100", "2026-09-28T13:01"), ("093100", "2026-09-28T09:31"),
                                       ("250000", None), ("93101", None), ("1500", None)])
def test_source_clock_is_not_truncated_or_rewritten(time, label):
    row = decode(encoded(capture(time=time)), FORMAT).rows[0]
    assert row.label == label and row.tokens["source_time"] == time


def test_numeric_failure_retains_received_value():
    row = decode(encoded(capture(opening="1.0000000000000000001", volume="1.5")), FORMAT).rows[0]
    assert row.values["open"] is None and row.values["volume"] is None
    assert row.tokens["open"] == "1.0000000000000000001"


@pytest.mark.parametrize("change", ["id", "stock", "length", "numeric_type", "empty", "duplicate"])
def test_malformed_response_is_rejected(change):
    bundle = capture(); response = json.loads(bundle["response_utf8"])
    stock = response["result"]["Value"]["600059.SH"]
    if change == "id": response["id"] = 402
    if change == "stock": response["result"]["Value"] = {"000001.SZ": stock}
    if change == "length": stock["High"] = []
    if change == "numeric_type": stock["Volume"] = [9007199254740993]
    if change == "empty": response["result"]["Value"]["600059.SH"] = {"ErrorId": "0", "Value": []}
    bundle["response_utf8"] = json.dumps(response)
    if change == "duplicate": bundle["response_utf8"] = bundle["response_utf8"].replace('"id": 401', '"id": 401, "id": 401')
    with pytest.raises(DecodeError): decode(encoded(bundle), FORMAT)


def test_nonmarket_request_is_rejected_before_persistence():
    with pytest.raises(NonMarketPayload): preflight(encoded(capture(method="get_account")), FORMAT)


def test_private_real_capture_matches_original_tokens_and_cache_labels():
    folder = Path(__file__).resolve().parents[1] / "artifacts/qualification/minute-read/20261008T140439Z"
    if not folder.exists(): pytest.skip("Real local sample unavailable; no network fallback")
    raw = (folder / "response.bin").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "826e7bcca37b7dde90a74f6348877044c77dbc1f678629b1a92c1793a6dba4a2"
    bundle = dict(request_utf8=(folder / "request.json").read_text(), response_utf8=raw.decode())
    data = decode(encoded(bundle), FORMAT)
    source = json.loads(raw)["result"]["Value"]["600059.SH"]
    assert len(data.rows) == 720
    assert data.rows[0].label == "2026-09-28T09:31" and data.rows[-1].label == "2026-09-30T15:00"
    for index, row in enumerate(data.rows):
        for field in FIELDS[2:]:
            assert row.tokens[field.lower()] == source[field][index]
            assert row.values[field.lower()] == Decimal(source[field][index])


def test_json_and_parquet_preserve_capture_values_and_tokens(tmp_path):
    from anatrading.store import EvidenceStore
    import pyarrow.parquet as pq

    with EvidenceStore(tmp_path / "store") as store:
        imported = store.import_bytes(encoded(capture()), FORMAT)
        assert imported["status"] == "committed"
        snapshot = imported["snapshot_id"]
        query = store.query(snapshot)
        exported = store.export_json(snapshot)
        assert json.loads(Path(exported["path"]).read_bytes()) == query
        row = query["rows"][0]
        assert row["tokens"]["open"] == "11.20" and row["tokens"]["source_time"] == "93100"
        assert row["values"]["volume"] == "9007199254740993"
        parquet = store.export_parquet(snapshot)
        restored = pq.read_table(parquet["path"]).to_pylist()[0]
        assert restored["source_volume"] == 9007199254740993
        assert restored["source_open"] == Decimal("11.20")
        assert restored["volume_shares"] is None and restored["amount_cny"] is None


def test_reader_keeps_exact_response_bytes_without_newline_conversion(monkeypatch):
    from anatrading import tdx_market

    response = b'{"id":1,"result":{}}\r\n'
    seen = []
    monkeypatch.setattr(tdx_market.acquisition, "_client_identity", lambda path: None)
    def http(port, method, path, body, headers, *, budget):
        seen.append((port, method, json.loads(body), budget))
        return 200, response
    monkeypatch.setattr(tdx_market.acquisition, "_http", http)
    raw = tdx_market.read_minutes("D:/tdx_64", "600059.SH", end_time="20260930150000")
    bundle = json.loads(raw)
    assert bundle["response_utf8"].encode() == response
    assert len(seen) == 1 and seen[0][0:2] == (17709, "POST") and seen[0][3] == 10
    assert seen[0][2]["params"]["fill_data"] is False
    with pytest.raises(DecodeError): tdx_market.read_minutes("D:/tdx_64", "600059.SH", count=0)
    assert len(seen) == 1


def test_read_command_imports_capture_without_manual_export(tmp_path, monkeypatch, capsys):
    from anatrading.cli import main
    from anatrading import tdx_market
    from anatrading.store import EvidenceStore

    calls = []
    def read(client, symbol, **kwargs):
        calls.append((symbol, kwargs))
        return encoded(capture())
    monkeypatch.setattr(tdx_market, "read_minutes", read)
    root = tmp_path / "store"
    assert main(["--root", str(root), "read-tdx-minutes", "--symbol", "600059.SH"]) == 0
    imported = json.loads(capsys.readouterr().out)
    assert imported["status"] == "committed"
    assert calls == [("600059.SH", {"count": 720, "end_time": ""})]
    with EvidenceStore(root) as store:
        assert store.query(imported["snapshot_id"])["rows"][0]["tokens"]["source_time"] == "93100"
