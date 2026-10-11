"""Independent synthetic tests for the public-capture design review.

No vendor requests, real price cells, historical header reconstruction or
transport assertions are made by these constructed captures.
"""
import base64
from dataclasses import asdict
from datetime import date, datetime, timedelta
from decimal import Decimal, Inexact, localcontext
import hashlib
import json

import pytest

from anatrading.formats import decode
from anatrading.models import DecodeError
from anatrading.public_market import (
    PUBLIC_FORMAT_IDS, build_capture, build_request, canonical_json,
    preflight_capture, validate_capture,
)
from anatrading.research_series import daily_bars
from anatrading.store import EvidenceStore
from test_public_market_formats import (
    check, mutate_body, sina_capture, sina_row,
    tx_capture, tx_row,
)


TX, SINA = PUBLIC_FORMAT_IDS


def digest(data):
    return hashlib.sha256(data).hexdigest()


def rehash_request(envelope):
    envelope["request_sha256"] = digest(canonical_json(envelope["request"]))


@pytest.mark.parametrize("source", [None, [], {}, True, 0, b"tencent"])
def test_constructor_bad_source_has_stable_public_error(source):
    request = build_request("sina", "600111.SH", "1m")
    with pytest.raises(DecodeError):
        build_capture(source, request, status=200, response_url=request["url"],
                      response_headers=[], body=b"")


@pytest.mark.parametrize("path", [
    ("capture_version",), ("source",), ("request",), ("request_sha256",),
    ("response",), ("response_headers_sha256",), ("body_base64",), ("body_sha256",),
    ("request", "method"), ("request", "url"), ("request", "parameters"),
    ("request", "headers"), ("response", "status"), ("response", "url"),
    ("response", "headers"), ("response", "headers", "content-type"),
    ("response", "headers", "content-encoding"),
])
@pytest.mark.parametrize("replacement", [None, [], {}, True, 1.25])
def test_every_fixed_envelope_type_replacement_is_rejected(path, replacement):
    envelope = json.loads(tx_capture())
    target = envelope
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement
    with pytest.raises(DecodeError):
        preflight_capture(canonical_json(envelope), TX)


@pytest.mark.parametrize("url_change", [
    lambda url: url.replace("https://", "http://"),
    lambda url: url.replace("proxy.finance.qq.com", "proxy.finance.qq.com.attacker.invalid"),
    lambda url: url.replace("proxy.finance.qq.com", "user:SECRET@proxy.finance.qq.com"),
    lambda url: url.replace("proxy.finance.qq.com", "127.0.0.1"),
    lambda url: url + "&param=sh600112%2Cday%2C2024-12-30%2C2025-01-03%2C640%2C",
    lambda url: url + "#fragment",
    lambda url: url.replace("%2C", ","),
    lambda url: url.replace("/app/newfqkline", "/app/../app/newfqkline"),
])
def test_rehashed_url_cannot_expand_destination_or_request(url_change, tmp_path):
    envelope = json.loads(tx_capture())
    envelope["request"]["url"] = url_change(envelope["request"]["url"])
    envelope["response"]["url"] = envelope["request"]["url"]
    rehash_request(envelope)
    raw = canonical_json(envelope)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["status"] == "rejected"
        assert result["raw_sha256"] is None
        assert store.list_snapshots() == []
    raw_directory = tmp_path / "store" / "raw"
    assert not raw_directory.exists() or not any(p.is_file() for p in raw_directory.rglob("*"))


@pytest.mark.parametrize("field,value", [
    ("_var", "kline_day2025"), ("r", "0.2"),
    ("param", "sh600111,day,2024-12-30,2025-01-03,0640,"),
    ("param", "sh600111,day,2024-12-30,2025-01-03,640,qfq"),
    ("param", "sh600111,day,2024-12-30,2025-01-03,640,hfq"),
])
def test_rehashed_parameters_still_obey_fixed_source_contract(field, value):
    from urllib.parse import urlencode
    envelope = json.loads(tx_capture())
    request = envelope["request"]
    request["parameters"][field] = value
    request["url"] = request["url"].split("?", 1)[0] + "?" + urlencode(
        [(key, request["parameters"][key]) for key in ("_var", "param", "r")])
    envelope["response"]["url"] = request["url"]
    rehash_request(envelope)
    with pytest.raises(DecodeError):
        validate_capture(canonical_json(envelope), TX)


@pytest.mark.parametrize("mutation", [
    lambda body: body.replace(b'"x":"uninterpreted"', b'"x":1,"x":2'),
    lambda body: body.replace(b'"x":"uninterpreted"', b'"x":Infinity'),
    lambda body: body.replace(b'"x":"uninterpreted"', b'"x":-Infinity'),
    lambda body: body + b";__import__('os').system('false')",
])
def test_nested_nonfinite_duplicate_and_code_never_reach_raw(mutation, tmp_path):
    raw = mutate_body(tx_capture(), mutation)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["status"] == "rejected" and result["raw_sha256"] is None
        assert store.list_snapshots() == []


def test_json_object_code_is_preserved_as_inert_body_string(tmp_path):
    marker = tmp_path / "MUST_NOT_BE_CREATED"
    string = f"__import__('pathlib').Path({str(marker)!r}).write_text('bad')"
    raw = tx_capture([tx_row(**{"6": {"source_text": string}})])
    result = decode(raw, TX)
    assert not marker.exists()
    assert len(result.rows) == 1
    assert result.rows[0].tokens["source_object_6_locator"].endswith("[0][6]")
    assert string.encode() in base64.b64decode(json.loads(raw)["body_base64"])


def test_full_640_row_older_context_remains_one_immutable_source(tmp_path):
    end = date(2025, 1, 3)
    days = [(end - timedelta(days=i)).isoformat() for i in reversed(range(640))]
    raw = tx_capture([tx_row(day) for day in days])
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["status"] == "committed"
        query = store.query(result["snapshot_id"])
        assert [r["label"] for r in query["rows"]] == days
        assert [r["ordinal"] for r in query["rows"]] == list(range(1, 641))
        assert query["metadata"]["before_start_count"] == 635
        assert query["metadata"]["in_request_count"] == 5
        assert query["metadata"]["count_saturated"] is True
        assert query["metadata"]["coverage"] == "unverified"
        assert len(daily_bars(query)) == 640
        assert all(bar["reason"] is None for bar in daily_bars(query))
        # The evidence viewer's ordinal selection cannot silently become a
        # shortened recurrence/context for research.
        selected = store.query(result["snapshot_id"], ordinal_start=636)
        with pytest.raises(ValueError, match="ordinal_window_not_supported"):
            daily_bars(selected)
        assert len(store.query(result["snapshot_id"])["rows"]) == 640


def test_full_1970_minute_window_has_no_calendar_or_clock_guess(tmp_path):
    origin = datetime(2050, 1, 3, 9, 31)
    rows = [sina_row((origin + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")) for i in range(1970)]
    raw = sina_capture(rows)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, SINA, interpretation={"instrument": "600111.SH", "asset_type": "stock"})
        assert result["status"] == "committed"
        query = store.query(result["snapshot_id"])
        assert len(query["rows"]) == 1970
        assert query["metadata"]["count_saturated"] is True
        assert query["metadata"]["acquisition_clock"] == "unavailable"
        assert query["metadata"]["response_identity"] == "absent"
        assert query["metadata"].get("source_code") is None
        semantics = query["manifest"]["contract"]["source_semantics"]["fields"]
        for key in ("known_at", "closed", "trading_phase", "price_unit", "amount_unit"):
            assert semantics[key]["status"] == "unknown"
        assert [r["tokens"]["source_day"] for r in query["rows"]] == [r["day"] for r in rows]


def test_decimal_context_cannot_round_exact_tokens_and_null_quantity(tmp_path):
    amount = "9223372036854775807.000000000000000001"
    price = "9007199254740993.012345678901234567"
    row = tx_row(**{"1": price, "2": price, "3": price, "4": price,
                    "5": "9223372036854775808.000000000000000001", "8": amount})
    raw = tx_capture([row])
    with localcontext() as context:
        context.prec = 2
        context.traps[Inexact] = True
        result = decode(raw, TX)
        assert result.rows[0].values["open"] == Decimal(price)
        assert result.rows[0].values["amount"] == Decimal(amount)
        assert result.rows[0].values["volume"] is None
        assert check(result.rows[0], "source_quantity_decimal").outcome == "pass"
    with EvidenceStore(tmp_path / "store") as store:
        imported = store.import_bytes(raw, TX)
        assert imported["status"] == "committed"
        saved = store.query(imported["snapshot_id"])["rows"][0]
        assert saved["values"]["open"] == price
        assert saved["values"]["amount"] == amount
        assert saved["values"]["volume"] is None
        assert saved["tokens"]["volume"] == row[5]


def test_header_only_version_and_interpretation_change_never_overwrite_snapshot(tmp_path):
    first_raw = tx_capture()
    second_raw = tx_capture(response_headers=[("Content-Type", "text/html; charset=utf-8")])
    assert json.loads(first_raw)["body_sha256"] == json.loads(second_raw)["body_sha256"]
    assert digest(first_raw) != digest(second_raw)
    with EvidenceStore(tmp_path / "store") as store:
        first = store.import_bytes(first_raw, TX)
        frozen = store.query(first["snapshot_id"])
        second = store.import_bytes(second_raw, TX)
        interpreted = store.import_bytes(first_raw, TX, interpretation={"instrument": "600111.SH"})
        assert len({first["snapshot_id"], second["snapshot_id"], interpreted["snapshot_id"]}) == 3
        assert store.query(first["snapshot_id"]) == frozen
        again = store.import_bytes(first_raw, TX)
        assert again["snapshot_id"] == first["snapshot_id"] and again["reused"] is True


def test_identity_source_symbol_swap_is_rejected_before_persistence(tmp_path):
    raw = tx_capture(symbol="sh600112")
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["status"] == "rejected" and result["raw_sha256"] is None
        assert store.list_snapshots() == []


def test_numerical_row_rejection_does_not_erase_other_raw_fields(tmp_path):
    raw = tx_capture([tx_row(volume="-0.01", **{"8": "1e-19"})])
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["status"] == "committed"
        query = store.query(result["snapshot_id"])
        row = query["rows"][0]
        checks = {item["name"]: item for item in row["checks"]}
        assert checks["source_quantity_decimal"]["reason"] == "negative_source_quantity"
        assert checks["numeric.amount"]["reason"] == "decimal_scale"
        assert row["values"]["volume"] is row["values"]["amount"] is None
        assert row["tokens"]["volume"] == "-0.01" and row["tokens"]["amount"] == "1e-19"
        assert daily_bars(query)[0]["reason"] is None


def test_four_legacy_contracts_and_rows_match_pre_public_capture_goldens():
    """Goldens came from the committed decoder before this format extension.

    Entire decoded contracts/metadata/rows/checks are covered, not only price
    equality. The source fixtures are synthetic and already used by legacy
    tests. This test has no runtime dependency on Git or a previous checkout.
    """
    from test_formats import text_file, text_row, day_record, bao_payload
    from test_tdx_http_format import capture, encoded
    from anatrading.store import _json

    cases = [
        ("tdx-public-text-v1", text_file([text_row()]),
         "c5abf5bfe8a8614150543b5e7fc42beff37cbb03a58301e4957d1394accb0621"),
        ("tdx-public-text-v1", text_file([text_row(volume="1.5")]),
         "babaabf75996b1be6c113da6298899e231e4582233082e3e53774f9c0f11d638"),
        ("tdx-public-text-v1", text_file([text_row(time="2500")]),
         "f31a953bade89eb6820009e2dce411028cf033dfa3f9e7deca9a386a82ad9bb8"),
        ("tdx-public-day-v1", day_record(),
         "edb0140428a9466c59eedaf370773404a00b5a1d808298558750ed2618749fa3"),
        ("tdx-public-day-v1", day_record(reserved=7),
         "412d8c2951ab744bff6432138635f87ce6cffd6964d55eec1fb0eb92251d8d5d"),
        ("baostock-decoded-v0.9.4", bao_payload(),
         "0e8d3e6fc4b8a63eea961a1f8ca0bbb3aaa51f7821c916ab00d9995cabd6ed5c"),
        ("baostock-decoded-v0.9.4", bao_payload(rows=[[
            "2021-02-26", "sh.601577", "10", "11", "9", "10", "1.5", "1000", "3"]]),
         "ba133068bc170835ffb000c656d98dbe42a7ff1067283c684ead8c3b5636167b"),
        ("tdx-http-market-v1", encoded(capture()),
         "3bdcb8a7cf29ce7a54d63c8c23c669f7e860d8cb6acfe1fd51856f197d895ded"),
        ("tdx-http-market-v1", encoded(capture(volume="1.5")),
         "588602982970eb32e779c3cafaa31359c225bfa9b378988e28e6405cd077323e"),
    ]
    for format_id, raw, expected in cases:
        assert digest(_json(asdict(decode(raw, format_id))).encode("utf-8")) == expected, format_id


@pytest.mark.parametrize("format_id,rows", [
    (SINA, [{"token": "PRIVATE_MARKER", "message": "login required"}]),
    (SINA, [17]),
    (SINA, [sina_row(), {"session": "PRIVATE_MARKER"}]),
    (TX, [{"token": "PRIVATE_MARKER", "message": "login required"}]),
    (TX, [17]),
    (TX, [tx_row(), {"session": "PRIVATE_MARKER"}]),
])
def test_jsonp_signature_alone_does_not_qualify_control_array_as_market_raw(tmp_path, format_id, rows):
    raw = sina_capture(rows) if format_id == SINA else tx_capture(rows)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, format_id)
        assert result["status"] == "rejected"
        assert result["raw_sha256"] is None, "Non-market control arrays must not be persisted"
        assert "PRIVATE_MARKER" not in json.dumps(result)
        assert store.list_snapshots() == []
    directory = tmp_path / "store" / "raw"
    assert not directory.exists() or not any(p.is_file() for p in directory.rglob("*"))


@pytest.mark.parametrize('format_id,factory,contract_sha,decoded_sha', [
    (TX, tx_capture,
     'e5a1552e4fcda01989da29ad147442b4c32e126eae48606856740450d68dfced',
     'cec70b352a129c15a383ce00963eb3f7dcf26e5eed79bf13d9d0728566cf3ed5'),
    (SINA, sina_capture,
     '61f3163e2d8c1c1f1b8776c204ae0b878572cc29ba07ddf6e3c282974d95cf50',
     '540581ef324974c3581607294e338024b178cba3995b9361725ef7bfabe40f0a'),
])
def test_prospective_v1_identity_does_not_change_for_legacy_amendment(format_id, factory, contract_sha, decoded_sha):
    """Frozen before the independently approved legacy branch was implemented."""
    from anatrading.public_market import decoder_identity
    from anatrading.store import _json
    assert decoder_identity(format_id)['source_contract_id'] == contract_sha
    assert digest(_json(asdict(decode(factory(), format_id))).encode()) == decoded_sha


@pytest.mark.parametrize('format_id,factory', [(TX, tx_capture), (SINA, sina_capture)])
def test_legacy_limitations_survive_store_query_and_export(tmp_path, format_id, factory):
    from test_public_market_legacy import legacy_capture, PROVENANCE
    from anatrading.public_market import LEGACY_CAPTURE_VERSION
    from pathlib import Path
    strict = factory()
    reconstructed = legacy_capture(strict)
    assert json.loads(strict)['body_sha256'] == json.loads(reconstructed)['body_sha256']
    with EvidenceStore(tmp_path / 'store') as store:
        normal = store.import_bytes(strict, format_id)
        legacy = store.import_bytes(reconstructed, format_id)
        assert normal['status'] == legacy['status'] == 'committed'
        assert normal['raw_sha256'] != legacy['raw_sha256']
        assert normal['batch_id'] != legacy['batch_id']
        assert normal['snapshot_id'] != legacy['snapshot_id']
        query = store.query(legacy['snapshot_id'])
        contract = query['manifest']['contract']
        assert contract['raw_kind'] == 'legacy_http_capture_reconstruction'
        for record in (query['metadata'], contract):
            assert record['capture_version'] == LEGACY_CAPTURE_VERSION
            assert record['capture_mode'] == 'legacy_reconstruction'
            assert record['header_cardinality'] == 'unrecorded'
            assert record['transport_evidence'] == 'not_established'
            assert record['provenance_hash_verification'] == 'syntax_only'
        assert query['metadata']['provenance'] == PROVENANCE
        exported = store.export_json(legacy['snapshot_id'])
        assert json.loads(Path(exported['path']).read_bytes()) == query
        assert 'provenance' not in store.query(normal['snapshot_id'])['metadata']
        assert store.import_bytes(reconstructed, format_id)['snapshot_id'] == legacy['snapshot_id']


@pytest.mark.parametrize('key', ['original_manifest_sha256', 'capture_script_sha256'])
def test_legacy_external_evidence_hash_is_part_of_immutable_identity(tmp_path, key):
    from test_public_market_legacy import legacy_capture, PROVENANCE
    raw = tx_capture()
    first = legacy_capture(raw)
    changed = legacy_capture(raw, provenance={**PROVENANCE, key: 'c' * 64})
    with EvidenceStore(tmp_path / 'store') as store:
        one = store.import_bytes(first, TX)
        two = store.import_bytes(changed, TX)
        assert one['snapshot_id'] != two['snapshot_id']
        assert store.query(one['snapshot_id'])['rows'] == store.query(two['snapshot_id'])['rows']


def test_star_attribute_never_becomes_an_identity_or_rights_claim(tmp_path):
    # Deliberately different values from the observed real-source metadata.
    attributes = dict(NoProfit='1', WeightedVotingRights='0', IsVIE='1', IsRegistration='0')
    plain = tx_capture()
    enriched = tx_capture(extra={'attribute': attributes})
    from test_public_market_legacy import legacy_capture
    with EvidenceStore(tmp_path / 'store') as store:
        snapshots = [store.import_bytes(raw, TX)['snapshot_id'] for raw in (plain, enriched, legacy_capture(enriched))]
        queried = [store.query(sid) for sid in snapshots]
        assert len(set(snapshots)) == 3
        assert queried[0]['rows'] == queried[1]['rows'] == queried[2]['rows']
        for query in queried:
            assert all(key not in json.dumps(query['metadata']) for key in attributes)
            assert query['metadata']['instrument_id'] is None
            assert query['metadata']['source_claims_status'] == 'assumed'
