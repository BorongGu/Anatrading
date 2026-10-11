"""Fixed-format boundaries; constructed data cannot qualify a market source."""
import hashlib
import json
from decimal import Decimal, localcontext
from pathlib import Path
import struct

import pytest

from anatrading.formats import FORMAT_IDS, decode, preflight
from anatrading.models import DecodeError, NonMarketPayload, VALUE_FIELDS


TEXT = "tdx-public-text-v1"
DAY = "tdx-public-day-v1"
BAO = "baostock-decoded-v0.9.4"
DAILY_FIELDS = ["date", "code", *VALUE_FIELDS, "adjustflag"]


def text_file(rows, *, bom=False):
    separator = " " if bom else ","
    lines = ["601577 长沙银行 1分钟线 不复权",
             "日期\t时间\t开盘\t最高\t最低\t收盘\t成交量\t成交额"]
    lines.extend(separator.join(row) for row in rows)
    lines.append("数据来源:通达信")
    return ("\r\n".join(lines) + "\r\n").encode("utf-8-sig" if bom else "gbk")


def text_row(date="2021/02/26", time="0931", **values):
    data = dict(open="10", high="11", low="9", close="10", volume="100", amount="1000")
    data.update(values)
    return [date, time, *(data[field] for field in VALUE_FIELDS)]


def bao_payload(rows=None, *, message_type="96", method="query_history_k_data_plus",
                user="anonymous", status="0", fields=None, frequency="d", adjustment="3",
                code="sh.601577"):
    fields = DAILY_FIELDS if fields is None else fields
    if rows is None:
        rows = [["2021-02-26", "sh.601577", "10", "11", "9", "10", "100", "1000", "3"]]
    body = "\x01".join([status, "success", method, user, "1", "2000",
                          json.dumps({"record": rows}), code, ",".join(fields),
                          "2021-02-26", "2021-02-26", frequency, adjustment])
    return (f"00.9.10\x01{message_type}\x01{len(body):010d}" + body).encode("utf-8")


def day_record(*, date=20210226, amount=1000.0, reserved=0):
    return struct.pack("<IIIIIfII", date, 1000, 1100, 900, 1000, amount, 100, reserved)


def check(row, name):
    return next(item for item in row.checks if item.name == name)


@pytest.mark.parametrize("format_id", FORMAT_IDS)
@pytest.mark.parametrize("changes", [
    {"message_type": "01"}, {"message_type": "03"},
    {"method": "login"}, {"method": "logout"},
    {"method": "query_stock_basic"}, {"status": "10002007"},
    {"user": "PRIVATE_MARKER_7"}, {"fields": [*DAILY_FIELDS, "api_key"]},
    {"fields": ["date", "date"]},
])
def test_control_payload_rejected_before_persistence_without_echo(changes, format_id):
    payload = bao_payload(**changes)
    with pytest.raises(NonMarketPayload) as caught:
        preflight(payload, format_id)
    message = str(caught.value).lower()
    assert message == "non_market_payload"
    assert all(word not in message for word in ("private_marker", "login", "logout", "api_key"))
    assert caught.value.__context__ is None


@pytest.mark.parametrize("raw", [b"", b"\xffsecret", b"00.9.10\x0196\x01", b'{"token":"PRIVATE_MARKER_7"}'])
def test_unrecognized_bao_envelope_is_non_market(raw):
    with pytest.raises(NonMarketPayload) as caught:
        decode(raw, BAO)
    assert str(caught.value) == "non_market_payload"
    assert caught.value.__context__ is None


def test_fixed_formats_and_safe_interpretation_keys():
    assert FORMAT_IDS == (TEXT, DAY, BAO, "tdx-http-market-v1",
                          "tencent-daily-capture-v1", "sina-minute-capture-v1")
    with pytest.raises(DecodeError, match="^unsupported_format$"):
        decode(b"", "csv")
    for declaration in ({"qualified": True}, {"instrument": 601577}, ["instrument"],
                        {"api_key": "PRIVATE_MARKER_7"}):
        with pytest.raises(DecodeError, match="^invalid_interpretation$"):
            decode(text_file([text_row()]), TEXT, declaration)


@pytest.mark.parametrize("raw", [b"", b"x" * 31, day_record() + b"x"])
def test_binary_truncation_is_file_rejection(raw):
    with pytest.raises(DecodeError, match="^invalid_day_length$"):
        decode(raw, DAY)


def test_text_structure_is_fixed_not_generic_csv():
    for raw in (b"date,open,high,low,close,volume,amount\n", text_file([text_row()])[:-20],
                text_file([text_row()[:-1]])):
        with pytest.raises(DecodeError):
            decode(raw, TEXT)


def test_invalid_fields_retained_and_dependent_checks_not_evaluated():
    data = decode(text_file([text_row(open="1e-19", high="NaN", volume="1.5", amount="")]), TEXT)
    row = data.rows[0]
    assert row.ordinal == 1 and row.locator == "line:3"
    assert row.values == {"open": None, "high": None, "low": Decimal("9"),
                          "close": Decimal("10"), "volume": None, "amount": None}
    assert row.tokens["open"] == "1e-19" and row.tokens["volume"] == "1.5"
    assert check(row, "numeric.open").outcome == "fail"
    assert check(row, "numeric.amount").reason == "missing"
    for name in ("ohlc_bounds", "zero_volume_amount", "conditional_price_bounds"):
        assert check(row, name).outcome == "not_evaluated"
        assert check(row, name).reason


def test_invalid_duplicate_and_out_of_order_labels_are_not_discarded():
    data = decode(text_file([text_row(time="0932"), text_row(time="2500"),
                             text_row(time="0931"), text_row(time="0931")]), TEXT)
    assert len(data.rows) == 4
    assert [row.label for row in data.rows] == ["2021-02-26T09:32", None,
                                               "2021-02-26T09:31", "2021-02-26T09:31"]
    assert data.rows[1].source_label == "2021/02/26 2500"
    assert check(data.rows[1], "label").outcome == "fail"
    assert check(data.rows[2], "source_order").outcome == "fail"
    assert all(check(row, "duplicate_label").outcome == "fail" for row in data.rows[2:])


def test_zero_negative_and_conditional_boundaries_are_separate():
    data = decode(text_file([text_row(volume="0", amount="4"), text_row(open="-1", amount="-1"),
                             text_row(low="10", high="10", amount="999.5")]), TEXT)
    zero, negative, slight = data.rows
    assert check(zero, "zero_volume_amount").outcome == "fail"
    assert check(zero, "conditional_price_bounds").outcome == "not_evaluated"
    assert negative.values["open"] == Decimal("-1")
    assert check(negative, "nonnegative_prices").outcome == "fail"
    assert check(negative, "nonnegative_amount").outcome == "fail"
    assert check(slight, "conditional_price_bounds").outcome == "fail"
    assert check(slight, "conditional_price_bounds_cent").outcome == "pass"
    assert check(slight, "conditional_price_bounds").assumption == "shares_cny_same_coverage"


def test_binary32_exact_value_bits_and_unrepresentable_amount():
    good = day_record(amount=37.020000457763671875, reserved=65536)
    bad = bytearray(day_record())
    bad[20:24] = (0x3F800001).to_bytes(4, "little")
    data = decode(good + bad, DAY)
    assert data.rows[0].values["amount"] == Decimal("37.020000457763671875")
    assert data.rows[0].tokens["amount"] == good[20:24].hex()
    assert data.rows[0].tokens["reserved"] == good[28:32].hex()
    assert data.rows[1].locator == "byte:32"
    assert data.rows[1].values["amount"] is None
    assert check(data.rows[1], "numeric.amount").outcome == "fail"
    assert data.metadata["amount_byte_offset"] == 20


def test_invalid_binary_date_is_a_preserved_row():
    row = decode(day_record(date=20210230), DAY).rows[0]
    assert row.label is None and row.source_label == "20210230"
    assert check(row, "label").outcome == "fail"


@pytest.mark.parametrize("format_id,raw", [(TEXT, text_file([text_row()])),
                                          (DAY, day_record()), (BAO, bao_payload())])
def test_user_declaration_cannot_qualify_units_or_identity(format_id, raw):
    data = decode(raw, format_id, {"instrument": "601577", "asset_type": "stock",
                                   "volume_unit": "shares", "amount_unit": "CNY"})
    assert data.contract["format_id"] == format_id
    assert data.contract["version"] == "2"
    assert data.contract["raw_kind"]
    assert data.metadata["instrument_id"] is None
    assert data.metadata["interpretation_status"] == "assumed"
    assert all(row.volume_shares is None and row.amount_cny is None for row in data.rows)
    assert all(check(row, "standard_units").outcome == "not_evaluated" for row in data.rows)


@pytest.mark.parametrize("format_id,raw", [(TEXT, text_file([text_row()])),
                                          (DAY, day_record()), (BAO, bao_payload())])
def test_source_semantics_contract_names_each_unknown_time(format_id, raw):
    data = decode(raw, format_id)
    semantics = data.contract["source_semantics"]
    assert semantics["scope"] == "all_records"
    fields = semantics["fields"]
    temporal_reasons = {
        "label_definition": "bar_label_definition_unverified",
        "period_start": "bar_start_unverified",
        "period_end": "bar_end_unverified",
        "closed": "bar_closure_unverified",
        "trading_phase": "trading_phase_unverified",
        "first_published_at": "first_publication_not_evidenced",
        "known_at": "historical_availability_not_evidenced",
    }
    assert set(fields) == {*temporal_reasons, "price_unit", "volume_unit", "amount_unit",
                           "volume_accumulation", "amount_accumulation",
                           "volume_amount_same_coverage", "adjustment"}
    for field in fields.values():
        assert {"value", "status", "reason", "evidence"} <= set(field)
        assert field["status"] in {"known", "assumed", "unknown"}
        assert field["reason"] and isinstance(field["evidence"], list)
    for name, reason in temporal_reasons.items():
        assert fields[name] == {"value": None, "status": "unknown", "reason": reason, "evidence": []}
    assert all(not hasattr(row, "source_semantics") for row in data.rows)


@pytest.mark.parametrize("format_id,raw,date_key,time_key,source_date,source_time", [
    (TEXT, text_file([text_row()]), "source_date", "source_time", "2021/02/26", "0931"),
    (DAY, day_record(), "source_date", None, "20210226", None),
    (BAO, bao_payload(), "date", None, "2021-02-26", None),
    (BAO, bao_payload([["2021-02-26", "20210226093500000", "sh.601577", "10", "11", "9", "10", "100", "1000", "3"]],
                      fields=["date", "time", "code", *VALUE_FIELDS, "adjustflag"], frequency="5"),
     "date", "time", "2021-02-26", "20210226093500000"),
])
def test_source_date_time_token_mapping_preserves_original_fields(format_id, raw, date_key, time_key, source_date, source_time):
    data = decode(raw, format_id)
    mapping = data.contract["source_token_mapping"]
    assert mapping == {"source_date": date_key, "source_time": time_key}
    assert data.rows[0].tokens[mapping["source_date"]] == source_date
    assert (data.rows[0].tokens[mapping["source_time"]] if time_key is not None else None) == source_time


@pytest.mark.parametrize("frequency", ["d", "5"])
def test_bao_documented_semantics_do_not_verify_applicability(frequency):
    fields = DAILY_FIELDS if frequency == "d" else ["date", "time", "code", *VALUE_FIELDS, "adjustflag"]
    row = ["2021-02-26", "sh.601577", "10", "11", "9", "10", "100", "1000", "3"]
    if frequency == "5":
        row.insert(1, "20210226093500000")
    data = decode(bao_payload([row], fields=fields, frequency=frequency), BAO)
    semantics = data.contract["source_semantics"]["fields"]
    for name, value in {"price_unit": "CNY", "volume_unit": "shares", "amount_unit": "CNY"}.items():
        assert semantics[name]["value"] == value and semantics[name]["status"] == "known"
        assert semantics[name]["applicability"] == "unverified"
        assert semantics[name]["evidence"][0]["sha256"] == "2a6db3b24ab21a199aa17bd949dfbe545d3279007bea1664854f9b7c20542aac"
    for name in ("volume_accumulation", "amount_accumulation"):
        assert semantics[name]["value"] == ("per_bar_total" if frequency == "5" else None)
        assert semantics[name]["status"] == ("known" if frequency == "5" else "unknown")
        if frequency == "5":
            assert semantics[name]["applicability"] == "unverified"
    assert semantics["volume_amount_same_coverage"] == {
        "value": None, "status": "unknown", "reason": "volume_amount_trade_coverage_unverified", "evidence": []}
    assert data.rows[0].volume_shares is None and data.rows[0].amount_cny is None
    assert next(item for item in data.checks if item.name == "source_units_and_coverage").outcome == "not_evaluated"


@pytest.mark.parametrize("format_id,raw,value,status,evidence", [
    (TEXT, text_file([text_row()]), "不复权", "assumed", "metadata.source_adjustment"),
    (DAY, day_record(), None, "unknown", None),
    (BAO, bao_payload(), "3", "assumed", "metadata.source_adjustflag"),
])
def test_adjustment_contract_preserves_source_claim_level(format_id, raw, value, status, evidence):
    data = decode(raw, format_id)
    adjustment = data.contract["source_semantics"]["fields"]["adjustment"]
    assert adjustment["value"] == value and adjustment["status"] == status
    assert adjustment["evidence"] == ([evidence] if evidence else [])
    assert adjustment["reason"] == ("source_claim_unverified" if evidence else "adjustment_not_provided_by_format")


def test_adjustment_contract_does_not_replace_conflicting_bao_tail_flag():
    data = decode(bao_payload(adjustment="2"), BAO)
    assert data.contract["source_semantics"]["fields"]["adjustment"]["value"] == "2"
    assert data.contract["source_semantics"]["fields"]["adjustment"]["status"] == "assumed"
    assert data.rows[0].tokens["adjustflag"] == "3"
    assert check(data.rows[0], "source_adjustflag").outcome == "fail"


@pytest.mark.parametrize("format_id,raw", [(TEXT, text_file([text_row()])),
                                          (DAY, day_record()), (BAO, bao_payload())])
def test_user_units_do_not_replace_source_semantics(format_id, raw):
    original = decode(raw, format_id)
    declared = decode(raw, format_id, {"volume_unit": "lots", "amount_unit": "USD"})
    assert declared.contract["source_semantics"] == original.contract["source_semantics"]
    assert declared.metadata["interpretation"] == {"volume_unit": "lots", "amount_unit": "USD"}
    assert declared.metadata["interpretation_status"] == "assumed"
    if format_id in {TEXT, DAY}:
        for name in ("price_unit", "volume_unit", "amount_unit", "volume_accumulation", "amount_accumulation"):
            field = declared.contract["source_semantics"]["fields"][name]
            assert field["value"] is None and field["status"] == "unknown" and field["evidence"] == []
    assert all(row.volume_shares is None and row.amount_cny is None for row in declared.rows)


def test_bao_full_tail_metadata_is_read_without_sdk_truncation():
    raw = bao_payload()
    assert preflight(raw, BAO) is None
    data = decode(raw, BAO)
    assert data.metadata["source_adjustflag"] == "3"
    assert data.metadata["period"] == "1d"
    assert data.rows[0].label == "2021-02-26"
    assert data.rows[0].locator == "record:1"


def test_bao_row_identity_and_date_time_conflicts_preserved():
    fields = ["date", "time", "code", *VALUE_FIELDS, "adjustflag"]
    row = ["2021-02-26", "20210225093500000", "sz.000001", "10", "11", "9", "10", "100", "1000", "2"]
    data = decode(bao_payload([row], fields=fields, frequency="5"), BAO)
    assert len(data.rows) == 1 and data.rows[0].label is None
    assert check(data.rows[0], "source_code").outcome == "fail"
    assert check(data.rows[0], "source_adjustflag").outcome == "fail"


def test_source_declaration_conflicts_do_not_replace_source_claims():
    data = decode(bao_payload(), BAO, {"instrument": "sz.000001", "venue": "sz"})
    assert data.metadata["source_code"] == "sh.601577"
    assert data.metadata["source_venue"] == "sh"
    assert {item.name: item.outcome for item in data.checks}["declared_instrument"] == "fail"
    assert {item.name: item.outcome for item in data.checks}["declared_venue"] == "fail"
    assert data.metadata["interpretation_status"] == "assumed"


@pytest.mark.parametrize("bits", [0x7F800000, 0xFF800000, 0x7FC00001])
def test_binary_nonfinite_is_a_field_failure_with_original_bits(bits):
    raw = bytearray(day_record())
    raw[20:24] = bits.to_bytes(4, "little")
    row = decode(bytes(raw), DAY).rows[0]
    assert row.values["amount"] is None
    assert row.tokens["amount"] == raw[20:24].hex()
    assert check(row, "numeric.amount").outcome == "fail"


@pytest.mark.parametrize("rows", [None, [["2021-02-26"]], [["2021-02-26", "sh.601577", 10, "11", "9", "10", "100", "1000", "3"]]])
def test_bao_malformed_market_records_are_decode_errors(rows):
    raw = bao_payload(rows=[] if rows is None else rows)
    if rows is None:
        assert decode(raw, BAO).rows == []
    else:
        with pytest.raises(DecodeError):
            decode(raw, BAO)


def test_exact_checks_do_not_use_the_callers_decimal_precision():
    with localcontext() as context:
        context.prec = 3
        row = decode(text_file([text_row(volume="9007199254740993", amount="90071992547409930")]), TEXT).rows[0]
    assert row.values["volume"] == 9007199254740993
    assert check(row, "conditional_price_bounds").outcome == "pass"


def canonical_digest(data):
    def text(value):
        if isinstance(value, int):
            return str(value)
        fixed = format(value, "f")
        return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed
    lines = [",".join([row.label, *(text(row.values[field]) for field in VALUE_FIELDS)])
             for row in data.rows]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("ascii")).hexdigest()


@pytest.mark.parametrize("filename,format_id,count,digest,strict,cent", [
    ("601577.txt", TEXT, 15840, "0b7e20dc3eec62330c67d6f2b78830103394f733e3b0791e6ab4f9b7682f4561", 1228, 211),
    ("SH_601577.txt", TEXT, 3216, "79a0d775307041e8a9678c558a35b09fbd73a017d0d9e2bae0fba757056da2ca", 7, 0),
    ("SH_ZXG_.txt", TEXT, 3216, "79a0d775307041e8a9678c558a35b09fbd73a017d0d9e2bae0fba757056da2ca", 7, 0),
    ("sz000001.day", DAY, 4995, "169cfff4724103e561501978a181cb110fdaba9ff73a340110f6572572eb9b4f", 2, 0),
])
def test_local_real_sample_control_values(filename, format_id, count, digest, strict, cent):
    path = Path(__file__).resolve().parents[1] / "data" / "reference" / filename
    if not path.exists():
        pytest.skip("Private G1 fixture is not available; no network fallback")
    raw = path.read_bytes()
    expected_raw = {
        "601577.txt": "c82327940c47a64890c2b7c2c0114216e5583aef85daca2744ef524e668dba3b",
        "SH_601577.txt": "46aee68ca6f442d00e18e3fafb209c01dbed0856baa3cfabb13791682d376993",
        "SH_ZXG_.txt": "a16476666a8b4a7bf1ab0f05c6302554bf9c89f61d2ff19876ed240fc5b24014",
        "sz000001.day": "9e817ed7cca1abe86becf39d0c2257858d7db5bb4f57674622fc970c94684dd9",
    }
    assert hashlib.sha256(raw).hexdigest() == expected_raw[filename]
    data = decode(raw, format_id)
    assert len(data.rows) == count and canonical_digest(data) == digest
    assert sum(check(row, "conditional_price_bounds").outcome == "fail" for row in data.rows) == strict
    assert sum(check(row, "conditional_price_bounds_cent").outcome == "fail" for row in data.rows) == cent


def test_known_negative_sample_remains_quarantined():
    path = Path(__file__).resolve().parents[1] / "data" / "reference" / "sh688001.day"
    if not path.exists():
        pytest.skip("Private negative G1 fixture is not available")
    data = decode(path.read_bytes(), DAY, {"asset_type": "stock", "instrument": "688001"})
    assert data.metadata["quarantined"] is True
    assert data.metadata["instrument_id"] is None
    assert all(row.volume_shares is None for row in data.rows)


@pytest.mark.parametrize("run,case,count,raw_hash,digest", [
    ("20261003T161007746978Z", "daily-overlap", 2,
     "c45a26783b0e90ecbb4c5f0c81a3d891dd7d7ceec5013a6af15e728e4e68af71",
     "caeab1c2db8b517c1c0a988390f29f3110e61d8cf29fa3289625923cadafbcd6"),
    ("20261003T161007746978Z", "minute-overlap", 48,
     "5741ee0ce09e1b978e08b77b3d3fb31bedd1a08b060d0ff50eb033a78f305134",
     "5d6cfea599be85afb13e45a43ffb1834319567580e579227260a9c383cbdaaad"),
    ("20261003T161007746978Z", "minute-recent", 48,
     "3602fd38725805ec17b3826b3b6c792f9f422f1bec4c61f1c528496d7345c7bd",
     "5bda8c0e5fbe3e55eab980dfffce1fe16e91601af9d2d43fa5bf18eda3de1d9b"),
    ("20261003T161821401061Z", "daily-bank-overlap", 1,
     "6cdc6a61ec20dc948f40bb51d09b391d4efd33b28dd75d736b22867a50790d49",
     "57f4664772986e1d0c66ffe37d2576535f9af9d7a423f6e787b4ee8d65d52edb"),
    ("20261003T161821401061Z", "daily-bank-recent", 1,
     "1eb4d66ae85fc91a298270f344ca962c63cf22d1e81ad8c0457d569b945ca931",
     "027ebb6775ed7a96aa9132d253a33a1122e990cab44d24a27f9dc8248c57b2dc"),
])
def test_local_bao_samples_keep_exact_source_values(run, case, count, raw_hash, digest):
    root = Path(__file__).resolve().parents[1]
    path = root / "artifacts" / "qualification" / "baostock" / run / case / "market-sdk-decoded.txt"
    if not path.exists():
        pytest.skip("Private BaoStock capture is not available; no network fallback")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == raw_hash
    data = decode(raw, BAO)
    assert len(data.rows) == count and canonical_digest(data) == digest
    assert all(check(row, "conditional_price_bounds").outcome == "pass" for row in data.rows)
