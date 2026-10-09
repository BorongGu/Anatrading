"""Reference arrays retain source strings and use an explicit local date window."""
import hashlib
import json
from pathlib import Path

import pytest

from anatrading import tdx_reference
from anatrading.tdx_acquisition import AcquireError


def response(dates, *, types=None, values=None):
    result = dict(ErrorId="0", Date=dates)
    if types is not None: result.update(Type=types, Value=values)
    return json.dumps(dict(id=1, result=result)).encode()


def view(raw, kind="calendar", target="SH", start="2026-09-01", end="2026-09-30"):
    return tdx_reference.reference_view(raw, kind=kind, target=target, start=start, end=end)


def test_calendar_local_window_includes_both_endpoints_and_keeps_source_ordinals():
    report = view(response(["20261008", "20260930", "20260901", "20260831"]))
    assert [(r["ordinal"], r["date"]) for r in report["rows"]] == [(2, "2026-09-30"), (3, "2026-09-01")]
    assert (report["returned_count"], report["selected_count"], report["before_start"], report["after_end"]) == (4, 2, 1, 1)
    assert report["qualification"] == "unverified_source_reference"


def test_actions_preserve_zero_tokens_unknown_types_and_same_date_events():
    raw = response(["20260624", "20260624"], types=["1", "99"],
                   values=[["0.90", "0.00", "0.00", "0.00"], ["-1", "6.40", "3.00", "0"]])
    report = view(raw, "actions", "600059.SH", "2026-01-01", "2026-10-08")
    assert report["selected_count"] == 2 and report["duplicate_date_rows"] == 1
    assert report["rows"][0]["values"] == dict(Bonus="0.90", AllotPrice="0.00", ShareBonus="0.00", Allotment="0.00")
    assert report["rows"][1]["source_type"] == "99" and report["rows"][1]["type_name"] is None
    assert report["rows"][1]["values"]["Bonus"] == "-1"


@pytest.mark.parametrize("raw", [response(["20260230"]), response(["20261099"]), response([20260901]),
    response(["20260901", "20260901"]), b'{"id":1,"id":1,"result":{"ErrorId":"0","Date":[]}}',
    b'{"id":true,"result":{"ErrorId":"0","Date":[]}}'])
def test_bad_calendar_dates_even_outside_window_and_duplicate_json_keys_are_rejected(raw):
    with pytest.raises(AcquireError, match="invalid_tdx_reference_response"): view(raw)


@pytest.mark.parametrize("types,values", [([], []), (["1"], [["1", "2", "3"]]),
    (["1"], [["1", "2", "3", "4", "5"]]), ([1], [["1"] * 4]),
    (["1"], [["", "0", "0", "0"]]), (["1"], [[0, "0", "0", "0"]]),
    (["1"], [["NaN", "0", "0", "0"]])])
def test_action_field_alignment_and_exact_numeric_strings(types, values):
    with pytest.raises(AcquireError, match="invalid_tdx_reference_response"):
        view(response(["20260624"], types=types, values=values), "actions", "600059.SH")


def test_empty_arrays_are_an_empty_observation_without_completeness_claim():
    for raw, kind, target in ((response([]), "calendar", "SH"), (response([], types=[], values=[]), "actions", "600059.SH")):
        report = view(raw, kind, target)
        assert report["returned_count"] == report["selected_count"] == 0
        assert report["coverage"] == "unverified" and report["rows"] == []
    assert view(response([]), "actions", "600059.SH")["rows"] == []


def test_observed_empty_value_without_date_is_explicit_and_does_not_imply_no_actions():
    raw = b'{"id":1,"result":{"ErrorId":"0","Value":[]}}'
    report = view(raw, "actions", "301718.SZ")
    assert report["rows"] == [] and report["empty_shape"] == "value_only_empty"
    assert report["coverage"] == "unverified" and report["historical_available_at"] is None
    for raw in (b'{"id":1,"result":{"ErrorId":"0","Value":[["1","0","0","0"]]}}',
                b'{"id":1,"result":{"ErrorId":"0","Date":null,"Value":[]}}'):
        with pytest.raises(AcquireError, match="invalid_tdx_reference_response"): view(raw, "actions", "301718.SZ")


def test_market_and_dates_are_validated_before_contacting_the_client(tmp_path, monkeypatch):
    def contacted(*a, **kw): raise AssertionError("invalid input contacted client")
    monkeypatch.setattr(tdx_reference.acquisition, "_client_identity", contacted)
    for kind, target, start, end in [("calendar", "SZ", "2026-09-01", "2026-09-30"),
        ("calendar", "INVALID", "2026-09-01", "2026-09-30"), ("trade", "SH", "2026-09-01", "2026-09-30"),
        ("actions", "../600059.SH", "2026-09-01", "2026-09-30"), ("calendar", "SH", "20260901", "2026-09-30"),
        ("calendar", "SH", "2026-09-30", "2026-09-01")]:
        with pytest.raises(AcquireError, match="invalid_tdx_reference_request"):
            tdx_reference.read_reference(tmp_path / "data", tmp_path / "client", kind=kind, target=target, start=start, end=end)
    assert not (tmp_path / "data").exists()


def test_capture_saves_original_bytes_and_only_filters_the_view(tmp_path, monkeypatch):
    raw = response(["19970901", "20260624"], types=["1", "1"], values=[["0", "0", "8", "0"], ["0.90", "0.00", "0.00", "0.00"]])
    monkeypatch.setattr(tdx_reference.acquisition, "_client_identity", lambda client: dict(pid=123))
    def receive(port, method, path, body, headers, **kwargs):
        request = json.loads(body)
        assert request["method"] == "get_divid_factors" and request["params"]["start_time"] == "20260101000000"
        return 200, raw
    monkeypatch.setattr(tdx_reference.acquisition, "_http", receive)
    report = tdx_reference.read_reference(tmp_path / "data", tmp_path / "client", kind="actions", target="600059.SH", start="2026-01-01", end="2026-10-08")
    folder = Path(report["evidence_directory"])
    assert (folder / "response.bin").read_bytes() == raw
    assert report["response_sha256"] == hashlib.sha256(raw).hexdigest()
    assert report["rows"][0]["ordinal"] == 2 and report["before_start"] == 1
    assert json.loads((folder / "report.json").read_text(encoding="utf-8")) == report
    assert report["historical_available_at"] is None and report["captured_at"].endswith("+00:00")


def test_invalid_response_is_archived_without_an_admitted_view(tmp_path, monkeypatch):
    raw = response(["bad"])
    monkeypatch.setattr(tdx_reference.acquisition, "_client_identity", lambda client: dict(pid=123))
    monkeypatch.setattr(tdx_reference.acquisition, "_http", lambda *a, **kw: (200, raw))
    with pytest.raises(AcquireError, match="invalid_tdx_reference_response"):
        tdx_reference.read_reference(tmp_path / "data", tmp_path / "client", kind="calendar", target="SH", start="2026-01-01", end="2026-10-08")
    folder = next((tmp_path / "data/acquisition/reference").iterdir())
    assert (folder / "response.bin").read_bytes() == raw
    assert not (folder / "report.json").exists()
    assert json.loads((folder / "capture.json").read_text())["status"] == "rejected"


def test_real_frozen_reference_samples():
    folder = Path(__file__).resolve().parents[1] / "artifacts/qualification/calendar-probe"
    if not (folder / "response.bin").exists(): pytest.skip("Private real reference samples unavailable")
    raw = (folder / "response.bin").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "925e31a9677fa20ea77d64445df0057067792ca137077ff14478b454585c7143"
    calendar = view(raw, end="2026-10-08")
    assert calendar["returned_count"] == calendar["selected_count"] == 22
    assert "2026-09-25" not in [r["date"] for r in calendar["rows"]]
    assert calendar["rows"][-1]["date"] == "2026-10-08"
    raw = (folder / "dividend-600059-response.bin").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "634742923f02fd833e8e60a8c5afa8accfef7c08a37f15ad865522d319e08f25"
    actions = view(raw, "actions", "600059.SH", "2026-01-01", "2026-10-08")
    assert (actions["returned_count"], actions["selected_count"], actions["before_start"], actions["after_end"]) == (31, 1, 30, 0)
    assert actions["rows"][0]["ordinal"] == 31 and actions["rows"][0]["date"] == "2026-06-24"
    assert actions["rows"][0]["values"] == dict(Bonus="0.90", AllotPrice="0.00", ShareBonus="0.00", Allotment="0.00")
