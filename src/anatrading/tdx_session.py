"""Read-only Windows session evidence, with exact FILETIME conversion."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import os
import re

from .tdx_acquisition import AcquireError, _remaining


_STARTED = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9])"
    r"(?:\.([0-9]{1,7}))?(Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])"
)


class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260),
    ]


def creation_filetime(started):
    match = _STARTED.fullmatch(started) if isinstance(started, str) else None
    if match is None:
        raise AcquireError("prior_process_unverified")
    whole, fraction, offset = match.groups()
    try:
        instant = datetime.fromisoformat(whole + offset).astimezone(timezone.utc)
        delta = instant - datetime(1601, 1, 1, tzinfo=timezone.utc)
        tick = (delta.days * 86400 + delta.seconds) * 10000000
        tick += int((fraction or "").ljust(7, "0"))
    except (ValueError, OverflowError):
        raise AcquireError("prior_process_unverified") from None
    if not 0 < tick <= 0xFFFFFFFFFFFFFFFF:
        raise AcquireError("prior_process_unverified")
    return tick


def _kernel():
    if os.name != "nt":
        raise AcquireError("windows_required")
    try:
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
        kernel.GetProcessTimes.restype = wintypes.BOOL
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
        kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
        for name in ("Process32FirstW", "Process32NextW"):
            function = getattr(kernel, name)
            function.argtypes = [wintypes.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
            function.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        return kernel
    except (OSError, AttributeError):
        raise AcquireError("prior_process_unverified") from None


def _close(kernel, handle):
    # Releasing an acquired handle is mandatory even after the query budget expires.
    if not kernel.CloseHandle(handle):
        raise AcquireError("prior_process_unverified")
    _remaining()


def _missing(kernel, pid):
    _remaining()
    snapshot = kernel.CreateToolhelp32Snapshot(2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        _remaining()
        raise AcquireError("prior_process_unverified")
    try:
        _remaining()
        entry = _PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        count = 0
        function = kernel.Process32FirstW
        while True:
            _remaining()
            found = function(snapshot, ctypes.byref(entry))
            error = ctypes.get_last_error()
            _remaining()
            if not found:
                if error != 18 or count == 0:
                    raise AcquireError("prior_process_unverified")
                return {"state": "missing", "creation_filetime": None,
                        "census_count": count, "census_complete": True, "open_error": 87}
            count += 1
            if count > 16384 or entry.th32ProcessID == pid:
                raise AcquireError("prior_process_unverified")
            function = kernel.Process32NextW
    finally:
        _close(kernel, snapshot)


def process_observation(pid):
    if isinstance(pid, bool) or not isinstance(pid, int) or not 0 < pid <= 0xFFFFFFFF:
        raise AcquireError("prior_process_unverified")
    _remaining()
    if ctypes.sizeof(ctypes.c_void_p) != 8 or ctypes.sizeof(_PROCESSENTRY32W) != 568:
        raise AcquireError("prior_process_unverified")
    try:
        kernel = _kernel()
        _remaining()
        handle = kernel.OpenProcess(0x00101000, False, pid)
        error = ctypes.get_last_error()
        if not handle:
            _remaining()
            if error != 87:
                raise AcquireError("prior_process_unverified")
            return _missing(kernel, pid)
        try:
            _remaining()
            stamps = [wintypes.FILETIME() for _ in range(4)]
            _remaining()
            valid = kernel.GetProcessTimes(handle, *(ctypes.byref(stamp) for stamp in stamps))
            _remaining()
            tick = (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime
            if not valid or not 0 < tick <= 0xFFFFFFFFFFFFFFFF:
                raise AcquireError("prior_process_unverified")
            _remaining()
            wait = kernel.WaitForSingleObject(handle, 0)
            _remaining()
            if wait not in (0, 258):
                raise AcquireError("prior_process_unverified")
            return {"state": "ended" if wait == 0 else "alive", "creation_filetime": tick,
                    "census_count": None, "census_complete": None, "open_error": None}
        finally:
            _close(kernel, handle)
    except (OSError, ctypes.ArgumentError):
        raise AcquireError("prior_process_unverified") from None
