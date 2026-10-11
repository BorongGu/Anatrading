"""Synthetic evidence contract consumed by the raw-record inspection UI."""
from copy import deepcopy
import math

import pytest

from anatrading.signal_research import signal_report
from test_research_series import source_query, source_row


def test_adjacent_endpoints_exact_and_gapped_interval_not_calendar_normalized():
    query = source_query(["10.000000000000000001", "20.000000000000000002"])
    query["rows"][0].update(label="2026-01-09", ordinal=7)
    query["rows"][1].update(label="2026-01-12", ordinal=82)
    a, b = signal_report(query)["series"]
    assert (a["date"], a["ordinal"], a["close"]) == ("2026-01-09", 7, "10.000000000000000001")
    assert (b["date"], b["ordinal"], b["close"]) == ("2026-01-12", 82, "20.000000000000000002")
    assert b["log_return"] == pytest.approx(math.log(2))
    assert a["log_return"] is None
    before = deepcopy(signal_report(query)["series"])
    query["rows"].append(source_row(20, "99"))
    assert signal_report(query)["series"][:2] == before


def test_invalid_and_duplicate_groups_block_adjacent_return_without_skipping():
    for duplicate in [False, True]:
        query = source_query([10, 20, 30, 30])
        if duplicate:
            query["rows"].append(source_row(1, "99", ordinal=9))
            reason = "duplicate_date"
        else:
            query["rows"][1]["values"]["high"] = None
            reason = "missing_ohlc"
        rows = signal_report(query)["series"]
        assert rows[1]["reason"] == reason and rows[1]["log_return"] is None
        assert rows[2]["reset_reason"] == reason and rows[2]["log_return"] is None
        assert rows[3]["log_return"] == 0
