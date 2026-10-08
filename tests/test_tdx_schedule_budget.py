"""A schedule deadline prevents new external actions, including after its guard."""
import time

import pytest

from anatrading import tdx_acquisition as acquisition


def test_expired_business_deadline_never_reaches_transport(monkeypatch):
    calls = []
    monkeypatch.setattr(acquisition, "_http", lambda *args, **kwargs: calls.append(args))
    token = acquisition._deadline.set(time.monotonic() - 1)
    try:
        with pytest.raises(acquisition.AcquireError, match="acquisition_deadline"):
            acquisition._request(17709, "POST", "/", b"synthetic")
        assert calls == []
    finally:
        acquisition._deadline.reset(token)


def test_deadline_expiring_during_civil_clock_check_prevents_post(monkeypatch):
    calls = []
    monkeypatch.setattr(acquisition, "_http", lambda *args, **kwargs: calls.append(args))
    clock = [100.0]
    monkeypatch.setattr(acquisition.time, "monotonic", lambda: clock[0])
    def slow_guard():
        clock[0] = 103.0
    token = acquisition._deadline.set(102.0)
    guard = acquisition._post_guard.set(slow_guard)
    try:
        with pytest.raises(acquisition.AcquireError, match="acquisition_deadline"):
            acquisition._request(8765, "POST", "/api/import", b"synthetic")
        assert calls == []
    finally:
        acquisition._post_guard.reset(guard)
        acquisition._deadline.reset(token)


def test_total_remaining_budget_caps_each_transport_request(monkeypatch):
    budgets = []
    def transport(*args, budget, **kwargs):
        budgets.append(budget)
        return 200, b"{}"
    monkeypatch.setattr(acquisition, "_http", transport)
    token = acquisition._deadline.set(time.monotonic() + 2)
    try:
        acquisition._request(17709, "POST", "/", budget=45)
        acquisition._request(8765, "GET", "/api/config", budget=15)
        assert len(budgets) == 2 and 0 < budgets[1] <= budgets[0] <= 2
    finally:
        acquisition._deadline.reset(token)


def test_native_connection_rechecks_guard_before_sending_request(monkeypatch):
    calls = []
    class Connection:
        sock = None
        def __init__(self, *args, **kwargs):
            self.sock = self
        def connect(self):
            calls.append("connect")
        def shutdown(self, *args):
            pass
        def settimeout(self, *args):
            pass
        def request(self, *args, **kwargs):
            calls.append("post")
        def close(self):
            calls.append("close")
    def expired_after_connect():
        raise acquisition.AcquireError("schedule_window_closed")
    monkeypatch.setattr(acquisition.http.client, "HTTPConnection", Connection)
    token = acquisition._post_guard.set(expired_after_connect)
    try:
        with pytest.raises(acquisition.AcquireError, match="schedule_window_closed"):
            acquisition._http(17709, "POST", "/", b"synthetic")
        assert calls == ["connect", "close"]
    finally:
        acquisition._post_guard.reset(token)
