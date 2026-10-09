"""Window confirmation is source-observation timing, without a PIT or trading claim."""
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

from anatrading.source_pivots import pivot_report
from anatrading.store import EvidenceStore
from anatrading.workbench import create_app


def row(ordinal, high, low="1", label=None):
    return dict(ordinal=ordinal, label=label or f"2026-09-{ordinal:02d}", tokens={},
                values=dict(open=str(low), high=str(high), low=str(low), close=str(high)))


def query(rows, unlocated=(), period="1d", **selection):
    return dict(snapshot_id="a" * 64, query_id="b" * 64, manifest=dict(qualification="source_evidence_retrospective_only"),
                metadata=dict(period=period), selection=selection, rows=list(rows), unlocated=list(unlocated))


def sample():
    return [row(1, 3), row(2, 4), row(3, 6, 0), row(4, 4), row(5, 3)]


def test_dual_extremum_has_distinct_anchor_and_confirmation_not_ordered_path():
    q = query(sample())
    before = deepcopy(q)
    result = pivot_report(q, q)
    center = result["rows"][2]
    assert center["high"]["is_pivot"] is True and center["low"]["is_pivot"] is True
    assert center["window_labels"] == [r["label"] for r in q["rows"]]
    assert [e["kind"] for e in result["events"]] == ["high", "low"]
    for event in result["events"]:
        assert event["anchor_ordinal"] == 3 and event["confirmation_ordinal"] == 5
        assert event["anchor_label"] == "2026-09-03" and event["confirmation_label"] == "2026-09-05"
        assert event["delay_source_labels"] == 2
    assert [e["price"] for e in result["events"]] == ["6", "0"]
    assert [r["reason"] for r in result["rows"]] == ["history_insufficient", "history_insufficient", None, "pending_right_window", "pending_right_window"]
    assert result["confirmation_semantics"] == "right_source_window_present" and "known_at" in result["unknowns"]
    assert q == before


@pytest.mark.parametrize("highs,expected", [(["5", "5", "7"], "not_high"), (["5", "5", "3"], "tied_not_strict"), (["1", "2", "1"], None)])
def test_tie_is_only_a_tie_at_the_window_extreme(highs, expected):
    q = query([row(i, h) for i, h in enumerate(highs, 1)])
    value = pivot_report(q, q, 1)["rows"][1]["high"]
    assert value["reason"] == expected and value["is_pivot"] == (expected is None)


@pytest.mark.parametrize("lows,expected", [(["2", "2", "0"], "not_low"), (["2", "2", "3"], "tied_not_strict"), (["2", "1", "2"], None)])
def test_low_tie_and_non_extreme(lows, expected):
    q = query([row(i, "7", low) for i, low in enumerate(lows, 1)])
    value = pivot_report(q, q, 1)["rows"][1]["low"]
    assert value["reason"] == expected and value["is_pivot"] == (expected is None)


@pytest.mark.parametrize("bad,reason", [("duplicate", "duplicate_label"), (None, "missing_ohlc"), ("bad", "invalid_price"), ("-1", "negative_price"), ("99", "invalid_ohlc")])
def test_bad_window_retains_groups_and_never_splices_neighbors(bad, reason):
    rows = sample()
    if bad == "duplicate":
        rows.append({**row(7, 4), "label": rows[3]["label"]})
    else:
        rows[3]["values"]["low"] = bad
    q = query(rows)
    result = pivot_report(q, q)
    center = result["rows"][2]
    assert center["reason"] == reason and center["high"]["is_pivot"] is None
    assert center["low"]["is_pivot"] is None and result["events"] == []
    assert len(center["window_labels"]) == 5
    assert result["members"][3]["reason"] == reason


def test_all_prefixes_match_final_events_available_by_source_confirmation_label():
    rows = sample() + [row(6, 5, 2), row(7, 4, 2), row(8, 3, 2)]
    full = query(rows)
    final = pivot_report(full, full)
    for size in range(1, len(rows) + 1):
        prefix = query(rows[:size], cutoff=rows[size - 1]["label"])
        report = pivot_report(prefix, full)
        assert report["events"] == [e for e in final["events"] if e["confirmation_label"] <= rows[size - 1]["label"]]
        for result in report["rows"]:
            if result["reason"] is None:
                assert result == final["rows"][result["ordinal"] - 1]
    assert pivot_report(query(rows[:4]), full)["rows"][2]["reason"] == "pending_right_window"


def test_window_supplies_left_context_without_borrowing_right_future():
    rows = sample()
    q = query(rows[2:4], ordinal_start=3, ordinal_end=4)
    result = pivot_report(q, query(rows))
    assert result["events"] == [] and result["as_of_label"] == rows[3]["label"]
    assert result["rows"][0]["left_count"] == 2 and result["rows"][0]["right_count"] == 1
    assert result["rows"][0]["reason"] == "pending_right_window"
    selected = query([rows[2], rows[4]])
    report = pivot_report(selected, query(rows))
    assert report["events"][0]["anchor_ordinal"] == 3 and report["events"][0]["confirmation_ordinal"] == 5
    assert report["rows"][0]["window_labels"] == [r["label"] for r in rows]


def test_unknown_labels_remain_qualified_and_parameter_snapshot_failures():
    rows = sample()
    unknown = row(9, 100)
    unknown["label"] = None
    q = query(rows, [unknown])
    report = pivot_report(q, q)
    assert report["context_unlocated_rows"] == 1 and report["coverage_reason"] == "unknown_source_window_coverage"
    assert report["unlocated"][0]["reason"] == "unlocated_label"
    assert len(report["events"]) == 2
    for invalid in (0, 21, True, "2", 2.0):
        with pytest.raises(ValueError, match="invalid_radius"):
            pivot_report(q, q, invalid)
    different = deepcopy(q)
    different["snapshot_id"] = "c" * 64
    with pytest.raises(ValueError, match="context_snapshot_mismatch"):
        pivot_report(q, different)
    q["metadata"]["period"] = "5m"
    assert all(r["reason"] == "unsupported_period" for r in pivot_report(q, q)["rows"])


def test_decimal_context_does_not_collapse_strict_extrema_or_source_event_identity():
    low = "99999999999999999999.999999999999999990"
    high = "99999999999999999999.999999999999999992"
    top = "99999999999999999999.999999999999999994"
    rows = [row(i, top if i == 3 else high, low) for i in range(1, 6)]
    q = query(rows)
    with localcontext() as arithmetic:
        arithmetic.prec = 3
        result = pivot_report(q, q)
    event = result["events"][0]
    assert event["price"] == top and event["kind"] == "high"
    assert result["rows"][2]["low"]["reason"] == "tied_not_strict"
    assert event == pivot_report(query([rows[2], rows[4]]), q)["events"][0]
    other = deepcopy(q)
    other["snapshot_id"] = "c" * 64
    assert pivot_report(other, other)["events"][0]["pivot_id"] != event["pivot_id"]


def _check_raw_window(report, prices, labels, radius):
    expected_events = []
    for i, result in enumerate(report["rows"]):
        if i < radius or i + radius >= len(prices):
            assert result["reason"] == ("history_insufficient" if i < radius else "pending_right_window")
            continue
        assert result["reason"] is None and result["window_labels"] == labels[i - radius:i + radius + 1]
        for kind, column in (("high", 1), ("low", 2)):
            value = prices[i][column]
            others = [prices[j][column] for j in range(i - radius, i + radius + 1) if j != i]
            strict = all(value > x if kind == "high" else value < x for x in others)
            reason = None if strict else ("not_high" if kind == "high" else "not_low") if any(value < x if kind == "high" else value > x for x in others) else "tied_not_strict"
            assert result[kind]["is_pivot"] == strict and result[kind]["reason"] == reason
            if strict:
                expected_events.append((i + 1, kind, value, i + radius + 1))
    assert len(report["events"]) == len(expected_events)
    for event, (anchor, kind, price, confirmation) in zip(report["events"], expected_events):
        assert (event["anchor_ordinal"], event["kind"], Fraction(event["price"]), event["confirmation_ordinal"]) == (anchor, kind, price, confirmation)
        assert event["anchor_label"] == labels[anchor - 1] and event["confirmation_label"] == labels[confirmation - 1]


@pytest.mark.parametrize("symbol,sha,counts", [
    ("600059.SH", "cefe9e437646382cf1a11345665ba969d6946335858704383234e38c1093e17d", (899, 882)),
    ("000001.SZ", "9f3a52bdbf68037850bc41347f913b32b665599b947b8602ec247a5cc08b4aad", (1055, 1022)),
    ("920000.BJ", "1068f2623c27522c58e421e5454f6b12b5d055608fd2e0db01b9a5a9c56213b9", (163, 157)),
])
def test_three_market_original_integer_oracle(tmp_path, symbol, sha, counts):
    path = Path(__file__).resolve().parents[1] / "artifacts/qualification/daily-native" / (symbol + ".day")
    if not path.exists():
        pytest.skip("Private real sample unavailable; no compatibility claim")
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == sha
    native = list(struct.iter_unpack("<IIIIIfII", raw))
    assert all(a[0] < b[0] for a, b in zip(native, native[1:]))
    prices = [tuple(Fraction(v, 100) for v in source[1:5]) for source in native]
    labels = [f"{v[0] // 10000:04d}-{v[0] // 100 % 100:02d}-{v[0] % 100:02d}" for v in native]
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(raw, "tdx-public-day-v1", interpretation=dict(instrument=symbol, venue=symbol[-2:], asset_type="stock"))["snapshot_id"]
        q = store.query(sid)
        for radius in (2, 5, 10):
            report = pivot_report(q, q, radius)
            _check_raw_window(report, prices, labels, radius)
            if radius == 2:
                assert tuple(sum(e["kind"] == kind for e in report["events"]) for kind in ("high", "low")) == counts


def test_real_minute_original_decimal_token_oracle(tmp_path):
    folder = Path(__file__).resolve().parents[1] / "artifacts/qualification/minute-read/20261008T140439Z"
    if not folder.exists():
        pytest.skip("Private real sample unavailable; no compatibility claim")
    raw = (folder / "response.bin").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "826e7bcca37b7dde90a74f6348877044c77dbc1f678629b1a92c1793a6dba4a2"
    values = json.loads(raw)["result"]["Value"]["600059.SH"]
    prices = [tuple(Fraction(values[k][i]) for k in ("Open", "High", "Low", "Close")) for i in range(len(values["Date"]))]
    labels = [f"{d[:4]}-{d[4:6]}-{d[6:]}T{t.zfill(6)[:2]}:{t.zfill(6)[2:4]}" for d, t in zip(values["Date"], values["Time"])]
    bundle = dict(request_utf8=(folder / "request.json").read_text(), response_utf8=raw.decode())
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(json.dumps(bundle).encode(), "tdx-http-market-v1", interpretation=dict(instrument="600059.SH", venue="SH", asset_type="stock"))["snapshot_id"]
        q = store.query(sid)
        for radius in (2, 5, 10):
            _check_raw_window(pivot_report(q, q, radius), prices, labels, radius)


def test_http_identity_previous_context_and_horizon(tmp_path):
    root = tmp_path / "store"
    raw = b"".join(struct.pack("<IIIIIfII", 20260900 + i, 100, high * 100, 100, high * 100, 0, 0, 0)
                   for i, high in enumerate((3, 4, 6, 4, 3), 1))
    with EvidenceStore(root) as store:
        sid = store.import_bytes(raw, "tdx-public-day-v1")["snapshot_id"]
        q = store.query(sid, ordinal_start=3, ordinal_end=4)

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                url = "/api/source-pivots/" + sid
                parameters = dict(ordinal_start=3, ordinal_end=4, query_id=q["query_id"])
                response = await client.get(url, params=parameters)
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                assert response.json()["rows"][0]["reason"] == "pending_right_window"
                assert response.json()["events"] == []
                assert (await client.get(url, params={**parameters, "query_id": "old"})).status_code == 409
                for invalid in ("0", "21", "bad", "2.0"):
                    assert (await client.get(url, params={**parameters, "radius": invalid})).status_code == 400
                assert (await client.get("/api/query/" + sid, params=dict(ordinal_start=3, ordinal_end=4))).json()["query"] == q
    asyncio.run(scenario())
