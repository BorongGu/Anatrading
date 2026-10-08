"""Recovery tests use private states, native stubs, and the existing ASGI writer."""
import base64
import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import time

import pytest

from test_tdx_acquisition import encoded, environment, module
from test_tdx_schedule import NOW, plan, read_control, schedule


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows recovery locks")
ENTRIES = ["recover", "acquire", "due"]


@pytest.fixture
def recovery():
    return importlib.import_module("anatrading.tdx_recovery")


@pytest.fixture
def session():
    return importlib.import_module("anatrading.tdx_session")


def unknown(env):
    env.refresh_fault = "timeout"
    assert env.acquire()["status"] == "refresh_unknown"
    current = env.state / "current.json"
    raw = current.read_bytes()
    old = json.loads(raw)
    directory = Path(old["evidence_directory"])
    assert (directory / "receipt.json").read_bytes() == raw
    env.refresh_fault = None
    env.calls.clear()
    return old, raw, directory


def changed_session(env, session, monkeypatch, *, prior_state="missing"):
    old_pid = env.identity["pid"]
    old_ticks = session.creation_filetime(env.identity["started"])
    env.identity["pid"] += 1
    env.identity["started"] = "2026-10-08T03:19:50.0000001Z"
    new_ticks = session.creation_filetime(env.identity["started"])

    def observation(pid):
        if pid == old_pid and prior_state == "missing":
            return {"state": "missing", "creation_filetime": None, "census_count": 7,
                    "census_complete": True, "open_error": 87}
        tick = old_ticks if pid == old_pid else new_ticks
        return {"state": prior_state if pid == old_pid else "alive", "creation_filetime": tick,
                "census_count": None, "census_complete": None, "open_error": None}

    monkeypatch.setattr(session, "process_observation", observation)
    return old_pid, old_ticks, new_ticks


def invoke(kind, env, recovery, schedule, plan):
    if kind == "recover":
        return recovery.recover(env.client_directory)
    if kind == "acquire":
        return env.acquire()
    return schedule.due(plan[0], now=NOW)


def quiet(env, directory, *, control=None):
    assert env.calls == []
    assert list((env.root / "acquisition").iterdir()) == [directory]
    if control is None:
        assert not (env.state / "dispatch.required").exists()
        assert not (env.state / "dispatch.json").exists()
    else:
        assert (env.state / "dispatch.json").read_bytes() == control


def refused(call, module):
    try:
        result = call()
    except module.AcquireError as error:
        assert error.code
    else:
        assert result["status"] in {"failed", "error", "refresh_unknown", "dispatch_unknown"}


@pytest.mark.parametrize("kind", ENTRIES)
def test_same_original_process_alive_blocks_every_entry_without_control_init(
        kind, environment, recovery, module, schedule, plan):
    env = environment
    _, raw, directory = unknown(env)
    refused(lambda: invoke(kind, env, recovery, schedule, plan), module)
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == raw
    assert not (directory / "recovery.json").exists()
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
def test_listener_transfer_does_not_prove_old_session_ended(
        kind, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch, prior_state="alive")
    refused(lambda: invoke(kind, env, recovery, schedule, plan), module)
    assert (env.state / "current.json").read_bytes() == raw
    quiet(env, directory)


@pytest.mark.parametrize("defect", ["duplicate", "bom", "utf8", "nan", "float", "oversize", "receipt-different"])
def test_invalid_original_bytes_fail_before_native_or_http(
        defect, environment, recovery, module, session, monkeypatch):
    env = environment
    old, raw, directory = unknown(env)
    if defect == "duplicate":
        broken = b'{"run_id":"x","run_id":"y"}'
    elif defect == "bom":
        broken = b"\xef\xbb\xbf" + raw
    elif defect == "utf8":
        broken = b"\xff"
    elif defect == "nan":
        broken = raw.replace(b'"identity": {', b'"bad": NaN, "identity": {')
    elif defect == "float":
        broken = raw.replace(b'"identity": {', b'"bad": 1.25, "identity": {')
    elif defect == "oversize":
        broken = b" " * (65536 + 1)
    else:
        broken = raw
    (env.state / "current.json").write_bytes(broken)
    (directory / "receipt.json").write_bytes(broken if defect != "receipt-different" else encoded(old))
    probes = []
    monkeypatch.setattr(session, "process_observation", lambda pid: probes.append(pid))
    refused(lambda: recovery.recover(env.client_directory), module)
    assert probes == []
    assert (env.state / "current.json").read_bytes() == broken
    quiet(env, directory)


@pytest.mark.parametrize("field,value", [
    ("root", "relative-root"), ("data_root_id", "0" * 64), ("run_id", "bad"),
    ("client_directory", "relative-client"), ("evidence_directory", "relative-evidence"),
    ("dispatch_id", None), ("plan_hash", "1" * 64), ("slot_id", "2026-10-08"),
    ("identity", {}), ("recovery_version", 1),
])
def test_old_identity_or_scheduled_association_cannot_be_recovered(
        field, value, environment, recovery, module, session, monkeypatch):
    env = environment
    old, _, directory = unknown(env)
    old[field] = value
    raw = encoded(old)
    (env.state / "current.json").write_bytes(raw)
    (directory / "receipt.json").write_bytes(raw)
    probes = []
    monkeypatch.setattr(session, "process_observation", lambda pid: probes.append(pid))
    refused(lambda: recovery.recover(env.client_directory), module)
    assert probes == []
    assert (env.state / "current.json").read_bytes() == raw
    quiet(env, directory)


@pytest.mark.parametrize("bad_observation", [
    {"state": "missing", "creation_filetime": None, "census_count": 7, "census_complete": False, "open_error": 87},
    {"state": "missing", "creation_filetime": None, "census_count": 0, "census_complete": True, "open_error": 87},
    {"state": "missing", "creation_filetime": None, "census_count": 16385, "census_complete": True, "open_error": 87},
    {"state": "missing", "creation_filetime": None, "census_count": 7, "census_complete": True, "open_error": 5},
    {"state": "missing", "creation_filetime": None, "census_count": True, "census_complete": True, "open_error": 87},
])
def test_incomplete_missing_proof_cannot_seal_checkpoint(
        bad_observation, environment, recovery, module, session, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    monkeypatch.setattr(session, "process_observation", lambda pid: dict(bad_observation))
    refused(lambda: recovery.recover(env.client_directory), module)
    assert (env.state / "current.json").read_bytes() == raw
    assert not (directory / "recovery.json").exists()
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
def test_proven_recovery_preserves_source_fields_and_returns_without_new_work(
        kind, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    old, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    result = invoke(kind, env, recovery, schedule, plan)
    assert result["status"] == "recovered"
    new = json.loads((env.state / "current.json").read_bytes())
    expected = copy.deepcopy(old)
    expected.update(status="failed", error_code="prior_listener_session_ended",
                    client_task_cancelled="not_proven", recovery_version=1)
    assert new == expected
    assert (directory / "receipt.json").read_bytes() == (env.state / "current.json").read_bytes()
    checkpoint = json.loads((directory / "recovery.json").read_bytes())
    assert base64.b64decode(checkpoint["old_bytes_base64"], validate=True) == raw
    assert checkpoint["old_sha256"] == hashlib.sha256(raw).hexdigest()
    assert checkpoint["new_sha256"] == hashlib.sha256((env.state / "current.json").read_bytes()).hexdigest()
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
@pytest.mark.parametrize("receipt_new,current_new", [(False, False), (True, False), (False, True)])
def test_frozen_old_new_combinations_finish_only_original_run(
        kind, receipt_new, current_new, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, old_raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    assert recovery.recover(env.client_directory)["status"] == "recovered"
    new_raw = (env.state / "current.json").read_bytes()
    checkpoint = (directory / "recovery.json").read_bytes()
    (directory / "receipt.json").write_bytes(new_raw if receipt_new else old_raw)
    (env.state / "current.json").write_bytes(new_raw if current_new else old_raw)
    assert invoke(kind, env, recovery, schedule, plan)["status"] == "recovered"
    assert (env.state / "current.json").read_bytes() == new_raw
    assert (directory / "receipt.json").read_bytes() == new_raw
    assert (directory / "recovery.json").read_bytes() == checkpoint
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
def test_completed_tag_without_checkpoint_blocks_ordinary_entries(
        kind, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, _, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    assert recovery.recover(env.client_directory)["status"] == "recovered"
    raw = (env.state / "current.json").read_bytes()
    (directory / "recovery.json").unlink()
    refused(lambda: invoke(kind, env, recovery, schedule, plan), module)
    assert (env.state / "current.json").read_bytes() == raw
    quiet(env, directory)


@pytest.mark.parametrize("defect", ["old-sha", "new-sha", "run", "state", "extra", "prior-pid", "old-base64", "candidate-change"])
def test_checkpoint_corruption_and_non_whitelist_terminal_change_remain_blocked(
        defect, environment, recovery, module, session, monkeypatch):
    env = environment
    _, _, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    assert recovery.recover(env.client_directory)["status"] == "recovered"
    path = directory / "recovery.json"
    checkpoint = json.loads(path.read_bytes())
    if defect == "old-sha":
        checkpoint["old_sha256"] = "0" * 64
    elif defect == "new-sha":
        checkpoint["new_sha256"] = "0" * 64
    elif defect == "run":
        checkpoint["run_id"] = "0" * 32
    elif defect == "state":
        checkpoint["state_directory"] = str(env.state.parent / "other")
    elif defect == "extra":
        checkpoint["extra"] = None
    elif defect == "prior-pid":
        checkpoint["observations"][0]["prior"]["pid"] += 1
    elif defect == "old-base64":
        checkpoint["old_bytes_base64"] += "!"
    else:
        record = json.loads((env.state / "current.json").read_bytes())
        record["coverage"] = "forged"
        changed = encoded(record)
        (env.state / "current.json").write_bytes(changed)
        (directory / "receipt.json").write_bytes(changed)
    path.write_bytes(encoded(checkpoint))
    refused(lambda: recovery.recover(env.client_directory), module)
    quiet(env, directory)


def test_recover_is_idempotent_and_completed_next_due_dispatches_normally(
        environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, _, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    first = recovery.recover(env.client_directory)
    checkpoint = (directory / "recovery.json").read_bytes()
    assert recovery.recover(env.client_directory) == first
    quiet(env, directory)
    result = schedule.due(plan[0], now=NOW)
    assert result["status"] == "committed"
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1
    assert (directory / "recovery.json").read_bytes() == checkpoint
    assert read_control(env)["active"] is None
    env.calls.clear()
    assert recovery.recover(env.client_directory)["status"] == "idle"
    assert env.calls == []


def test_existing_inactive_control_is_unchanged_during_recovery(
        environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    schedule.due(plan[0], now=NOW.replace(hour=9))
    before = (env.state / "dispatch.json").read_bytes()
    _, _, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    assert schedule.due(plan[0], now=NOW)["status"] == "recovered"
    quiet(env, directory, control=before)


@pytest.mark.parametrize("kind", ENTRIES)
@pytest.mark.parametrize("target,after_replace", [("receipt", False), ("receipt", True), ("current", False), ("current", True)])
def test_interrupted_journal_atomic_replace_reenters_through_every_gate(
        kind, target, after_replace, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, old_raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    original = Path.replace
    hit = []

    def interrupt(path, destination):
        destination = Path(destination)
        expected = directory / "receipt.json" if target == "receipt" else env.state / "current.json"
        if destination == expected and not hit:
            hit.append(True)
            if after_replace:
                original(path, destination)
            raise OSError("synthetic interrupted replace")
        return original(path, destination)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "replace", interrupt)
        try:
            invoke(kind, env, recovery, schedule, plan)
        except (module.AcquireError, OSError):
            pass
    assert hit == [True]
    checkpoint = (directory / "recovery.json").read_bytes()
    new_raw = json.dumps(dict(json.loads(old_raw), status="failed", error_code="prior_listener_session_ended",
                            client_task_cancelled="not_proven", recovery_version=1),
                         ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    complete = target == "current" and after_replace
    if complete and kind != "recover":
        assert recovery.recover(env.client_directory)["status"] == "recovered"
    else:
        assert invoke(kind, env, recovery, schedule, plan)["status"] == "recovered"
    assert (directory / "receipt.json").read_bytes() == new_raw
    assert (env.state / "current.json").read_bytes() == new_raw
    assert (directory / "recovery.json").read_bytes() == checkpoint
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
@pytest.mark.parametrize("after_rename", [False, True])
def test_checkpoint_atomic_rename_interruption_never_starts_new_run(
        kind, after_rename, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    original = Path.rename
    hit = []

    def interrupt(path, destination):
        if Path(destination) == directory / "recovery.json" and not hit:
            hit.append(True)
            if after_rename:
                original(path, destination)
            raise OSError("synthetic checkpoint rename interruption")
        return original(path, destination)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "rename", interrupt)
        try:
            invoke(kind, env, recovery, schedule, plan)
        except (module.AcquireError, OSError):
            pass
    assert hit == [True]
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == raw
    assert (directory / "recovery.json").exists() is after_rename
    quiet(env, directory)
    assert invoke(kind, env, recovery, schedule, plan)["status"] == "recovered"
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
@pytest.mark.parametrize("target", ["recovery", "receipt", "current"])
@pytest.mark.parametrize("stage", ["before", "partial", "before-fsync", "after-fsync"])
def test_temporary_write_and_fsync_faults_recover_without_new_dispatch(
        kind, target, stage, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    original = recovery._write
    target_path = env.state / "current.tmp" if target == "current" else directory / (target + ".tmp")
    hit = []

    def interrupt(path, data):
        if Path(path) != target_path or hit:
            return original(path, data)
        hit.append(True)
        if stage == "partial":
            Path(path).write_bytes(data[:len(data) // 2])
        elif stage == "before-fsync":
            with Path(path).open("wb") as output:
                output.write(data)
                output.flush()
        elif stage == "after-fsync":
            original(path, data)
        raise OSError("synthetic interrupted temporary write")

    with monkeypatch.context() as patch:
        patch.setattr(recovery, "_write", interrupt)
        try:
            invoke(kind, env, recovery, schedule, plan)
        except (module.AcquireError, OSError):
            pass
    assert hit == [True]
    assert (env.state / "current.json").read_bytes() == raw
    quiet(env, directory)
    assert invoke(kind, env, recovery, schedule, plan)["status"] == "recovered"
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
def test_partial_checkpoint_reentry_requires_fresh_original_termination_proof(
        kind, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    old, raw, directory = unknown(env)
    old_pid, old_ticks, new_ticks = changed_session(env, session, monkeypatch)
    assert recovery.recover(env.client_directory)["status"] == "recovered"
    new_raw = (env.state / "current.json").read_bytes()
    (env.state / "current.json").write_bytes(raw)
    checkpoint = (directory / "recovery.json").read_bytes()

    def live_again(pid):
        return {"state": "alive", "creation_filetime": old_ticks if pid == old_pid else new_ticks,
                "census_count": None, "census_complete": None, "open_error": None}

    monkeypatch.setattr(session, "process_observation", live_again)
    refused(lambda: invoke(kind, env, recovery, schedule, plan), module)
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == new_raw
    assert (directory / "recovery.json").read_bytes() == checkpoint
    quiet(env, directory)


def test_original_pid_reused_with_last_tick_different_can_be_safely_closed(
        environment, recovery, module, session, monkeypatch):
    env = environment
    env.identity["started"] = "2026-10-08T03:19:49.0000001Z"
    _, _, directory = unknown(env)
    env.identity["started"] = "2026-10-08T03:19:49.0000002Z"
    new_ticks = session.creation_filetime(env.identity["started"])
    monkeypatch.setattr(session, "process_observation", lambda pid: {
        "state": "alive", "creation_filetime": new_ticks,
        "census_count": None, "census_complete": None, "open_error": None})
    assert recovery.recover(env.client_directory)["status"] == "recovered"
    quiet(env, directory)


def test_original_signaled_process_with_matching_creation_allows_recovery(
        environment, recovery, module, session, monkeypatch):
    env = environment
    _, _, directory = unknown(env)
    changed_session(env, session, monkeypatch, prior_state="ended")
    assert recovery.recover(env.client_directory)["status"] == "recovered"
    quiet(env, directory)


def test_completed_recover_does_not_require_new_client_to_stay_running(
        environment, recovery, module, session, monkeypatch):
    env = environment
    _, _, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    expected = recovery.recover(env.client_directory)
    calls = []
    monkeypatch.setattr(session, "process_observation", lambda pid: calls.append(pid))
    monkeypatch.setattr(module, "_client_identity", lambda client: calls.append(client))
    assert recovery.recover(env.client_directory) == expected
    assert calls == []
    quiet(env, directory)


def test_expired_inherited_deadline_does_not_reset_budget_or_mutate_unknown(
        environment, recovery, module, session, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    previous_deadline = time.monotonic() - 1
    token = module._deadline.set(previous_deadline)
    try:
        refused(lambda: recovery.recover(env.client_directory), module)
        assert module._deadline.get() == previous_deadline
    finally:
        module._deadline.reset(token)
    assert (env.state / "current.json").read_bytes() == raw
    quiet(env, directory)


def test_new_receipt_without_checkpoint_cannot_authorize_initial_recovery(
        environment, recovery, module, session, monkeypatch):
    env = environment
    old, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    forged = dict(old, status="failed", error_code="prior_listener_session_ended",
                  client_task_cancelled="not_proven", recovery_version=1)
    receipt_raw = json.dumps(forged, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")
    (directory / "receipt.json").write_bytes(receipt_raw)
    refused(lambda: recovery.recover(env.client_directory), module)
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == receipt_raw
    assert not (directory / "recovery.json").exists()
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
@pytest.mark.parametrize("code", ["prior_process_unverified", "client_identity_unavailable", "acquisition_deadline"])
def test_runtime_probe_failure_keeps_original_receipts_and_creates_nothing(
        kind, code, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)

    def unavailable(pid):
        raise module.AcquireError(code)

    monkeypatch.setattr(session, "process_observation", unavailable)
    result = invoke(kind, env, recovery, schedule, plan)
    assert result["status"] == "refresh_unknown" and result["error_code"] == code
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == raw
    assert not (directory / "recovery.json").exists()
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
def test_second_listener_identity_change_is_detected_before_checkpoint_or_journals(
        kind, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    calls = []

    def moving_listener(client):
        calls.append(client)
        value = dict(env.identity)
        if len(calls) == 2:
            value["started"] = "2026-10-08T03:19:50.0000002Z"
        return value

    monkeypatch.setattr(module, "_client_identity", moving_listener)
    refused(lambda: invoke(kind, env, recovery, schedule, plan), module)
    assert len(calls) == 2
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == raw
    assert not (directory / "recovery.json").exists()
    quiet(env, directory)


@pytest.mark.parametrize("kind", ENTRIES)
def test_active_scheduled_dispatch_cannot_be_closed_by_unlinked_recovery(
        kind, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    schedule.due(plan[0], now=NOW.replace(hour=9))
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    control = read_control(env)
    binding = schedule._binding(control["plan"], control["plan_hash"], "2026-10-08", "a" * 32, "b" * 32)
    control["last_observed_utc"] = NOW.isoformat()
    control["active"] = dict(binding, state="reserved", owner_pid=9876, owner_started_filetime=134359200000000000)
    control["slots"]["2026-10-08"] = dict(status="reserved", run_id="a" * 32, dispatch_id="b" * 32, result=None)
    schedule._save_control(env.state, control)
    before = (env.state / "dispatch.json").read_bytes()
    refused(lambda: invoke(kind, env, recovery, schedule, plan), module)
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == raw
    assert not (directory / "recovery.json").exists()
    quiet(env, directory, control=before)


@pytest.mark.parametrize("kind", ENTRIES)
@pytest.mark.parametrize("single_file", ["marker", "control"])
def test_incomplete_schedule_control_blocks_recovery_without_repair_or_initialization(
        kind, single_file, environment, recovery, module, session, schedule, plan, monkeypatch):
    env = environment
    _, raw, directory = unknown(env)
    changed_session(env, session, monkeypatch)
    marker, control = env.state / "dispatch.required", env.state / "dispatch.json"
    if single_file == "marker":
        marker.write_bytes(b"anatrading-tdx-dispatch-v1\n")
    else:
        control.write_bytes(b"{}")
    marker_before = marker.read_bytes() if marker.exists() else None
    control_before = control.read_bytes() if control.exists() else None
    refused(lambda: invoke(kind, env, recovery, schedule, plan), module)
    assert (env.state / "current.json").read_bytes() == raw
    assert (directory / "receipt.json").read_bytes() == raw
    assert not (directory / "recovery.json").exists()
    assert env.calls == []
    assert (marker.read_bytes() if marker.exists() else None) == marker_before
    assert (control.read_bytes() if control.exists() else None) == control_before


def test_surrogate_root_is_typed_refusal_before_process_probe(
        environment, recovery, module, session, monkeypatch):
    env = environment
    old, _, directory = unknown(env)
    old["root"] += "\ud800"
    raw = json.dumps(old, ensure_ascii=True, allow_nan=False).encode("utf-8")
    (env.state / "current.json").write_bytes(raw)
    (directory / "receipt.json").write_bytes(raw)
    probes = []
    monkeypatch.setattr(session, "process_observation", lambda pid: probes.append(pid))
    with pytest.raises(module.AcquireError):
        recovery.recover(env.client_directory)
    assert probes == []
    assert (env.state / "current.json").read_bytes() == raw
    quiet(env, directory)


@pytest.mark.parametrize("failure", ["deadline", "short_write"])
def test_write_failure_stops_before_flush_fsync_and_atomic_replace(
        failure, environment, recovery, module, monkeypatch):
    env = environment
    _, original_raw, directory = unknown(env)
    current = env.state / "current.json"
    target = env.state / "current.tmp"
    clock, calls = [100.0], []
    original_open = Path.open

    class SlowOutput:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            calls.append("close")

        def write(self, raw):
            calls.append("write")
            if failure == "deadline":
                clock[0] = 102.0
            return len(raw) if failure == "deadline" else len(raw) - 1

        def flush(self):
            calls.append("flush")

        def fileno(self):
            return 123

    def slow_open(path, *args, **kwargs):
        return SlowOutput() if path == target else original_open(path, *args, **kwargs)

    token = module._deadline.set(101.0)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(module.time, "monotonic", lambda: clock[0])
            patch.setattr(Path, "open", slow_open)
            patch.setattr(os, "fsync", lambda fd: calls.append("fsync"))
            patch.setattr(Path, "replace", lambda *args: calls.append("replace"))
            with pytest.raises(module.AcquireError) as caught:
                recovery._publish(current, env.state, b"replacement")
            assert caught.value.code == ("acquisition_deadline" if failure == "deadline" else "invalid_acquisition_recovery")
    finally:
        module._deadline.reset(token)
    assert calls == ["write", "close"]
    assert current.read_bytes() == original_raw
    assert (directory / "receipt.json").read_bytes() == original_raw
    quiet(env, directory)


def test_read_crossing_deadline_stops_before_decode_or_any_later_phase(
        environment, recovery, module, monkeypatch):
    env = environment
    _, original_raw, directory = unknown(env)
    current = env.state / "current.json"
    clock, decodes = [100.0], []
    original_open, original_decode = Path.open, recovery._decode

    class SlowInput:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self, limit):
            clock[0] = 102.0
            return original_raw

    def slow_open(path, *args, **kwargs):
        return SlowInput() if path == current else original_open(path, *args, **kwargs)

    def decode(raw):
        decodes.append(True)
        return original_decode(raw)

    token = module._deadline.set(101.0)
    try:
        with monkeypatch.context() as patch:
            patch.setattr(module.time, "monotonic", lambda: clock[0])
            patch.setattr(Path, "open", slow_open)
            patch.setattr(recovery, "_decode", decode)
            with pytest.raises(module.AcquireError) as caught:
                recovery.recovery_gate(env.state, env.client_directory, explicit=True)
            assert caught.value.code == "acquisition_deadline"
    finally:
        module._deadline.reset(token)
    assert decodes == []
    assert current.read_bytes() == original_raw
    assert (directory / "receipt.json").read_bytes() == original_raw
    quiet(env, directory)
