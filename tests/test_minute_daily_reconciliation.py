"""Independent source arithmetic and ambiguous-record boundaries."""
import asyncio
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import struct

import httpx
import pytest

from anatrading.minute_daily_reconciliation import reconciliation_report
from anatrading.store import EvidenceStore
from anatrading.workbench import create_app
from test_daily_background import samples


def row(ordinal, label, volume="10", amount="20", day=None):
    return dict(ordinal=ordinal, label=label, tokens=dict(source_date=day),
                values=dict(volume=volume, amount=amount))


def query(period, rows=(), unlocated=()):
    return dict(snapshot_id=period, query_id=period, metadata=dict(period=period),
                selection={}, rows=list(rows), unlocated=list(unlocated))


def test_partial_selection_and_explicit_amount_scale():
    minute = query("1m", [row(1, "2026-09-28T09:31", "10", "1.2345")])
    daily = query("1d", [row(2, "2026-09-28", "100", "12000")])
    before = deepcopy((minute, daily))
    result = reconciliation_report(minute, daily)
    day = result["days"][0]
    assert day["quantity"] == dict(selected_minute_sum="10", daily_source_value="100", difference="-90", minute_reason=None, daily_reason=None)
    assert day["amount"]["difference"] is None
    assert len(day["coverage"]["missing_clocks"]) == 239
    assert day["selected_count"] == 1 and day["minute_ordinals"] == [1]
    scaled = reconciliation_report(minute, daily, 10000)
    assert scaled["days"][0]["amount"]["difference"] == "345"
    assert scaled["reconciliation_id"] != result["reconciliation_id"]
    assert (minute, daily) == before


@pytest.mark.parametrize("bad", [None, "bad", "-1", "1.5"])
def test_field_validity_is_independent_and_zero_is_valid(bad):
    minute = query("1m", [row(1, "2026-09-28T09:31", "0", "0"), row(2, "2026-09-28T09:32", bad, "0")])
    daily = query("1d", [row(3, "2026-09-28", "0", "0")])
    day = reconciliation_report(minute, daily, 1)["days"][0]
    assert day["quantity"]["selected_minute_sum"] is None
    assert day["amount"]["selected_minute_sum"] == "0" and day["amount"]["difference"] == "0"
    minute["rows"][1]["values"]["volume"] = "0"
    assert reconciliation_report(minute, daily)["days"][0]["quantity"]["difference"] == "0"


@pytest.mark.parametrize("kind", ["duplicate", "unlocated_clock", "unreadable_date"])
def test_ambiguous_minute_membership_blocks_both_sums(kind):
    minute = query("1m", [row(1, "2026-09-28T09:31")])
    if kind == "duplicate":
        minute["rows"].append(row(2, "2026-09-28T09:31"))
    else:
        minute["unlocated"].append(row(2, None, day="2026/09/28" if kind == "unlocated_clock" else "bad"))
    day = reconciliation_report(minute, query("1d", [row(1, "2026-09-28")]))["days"][0]
    assert day["quantity"]["selected_minute_sum"] is None
    assert day["amount"]["selected_minute_sum"] is None
    assert day["quantity"]["minute_reason"] in {"duplicate_clock", "unlocated_clock", "date_membership_unknown"}


def test_daily_missing_duplicate_and_unreadable_date_are_not_replaced():
    minute = query("1m", [row(1, "2026-09-28T09:31")])
    for daily, reason in [(query("1d"), "missing_date"),
                          (query("1d", [row(1, "2026-09-28"), row(2, "2026-09-28")]), "duplicate_date"),
                          (query("1d", [row(1, "2026-09-28")], [row(2, None, day="bad")]), "date_membership_unknown")]:
        value = reconciliation_report(minute, daily)["days"][0]["quantity"]
        assert value["daily_source_value"] is None and value["daily_reason"] == reason
        assert value["selected_minute_sum"] == "10" and value["difference"] is None


def test_extra_clock_is_in_sum_and_wide_summaries_remain_exact():
    minute = query("1m", [row(1, "2026-09-28T09:30", "9223372036854775807", "99999999999999999999.999999999999999999"),
                          row(2, "2026-09-28T09:31", "1", "0.000000000000000001")])
    day = reconciliation_report(minute, query("1d", [row(1, "2026-09-28", "0", "0")]), 10000)["days"][0]
    assert day["quantity"]["difference"] == "9223372036854775808"
    assert day["amount"]["selected_minute_sum"] == "100000000000000000000"
    assert day["amount"]["difference"] == "1000000000000000000000000"
    assert day["coverage"]["extra_clocks"] == ["09:30"]


def test_appending_later_dated_records_does_not_change_an_earlier_day():
    minute = query("1m", [row(1, "2026-09-28T09:31")])
    daily = query("1d", [row(1, "2026-09-28")])
    before = reconciliation_report(minute, daily, 1)["days"][0]
    minute["rows"].append(row(2, "2026-09-29T09:31", "999", "999"))
    daily["rows"].append(row(2, "2026-09-29", "999", "999"))
    assert reconciliation_report(minute, daily, 1)["days"][0] == before


@pytest.mark.parametrize("scale", [0, 100, True, "10000"])
def test_invalid_multiplier(scale):
    with pytest.raises(ValueError, match="invalid_amount_multiplier"):
        reconciliation_report(query("1m"), query("1d"), scale)


def test_api_selection_identity_pairing_and_validation(tmp_path):
    root = tmp_path / "store"
    with EvidenceStore(root) as store:
        minute, daily = samples(store)
        expected = store.query(minute, ordinal_end=1)

    async def scenario():
        app = create_app(root)
        async with app.router.lifespan_context(app):
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://127.0.0.1:8765") as client:
                path = "/api/minute-daily-reconciliation/" + minute
                params = dict(daily_snapshot=daily, ordinal_end=1, query_id=expected["query_id"])
                response = await client.get(path, params=params)
                assert response.status_code == 200
                result = response.json()
                assert result["minute_query_id"] == expected["query_id"]
                assert result["days"][0]["selected_count"] == 1
                assert result["days"][0]["daily_ordinals"] == [3]
                assert result["pairing_status"] == "assumed_text_match"
                assert (await client.get(path, params={**params, "query_id": "bad"})).status_code == 409
                assert (await client.get(path, params={**params, "amount_multiplier": "100"})).status_code == 400
                assert (await client.get(path, params={**params, "daily_snapshot": minute})).status_code == 409
    asyncio.run(scenario())


def test_private_real_pair_against_raw_independent_oracle(tmp_path):
    root = Path(__file__).resolve().parents[1]
    day_path = root / "data/local/acquisition/ad38b26212eb4e7ba6f58a57dc9e2c78/after.day"
    folder = root / "artifacts/qualification/minute-read/20261008T140439Z"
    if not day_path.exists() or not folder.exists():
        pytest.skip("Private real samples unavailable; no network fallback")
    day_raw, minute_raw = day_path.read_bytes(), (folder / "response.bin").read_bytes()
    assert hashlib.sha256(day_raw).hexdigest() == "f9271218e4ae49729d4b38976552432da7bf529aa677a2c89358fa5df6887f30"
    assert hashlib.sha256(minute_raw).hexdigest() == "826e7bcca37b7dde90a74f6348877044c77dbc1f678629b1a92c1793a6dba4a2"
    values = json.loads(minute_raw)["result"]["Value"]["600059.SH"]
    native = {str(bar[0]): bar for bar in struct.iter_unpack("<IIIIIfII", day_raw)}
    bundle = dict(request_utf8=(folder / "request.json").read_text(), response_utf8=minute_raw.decode())
    declaration = dict(instrument="600059.SH", venue="SH", asset_type="stock")
    with EvidenceStore(tmp_path / "store") as store:
        daily = store.import_bytes(day_raw, "tdx-public-day-v1", interpretation=declaration)["snapshot_id"]
        minute = store.import_bytes(json.dumps(bundle).encode(), "tdx-http-market-v1", interpretation=declaration)["snapshot_id"]
        report = reconciliation_report(store.query(minute), store.query(daily), 10000)
    for day in report["days"]:
        token = day["source_date"].replace("-", "")
        indices = [i for i, d in enumerate(values["Date"]) if d == token]
        quantity = sum(int(Decimal(values["Volume"][i])) for i in indices)
        # Fraction bypasses the implementation's Decimal aggregation.
        from fractions import Fraction
        amount_difference = sum(Fraction(values["Amount"][i]) for i in indices) * 10000 - Fraction(native[token][5])
        assert day["quantity"]["difference"] == str(quantity - native[token][6])
        assert Fraction(day["amount"]["difference"]) == amount_difference
        assert day["coverage"]["missing_clocks"] == [] and day["selected_count"] == 240
    assert [d["quantity"]["difference"] for d in report["days"]] == ["33", "20", "19"]
    assert [d["amount"]["difference"] for d in report["days"]] == ["-168", "60", "416"]
