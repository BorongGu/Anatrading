"""Seal an unlinked unknown refresh only after its original session has ended."""
import base64
import hashlib
import json
import os
from pathlib import Path
import time
from datetime import datetime, timezone

from . import tdx_acquisition as acquisition
from . import tdx_session as session
from .store import _DirectoryLock


_JOURNAL_LIMIT = 65536
_CHECKPOINT_LIMIT = 262144
_CHECKPOINT_KEYS = {"schema", "client_directory", "state_directory", "run_id", "root", "evidence_directory",
                    "old_bytes_base64", "old_sha256", "new_sha256", "observations"}
_IDENTITY_KEYS = {"path", "pid", "started", "exe_sha256", "sdk_sha256"}
_PROCESS_KEYS = {"state", "creation_filetime", "census_count", "census_complete", "open_error"}


def _reject():
    raise acquisition.AcquireError("invalid_acquisition_recovery")


def _path(path, directory):
    if path.resolve() != directory / path.name:
        _reject()
    return path


def _read(path, directory, limit):
    acquisition._remaining()
    _path(path, directory)
    acquisition._remaining()
    with path.open("rb") as source:
        acquisition._remaining()
        raw = source.read(limit + 1)
    acquisition._remaining()
    if len(raw) > limit:
        _reject()
    return raw


def _plain(value):
    if type(value) in (str, int, bool, type(None)):
        return True
    if type(value) is list:
        return all(_plain(item) for item in value)
    if type(value) is dict:
        return all(_plain(item) for item in value.values())
    return False


def _decode(raw):
    if raw.startswith(b"\xef\xbb\xbf"):
        _reject()
    try:
        value = acquisition._decode_json(raw)
        if type(value) is not dict or not _plain(value):
            _reject()
        return value
    except (acquisition.AcquireError, RecursionError):
        _reject()


def _identity(value, client):
    if (type(value) is not dict or set(value) != _IDENTITY_KEYS
            or type(value["pid"]) is not int or not 1 <= value["pid"] <= 0xFFFFFFFF
            or value["path"] != str(client / "TdxW.exe")
            or value["exe_sha256"] != acquisition._EXE_SHA or value["sdk_sha256"] != acquisition._SDK_SHA):
        _reject()
    try:
        return session.creation_filetime(value["started"])
    except acquisition.AcquireError:
        _reject()


def _old(record, client):
    acquisition._validate_journal(record, client)
    if (record["status"] not in {"preparing", "refresh_unknown"}
            or any(key in record for key in ("dispatch_id", "plan_hash", "slot_id", "recovery_version"))):
        _reject()
    root = Path(record["root"])
    directory = root / "acquisition" / record["run_id"]
    if (not root.is_absolute() or record["root"] != str(root.resolve())
            or record["client_directory"] != str(client)
            or record["evidence_directory"] != str(directory) or directory.resolve() != directory
            or not directory.is_dir()):
        _reject()
    _identity(record["identity"], client)
    return directory


def _new(record):
    new = {**record, "status": "failed", "error_code": "prior_listener_session_ended",
           "client_task_cancelled": "not_proven", "recovery_version": 1}
    raw = json.dumps(new, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    if len(raw) > _JOURNAL_LIMIT:
        _reject()
    return raw


def _process(observation):
    if type(observation) is not dict or set(observation) != _PROCESS_KEYS:
        _reject()
    if observation["state"] == "missing":
        if (observation["creation_filetime"] is not None or type(observation["census_count"]) is not int
                or not 1 <= observation["census_count"] <= 16384 or observation["census_complete"] is not True
                or type(observation["open_error"]) is not int or observation["open_error"] != 87):
            _reject()
    elif (observation["state"] not in {"alive", "ended"}
          or type(observation["creation_filetime"]) is not int
          or not 1 <= observation["creation_filetime"] <= 0xFFFFFFFFFFFFFFFF
          or any(observation[key] is not None for key in ("census_count", "census_complete", "open_error"))):
        _reject()
    return observation


def _ended(observation, expected):
    return observation["state"] == "missing" or observation["creation_filetime"] != expected or observation["state"] == "ended"


def _observations(items, old, client):
    if type(items) is not list or len(items) != 2:
        _reject()
    times, listeners = [], []
    expected = _identity(old["identity"], client)
    for item in items:
        if type(item) is not dict or set(item) != {"observed_at_utc", "prior", "listener"}:
            _reject()
        stamp = item["observed_at_utc"]
        if type(stamp) is not str or not stamp.endswith(("Z", "+00:00")):
            _reject()
        times.append(session.creation_filetime(stamp))
        prior, listener = item["prior"], item["listener"]
        if (type(prior) is not dict or set(prior) != {"pid", "expected_started_filetime", "observation"}
                or type(prior["pid"]) is not int or prior["pid"] != old["identity"]["pid"]
                or type(prior["expected_started_filetime"]) is not int or prior["expected_started_filetime"] != expected
                or not _ended(_process(prior["observation"]), expected)
                or type(listener) is not dict or set(listener) != _IDENTITY_KEYS | {"started_filetime"}):
            _reject()
        tick = _identity({key: listener[key] for key in _IDENTITY_KEYS}, client)
        if (type(listener["started_filetime"]) is not int or listener["started_filetime"] != tick
                or (listener["pid"], tick) == (old["identity"]["pid"], expected)):
            _reject()
        listeners.append({key: listener[key] for key in ("pid", "path", "exe_sha256", "sdk_sha256", "started_filetime")})
    if times[0] > times[1] or listeners[0] != listeners[1]:
        _reject()


def _observe(old, client):
    expected = _identity(old["identity"], client)
    items = []
    for _ in range(2):
        acquisition._remaining()
        prior = _process(session.process_observation(old["identity"]["pid"]))
        if not _ended(prior, expected):
            raise acquisition.AcquireError("client_task_unresolved")
        listener = acquisition._client_identity(client)
        tick = _identity(listener, client)
        observed = _process(session.process_observation(listener["pid"]))
        if observed["state"] != "alive" or observed["creation_filetime"] != tick:
            raise acquisition.AcquireError("client_identity_unavailable")
        items.append(dict(observed_at_utc=datetime.now(timezone.utc).isoformat(),
                          prior=dict(pid=old["identity"]["pid"], expected_started_filetime=expected, observation=prior),
                          listener={**listener, "started_filetime": tick}))
    _observations(items, old, client)
    acquisition._remaining()
    return items


def _checkpoint(raw, state, client, directory):
    record = _decode(raw)
    if set(record) != _CHECKPOINT_KEYS or type(record["schema"]) is not int or record["schema"] != 1:
        _reject()
    try:
        original = base64.b64decode(record["old_bytes_base64"], validate=True)
    except (ValueError, TypeError):
        _reject()
    if (len(original) > _JOURNAL_LIMIT or base64.b64encode(original).decode("ascii") != record["old_bytes_base64"]
            or record["old_sha256"] != hashlib.sha256(original).hexdigest()):
        _reject()
    old = _decode(original)
    if (_old(old, client) != directory
            or any(record[key] != old[key] for key in ("run_id", "root", "evidence_directory", "client_directory"))
            or record["state_directory"] != str(state)):
        _reject()
    new = _new(old)
    if record["new_sha256"] != hashlib.sha256(new).hexdigest():
        _reject()
    _observations(record["observations"], old, client)
    return old, original, new


def _write(path, raw):
    directory = path.parent
    acquisition._remaining()
    _path(path, directory)
    acquisition._remaining()
    with path.open("wb", buffering=0) as output:
        acquisition._remaining()
        _path(path, directory)
        acquisition._remaining()
        written = output.write(raw)
        acquisition._remaining()
        if written != len(raw):
            _reject()
        _path(path, directory)
        acquisition._remaining()
        output.flush()
        acquisition._remaining()
        _path(path, directory)
        acquisition._remaining()
        os.fsync(output.fileno())
        acquisition._remaining()


def _publish(path, directory, raw, *, immutable=False):
    acquisition._remaining()
    _path(path, directory)
    temporary = _path(path.with_suffix(".tmp"), directory)
    _write(temporary, raw)
    acquisition._remaining()
    _path(path, directory)
    _path(temporary, directory)
    acquisition._remaining()
    if immutable:
        if path.exists():
            _reject()
        acquisition._remaining()
        temporary.rename(path)
    else:
        temporary.replace(path)
    acquisition._remaining()


def _report(old, *, error=None):
    result = dict(status="refresh_unknown" if error else "recovered", run_id=old["run_id"], recovery_version=1,
                  source_status=old["status"] if error else "failed", client_task_cancelled="not_proven")
    if error:
        result["error_code"] = error
    return result


def _recovery_gate(state, client, *, explicit=False):
    state, client = Path(state).resolve(), Path(client).resolve()
    current = state / "current.json"
    if not current.exists():
        return dict(status="idle") if explicit else None
    current_raw = _read(current, state, _JOURNAL_LIMIT)
    current_record = _decode(current_raw)
    acquisition._validate_journal(current_record, client)
    directory = Path(current_record["evidence_directory"])
    checkpoint = _path(directory / "recovery.json", directory.resolve())
    if (not checkpoint.exists() and "recovery_version" not in current_record
            and current_record["status"] not in {"preparing", "refresh_unknown"}):
        return dict(status="idle") if explicit else None
    deadline = acquisition._deadline.get()
    token = acquisition._deadline.set(min(deadline, time.monotonic() + 60) if deadline is not None else time.monotonic() + 60)
    try:
        expected_state = Path(os.environ["LOCALAPPDATA"]).resolve() / "Anatrading" / "acquisition" / acquisition.data_root_id(client)
        if state != expected_state or state != acquisition._state_directory(client).resolve():
            _reject()
        if checkpoint.exists():
            old, original, new = _checkpoint(_read(checkpoint, directory.resolve(), _CHECKPOINT_LIMIT), state, client, directory)
        else:
            old, original = current_record, current_raw
            directory = _old(old, client)
            new = _new(old)
        receipt = directory / "receipt.json"
        receipt_raw = _read(receipt, directory, _JOURNAL_LIMIT)
        if not checkpoint.exists() and receipt_raw != original:
            _reject()
        if current_raw not in (original, new) or receipt_raw not in (original, new):
            _reject()
        if checkpoint.exists() and current_raw == receipt_raw == new:
            return _report(old) if explicit else None
        try:
            observations = _observe(old, client)
        except acquisition.AcquireError as error:
            if error.code in {"invalid_acquisition_recovery", "invalid_acquisition_journal"}:
                raise
            return _report(old, error=error.code)
        if not checkpoint.exists():
            record = dict(schema=1, client_directory=str(client), state_directory=str(state), run_id=old["run_id"],
                          root=old["root"], evidence_directory=str(directory), old_bytes_base64=base64.b64encode(original).decode("ascii"),
                          old_sha256=hashlib.sha256(original).hexdigest(), new_sha256=hashlib.sha256(new).hexdigest(), observations=observations)
            raw = json.dumps(record, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
            if len(raw) > _CHECKPOINT_LIMIT:
                _reject()
            _publish(checkpoint, directory, raw, immutable=True)
        _checkpoint(_read(checkpoint, directory, _CHECKPOINT_LIMIT), state, client, directory)
        if _read(current, state, _JOURNAL_LIMIT) not in (original, new) or _read(receipt, directory, _JOURNAL_LIMIT) not in (original, new):
            _reject()
        _publish(receipt, directory, new)
        _publish(current, state, new)
        if _read(current, state, _JOURNAL_LIMIT) != new or _read(receipt, directory, _JOURNAL_LIMIT) != new:
            _reject()
        return _report(old)
    finally:
        acquisition._deadline.reset(token)


def recovery_gate(state, client, *, explicit=False):
    try:
        return _recovery_gate(state, client, explicit=explicit)
    except acquisition.AcquireError:
        raise
    except (OSError, KeyError, ValueError, TypeError, RecursionError):
        _reject()


def recover(client_directory):
    client = Path(client_directory)
    if not client.is_absolute():
        _reject()
    client = client.resolve()
    state = acquisition._state_directory(client)
    state.mkdir(parents=True, exist_ok=True)
    with _DirectoryLock(state):
        from .tdx_schedule import _read_control

        control = _read_control(state, client)
        if control is not None and control["active"] is not None:
            raise acquisition.AcquireError("schedule_dispatch_unresolved")
        return recovery_gate(state, client, explicit=True)
