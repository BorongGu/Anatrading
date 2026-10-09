"""Frozen action arrays retain interval boundaries and query membership."""
from copy import deepcopy
import asyncio
import hashlib
import json
from pathlib import Path

import pytest
import httpx

from anatrading.source_actions import action_window, captured_actions, action_captures
from anatrading.tdx_acquisition import AcquireError
from anatrading.tdx_reference import _request, reference_view
from test_tdx_reference import response
from test_daily_background import samples
from anatrading.store import EvidenceStore
from anatrading.workbench import create_app


def query(rows=(), cutoff=None):
    return dict(snapshot_id="snapshot", query_id="query", metadata=dict(period="1d"),
                selection=dict(cutoff=cutoff), rows=[dict(ordinal=i, label=day, tokens={}) for i, day in rows], unlocated=[])


def reference(raw=None, start="2026-01-01"):
    raw = raw or response(["20260623", "20260624", "20260624", "20260625"], types=["1", "11", "99", "15"], values=[["0", "0", "0", "0"]] * 4)
    result = reference_view(raw, kind="actions", target="600059.SH", start="0001-01-01", end="9999-12-31")
    return dict(**result, capture_selection=dict(start=start, end="2026-10-08"),
                capture_id="a" * 32, captured_at="2026-10-09T00:00:00Z", request_sha256="b" * 64, response_sha256="c" * 64)


def test_exclusive_start_inclusive_end_and_same_date_records_are_retained():
    q = query([(7, "2026-06-24"), (8, "2026-06-24")])
    ref = reference()
    before = deepcopy((q, ref))
    result = action_window(q, ref, "2026-06-23", "2026-06-24")
    assert [row["ordinal"] for row in result["rows"]] == [2, 3]
    assert [row["source_type"] for row in result["rows"]] == ["11", "99"]
    assert all(row["query_ordinals"] == [7, 8] and row["link_reason"] == "duplicate_query_date" for row in result["rows"])
    assert result["rows"][1]["type_name"] is None
    other = action_window(q, ref, "2026-06-24", "2026-06-25")
    assert [row["ordinal"] for row in other["rows"]] == [4]
    assert result["action_window_id"] != other["action_window_id"]
    assert (q, ref) == before


def test_cutoff_and_ordinal_window_do_not_create_false_missing_source_days():
    ref = reference()
    result = action_window(query([(1, "2026-06-23")], "2026-06-23"), ref, "2026-06-23", "2026-06-24")
    assert all(row["link_reason"] == "outside_query_cutoff" and not row["query_ordinals"] for row in result["rows"])
    result = action_window(query(), ref, "2026-06-23", "2026-06-24")
    assert all(row["link_reason"] == "not_returned_by_query" for row in result["rows"])
    q = query()
    q["unlocated"] = [dict(ordinal=4, label=None, tokens=dict(date="bad"))]
    assert action_window(q, ref, "2026-06-23", "2026-06-24")["unreadable_query_date_ordinals"] == [4]


def test_window_outside_capture_request_and_empty_results_keep_coverage_unknown():
    ref = reference(start="2026-06-24")
    result = action_window(query(), ref, "2026-06-22", "2026-06-24")
    assert result["request_range_status"] == "range_not_requested"
    assert result["coverage"] == "unverified"
    assert action_window(query(), ref, "2026-06-23", "2026-06-24")["request_range_status"] == "within_requested_range"
    empty = reference(response([], types=[], values=[]))
    result = action_window(query(), empty, "2026-06-23", "2026-06-24")
    assert result["rows"] == [] and result["observation_status"] == "no_returned_records"
    assert result["historical_available_at"] is None


@pytest.mark.parametrize("start,end", [("2026-06-24", "2026-06-24"), ("2026-06-25", "2026-06-24"), ("20260623", "2026-06-24")])
def test_invalid_interval(start, end):
    with pytest.raises(AcquireError, match="invalid_action_window"):
        action_window(query(), reference(), start, end)


def archive(root, raw=None):
    raw = raw or response(["20260624"], types=["1"], values=[["0.90", "0", "0", "0"]])
    request = json.dumps(_request("actions", "600059.SH", "2026-01-01", "2026-10-08")).encode()
    folder = root / "acquisition/reference" / ("a" * 32)
    folder.mkdir(parents=True)
    (folder / "request.json").write_bytes(request)
    (folder / "response.bin").write_bytes(raw)
    capture = dict(capture_id=folder.name, status="received", http_status=200, captured_at="2026-10-09T00:00:00Z",
        request_sha256=hashlib.sha256(request).hexdigest(), response_sha256=hashlib.sha256(raw).hexdigest(), evidence_directory="do not follow this")
    (folder / "capture.json").write_text(json.dumps(capture), encoding="utf-8")
    (folder / "report.json").write_text('{"fake":true}', encoding="utf-8")
    return folder


def test_archive_reparses_hashed_originals_not_report_json(tmp_path):
    folder = archive(tmp_path)
    result = captured_actions(tmp_path, folder.name)
    assert result["target"] == "600059.SH" and result["rows"][0]["values"]["Bonus"] == "0.90"
    assert action_captures(tmp_path)[0]["capture_id"] == folder.name
    (folder / "response.bin").write_bytes(b'{}')
    with pytest.raises(AcquireError, match="reference_capture_mismatch"):
        captured_actions(tmp_path, folder.name)
    assert action_captures(tmp_path)[0]["status"] == "unavailable"


def test_bad_date_is_rejected_instead_of_an_empty_action_table(tmp_path):
    folder = archive(tmp_path, response(["20260230"], types=["1"], values=[["0", "0", "0", "0"]]))
    with pytest.raises(AcquireError, match="invalid_tdx_reference_response"):
        captured_actions(tmp_path, folder.name)


@pytest.mark.parametrize("capture_id", ["..", "a" * 31, "a" * 32 + "/x", "../" + "a" * 32])
def test_capture_id_is_scoped(tmp_path, capture_id):
    with pytest.raises(AcquireError, match="invalid_reference_capture"):
        captured_actions(tmp_path, capture_id)


def test_private_real_action_boundary_and_original_values():
    root = Path(__file__).resolve().parents[1] / "data/local"
    capture = "a6291b8e16264dc4b574f804a8c6a9a5"
    path = root / "acquisition/reference" / capture / "response.bin"
    if not path.exists():
        pytest.skip("Private real capture unavailable; no network fallback")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "634742923f02fd833e8e60a8c5afa8accfef7c08a37f15ad865522d319e08f25"
    ref = captured_actions(root, capture)
    result = action_window(query([(1, "2026-06-24")]), ref, "2026-06-23", "2026-06-24")
    assert len(result["rows"]) == 1
    assert result["rows"][0]["ordinal"] == 31
    assert result["rows"][0]["source_type"] == "1" and result["rows"][0]["values"]["Bonus"] == "0.90"
    assert action_window(query(), ref, "2026-06-24", "2026-06-25")["rows"] == []


@pytest.mark.parametrize("capture_id,sha,day,bonus,shares", [
    ("a6291b8e16264dc4b574f804a8c6a9a5", "634742923f02fd833e8e60a8c5afa8accfef7c08a37f15ad865522d319e08f25", "2026-06-24", "0.90", "0.00"),
    ("318f91e1f5a34671b2a142df98ec6534", "0d9870cf1967cb4f6c80e45115bec6b6666a880d320f2650566dca565b66383c", "2026-06-12", "3.60", "0.00"),
    ("570ba6ba95b94da292c82d36916a7dc1", "092ffbc4707ea1d5a021dba10d6ade37cc0ff291ce70c1238fd433d4a4340c4a", "2026-05-27", "1.00", "4.00"),
])
def test_private_three_market_type_one_records(capture_id, sha, day, bonus, shares):
    root = Path(__file__).resolve().parents[1] / "data/local"
    path = root / "acquisition/reference" / capture_id / "response.bin"
    if not path.exists():
        pytest.skip("Private real capture unavailable; no network fallback")
    if sha is not None:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
    ref = captured_actions(root, capture_id)
    original = json.loads(path.read_bytes())["result"]
    index = original["Date"].index(day.replace("-", ""))
    start = day[:8] + "01"
    result = action_window(query([(17, day)]), ref, start, day)
    matching = [row for row in result["rows"] if row["date"] == day]
    assert len(matching) == 1
    row = matching[0]
    assert row["ordinal"] == index + 1 and row["source_type"] == original["Type"][index] == "1"
    assert list(row["values"].values()) == original["Value"][index]
    assert row["values"]["Bonus"] == bonus and row["values"]["ShareBonus"] == shares
    assert row["query_ordinals"] == [17]


def test_api_query_identity_and_securities_remain_bound(tmp_path):
    root = tmp_path / "store"
    folder = archive(root)
    with EvidenceStore(root) as store:
        minute, daily = samples(store)
        q = store.query(daily, cutoff="2026-09-29")

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                assert (await client.get('/api/action-captures')).json()['captures'][0]['capture_id'] == folder.name
                params = dict(capture_id=folder.name, query_id=q['query_id'], cutoff='2026-09-29', start='2026-06-23', end='2026-06-24')
                url = '/api/action-window/'+daily
                reply = await client.get(url, params=params)
                assert reply.status_code == 200 and reply.headers['cache-control'] == 'no-store'
                assert reply.json()['rows'][0]['link_reason'] == 'not_returned_by_query'
                assert (await client.get(url, params={**params, 'query_id':'old'})).status_code == 409
                assert (await client.get(url, params={**params, 'start':'bad'})).status_code == 400
                other_request = _request('actions', '000001.SZ', '2026-01-01', '2026-10-08')
                data = json.dumps(other_request).encode()
                (folder/'request.json').write_bytes(data)
                meta = json.loads((folder/'capture.json').read_text())
                meta['request_sha256'] = hashlib.sha256(data).hexdigest()
                (folder/'capture.json').write_text(json.dumps(meta))
                assert (await client.get(url, params=params)).json() == {'error':'background_symbol_mismatch'}
    asyncio.run(scenario())
