"""Explicit legacy provenance and narrowly observed Tencent auxiliary shape."""
import base64
from dataclasses import asdict
import hashlib
import json

import pytest

from anatrading.formats import decode
from anatrading.models import DecodeError, NonMarketPayload
from anatrading.public_market import (
    CAPTURE_VERSION, LEGACY_CAPTURE_VERSION, build_capture, build_legacy_capture,
    canonical_json, decoder_identity, preflight_capture, public_contract, validate_capture,
)
from anatrading.store import EvidenceStore, _json
from test_public_market_formats import TX, SINA, tx_capture, sina_capture, mutate_capture


PROVENANCE = dict(capture_mode="legacy_reconstruction", header_cardinality="unrecorded",
                  transport_evidence="not_established", original_manifest_sha256="a" * 64,
                  capture_script_sha256="b" * 64)
ATTRIBUTES = dict(NoProfit="0", WeightedVotingRights="1", IsVIE="0", IsRegistration="1")


def legacy_capture(raw=None, *, provenance=None, selected_headers=None):
    envelope = json.loads(tx_capture() if raw is None else raw)
    return build_legacy_capture(envelope["source"], envelope["request"], status=envelope["response"]["status"],
                                response_url=envelope["response"]["url"],
                                selected_headers=envelope["response"]["headers"] if selected_headers is None else selected_headers,
                                body=base64.b64decode(envelope["body_base64"]),
                                provenance=PROVENANCE if provenance is None else provenance)


@pytest.mark.parametrize("raw,fmt,expected", [
    (tx_capture, TX, "cec70b352a129c15a383ce00963eb3f7dcf26e5eed79bf13d9d0728566cf3ed5"),
    (sina_capture, SINA, "540581ef324974c3581607294e338024b178cba3995b9361725ef7bfabe40f0a"),
])
def test_strict_v1_complete_decoded_golden_stays_unchanged(raw, fmt, expected):
    decoded = decode(raw(), fmt)
    assert hashlib.sha256(_json(asdict(decoded)).encode()).hexdigest() == expected
    assert decoded.contract["capture_version"] == CAPTURE_VERSION
    assert decoded.contract == public_contract(fmt)
    assert decoder_identity(fmt)["capture_version"] == CAPTURE_VERSION
    assert "provenance" not in decoded.metadata


@pytest.mark.parametrize("raw,fmt", [(tx_capture, TX), (sina_capture, SINA)])
def test_legacy_identity_and_visible_limits_differ_from_v1(raw, fmt, tmp_path):
    strict, legacy = raw(), legacy_capture(raw())
    strict_capture, reconstructed = validate_capture(strict, fmt), validate_capture(legacy, fmt)
    assert reconstructed.body == strict_capture.body
    assert reconstructed.envelope["request"] == strict_capture.envelope["request"]
    assert reconstructed.envelope["response"] == strict_capture.envelope["response"]
    assert reconstructed.envelope["capture_version"] == LEGACY_CAPTURE_VERSION
    decoded, original = decode(legacy, fmt), decode(strict, fmt)
    assert decoded.rows == original.rows
    assert decoded.contract == public_contract(fmt, capture_version=LEGACY_CAPTURE_VERSION)
    assert decoded.contract != original.contract
    assert decoded.contract["raw_kind"] == "legacy_http_capture_reconstruction"
    for key, expected in [("capture_version", LEGACY_CAPTURE_VERSION), ("capture_mode", "legacy_reconstruction"),
                          ("header_cardinality", "unrecorded"), ("transport_evidence", "not_established"),
                          ("provenance_hash_verification", "syntax_only")]:
        assert decoded.metadata[key] == decoded.contract[key] == expected
    assert decoded.metadata["provenance"] == PROVENANCE
    assert decoded.metadata["coverage"] == "unverified"
    with EvidenceStore(tmp_path / "store") as store:
        before = store.import_bytes(strict, fmt)
        first = store.import_bytes(legacy, fmt)
        again = store.import_bytes(legacy_capture(raw()), fmt)
        assert before["status"] == first["status"] == again["status"] == "committed"
        assert before["snapshot_id"] != first["snapshot_id"]
        assert first["snapshot_id"] == again["snapshot_id"]
        assert again["reused"] is True
        other = legacy_capture(raw(), provenance={**PROVENANCE, "original_manifest_sha256": "c" * 64})
        different = store.import_bytes(other, fmt)
        assert different["snapshot_id"] != first["snapshot_id"]


@pytest.mark.parametrize("mutation", [
    lambda p: p.update(extra="x"), lambda p: p.pop("header_cardinality"),
    lambda p: p.update(capture_mode="live"), lambda p: p.update(header_cardinality="verified"),
    lambda p: p.update(transport_evidence="established"),
    lambda p: p.update(original_manifest_sha256="A" * 64),
    lambda p: p.update(capture_script_sha256="short"),
    lambda p: p.update(capture_script_sha256=None),
    lambda p: p.update(original_manifest_sha256=[]),
])
def test_legacy_provenance_exact_shape_and_qualifications(mutation):
    provenance = dict(PROVENANCE)
    mutation(provenance)
    with pytest.raises(DecodeError):
        legacy_capture(provenance=provenance)
    raw = mutate_capture(legacy_capture(), lambda e: e.update(provenance=provenance))
    with pytest.raises(DecodeError):
        preflight_capture(raw, TX)


@pytest.mark.parametrize("change", [
    lambda e: e.pop("provenance"),
    lambda e: e.update(capture_version=CAPTURE_VERSION),
    lambda e: e.update(capture_version="arbitrary_legacy"),
    lambda e: e.update(reconstructed_at="2026-10-11"),
    lambda e: e["provenance"].update(path="/tmp/private"),
])
def test_version_provenance_pair_cannot_be_weakened(change):
    with pytest.raises(DecodeError):
        preflight_capture(mutate_capture(legacy_capture(), change), TX)
    strict_with_provenance = mutate_capture(tx_capture(), lambda e: e.update(provenance=PROVENANCE))
    with pytest.raises(DecodeError):
        preflight_capture(strict_with_provenance, TX)


@pytest.mark.parametrize("headers", [
    [("content-type", "text/html; charset=UTF-8")], {},
    {"content-type": "text/html; charset=UTF-8"},
    {"content-type": "text/html; charset=UTF-8", "content-encoding": "gzip"},
    {"content-type": "text/html; charset=UTF-8", "content-encoding": "", "cardinality": "one"},
])
def test_legacy_builder_never_invents_pairs_or_missing_selected_values(headers):
    with pytest.raises(DecodeError):
        legacy_capture(selected_headers=headers)


def test_legacy_builder_does_not_invoke_actual_pair_constructor(monkeypatch):
    import anatrading.public_market as module
    strict = tx_capture()
    monkeypatch.setattr(module, "build_capture", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fake pairs")))
    raw = legacy_capture(strict)
    assert validate_capture(raw, TX).envelope["capture_version"] == LEGACY_CAPTURE_VERSION
    envelope = json.loads(strict)
    with pytest.raises(DecodeError):
        build_capture("tencent", envelope["request"], status=200, response_url=envelope["response"]["url"],
                      response_headers=envelope["response"]["headers"], body=base64.b64decode(envelope["body_base64"]))


def test_star_attribute_is_preserved_only_in_entity():
    ordinary = decode(tx_capture(), TX)
    raw = tx_capture(extra={"attribute": ATTRIBUTES})
    decoded = decode(raw, TX)
    assert decoded.rows == ordinary.rows
    assert decoded.contract == ordinary.contract
    assert set(decoded.metadata) == set(ordinary.metadata)
    assert all("attribute" not in row.tokens for row in decoded.rows)
    assert all(key not in json.dumps(decoded.metadata) for key in ATTRIBUTES)
    body = validate_capture(raw, TX).body
    assert json.loads(body.split(b"=", 1)[1])["data"]["sh600111"]["attribute"] == ATTRIBUTES


@pytest.mark.parametrize("attribute", [
    None, [], "0", {}, {**ATTRIBUTES, "Unknown": "0"},
    {k: v for k, v in ATTRIBUTES.items() if k != "IsVIE"},
    {**ATTRIBUTES, "IsVIE": 0}, {**ATTRIBUTES, "IsVIE": False},
    {**ATTRIBUTES, "IsVIE": "2"}, {**ATTRIBUTES, "IsVIE": "00"},
])
def test_star_attribute_whitelist_rejects_unknown_shapes_before_raw(attribute, tmp_path):
    raw = tx_capture(extra={"attribute": attribute})
    with pytest.raises(NonMarketPayload):
        preflight_capture(raw, TX)
    with EvidenceStore(tmp_path / "store") as store:
        result = store.import_bytes(raw, TX)
        assert result["raw_sha256"] is None


def test_unrelated_tencent_auxiliary_keys_still_rejected():
    with pytest.raises(NonMarketPayload):
        preflight_capture(tx_capture(extra={"arbitrary": ATTRIBUTES}), TX)
