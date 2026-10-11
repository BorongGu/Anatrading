"""Strict daily normalization preserves source slots, including explicit errors."""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal, localcontext

import pytest

from anatrading.research_series import daily_bars, daily_coverage


def source_row(i, close="10", **changes):
    row = dict(ordinal=i + 1, label=(date(2026, 1, 1) + timedelta(days=i)).isoformat(),
               tokens={}, values=dict(open=close, high=close, low=close, close=close))
    row.update(changes)
    return row


def source_query(prices, **changes):
    query = dict(snapshot_id="a" * 64, query_id="b" * 64, metadata=dict(period="1d"),
                 rows=[source_row(i, str(price)) for i, price in enumerate(prices)], unlocated=[])
    query.update(changes)
    return query


@pytest.mark.parametrize("field,value,reason", [
    ("open", None, "missing_ohlc"), ("high", "bad", "invalid_price"),
    ("low", "0", "invalid_price"), ("close", "-1", "invalid_price"),
    ("close", True, "invalid_price"), ("close", 10.0, "invalid_price"),
    ("close", "NaN", "invalid_price"), ("high", "Infinity", "invalid_price"),
    ("close", "1e999", "invalid_price"), ("low", "1e-999", "invalid_price"),
    ("open", "11", "invalid_ohlc"),
])
def test_invalid_ohlc_retains_date_slot(field, value, reason):
    query = source_query([10, 10, 10])
    query["rows"][1]["values"][field] = value
    before = deepcopy(query)
    bars = daily_bars(query)
    assert len(bars) == 3 and bars[1]["reason"] == reason
    assert bars[2]["ordinal"] == 3 and query == before


def test_duplicates_dated_unlocated_unknown_dates_and_coverage():
    query = source_query([10, 11, 12, 13])
    query["rows"].append(source_row(1, "99", ordinal=5))
    bad = query["rows"].pop(2)
    bad.update(label=None, tokens=dict(source_date="20260103"))
    query["unlocated"] = [bad, source_row(6, label=None, tokens={})]
    bars = daily_bars(query)
    assert [r["date"] for r in bars] == ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    assert bars[1]["reason"] == "duplicate_date" and bars[1]["ordinal"] is None
    assert bars[1]["close"] is None and bars[2]["reason"] == "unlocated_label"
    coverage = daily_coverage(query, bars)
    assert coverage == dict(source_rows=6, date_groups=4, valid_groups=2, invalid_groups=2,
                           duplicate_groups=1, unlocated_rows=2, unreadable_date_rows=1,
                           batch_unlocated_rows=2, coverage_known=False)


def test_source_order_is_irrelevant_and_no_calendar_is_inferred():
    query = source_query([10, 11])
    query["rows"][1]["label"] = "2026-02-28"
    query["rows"].reverse()
    for row in query["rows"]:
        row["values"].update(volume=None, amount="invalid")
    assert [b["reason"] for b in daily_bars(query)] == [None, None]
    assert [b["ordinal"] for b in daily_bars(query)] == [1, 2]


@pytest.mark.parametrize("period", [None, "", "1m", "5m", "1D"])
def test_only_explicit_daily_metadata_is_supported(period):
    with pytest.raises(ValueError, match="^unsupported_period$"):
        daily_bars(source_query([10], metadata=dict(period=period)))


def test_strict_labels_and_raw_tokens_never_repair_observation_qualification():
    query = source_query([10, 11, 12])
    query["rows"][0].update(label="20260101", tokens=dict(date="2026/01/01"))
    query["rows"][1]["label"] = "2026-01-02T00:00"
    query["rows"][2]["label"] = "2026-02-30"
    bars = daily_bars(query)
    assert len(bars) == 1 and bars[0]["reason"] == "unlocated_label"
    assert daily_coverage(query, bars)["unreadable_date_rows"] == 2


def test_explicit_cutoff_blocks_future_slots_but_keeps_unlocated_disclosure():
    query = source_query([10, 11, 12], selection=dict(cutoff="2026-01-02"))
    query["unlocated"] = [source_row(9, label=None, tokens=dict(date="20260110"))]
    assert len(daily_bars(query)) == 2
    assert daily_coverage(query)["unlocated_rows"] == 1
    assert daily_coverage(query)["coverage_known"] is False


def test_decimal_values_preserved_without_global_rounding():
    value = "99999999999999999999.999999999999999998"
    with localcontext() as context:
        context.prec = 3
        bars = daily_bars(source_query([value]))
    assert bars[0]["close"] == Decimal(value) and bars[0]["reason"] is None


def test_row_budget_and_invalid_cutoff_are_rejected():
    with pytest.raises(ValueError, match="research_row_limit"):
        daily_bars(source_query([10] * 20001))
    with pytest.raises(ValueError, match="invalid_cutoff"):
        daily_bars(source_query([10], selection=dict(cutoff="20260101")))


@pytest.mark.parametrize("selection", [dict(ordinal_start=1), dict(ordinal_end=5)])
def test_ordinal_crop_cannot_silently_restart_full_prefix(selection):
    with pytest.raises(ValueError, match="ordinal_window_not_supported"):
        daily_bars(source_query([10], selection=selection))


def test_batch_unknown_dates_and_dated_unlocated_duplicate_are_disclosed():
    query = source_query([10], counts=dict(batch_unlocated_rows=2))
    assert daily_coverage(query)["coverage_known"] is False
    query["unlocated"] = [source_row(0, label=None, tokens=dict(date="2026/01/01"))]
    assert daily_bars(query)[0]["reason"] == "duplicate_date"


@pytest.mark.parametrize("conflict,reason", [("code", "source_identity_conflict"),
                                               ("adjustflag", "source_adjustment_conflict")])
def test_real_decoded_query_conflicting_source_claim_stays_invalid_not_breakout(tmp_path, conflict, reason):
    """Constructed Bao bytes exercise the actual parser/storage check contract."""
    from anatrading.signal_research import signal_report
    from anatrading.store import EvidenceStore
    from test_formats import bao_payload
    rows = [[f"2021-02-{day:02d}", "sh.600001", str(price), str(price), str(price), str(price),
             "100", "1000", "3"]
            for day, price in zip((23, 24, 25, 26, 27, 28), (10, 11, 999, 12, 13, 14))]
    rows[2][1 if conflict == "code" else 8] = "sz.000001" if conflict == "code" else "2"
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(bao_payload(rows, code="sh.600001"), "baostock-decoded-v0.9.4")["snapshot_id"]
        query = store.query(sid)
        before = deepcopy(query)
        assert any(c["name"] == ("source_code" if conflict == "code" else "source_adjustflag")
                   and c["outcome"] == "fail" for c in query["rows"][2]["checks"])
        bars = daily_bars(query)
        assert len(bars) == 6 and bars[2]["date"] == "2021-02-25"
        assert bars[2]["reason"] == reason and bars[2]["close"] == Decimal(999)
        result = signal_report(query, lookback=2, horizon=1)
        assert result["series"][2]["close"] == "999"
        assert result["series"][2]["reason"] == reason
        assert result["series"][2]["breakout"] is None
        assert result["series"][3]["reset_reason"] == reason
        assert result["series"][3]["breakout_reason"] == "invalid_history_window"
        assert result["series"][4]["breakout_reason"] == "invalid_history_window"
        assert result["events"]["counts"]["raw_events"] == 1
        assert result["events"]["counts"]["valid"] == 0
        assert query == before and store.query(sid) == before


def test_real_decoded_unrelated_volume_amount_failure_does_not_block_price_research(tmp_path):
    from anatrading.signal_research import signal_report
    from anatrading.store import EvidenceStore
    from test_formats import bao_payload
    rows = [[f"2021-02-{day:02d}", "sh.600001", str(price), str(price), str(price), str(price),
             "bad", "bad", "3"] for day, price in ((24, 10), (25, 11), (26, 12), (27, 13))]
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(bao_payload(rows, code="sh.600001"), "baostock-decoded-v0.9.4")["snapshot_id"]
        query = store.query(sid)
        assert all(any(c["name"] == "numeric.volume" and c["outcome"] == "fail" for c in r["checks"])
                   for r in query["rows"])
        assert all(b["reason"] is None for b in daily_bars(query))
        result = signal_report(query, lookback=2, horizon=1)
        assert result["events"]["counts"]["valid"] == 1


@pytest.mark.parametrize("field,metadata_key,conflicting,reason", [
    ("code", "source_code", "sz.000001", "source_identity_conflict"),
    ("adjustflag", "source_adjustflag", "2", "source_adjustment_conflict"),
])
def test_explicit_conflicting_tokens_fail_closed_even_without_cached_check(field, metadata_key, conflicting, reason):
    query = source_query([10, 11, 12])
    query["metadata"].update(source_code="sh.600001", source_adjustflag="3")
    query["rows"][1]["tokens"][field] = conflicting
    assert daily_bars(query)[1]["reason"] == reason


def test_real_decoded_consistent_but_unsupported_adjustment_is_not_repaired(tmp_path):
    from anatrading.store import EvidenceStore
    from test_formats import bao_payload
    rows = [["2021-02-26", "sh.600001", "10", "10", "10", "10", "100", "1000", "1"]]
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(bao_payload(rows, code="sh.600001", adjustment="1"),
                                 "baostock-decoded-v0.9.4")["snapshot_id"]
        query = store.query(sid)
        assert query["metadata"]["source_adjustflag"] == "1"
        assert daily_bars(query)[0]["reason"] == "source_adjustment_check_failed"
        assert daily_bars(query)[0]["close"] == Decimal(10)


def test_actual_decoder_quarantine_and_persisted_failure_block_research(tmp_path, monkeypatch):
    import hashlib
    import anatrading.formats as formats
    from anatrading.signal_research import signal_report
    from anatrading.store import EvidenceStore
    from test_formats import bao_payload
    rows = [[f"2021-02-{day:02d}", "sh.600001", str(price), str(price), str(price), str(price),
             "100", "1000", "3"] for day, price in ((24, 10), (25, 11), (26, 12), (27, 13))]
    raw = bao_payload(rows, code="sh.600001")
    # Substitute only the registry hash to exercise actual decoding/persistence;
    # no private known-negative source is shipped with this constructed fixture.
    monkeypatch.setattr(formats, "_NEGATIVE_DAY", hashlib.sha256(raw).hexdigest())
    with EvidenceStore(tmp_path / "store") as store:
        sid = store.import_bytes(raw, "baostock-decoded-v0.9.4")["snapshot_id"]
        query = store.query(sid)
        assert query["metadata"]["quarantined"] is True
        assert any(c["name"] == "known_negative_sample" and c["outcome"] == "fail" for c in query["batch_checks"])
        result = signal_report(query, lookback=2, horizon=1)
        assert result["qualification"] == "source_rejected"
        assert result["events"]["counts"]["rule_computable"] == 0
        assert all(r["reason"] == "known_negative_source" and r["kalman_level"] is None for r in result["series"])
        assert [r["close"] for r in result["series"]] == ["10", "11", "12", "13"]
        query["metadata"]["quarantined"] = False
        assert all(b["reason"] == "known_negative_source" for b in daily_bars(query))
        assert signal_report(query)["qualification"] == "source_rejected"
