"""Source gap boundaries and causal observations; artificial cases are not market evidence."""
import asyncio
from copy import deepcopy
from decimal import localcontext
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct

import httpx
import pytest

from anatrading.source_gaps import gap_report
from anatrading.store import EvidenceStore
from anatrading.workbench import create_app


def row(ordinal, low, high, opening=None, close=None, label=None):
    return dict(ordinal=ordinal, label=label or f"2026-09-{ordinal:02d}", tokens={},
                values=dict(open=str(low if opening is None else opening), high=str(high),
                            low=str(low), close=str(high if close is None else close)))


def query(rows, unlocated=(), period="1d", **selection):
    return dict(snapshot_id="a" * 64, query_id="b" * 64, metadata=dict(period=period),
                manifest=dict(qualification="source_evidence_retrospective_only"), selection=selection,
                rows=list(rows), unlocated=list(unlocated))


def test_strict_range_gap_and_open_close_change_are_distinct():
    q = query([row(1, 9, 10), row(2, 12, 13), row(3, 13, 14), row(4, 11, 13)])
    before = deepcopy(q)
    result = gap_report(q, q)
    first, up, equal, overlap = result["rows"]
    assert first["reason"] == "no_previous_source_bar"
    assert (up["gap"]["direction"], up["gap"]["lower"], up["gap"]["upper"], up["gap"]["width"]) == ("up", "10", "12", "2")
    assert up["open_close_change"] == "2" and up["previous_ordinals"] == [1]
    assert equal["gap"] is None and equal["reason"] is None
    assert overlap["gap"] is None and overlap["open_close_change"] == "-3"
    assert result["observation_scope"] == "full_source_context_to_asof"
    assert q == before


def test_formation_excluded_near_touch_partial_and_far_equal():
    rows = [row(1, 9, 10), row(2, 12, 13), row(3, 12, 13), row(4, 11, 13), row(5, 10, 11)]
    gap = gap_report(query(rows), query(rows))["rows"][1]["gap"]
    assert gap["near_event"]["ordinal"] == 3 and gap["near_event"]["relation"] == "equal"
    assert gap["far_event"]["ordinal"] == 5 and gap["far_event"]["relation"] == "equal"
    assert gap["far_event"]["range_relation"] == "overlaps_interval"
    prefix = query(rows[:4])
    prior = gap_report(prefix, prefix)["rows"][1]["gap"]
    assert prior["far_event"] is None and prior["state"] == "near_boundary_observed"
    assert gap["gap_id"] == prior["gap_id"] and gap["near_event"] == prior["near_event"]


@pytest.mark.parametrize("rows,direction,extreme", [
    ([row(1, 9, 10), row(2, 12, 13), row(3, 7, 8)], "up", "7"),
    ([row(1, 12, 13), row(2, 9, 10), row(3, 14, 15)], "down", "15"),
])
def test_same_bar_both_boundaries_and_jump_without_overlap(rows, direction, extreme):
    q = query(rows)
    gap = gap_report(q, q)["rows"][1]["gap"]
    assert gap["direction"] == direction and gap["state"] == "far_boundary_observed"
    for name in ("near_event", "far_event"):
        assert gap[name]["ordinal"] == 3 and gap[name]["extreme"] == extreme
        assert gap[name]["range_relation"] == "passed_without_overlap"
    assert gap["near_event"]["label"] == gap["far_event"]["label"]


@pytest.mark.parametrize("bad,reason", [("duplicate", "duplicate_label"), (None, "missing_ohlc"), ("oops", "invalid_price"), ("-1", "negative_price")])
def test_bad_or_duplicate_interrupts_pending_without_future_first_claim(bad, reason):
    rows = [row(1, 9, 10), row(2, 12, 13), row(3, 12, 13), row(4, 12, 13), row(5, 7, 8), row(6, 10, 11)]
    if bad == "duplicate":
        rows.append({**row(7, 12, 13), "label": rows[3]["label"]})
    else:
        rows[3]["values"]["low"] = bad
    q = query(rows)
    report = gap_report(q, q)
    gap = report["rows"][1]["gap"]
    assert gap["near_event"]["ordinal"] == 3 and gap["far_event"] is None
    assert gap["interrupted_at"]["label"] == rows[3]["label"]
    assert gap["interrupted_at"]["reason"] == reason and gap["state"] == "observation_interrupted"
    assert report["rows"][4]["reason"] == "previous_bar_unavailable"
    # The valid-valid pair after the barrier can form its own new gap.
    assert report["rows"][5]["gap"]["direction"] == "up"


def test_window_previous_context_horizon_and_fixed_cutoff():
    rows = [row(1, 9, 10), row(2, 12, 13), row(3, 14, 15), row(4, 9, 10)]
    selected, context = query(rows[1:3], ordinal_start=2, ordinal_end=3), query(rows)
    report = gap_report(selected, context)
    assert report["as_of_label"] == rows[2]["label"]
    assert report["rows"][0]["previous_ordinals"] == [1]
    assert report["rows"][0]["gap"]["near_event"] is None
    assert report["rows"] == gap_report(selected, query(rows[:3]))["rows"]
    selected["selection"]["cutoff"] = rows[1]["label"]
    selected["rows"] = selected["rows"][:1]
    assert gap_report(selected, context)["as_of_label"] == rows[1]["label"]
    assert gap_report(selected, context)["rows"][0]["gap"]["near_event"] is None


def test_unlocated_kept_with_explicit_first_observation_coverage_qualification():
    q = query([row(1, 9, 10), row(2, 12, 13), row(3, 7, 8)])
    unknown = row(4, 9, 10)
    unknown["label"] = None
    q["unlocated"] = [unknown]
    report = gap_report(q, q)
    assert report["coverage_reason"] == "unknown_adjacency_and_first_observation_coverage"
    assert report["context_unlocated_rows"] == 1
    assert report["unlocated"][0]["reason"] == "unlocated_label"
    assert report["rows"][1]["gap"]["far_event"]["ordinal"] == 3


def test_high_precision_under_low_context_and_source_scale_invariance():
    base = "99999999999999999999.999999999999999990"
    rows = [row(1, base, base), row(2, "99999999999999999999.999999999999999992", "99999999999999999999.999999999999999994"),
            row(3, base, base)]
    q = query(rows)
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        gap = gap_report(q, q)["rows"][1]["gap"]
    assert gap["width"] == "0.000000000000000002"
    assert gap["far_event"]["ordinal"] == 3
    scaled = query([row(1, 90, 100), row(2, 120, 130), row(3, 70, 80)])
    value = gap_report(scaled, scaled)["rows"][1]["gap"]
    assert (value["lower"], value["upper"], value["width"]) == ("100", "120", "20")


def test_minute_labels_sorted_and_cross_session_is_not_consecutive_trading_claim():
    rows = [row(1, 9, 10, label="2026-09-28T15:00"), row(2, 12, 13, label="2026-09-29T09:31"),
            row(3, 9, 10, label="2026-09-29T09:32")]
    q = query(list(reversed(rows)), period="1m")
    report = gap_report(q, q)
    assert report["rows"][1]["gap"]["far_event"]["ordinal"] == 3
    assert report["adjacency"] == "adjacent_located_labels"
    assert "calendar" in report["unknowns"]
    q["metadata"]["period"] = "5m"
    assert all(r["reason"] == "unsupported_period" for r in gap_report(q, q)["rows"])
    other = deepcopy(q)
    other["snapshot_id"] = "c" * 64
    with pytest.raises(ValueError, match="context_snapshot_mismatch"):
        gap_report(q, other)


def _oracle_rows(values):
    """Direct per-gap scan, independent of the implementation's heaps/Decimal arithmetic."""
    result = []
    for i, (opening, high, low, close) in enumerate(values):
        if not i:
            result.append(None)
            continue
        a = values[i - 1]
        up, down = low > a[1], high < a[2]
        if not (up or down):
            result.append(None)
            continue
        lower, upper = (a[1], low) if up else (high, a[2])
        near = next((j + 1 for j in range(i + 1, len(values)) if values[j][2] <= upper), None) if up else next((j + 1 for j in range(i + 1, len(values)) if values[j][1] >= lower), None)
        far = next((j + 1 for j in range(i + 1, len(values)) if values[j][2] <= lower), None) if up else next((j + 1 for j in range(i + 1, len(values)) if values[j][1] >= upper), None)
        result.append(("up" if up else "down", lower, upper, near, far))
    return result


def test_many_overlapping_thresholds_match_independent_full_scan():
    from datetime import date, timedelta
    from random import Random
    random = Random(1049)
    rows = []
    prices = []
    for i in range(250):
        low = random.randrange(0, 30)
        high = low + random.randrange(0, 8)
        opening, close = random.randint(low, high), random.randint(low, high)
        rows.append(row(i + 1, low, high, opening, close, (date(2025, 1, 1) + timedelta(days=i)).isoformat()))
        prices.append((opening, high, low, close))
    q = query(rows)
    for result, expected in zip(gap_report(q, q)["rows"], _oracle_rows(prices)):
        gap = result["gap"]
        if expected is None:
            assert gap is None
        else:
            direction, lower, upper, near, far = expected
            assert (gap["direction"], Fraction(gap["lower"]), Fraction(gap["upper"])) == (direction, lower, upper)
            assert [gap[k]["ordinal"] if gap[k] else None for k in ("near_event", "far_event")] == [near, far]


def test_unselected_context_can_supply_observation_and_completed_gap_not_interrupted():
    rows = [row(1, 9, 10), row(2, 12, 13), row(3, 10, 11), row(4, 14, 15), row(5, 14, 15)]
    rows[4]["values"]["low"] = None
    selected = query([rows[1], rows[3], rows[4]])
    report = gap_report(selected, query(rows))
    gap = report["rows"][0]["gap"]
    assert gap["near_event"]["ordinal"] == gap["far_event"]["ordinal"] == 3
    assert gap["interrupted_at"] is None and gap["state"] == "far_boundary_observed"
    assert report["rows"][1]["gap"]["state"] == "observation_interrupted"


@pytest.mark.parametrize("symbol,sha,count", [
    ("600059.SH", "cefe9e437646382cf1a11345665ba969d6946335858704383234e38c1093e17d", 195),
    ("000001.SZ", "9f3a52bdbf68037850bc41347f913b32b665599b947b8602ec247a5cc08b4aad", 452),
    ("920000.BJ", "1068f2623c27522c58e421e5454f6b12b5d055608fd2e0db01b9a5a9c56213b9", 38),
])
def test_real_three_market_uint32_oracle(tmp_path, symbol, sha, count):
    path = Path(__file__).resolve().parents[1] / "artifacts/qualification/daily-native" / (symbol + ".day")
    if not path.exists():
        pytest.skip("Private original unavailable; no compatibility claim")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha
    native = list(struct.iter_unpack("<IIIIIfII", raw))
    assert all(a[0] < b[0] for a, b in zip(native, native[1:]))
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(raw, "tdx-public-day-v1", interpretation=dict(instrument=symbol, venue=symbol[-2:], asset_type="stock"))["snapshot_id"]
        q = store.query(sid)
        report = gap_report(q, q)
    oracle = _oracle_rows([v[1:5] for v in native])
    assert sum(v is not None for v in oracle) == count
    for i, (row_value, expected) in enumerate(zip(report["rows"], oracle)):
        if i:
            assert Fraction(row_value["open_close_change"]) == Fraction(native[i][1] - native[i - 1][4], 100)
        gap = row_value["gap"]
        if expected is None:
            assert gap is None
            continue
        direction, lower, upper, near, far = expected
        assert gap["direction"] == direction
        assert (Fraction(gap["lower"]), Fraction(gap["upper"]), Fraction(gap["width"])) == (Fraction(lower, 100), Fraction(upper, 100), Fraction(upper - lower, 100))
        for name, ordinal in (("near_event", near), ("far_event", far)):
            assert (gap[name]["ordinal"] if gap[name] else None) == ordinal


def test_real_minute_http_tokens_exact_oracle(tmp_path):
    folder = Path(__file__).resolve().parents[1] / "artifacts/qualification/minute-read/20261008T140439Z"
    if not folder.exists():
        pytest.skip("Private original unavailable; no compatibility claim")
    raw = (folder / "response.bin").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "826e7bcca37b7dde90a74f6348877044c77dbc1f678629b1a92c1793a6dba4a2"
    values = json.loads(raw)["result"]["Value"]["600059.SH"]
    fields = ("Open", "High", "Low", "Close")
    prices = [tuple(Fraction(values[key][i]) for key in fields) for i in range(len(values["Date"]))]
    bundle = dict(request_utf8=(folder / "request.json").read_text(), response_utf8=raw.decode())
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(json.dumps(bundle).encode(), "tdx-http-market-v1", interpretation=dict(instrument="600059.SH", venue="SH", asset_type="stock"))["snapshot_id"]
        q = store.query(sid)
        report = gap_report(q, q)
    assert len(report["rows"]) == 720
    for result, expected in zip(report["rows"], _oracle_rows(prices)):
        gap = result["gap"]
        if expected is None:
            assert gap is None
        else:
            direction, lower, upper, near, far = expected
            assert (gap["direction"], Fraction(gap["width"])) == (direction, upper - lower)
            assert [gap[k]["ordinal"] if gap[k] else None for k in ("near_event", "far_event")] == [near, far]


def test_api_origin_selection_and_observation_horizon(tmp_path):
    root = tmp_path / "store"
    raw = b"".join(struct.pack("<IIIIIfII", 20260900 + i, low * 100, high * 100, low * 100, high * 100, 0, 0, 0)
                   for i, (low, high) in enumerate(((9, 10), (12, 13), (14, 15), (9, 10)), 1))
    with EvidenceStore(root) as store:
        sid = store.import_bytes(raw, "tdx-public-day-v1")["snapshot_id"]
        expected = store.query(sid, ordinal_start=2, ordinal_end=3)

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                url = "/api/source-gaps/" + sid
                params = dict(ordinal_start=2, ordinal_end=3, query_id=expected["query_id"])
                response = await client.get(url, params=params)
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                result = response.json()
                assert result["as_of_label"] == "2026-09-03"
                assert result["rows"][0]["previous_ordinals"] == [1]
                assert result["rows"][0]["gap"]["far_event"] is None
                assert (await client.get(url, params={**params, "query_id": "old"})).status_code == 409
                assert (await client.get("/api/query/" + sid, params=dict(ordinal_start=2, ordinal_end=3))).json()["query"] == expected
    asyncio.run(scenario())
