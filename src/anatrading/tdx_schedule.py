"""Finite daily dispatches share the acquisition lock and the existing writer."""
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time
import uuid
import xml.etree.ElementTree as ET

from . import tdx_acquisition as acquisition
from .store import _DirectoryLock, _identity


_MARKER = b"anatrading-tdx-dispatch-v1\n"
_CALENDAR = [
    {"source_url": "https://www.sse.com.cn/disclosure/dealinstruc/closed/",
     "sha256": "7ea10c16202c4748f0ad5bcdfe6ee07b85b5462589504604b17c9d63865e7d8c"},
    {"source_url": "https://one.sse.com.cn/onething/gptz/",
     "sha256": "f5d95746ec6f8dc7d5c9f057b230ba56eae67dce05dbae06fe62a0bdad98f0db"},
]
_PLAN_FIELDS = {"schema", "root", "client_directory", "port", "symbol", "period", "exe_sha256",
                "sdk_sha256", "start_at", "end_at", "days", "calendar"}
_ASSOCIATION = {"run_id", "dispatch_id", "plan_hash", "slot_id", "root", "data_root_id", "port",
                "client_directory", "symbol", "target_date"}
_ACTIVE_STATES = {"reserved", "linked", "dispatch_unknown"}
_SHANGHAI = timezone(timedelta(hours=8))
AcquireError = acquisition.AcquireError


def _utc_now():
    return datetime.now(timezone.utc)


def _timestamp(value, offset):
    try:
        if type(value) is not str:
            raise ValueError
        parsed = datetime.fromisoformat(value)
        if parsed.utcoffset() != offset:
            raise ValueError
        return parsed
    except ValueError:
        raise AcquireError("invalid_schedule_plan") from None


def _hex(value, length):
    return type(value) is str and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def _absolute(value):
    return type(value) is str and Path(value).is_absolute() and str(Path(value).resolve()) == value


def _validate_plan(plan, now):
    if (type(plan) is not dict or set(plan) != _PLAN_FIELDS or type(plan["schema"]) is not int
            or plan["schema"] != 1 or not _absolute(plan["root"]) or not _absolute(plan["client_directory"])
            or type(plan["port"]) is not int or not 1 <= plan["port"] <= 65535 or plan["port"] == 17709
            or plan["symbol"] != "600059.SH" or plan["period"] != "1d"
            or plan["exe_sha256"] != acquisition._EXE_SHA or plan["sdk_sha256"] != acquisition._SDK_SHA
            or type(plan["days"]) is not list or not 1 <= len(plan["days"]) <= 7
            or type(plan["calendar"]) is not list or len(plan["calendar"]) != len(_CALENDAR)):
        raise AcquireError("invalid_schedule_plan")
    previous, open_days = None, 0
    for day in plan["days"]:
        if type(day) is not dict or set(day) != {"date", "kind", "due_at"} or type(day["date"]) is not str:
            raise AcquireError("invalid_schedule_plan")
        try:
            target = date.fromisoformat(day["date"])
        except ValueError:
            raise AcquireError("invalid_schedule_plan") from None
        if not date(2026, 10, 8) <= target <= date(2026, 10, 14):
            raise AcquireError("calendar_unknown")
        kind = "closed" if target in {date(2026, 10, 10), date(2026, 10, 11)} else "open"
        if (day["date"] != target.isoformat() or day["kind"] != kind
                or day["due_at"] != f"{target.isoformat()}T18:00:00+08:00"
                or previous is not None and target != previous + timedelta(days=1)):
            raise AcquireError("invalid_schedule_plan")
        previous = target
        open_days += kind == "open"
    if (open_days > 5 or plan["start_at"] != f'{plan["days"][0]["date"]}T00:00:00+08:00'
            or plan["end_at"] != f'{plan["days"][-1]["date"]}T23:59:59+08:00'):
        raise AcquireError("invalid_schedule_plan")
    for reference, expected in zip(plan["calendar"], _CALENDAR, strict=True):
        if (type(reference) is not dict or set(reference) != {"path", "source_url", "sha256", "captured_at_utc"}
                or not _absolute(reference["path"])
                or any(reference[key] != expected[key] for key in ("source_url", "sha256"))
                or _timestamp(reference["captured_at_utc"], timedelta(0)) > now
                or acquisition._file_hash(Path(reference["path"]), acquisition._MAX_BYTES) != reference["sha256"]):
            raise AcquireError("calendar_unknown")
    return plan


def _load_plan(path, now):
    path = Path(path)
    if not path.is_absolute():
        raise AcquireError("invalid_schedule_plan")
    with path.open("rb") as source:
        plan = acquisition._decode_json(source.read(acquisition._MAX_BYTES + 1))
    return _validate_plan(plan, now)


def _binding(plan, plan_hash, slot_id, run_id, dispatch_id):
    return dict(run_id=run_id, dispatch_id=dispatch_id, plan_hash=plan_hash, slot_id=slot_id,
                root=plan["root"], data_root_id=acquisition.data_root_id(plan["root"]), port=plan["port"],
                client_directory=plan["client_directory"], symbol=plan["symbol"], target_date=slot_id)


def _matches(record, binding):
    return (type(record) is dict and all(record.get(key) == binding[key] for key in _ASSOCIATION)
            and type(record.get("port")) is int
            and record.get("evidence_directory") == str(Path(binding["root"]) / "acquisition" / binding["run_id"]))


def _read_control(state, client_directory):
    """Parse all cross-entry control invariants before either recovery or dispatch."""
    marker, path = state / "dispatch.required", state / "dispatch.json"
    if not marker.exists() and not path.exists():
        return None
    try:
        with marker.open("rb") as source:
            if source.read(len(_MARKER) + 1) != _MARKER:
                raise ValueError
        with path.open("rb") as source:
            control = acquisition._decode_json(source.read(acquisition._MAX_BYTES + 1))
        if (type(control) is not dict
                or set(control) != {"schema", "plan_hash", "plan", "last_observed_utc", "slots", "active"}
                or type(control["schema"]) is not int or control["schema"] != 1):
            raise ValueError
        plan = _validate_plan(control["plan"], _utc_now())
        if (control["plan_hash"] != _identity(plan) or plan["client_directory"] != str(client_directory)
                or type(control["slots"]) is not dict
                or set(control["slots"]) != {day["date"] for day in plan["days"]}):
            raise ValueError
        _timestamp(control["last_observed_utc"], timedelta(0))
        live, runs, dispatches = [], set(), set()
        for day in plan["days"]:
            slot_id, slot = day["date"], control["slots"][day["date"]]
            if type(slot) is not dict or set(slot) != {"status", "run_id", "dispatch_id", "result"}:
                raise ValueError
            status = slot["status"]
            if type(status) is not str or status not in {"pending", "closed_no_target", *_ACTIVE_STATES, *acquisition._TERMINAL}:
                raise ValueError
            if (day["kind"] == "closed") != (status == "closed_no_target"):
                raise ValueError
            if status in {"pending", "closed_no_target"}:
                if any(slot[key] is not None for key in ("run_id", "dispatch_id", "result")):
                    raise ValueError
                continue
            if (not _hex(slot["run_id"], 32) or not _hex(slot["dispatch_id"], 32)
                    or slot["run_id"] in runs or slot["dispatch_id"] in dispatches):
                raise ValueError
            runs.add(slot["run_id"])
            dispatches.add(slot["dispatch_id"])
            binding = _binding(plan, control["plan_hash"], slot_id, slot["run_id"], slot["dispatch_id"])
            if status in _ACTIVE_STATES:
                if slot["result"] is not None:
                    raise ValueError
                live.append((slot_id, binding, status))
            else:
                record = slot["result"]
                if not _matches(record, binding) or record.get("status") != status:
                    raise ValueError
                acquisition._validate_journal(record, client_directory)
                if status == "committed" and (not _hex(record.get("raw_sha256"), 64)
                        or not _hex(record.get("snapshot_id"), 64) or not _hex(record.get("attempt_id"), 32)
                        or not _hex(record.get("workbench_session_id"), 64)):
                    raise ValueError
        active = control["active"]
        if active is None:
            if live:
                raise ValueError
        elif (type(active) is not dict or set(active) != _ASSOCIATION | {"owner_pid", "owner_started_filetime", "state"}
                or len(live) != 1 or active["state"] != live[0][2]
                or any(active[key] != live[0][1][key] for key in _ASSOCIATION)
                or type(active["port"]) is not int
                or type(active["owner_pid"]) is not int or active["owner_pid"] < 1
                or type(active["owner_started_filetime"]) is not int or active["owner_started_filetime"] < 1):
            raise ValueError
        return control
    except (AcquireError, OSError, ValueError, KeyError, TypeError):
        raise AcquireError("invalid_schedule_control") from None


def _save_control(state, control):
    raw = json.dumps(control, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    if len(raw) > acquisition._MAX_BYTES:
        raise AcquireError("schedule_control_limit")
    temporary = state / "dispatch.tmp"
    acquisition._write(temporary, raw)
    temporary.replace(state / "dispatch.json")


def _owner():
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE, *([ctypes.POINTER(wintypes.FILETIME)] * 4)]
    stamps = [wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(), *(ctypes.byref(stamp) for stamp in stamps)):
        raise AcquireError("schedule_owner_unavailable")
    return os.getpid(), stamps[0].dwHighDateTime << 32 | stamps[0].dwLowDateTime


def _host_clock(now):
    if os.name != "nt" or now.astimezone().utcoffset() != timedelta(hours=8):
        raise AcquireError("schedule_timezone_mismatch")
    command = "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();(Get-TimeZone).Id"
    try:
        result = subprocess.run([r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe", "-NoProfile",
                                 "-NonInteractive", "-Command", command], capture_output=True,
                                timeout=acquisition._remaining(8), creationflags=subprocess.CREATE_NO_WINDOW)
    except subprocess.TimeoutExpired:
        raise AcquireError("schedule_timezone_mismatch") from None
    if result.returncode or result.stdout.decode("utf-8-sig").strip() != "China Standard Time":
        raise AcquireError("schedule_timezone_mismatch")


def _observe(control, state, clock):
    now = clock()
    if not isinstance(now, datetime) or now.utcoffset() != timedelta(0):
        raise AcquireError("invalid_schedule_clock")
    if now < _timestamp(control["last_observed_utc"], timedelta(0)):
        raise AcquireError("clock_rollback")
    _host_clock(now)
    checked = clock()
    if not isinstance(checked, datetime) or checked.utcoffset() != timedelta(0):
        raise AcquireError("invalid_schedule_clock")
    if checked < now:
        raise AcquireError("clock_rollback")
    acquisition._remaining()
    control["last_observed_utc"] = checked.isoformat()
    _save_control(state, control)
    return checked


def _summary(control, now, status, error_code=None):
    counts = {key: sum(slot["status"] == key for slot in control["slots"].values())
              for key in ("committed", "failed", "not_covered", "pending", "closed_no_target", *_ACTIVE_STATES)}
    overdue = sum(control["slots"][day["date"]]["status"] == "pending"
                  and _timestamp(day["due_at"], timedelta(hours=8)) <= now for day in control["plan"]["days"])
    result = dict(status=status, plan_hash=control["plan_hash"], civil_days=len(control["slots"]),
                  trading_days=sum(day["kind"] == "open" for day in control["plan"]["days"]),
                  counts=counts, pending_overdue=overdue)
    if error_code is not None:
        result["error_code"] = error_code
    return result


def _close(control, state, record):
    active = control["active"]
    slot = control["slots"][active["slot_id"]]
    if not _matches(record, active):
        active["state"] = slot["status"] = "dispatch_unknown"
        _save_control(state, control)
        return "dispatch_unknown"
    if record["status"] in acquisition._TERMINAL:
        slot.update(status=record["status"], result=record)
        control["active"] = None
    _save_control(state, control)
    return record["status"]


def _recover_active(control, state, client):
    active = control["active"]
    try:
        record = acquisition._journal(state / "current.json", client)
        receipt_path = Path(record["evidence_directory"]) / "receipt.json"
        with receipt_path.open("rb") as source:
            receipt = acquisition._decode_json(source.read(acquisition._MAX_BYTES + 1))
        if not _matches(record, active) or receipt != record:
            raise AcquireError("schedule_dispatch_unresolved")
    except (AcquireError, OSError):
        return "dispatch_unknown"
    if record["status"] in {"publication_unknown", "committed"}:
        record = acquisition._recover_locked(record, state)
        if record is None:
            return "dispatch_unknown"
    if record["status"] not in acquisition._TERMINAL:
        return record["status"]
    return _close(control, state, record)


def due(plan_path, *, now=None):
    clock = _utc_now if now is None else lambda: now
    observed = clock()
    if not isinstance(observed, datetime) or observed.utcoffset() != timedelta(0):
        raise AcquireError("invalid_schedule_clock")
    deadline_token = acquisition._deadline.set(time.monotonic() + 150)
    try:
        plan = _load_plan(plan_path, observed)
        client = Path(plan["client_directory"])
        state = acquisition._state_directory(client)
        state.mkdir(parents=True, exist_ok=True)
        with _DirectoryLock(state):
            control = _read_control(state, client)
            if control is not None:
                if control["plan_hash"] != _identity(plan):
                    raise AcquireError("schedule_plan_mismatch")
                if control["active"] is not None:
                    observed = _observe(control, state, clock)
                    return _summary(control, observed, _recover_active(control, state, client))
            from .tdx_recovery import recovery_gate

            recovered = recovery_gate(state, client)
            if recovered is not None:
                return {**recovered, "plan_hash": _identity(plan)}
            if control is None:
                _host_clock(observed)
                control = dict(schema=1, plan=plan, plan_hash=_identity(plan), last_observed_utc=observed.isoformat(),
                               slots={day["date"]: dict(status="closed_no_target" if day["kind"] == "closed" else "pending",
                                                       run_id=None, dispatch_id=None, result=None) for day in plan["days"]},
                               active=None)
                acquisition._write(state / "dispatch.required", _MARKER)
                _save_control(state, control)
            if control["plan_hash"] != _identity(plan):
                raise AcquireError("schedule_plan_mismatch")
            observed = _observe(control, state, clock)
            if control["active"] is not None:
                return _summary(control, observed, _recover_active(control, state, client))
            current = state / "current.json"
            if current.exists():
                old = acquisition._journal(current, client)
                if old["status"] == "publication_unknown":
                    recovered = acquisition._recover_locked(old, state)
                    return _summary(control, observed, recovered["status"], recovered.get("error_code"))
                if old["status"] not in acquisition._TERMINAL:
                    return _summary(control, observed, "refresh_unknown", "client_task_unresolved")
            if not (_timestamp(plan["start_at"], timedelta(hours=8)) <= observed
                    <= _timestamp(plan["end_at"], timedelta(hours=8))):
                return _summary(control, observed, "idle")
            selected = next((day for day in plan["days"] if control["slots"][day["date"]]["status"] == "pending"
                             and _timestamp(day["due_at"], timedelta(hours=8)) <= observed), None)
            if selected is None:
                return _summary(control, observed, "idle")
            acquisition._parameters(plan["symbol"], selected["date"], plan["port"])
            pid, started = _owner()
            binding = _binding(plan, control["plan_hash"], selected["date"], uuid.uuid4().hex, uuid.uuid4().hex)
            control["active"] = dict(binding, owner_pid=pid, owner_started_filetime=started, state="reserved")
            slot = control["slots"][selected["date"]]
            slot.update(status="reserved", run_id=binding["run_id"], dispatch_id=binding["dispatch_id"])
            _save_control(state, control)

            def prepared(record):
                if not _matches(record, binding):
                    raise AcquireError("schedule_dispatch_unresolved")
                control["active"]["state"] = slot["status"] = "linked"
                _save_control(state, control)

            def before_post():
                latest = _observe(control, state, clock)
                if not (_timestamp(selected["due_at"], timedelta(hours=8)) <= latest
                        <= _timestamp(plan["end_at"], timedelta(hours=8))):
                    raise AcquireError("schedule_window_closed")

            guard_token = acquisition._post_guard.set(before_post)
            try:
                record = acquisition._collect_locked(Path(plan["root"]), client, plan["symbol"], selected["date"],
                                                     plan["port"], state, run_id=binding["run_id"],
                                                     association={key: binding[key] for key in ("dispatch_id", "plan_hash", "slot_id")},
                                                     on_prepared=prepared)
            finally:
                acquisition._post_guard.reset(guard_token)
            return _summary(control, observed, _close(control, state, record), record.get("error_code"))
    finally:
        acquisition._deadline.reset(deadline_token)


def task_xml(plan_path, python, working_directory, user_sid):
    """Generate an unregistered task; Hidden does not suppress console windows."""
    plan = _load_plan(plan_path, _utc_now())
    python, working_directory = Path(python), Path(working_directory)
    if (not python.is_absolute() or not working_directory.is_absolute() or type(user_sid) is not str
            or re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", user_sid) is None):
        raise AcquireError("invalid_schedule_task")
    namespace = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", namespace)
    task = ET.Element(f"{{{namespace}}}Task", version="1.2")
    def element(parent, name, text=None, **attributes):
        child = ET.SubElement(parent, f"{{{namespace}}}{name}", **attributes)
        child.text = text
        return child
    trigger = element(element(task, "Triggers"), "CalendarTrigger")
    element(trigger, "StartBoundary", plan["days"][0]["due_at"])
    element(trigger, "EndBoundary", plan["end_at"])
    element(trigger, "Enabled", "true")
    element(element(trigger, "ScheduleByDay"), "DaysInterval", "1")
    principal = element(element(task, "Principals"), "Principal", id="CurrentUser")
    element(principal, "UserId", user_sid)
    element(principal, "LogonType", "InteractiveToken")
    element(principal, "RunLevel", "LeastPrivilege")
    settings = element(task, "Settings")
    for name, value in (("MultipleInstancesPolicy", "IgnoreNew"), ("StartWhenAvailable", "true"),
                        ("Enabled", "true"), ("Hidden", "true"), ("ExecutionTimeLimit", "PT3M")):
        element(settings, name, value)
    action = element(element(task, "Actions", Context="CurrentUser"), "Exec")
    element(action, "Command", str(python))
    element(action, "Arguments", subprocess.list2cmdline(["-X", "utf8", "-m", "anatrading.cli", "acquire-tdx-due",
                                                         "--plan", str(Path(plan_path))]))
    element(action, "WorkingDirectory", str(working_directory))
    return ET.tostring(task, encoding="unicode", xml_declaration=False)
