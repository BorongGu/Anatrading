"""Daily context is a date-bounded source view, not a point-in-time signal."""
import asyncio
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import struct

import httpx
import pytest

from anatrading.store import EvidenceStore
from anatrading.workbench import _daily_background, _pair_claim, _RequestError, create_app
from test_formats import bao_payload


def raw(period, rows, code="600059"):
    if period == "1d":
        return bao_payload([[day.replace("/", "-"), f"sh.{code}", "10", "999", "1", close, "100", "1000", "3"]
                            for day, _, close in rows], code=f"sh.{code}")
    title = f"{code} 合成验收 1分钟线 不复权"
    header = "日期\t时间\t开盘\t最高\t最低\t收盘\t成交量\t成交额"
    lines = [title, header]
    for day, clock, close in rows:
        lines.append(",".join([day, clock, "10", "999", "1", close, "100", "1000"]))
    return ("\r\n".join([*lines, "数据来源:通达信"]) + "\r\n").encode("gbk")


def import_source(store, period, rows, code="600059"):
    result = store.import_bytes(raw(period, rows, code), "baostock-decoded-v0.9.4" if period == "1d" else "tdx-public-text-v1",
                                interpretation=dict(instrument=f"{code}.SH", venue="SH", asset_type="stock"))
    assert result["status"] == "committed"
    return result["snapshot_id"]


def samples(store):
    minute = import_source(store, "1m", [("2026/09/30", "0931", "10"), ("2026/09/30", "1500", "20")])
    daily = import_source(store, "1d", [("2026/09/28", "", "10"), ("2026/09/29", "", "11"),
                                         ("2026/09/30", "", "999")])
    return minute, daily


def test_daily_context_excludes_entire_current_date_even_at_1500(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        minute, daily = samples(store)
        for ordinal in (1, 2):
            result = _daily_background(store, minute, daily, ordinal)
            assert result["anchor"]["ordinal"] == ordinal
            assert result["daily"]["query"]["selection"]["cutoff"] == "2026-09-29"
            assert [r["label"] for r in result["daily"]["query"]["rows"]] == ["2026-09-28", "2026-09-29"]
            assert result["latest_source_date"] == "2026-09-29"
            assert result["calendar_gap_days"] == 1
            assert result["pairing_status"] == "assumed_text_match"
            assert result["qualification"] == "source_date_retrospective_only"
            assert all(r["values"]["close"] != "999" for r in result["daily"]["query"]["rows"])


def test_same_day_or_future_values_cannot_change_previous_background(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        minute, daily = samples(store)
        before = _daily_background(store, minute, daily, 1)
        revised = import_source(store, "1d", [("2026/09/28", "", "10"), ("2026/09/29", "", "11"),
                                               ("2026/09/30", "", "1"), ("2026/10/01", "", "999")])
        after = _daily_background(store, minute, revised, 1)
        assert after["daily"]["query"]["rows"] == before["daily"]["query"]["rows"]
        assert after["daily"]["geometry"]["rows"] == before["daily"]["geometry"]["rows"]
        assert after["background_id"] != before["background_id"]


def test_duplicate_dates_bad_prices_and_unlocated_are_not_replaced(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        minute, _ = samples(store)
        daily = import_source(store, "1d", [("2026/09/29", "", "11"), ("2026/09/29", "", "bad"),
                                            ("unreadable", "", "12")])
        result = _daily_background(store, minute, daily, 1)
        q = result["daily"]["query"]
        assert len(q["rows"]) == 2 and q["rows"][1]["values"]["close"] is None
        assert q["rows"][1]["tokens"]["close"] == "bad"
        assert len(q["unlocated"]) == 1
        assert result["latest_source_date"] == "2026-09-29"
        assert all(any(c["name"] == "duplicate_label" and c["outcome"] == "fail" for c in r["checks"]) for r in q["rows"])


def test_missing_days_stay_missing_and_gap_is_calendar_distance_only(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        minute, _ = samples(store)
        daily = import_source(store, "1d", [("2026/09/25", "", "10")])
        result = _daily_background(store, minute, daily, 1)
        assert result["latest_source_date"] == "2026-09-25" and result["calendar_gap_days"] == 5
        assert len(result["daily"]["query"]["rows"]) == 1
        empty = import_source(store, "1d", [("2026/10/01", "", "10")])
        result = _daily_background(store, minute, empty, 1)
        assert result["latest_source_date"] is None and result["calendar_gap_days"] is None
        assert result["daily"]["query"]["rows"] == []


@pytest.mark.parametrize("ordinal", [0, -1, 3, True])
def test_invalid_anchor(tmp_path, ordinal):
    with EvidenceStore(tmp_path / "store") as store:
        minute, daily = samples(store)
        with pytest.raises(_RequestError): _daily_background(store, minute, daily, ordinal)


def test_unlocated_anchor_other_security_and_wrong_period_rejected(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        minute, daily = samples(store)
        other = import_source(store, "1d", [("2026/09/29", "", "10")], code="000001")
        unlocated = import_source(store, "1m", [("2026/09/30", "2500", "10")])
        for minute_id, daily_id, reason in [(minute, other, "background_symbol_mismatch"),
                                            (daily, minute, "background_period_mismatch"),
                                            (unlocated, daily, "background_anchor_unlocated")]:
            with pytest.raises(_RequestError, match=reason): _daily_background(store, minute_id, daily_id, 1)


def test_pair_claim_normalizes_supported_text_only_without_mutation():
    meta = dict(source_code="sh.600059", source_venue="SH", interpretation=dict(instrument="600059.SH", venue="SH"))
    before = deepcopy(meta)
    assert _pair_claim(meta) == ("600059", "SH")
    assert meta == before
    meta["source_code"] = "600059.SZ"
    with pytest.raises(_RequestError, match="background_symbol_mismatch"): _pair_claim(meta)
    for value in ({}, dict(source_code="600059"), dict(source_code="alias.SH")):
        with pytest.raises(_RequestError, match="background_symbol_unavailable"): _pair_claim(value)


def test_window_keeps_all_boundary_duplicates_bad_fields_and_unlocated(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        minute, _ = samples(store)
        daily = import_source(store, "1d", [("2026/09/28", "", "10"), ("2026/09/29", "", "11"),
                                            ("unreadable", "", "12"), ("2026/09/29", "", "bad")])
        result = _daily_background(store, minute, daily, 1, 1)
        q = result["daily"]["query"]
        assert result["requested_rows"] == 1 and result["context_unlocated_rows"] == 1
        assert [r["ordinal"] for r in q["rows"]] == [2, 4]
        assert q["rows"][-1]["values"]["close"] is None
        assert [r["ordinal"] for r in q["unlocated"]] == [3]
        assert q == store.query(daily, cutoff="2026-09-29", ordinal_start=2, ordinal_end=4)


def test_source_order_gap_retains_extra_older_records_inside_actual_query(tmp_path):
    with EvidenceStore(tmp_path / "store") as store:
        minute, _ = samples(store)
        daily = import_source(store, "1d", [("2026/09/29", "", "11"), ("2026/09/28", "", "10"),
                                            ("2026/09/29", "", "12")])
        q = _daily_background(store, minute, daily, 1, 1)["daily"]["query"]
        assert [r["ordinal"] for r in q["rows"]] == [2, 1, 3]
        assert q == store.query(daily, cutoff="2026-09-29", ordinal_start=1, ordinal_end=3)


def test_background_api_matches_selected_source_ordinal(tmp_path):
    root = tmp_path / "store"
    with EvidenceStore(root) as store: minute, daily = samples(store)

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                path = "/api/daily-background/" + minute
                response = await client.get(path, params=dict(daily_snapshot=daily, ordinal=1))
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                result = response.json()
                assert result["anchor"]["snapshot_id"] == minute and result["anchor"]["label"] == "2026-09-30T09:31"
                assert result["daily"]["query"]["snapshot_id"] == daily
                assert result["daily"]["query"]["selection"]["cutoff"] == "2026-09-29"
                assert result["requested_rows"] == 60
                assert (await client.get(path, params=dict(daily_snapshot=daily, ordinal=1, window="all"))).json()["requested_rows"] is None
                for params in ({}, dict(daily_snapshot=daily, ordinal="bad"), dict(daily_snapshot=daily, ordinal=0),
                               dict(daily_snapshot=daily, ordinal=1, cutoff="2026-09-30"),
                               dict(daily_snapshot=daily, ordinal=1, window=0), dict(daily_snapshot=daily, ordinal=1, window="bad")):
                    assert (await client.get(path, params=params)).status_code == 400
    asyncio.run(scenario())


def test_private_real_pair_against_original_daily_integers(tmp_path):
    root = Path(__file__).resolve().parents[1]
    day_path = root / "data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78/after.day"
    minute_folder = root / "artifacts/qualification/minute-read/20261008T140439Z"
    if not day_path.exists() or not minute_folder.exists():
        pytest.skip("Private real samples unavailable; no network fallback")
    day_bytes = day_path.read_bytes()
    minute_bytes = (minute_folder / "response.bin").read_bytes()
    assert hashlib.sha256(day_bytes).hexdigest() == "f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30"
    assert hashlib.sha256(minute_bytes).hexdigest() == "826e7bcca37b7dde90a74f6348877044c77dbc1f678629b1a92c1793a6dba4a2"
    original = list(struct.iter_unpack("<IIIIIfII", day_bytes))
    bundle = dict(request_utf8=(minute_folder / "request.json").read_text(), response_utf8=minute_bytes.decode())
    declaration = dict(instrument="600059.SH", venue="SH", asset_type="stock")
    with EvidenceStore(tmp_path / "store") as store:
        daily = store.import_bytes(day_bytes, "tdx-public-day-v1", interpretation=declaration)["snapshot_id"]
        minute = store.import_bytes(json.dumps(bundle).encode(), "tdx-http-market-v1", interpretation=declaration)["snapshot_id"]
        for ordinal, target, expected_last in [(1, 20260928, "2026-09-24"), (241, 20260929, "2026-09-28"),
                                               (481, 20260930, "2026-09-29")]:
            result = _daily_background(store, minute, daily, ordinal, None)
            close_result = _daily_background(store, minute, daily, ordinal + 239, None)
            assert result["daily"]["query"] == close_result["daily"]["query"]
            assert result["latest_source_date"] == expected_last
            expected = [item for item in original if item[0] < target]
            selected = result["daily"]["query"]["rows"]
            assert len(selected) == len(expected) and result["daily"]["query"]["unlocated"] == []
            for source, item in zip(selected, expected):
                assert source["label"].replace("-", "") == str(item[0])
                for index, field in enumerate(("open", "high", "low", "close"), 1):
                    assert Fraction(source["values"][field]) == Fraction(item[index], 100)
                assert Fraction(source["values"]["amount"]) == Fraction.from_float(item[5])
                assert int(source["values"]["volume"]) == item[6]
                assert source["volume_shares"] is None and source["amount_cny"] is None
            window = _daily_background(store, minute, daily, ordinal)
            assert window["requested_rows"] == 60
            assert window["daily"]["query"]["rows"] == selected[-60:]
