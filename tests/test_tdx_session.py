"""Native session evidence rejects uncertainty and retains every 100ns digit."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timedelta, timezone
import importlib
import os

import pytest

from anatrading.tdx_acquisition import AcquireError


@pytest.fixture
def module():
    return importlib.import_module("anatrading.tdx_session")


@pytest.mark.parametrize("started", [
    None, 123, True, "", "2026-10-08T03:19:49", "2026-10-08 03:19:49Z",
    "2026-10-08T03:19:49.12345678Z", "2026-10-08T03:19:49.Z",
    "2026-02-30T03:19:49Z", "2026-10-08T24:00:00Z",
    "2026-10-08T03:19:60Z", "2026-10-08T03:19:49+24:00",
    "2026-10-08T03:19:49+01:60", "2026-10-08T03:19:49+0100",
    "2026-10-08T03:19:49+1:00", "2026-10-08T03:19:49+00:00:01",
    "2026-10-08T03:19:49Z\n", "1601-01-01T00:00:00Z",
    "1600-12-31T23:59:59.9999999Z", "1601-01-01T00:00:00+01:00",
    "0001-01-01T00:00:00+23:59", "9999-12-31T23:59:59-23:59",
])
def test_invalid_creation_time_rejected(module, started):
    with pytest.raises(AcquireError) as caught:
        module.creation_filetime(started)
    assert caught.value.code == "prior_process_unverified"


def test_exact_creation_time_and_offsets(module):
    assert module.creation_filetime("1601-01-01T00:00:00.0000001Z") == 1
    assert module.creation_filetime("1601-01-02T00:00:00Z") == 864000000000
    assert module.creation_filetime("1970-01-01T00:00:00Z") == 116444736000000000
    tick = module.creation_filetime("2026-10-08T03:19:49.7815869Z")
    assert tick == 134359031897815869
    assert module.creation_filetime("2026-10-08T11:19:49.7815869+08:00") == tick
    assert module.creation_filetime("2026-10-07T22:19:49.7815869-05:00") == tick
    assert module.creation_filetime("2026-10-08T03:19:49.7815870Z") == tick + 1
    assert module.creation_filetime("1601-01-01T00:00:00.1Z") == 1000000


class Kernel:
    def __init__(self, *, open_error=0, tick=134359031897815869, wait=258,
                 pids=(4, 20), snapshot=202, first_error=18, next_error=18,
                 times_ok=True, close_ok=True):
        self.error = open_error
        self.open_error, self.tick, self.wait = open_error, tick, wait
        self.pids, self.snapshot = pids, snapshot
        self.first_error, self.next_error = first_error, next_error
        self.times_ok, self.close_ok = times_ok, close_ok
        self.calls, self.closed = [], []
        self.index = 0

    def OpenProcess(self, rights, inherit, pid):
        self.calls.append(("open", rights, inherit, pid))
        self.error = self.open_error
        return 0 if self.open_error else 101

    def GetProcessTimes(self, handle, created, exited, kernel, user):
        self.calls.append(("times", handle))
        created._obj.dwLowDateTime = self.tick & 0xFFFFFFFF
        created._obj.dwHighDateTime = self.tick >> 32
        return self.times_ok

    def WaitForSingleObject(self, handle, timeout):
        self.calls.append(("wait", handle, timeout))
        return self.wait

    def CreateToolhelp32Snapshot(self, flags, pid):
        self.calls.append(("snapshot", flags, pid))
        return self.snapshot

    def Process32FirstW(self, handle, entry):
        self.calls.append(("first", handle, entry._obj.dwSize))
        self.index = 0
        if not self.pids:
            self.error = self.first_error
            return False
        entry._obj.th32ProcessID = self.pids[0]
        return True

    def Process32NextW(self, handle, entry):
        self.calls.append(("next", handle))
        self.index += 1
        if self.index >= len(self.pids):
            self.error = self.next_error
            return False
        entry._obj.th32ProcessID = self.pids[self.index]
        return True

    def CloseHandle(self, handle):
        self.closed.append(handle)
        return self.close_ok


def inject(module, monkeypatch, kernel):
    monkeypatch.setattr(module, "_kernel", lambda: kernel)
    monkeypatch.setattr(module.ctypes, "get_last_error", lambda: kernel.error, raising=False)


@pytest.mark.parametrize("pid", [True, False, 0, -1, 2**32, 1.0, "42", None])
def test_invalid_pid_never_reaches_native(module, monkeypatch, pid):
    kernel = Kernel()
    inject(module, monkeypatch, kernel)
    with pytest.raises(AcquireError):
        module.process_observation(pid)
    assert not kernel.calls and not kernel.closed


@pytest.mark.parametrize("error", [5, 6, 123])
def test_open_errors_do_not_infer_missing(module, monkeypatch, error):
    kernel = Kernel(open_error=error)
    inject(module, monkeypatch, kernel)
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "prior_process_unverified"
    assert [c[0] for c in kernel.calls] == ["open"]
    assert not kernel.closed


def test_null_handle_without_error_rejected(module, monkeypatch):
    kernel = Kernel()
    kernel.OpenProcess = lambda *args: 0
    inject(module, monkeypatch, kernel)
    with pytest.raises(AcquireError):
        module.process_observation(42)
    assert not kernel.closed


@pytest.mark.parametrize("wait,state", [(258, "alive"), (0, "ended")])
def test_process_creation_bound_to_handle_with_zero_wait(module, monkeypatch, wait, state):
    kernel = Kernel(wait=wait)
    inject(module, monkeypatch, kernel)
    assert module.process_observation(42) == {
        "state": state, "creation_filetime": kernel.tick,
        "census_count": None, "census_complete": None, "open_error": None,
    }
    assert kernel.calls[0] == ("open", 0x00101000, False, 42)
    assert kernel.calls[-1] == ("wait", 101, 0)
    assert kernel.closed == [101]


def test_maximum_dword_pid_retained_without_truncation(module, monkeypatch):
    kernel = Kernel()
    inject(module, monkeypatch, kernel)
    assert module.process_observation(0xFFFFFFFF)["state"] == "alive"
    assert kernel.calls[0] == ("open", 0x00101000, False, 0xFFFFFFFF)
    assert kernel.closed == [101]


@pytest.mark.parametrize("kwargs", [
    {"times_ok": False}, {"tick": 0}, {"wait": 0xFFFFFFFF}, {"wait": 128},
    {"close_ok": False},
])
def test_process_failures_always_close(module, monkeypatch, kwargs):
    kernel = Kernel(**kwargs)
    inject(module, monkeypatch, kernel)
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "prior_process_unverified"
    assert kernel.closed == [101]


def test_error87_requires_complete_nonempty_census(module, monkeypatch):
    kernel = Kernel(open_error=87)
    inject(module, monkeypatch, kernel)
    assert module.process_observation(42) == {
        "state": "missing", "creation_filetime": None,
        "census_count": 2, "census_complete": True, "open_error": 87,
    }
    assert kernel.calls[1] == ("snapshot", 2, 0)
    assert kernel.calls[2] == ("first", 202, 568)
    assert kernel.closed == [202]


@pytest.mark.parametrize("kwargs,closed", [
    ({"snapshot": ctypes.c_void_p(-1).value}, []),
    ({"pids": ()}, [202]), ({"pids": (), "first_error": 5}, [202]),
    ({"pids": (4, 42, 20)}, [202]), ({"next_error": 5}, [202]),
    ({"next_error": 0}, [202]), ({"pids": tuple(range(100, 16485))}, [202]),
    ({"close_ok": False}, [202]),
])
def test_incomplete_or_uncertain_census_rejected(module, monkeypatch, kwargs, closed):
    kernel = Kernel(open_error=87, **kwargs)
    inject(module, monkeypatch, kernel)
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "prior_process_unverified"
    assert kernel.closed == closed


def test_census_exact_limit_allowed(module, monkeypatch):
    kernel = Kernel(open_error=87, pids=tuple(range(100, 16484)))
    inject(module, monkeypatch, kernel)
    assert module.process_observation(42)["census_count"] == 16384
    assert kernel.closed == [202]


@pytest.mark.parametrize("stage", ["open", "times", "wait", "snapshot", "first", "next"])
def test_budget_checked_after_native_calls_and_handles_closed(module, monkeypatch, stage):
    kernel = Kernel(open_error=87 if stage in {"snapshot", "first", "next"} else 0)
    inject(module, monkeypatch, kernel)
    def remaining(*args):
        if kernel.calls and kernel.calls[-1][0] == stage:
            raise AcquireError("acquisition_deadline")
    monkeypatch.setattr(module, "_remaining", remaining)
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "acquisition_deadline"
    assert kernel.closed == ([202] if stage in {"snapshot", "first", "next"} else [101])
    assert kernel.calls[-1][0] == stage


def test_expired_budget_has_no_native_calls(module, monkeypatch):
    kernel = Kernel()
    inject(module, monkeypatch, kernel)
    def expired():
        raise AcquireError("acquisition_deadline")
    monkeypatch.setattr(module, "_remaining", expired)
    with pytest.raises(AcquireError):
        module.process_observation(42)
    assert not kernel.calls and not kernel.closed


@pytest.mark.parametrize("wrong_type,wrong_size", [(ctypes.c_void_p, 4), ("entry", 564)])
def test_incompatible_native_layout_rejected_before_open(module, monkeypatch, wrong_type, wrong_size):
    kernel = Kernel()
    inject(module, monkeypatch, kernel)
    original = ctypes.sizeof
    target = module._PROCESSENTRY32W if wrong_type == "entry" else wrong_type
    monkeypatch.setattr(module.ctypes, "sizeof", lambda value: wrong_size if value is target else original(value))
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "prior_process_unverified"
    assert not kernel.calls and not kernel.closed


def test_census_exception_still_closes_snapshot(module, monkeypatch):
    kernel = Kernel(open_error=87)
    inject(module, monkeypatch, kernel)
    def failed(*args):
        raise OSError("native call failure")
    kernel.Process32NextW = failed
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "prior_process_unverified"
    assert kernel.closed == [202]


def test_process_exception_still_closes_handle(module, monkeypatch):
    kernel = Kernel()
    inject(module, monkeypatch, kernel)
    def failed(*args):
        raise OSError("native call failure")
    kernel.WaitForSingleObject = failed
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "prior_process_unverified"
    assert kernel.closed == [101]


def test_close_exception_is_typed(module, monkeypatch):
    kernel = Kernel()
    inject(module, monkeypatch, kernel)
    def failed(handle):
        kernel.closed.append(handle)
        raise OSError("native close failure")
    kernel.CloseHandle = failed
    with pytest.raises(AcquireError) as caught:
        module.process_observation(42)
    assert caught.value.code == "prior_process_unverified"
    assert kernel.closed == [101]


@pytest.mark.skipif(os.name != "nt", reason="Windows native current-process evidence")
def test_native_current_process_readonly_creation_and_state(module):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    kernel.GetProcessTimes.restype = wintypes.BOOL
    stamps = [wintypes.FILETIME() for _ in range(4)]
    assert kernel.GetProcessTimes(kernel.GetCurrentProcess(), *(ctypes.byref(s) for s in stamps))
    tick = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
    whole, remainder = divmod(tick, 10000000)
    date = datetime(1601, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=whole)
    started = f"{date:%Y-%m-%dT%H:%M:%S}.{remainder:07d}Z"
    assert module.creation_filetime(started) == tick
    assert module.process_observation(os.getpid()) == {
        "state": "alive", "creation_filetime": tick,
        "census_count": None, "census_complete": None, "open_error": None,
    }
