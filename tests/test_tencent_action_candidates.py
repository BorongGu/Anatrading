"""合成原串及失败反例，不为真实来源授予经济含义。"""
import base64
from dataclasses import asdict
import hashlib
import json

import pytest

from anatrading.formats import decode
from anatrading.models import DecodeError
from anatrading.public_market import (
    CAPTURE_VERSION, LEGACY_CAPTURE_VERSION, build_capture, build_legacy_capture,
    build_request, canonical_json, capture_rows, validate_capture,
)
from anatrading.store import _json
from anatrading.tencent_action_candidates import (
    UnsupportedSourceActionShape, extract_tencent_action_candidates,
)


FORMAT = "tencent-daily-capture-v1"
FIELDS = ("nd", "fh_sh", "djr", "cqr", "FHcontent")
PROVENANCE = dict(capture_mode="legacy_reconstruction", header_cardinality="unrecorded",
                  transport_evidence="not_established", original_manifest_sha256="1" * 64,
                  capture_script_sha256="2" * 64)


def source_object(**changes):
    return dict(nd="2024", fh_sh="1.2000", djr="2025-05-08", cqr="2025-05-09",
                FHcontent="10派1.2000元") | changes


def source_row(obj, day="2025-05-09"):
    return [day, "10.00", "10.10", "10.20", "9.90", "100.50", obj,
            "0.1", "101.00", "0", "0"]


def capture(rows, *, legacy=False, source_symbol="sh600111"):
    request = build_request("tencent", "600111.SH", "1d", start="2025-01-01",
                            end="2025-12-31", count=640)
    payload = {"code": 0, "msg": "", "data": {source_symbol: {"day": rows}}}
    body = b"kline_day2025=" + canonical_json(payload)
    common = dict(status=200, response_url=request["url"], body=body)
    if legacy:
        return build_legacy_capture("tencent", request, **common,
                                    selected_headers={"content-type": "text/html; charset=UTF-8",
                                                      "content-encoding": ""},
                                    provenance=PROVENANCE)
    return build_capture("tencent", request, **common,
                         response_headers=[("Content-Type", "text/html; charset=UTF-8")])


def test_exact_source_strings_order_and_positions_without_economic_interpretation():
    objects = [source_object(),
               source_object(fh_sh="4.000", FHcontent="10派1元，10派3元"),
               source_object(fh_sh="0", FHcontent="10转4.9股"),
               source_object(FHcontent="10送1股转2股派1.2元", cqr="2026-12-31")]
    rows = [source_row({}, "2024-12-31"), *[source_row(obj) for obj in objects]]
    rows.append(source_row(objects[0]))
    raw = capture(rows)
    report = extract_tencent_action_candidates(raw)
    assert report["source_row_count"] == 6
    assert report["empty_object_count"] == 1
    assert report["candidate_count"] == 5
    expected = [dict(ordinal=i + 1, source_date=row[0],
                     locator=f"body:$.data.sh600111.day[{i}][6]", **row[6])
                for i, row in enumerate(rows) if row[6]]
    assert report["candidates"] == expected
    assert set(expected[0]) == {"ordinal", "source_date", "locator", *FIELDS}
    assert report["qualification"] == "retrospective_source_candidates"
    assert report["economic_semantics"] == "unverified"
    assert report["coverage"] == "unknown"
    assert report["historical_known_at"] is None


@pytest.mark.parametrize("legacy", [False, True])
def test_capture_identity_and_legacy_limits_are_preserved(legacy):
    raw = capture([source_row(source_object())], legacy=legacy)
    envelope = json.loads(raw)
    report = extract_tencent_action_candidates(raw)
    assert report["method_id"] == "tencent-action-candidates-v1"
    assert report["source"] == "tencent"
    assert report["requested_symbol"] == "600111.SH"
    assert report["source_symbol"] == "sh600111"
    assert report["response_identity"] == "source_key"
    assert report["capture_sha256"] == hashlib.sha256(raw).hexdigest()
    for key in ("capture_version", "body_sha256", "request_sha256", "response_headers_sha256"):
        assert report[key] == envelope[key]
    if legacy:
        assert report["capture_version"] == LEGACY_CAPTURE_VERSION
        assert report["provenance"] == PROVENANCE
        for key in ("capture_mode", "header_cardinality", "transport_evidence"):
            assert report[key] == PROVENANCE[key]
        assert report["provenance_hash_verification"] == "syntax_only"
    else:
        assert report["capture_version"] == CAPTURE_VERSION
        assert not {"provenance", "capture_mode", "transport_evidence", "header_cardinality",
                    "provenance_hash_verification"} & report.keys()


def test_empty_objects_are_unreturned_candidates_with_unknown_coverage():
    report = extract_tencent_action_candidates(capture([source_row({}), source_row({})]))
    assert report["candidates"] == []
    assert report["candidate_count"] == 0
    assert report["source_row_count"] == report["empty_object_count"] == 2
    assert report["coverage"] == "unknown"


def test_empty_day_matches_existing_decoder_failure():
    raw = capture([])
    for operation in (lambda: decode(raw, FORMAT), lambda: extract_tencent_action_candidates(raw)):
        with pytest.raises(DecodeError, match="^empty_public_market_result$"):
            operation()


@pytest.mark.parametrize("obj", [
    {"extra": "ignored?"}, source_object(extra="unexpected"),
    {key: value for key, value in source_object().items() if key != "nd"},
    *[source_object(fh_sh=value) for value in (None, False, 0, 1.2, [], {})],
])
def test_unknown_nonempty_shape_rejects_entire_result_and_keeps_first_bad_location(obj):
    raw = capture([source_row(source_object()), source_row(obj), source_row({"x": "later"})])
    old = decode(raw, FORMAT)
    assert len(old.rows) == 3
    with pytest.raises(UnsupportedSourceActionShape) as caught:
        extract_tencent_action_candidates(raw)
    error = caught.value
    assert error.code == str(error) == "unsupported_tencent_action_shape"
    assert error.context["ordinal"] == 2
    assert error.context["source_date"] == "2025-05-09"
    assert error.context["locator"] == "body:$.data.sh600111.day[1][6]"
    assert error.context["capture_sha256"] == hashlib.sha256(raw).hexdigest()
    assert error.context["body_sha256"] == json.loads(raw)["body_sha256"]
    assert "candidates" not in error.context


@pytest.mark.parametrize("obj", [None, [], "", 0, False])
def test_null_and_non_objects_use_existing_row_rejection(obj):
    with pytest.raises(DecodeError, match="^invalid_public_rows$"):
        extract_tencent_action_candidates(capture([source_row(obj)]))


def test_missing_slot_is_not_invented():
    row = source_row({})
    del row[6]
    with pytest.raises(DecodeError, match="^non_market_payload$"):
        extract_tencent_action_candidates(capture([row]))


@pytest.mark.parametrize("field", FIELDS)
def test_empty_whitespace_and_nonstandard_strings_are_not_parsed(field):
    for value in ("", " \t\n ", "不是日期，也不是金额"):
        obj = source_object(**{field: value})
        report = extract_tencent_action_candidates(capture([source_row(obj)]))
        assert report["candidates"][0][field] == value


def test_long_untrusted_text_remains_inert_and_output_is_repeatable():
    text = "<script>alert('untrusted')</script>\n${shell text};" + "汉" * 40000
    obj = source_object(FHcontent=text)
    raw = capture([source_row(obj)])
    first = extract_tencent_action_candidates(raw)
    assert first["candidates"][0]["FHcontent"] == text
    first["candidates"][0]["FHcontent"] = "caller edit"
    second = extract_tencent_action_candidates(raw)
    assert second["candidates"][0]["FHcontent"] == text


def test_duplicate_rows_keep_original_ordinals_up_to_existing_640_limit():
    row = source_row(source_object())
    report = extract_tencent_action_candidates(capture([row] * 640))
    assert report["candidate_count"] == 640
    assert [item["ordinal"] for item in report["candidates"]] == list(range(1, 641))
    with pytest.raises(DecodeError, match="^public_row_limit$"):
        extract_tencent_action_candidates(capture([row] * 641))


@pytest.mark.parametrize("key,code", [
    ("body_sha256", "public_body_hash_mismatch"),
    ("request_sha256", "public_request_hash_mismatch"),
    ("response_headers_sha256", "public_header_hash_mismatch"),
])
def test_hash_checks_are_reused(key, code):
    envelope = json.loads(capture([source_row(source_object())]))
    envelope[key] = "0" * 64
    with pytest.raises(DecodeError, match=f"^{code}$"):
        extract_tencent_action_candidates(canonical_json(envelope))


def test_wrong_response_symbol_and_raw_body_are_rejected():
    with pytest.raises(DecodeError, match="^non_market_payload$"):
        extract_tencent_action_candidates(capture([source_row(source_object())], source_symbol="sz600111"))
    raw = capture([source_row(source_object())])
    body = base64.b64decode(json.loads(raw)["body_base64"])
    with pytest.raises(DecodeError):
        extract_tencent_action_candidates(body)


@pytest.mark.parametrize("legacy", [False, True])
def test_old_decode_and_capture_rows_bytes_unchanged_after_success_or_rejection(legacy):
    for obj in (source_object(), {"unknown": "preserve old acceptance"}):
        raw = capture([source_row(obj)], legacy=legacy)
        decoded_before = _json(asdict(decode(raw, FORMAT))).encode()
        rows_before = canonical_json(list(capture_rows(validate_capture(raw, FORMAT))))
        if "unknown" in obj:
            with pytest.raises(UnsupportedSourceActionShape):
                extract_tencent_action_candidates(raw)
        else:
            extract_tencent_action_candidates(raw)
        assert _json(asdict(decode(raw, FORMAT))).encode() == decoded_before
        assert canonical_json(list(capture_rows(validate_capture(raw, FORMAT)))) == rows_before
