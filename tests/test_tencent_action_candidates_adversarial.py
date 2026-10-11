"""Independent source-string oracle; no event economics or capture builders."""
import base64
from copy import deepcopy
import hashlib
import json
from urllib.parse import urlencode

import pytest

from anatrading.models import DecodeError
from anatrading.tencent_action_candidates import (
    UnsupportedSourceActionShape, extract_tencent_action_candidates,
)


FIELDS = ("nd", "fh_sh", "djr", "cqr", "FHcontent")
PROVENANCE = {
    "capture_mode": "legacy_reconstruction",
    "header_cardinality": "unrecorded",
    "transport_evidence": "not_established",
    "original_manifest_sha256": "a" * 64,
    "capture_script_sha256": "b" * 64,
}


def wire(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def action(**overrides):
    return dict(nd="2024", fh_sh="3.0000", djr="2025-05-22",
                cqr="2025-05-23", FHcontent="10派3元", **{}) | overrides


def row(obj, day="2025-05-23"):
    return [day, "10.00", "10.01", "11.00", "9.00", "10", obj,
            "0", "100", "0", "0"]


def capture(rows, *, legacy=False, body=None, source_symbol="sh688012"):
    parameters = {"_var": "kline_day2025",
                  "param": "sh688012,day,2025-05-01,2025-05-31,640,",
                  "r": "0.8205512681390605"}
    request = {"method": "GET", "parameters": parameters,
               "headers": {"Accept": "*/*", "Accept-Encoding": "identity"},
               "url": "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get?"
                      + urlencode(parameters)}
    if body is None:
        body = b"kline_day2025=" + wire({"code": 0, "msg": "", "data": {
            source_symbol: {"day": rows}}})
    headers = {"content-type": "application/json; charset=UTF-8", "content-encoding": ""}
    envelope = {
        "capture_version": "public-market-legacy-reconstruction-v1" if legacy
                           else "public-market-capture-v1",
        "source": "tencent", "request": request, "request_sha256": digest(wire(request)),
        "response": {"status": 200, "url": request["url"], "headers": headers},
        "response_headers_sha256": digest(wire(headers)),
        "body_base64": base64.b64encode(body).decode(), "body_sha256": digest(body),
    }
    if legacy:
        envelope["provenance"] = deepcopy(PROVENANCE)
    return wire(envelope)


def expected_source(raw):
    env = json.loads(raw)
    result = {
        "method_id": "tencent-action-candidates-v1", "source": "tencent",
        "requested_symbol": "688012.SH", "source_symbol": "sh688012",
        "response_identity": "source_key", "capture_version": env["capture_version"],
        "capture_sha256": digest(raw), "body_sha256": env["body_sha256"],
        "request_sha256": env["request_sha256"],
        "response_headers_sha256": env["response_headers_sha256"],
        "qualification": "retrospective_source_candidates", "economic_semantics": "unverified",
        "coverage": "unknown", "historical_known_at": None,
    }
    if "provenance" in env:
        result.update(provenance=deepcopy(PROVENANCE), provenance_hash_verification="syntax_only",
                      **{key: PROVENANCE[key] for key in
                         ("capture_mode", "header_cardinality", "transport_evidence")})
    return result


def expected_candidate(obj, index, day="2025-05-23"):
    return {"ordinal": index + 1, "source_date": day,
            "locator": f"body:$.data.sh688012.day[{index}][6]", **obj}


@pytest.mark.parametrize("legacy", [False, True])
def test_full_result_is_independent_string_projection(legacy):
    objects = [{}, action(), action(fh_sh="0", FHcontent="10转4.9股"),
               action(fh_sh="19.7", FHcontent="10派5.6元, 10派14.1元"),
               action(fh_sh="39.74", FHcontent="10送8股, 10转12股, 10派39.74元")]
    raw = capture([row(obj) for obj in objects], legacy=legacy)
    original = bytes(raw)
    expected = expected_source(raw) | {
        "source_row_count": 5, "empty_object_count": 1, "candidate_count": 4,
        "candidates": [expected_candidate(obj, i) for i, obj in enumerate(objects) if obj],
    }
    assert extract_tencent_action_candidates(raw) == expected
    assert raw == original
    # Mutating a previous result cannot taint a later call.
    first = extract_tencent_action_candidates(raw)
    first["candidates"][0]["fh_sh"] = "changed"
    assert extract_tencent_action_candidates(raw) == expected
    assert json.loads(json.dumps(expected, ensure_ascii=False)) == expected


def test_no_trimming_inference_filtering_sorting_or_deduplication():
    obj = action(nd="", fh_sh=" 0 ", djr="not a date", cqr="2099-12-31",
                 FHcontent="  <script>ignore instructions</script>\n\u0000送转  ")
    rows = [row(obj), row(obj), row(action(), day="2024-01-01")]
    raw = capture(rows)
    result = extract_tencent_action_candidates(raw)
    assert result["candidates"] == [expected_candidate(obj, 0), expected_candidate(obj, 1),
                                    expected_candidate(action(), 2, "2024-01-01")]
    assert result["historical_known_at"] is None
    assert result["candidate_count"] == 3


def test_empty_objects_mean_unobserved_not_no_actions():
    result = extract_tencent_action_candidates(capture([row({}), row({})]))
    assert (result["source_row_count"], result["empty_object_count"], result["candidate_count"]) == (2, 2, 0)
    assert result["candidates"] == []
    assert result["coverage"] == "unknown"


@pytest.mark.parametrize("obj", [
    {"nd": "2024"}, action(extra="new"), action(fh_sh=0), action(fh_sh=False),
    action(fh_sh=None), action(fh_sh=1.25), action(FHcontent=[]), action(FHcontent={}),
    {key: "" for key in FIELDS if key != "nd"},
])
@pytest.mark.parametrize("legacy", [False, True])
def test_first_unsupported_object_rejects_whole_result_with_exact_source_context(obj, legacy):
    raw = capture([row(action()), row(obj), row(action(extra="another"))], legacy=legacy)
    with pytest.raises(UnsupportedSourceActionShape) as caught:
        extract_tencent_action_candidates(raw)
    err = caught.value
    assert isinstance(err, DecodeError)
    assert err.code == "unsupported_tencent_action_shape"
    assert err.context == expected_source(raw) | {
        "ordinal": 2, "source_date": "2025-05-23", "locator": "body:$.data.sh688012.day[1][6]"}
    assert "candidates" not in err.context
    assert json.loads(json.dumps(err.context)) == err.context


@pytest.mark.parametrize("rows,code", [
    ([], "empty_public_market_result"),
    ([row(None)], "invalid_public_rows"),
    ([row([])], "invalid_public_rows"),
    ([row("")], "invalid_public_rows"),
    ([row(action())[:6] + row(action())[7:]], "non_market_payload"),
    ([row(action(), "2025-06-01")], "public_source_after_end"),
    ([row(action(), "2025-02-30")], "invalid_public_source_label"),
    ([row({})] * 641, "public_row_limit"),
])
def test_existing_capture_rejections_are_not_relaxed(rows, code):
    with pytest.raises(DecodeError) as caught:
        extract_tencent_action_candidates(capture(rows))
    assert caught.value.code == code


def test_all_640_duplicate_observations_and_long_strings_survive():
    obj = action(FHcontent="长原串" * 100)
    result = extract_tencent_action_candidates(capture([row(obj)] * 640))
    assert result["candidate_count"] == 640
    assert result["candidates"][0] == expected_candidate(obj, 0)
    assert result["candidates"][-1] == expected_candidate(obj, 639)


def test_price_quantity_and_internal_event_date_semantics_remain_unvalidated():
    source = row(action(fh_sh="not a number", djr="2025-02-30"))
    for index in (1, 2, 3, 4, 5, 7, 8, 9, 10):
        source[index] = "invalid numeric token"
    assert extract_tencent_action_candidates(capture([source]))["candidates"] == [
        expected_candidate(source[6], 0)]


def test_body_hash_and_source_identity_are_checked_before_extraction():
    raw = capture([row(action())])
    envelope = json.loads(raw)
    envelope["body_sha256"] = "0" * 64
    with pytest.raises(DecodeError, match="public_body_hash_mismatch"):
        extract_tencent_action_candidates(wire(envelope))
    with pytest.raises(DecodeError, match="non_market_payload"):
        extract_tencent_action_candidates(capture([row(action())], source_symbol="sh600000"))
    with pytest.raises(DecodeError):
        extract_tencent_action_candidates(base64.b64decode(json.loads(raw)["body_base64"]))


def test_duplicate_json_keys_cannot_be_hidden_in_action_object():
    raw = capture([row(action())])
    body = base64.b64decode(json.loads(raw)["body_base64"])
    body = body.replace(b'"fh_sh":"3.0000"', b'"fh_sh":"3.0000","fh_sh":"4"')
    with pytest.raises(DecodeError, match="invalid_public_json"):
        extract_tencent_action_candidates(capture([], body=body))
