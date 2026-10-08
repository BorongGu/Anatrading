"""Schedule boundaries use private controls, synthetic bytes, and the existing ASGI writer."""
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

from test_tdx_acquisition import day, encoded, environment, module
from anatrading.store import EvidenceStore, StoreError


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows acquisition locks")
NOW = datetime(2026, 10, 8, 10, tzinfo=timezone.utc)
MARKER = b"anatrading-tdx-dispatch-v1\n"


@pytest.fixture
def schedule():
    return importlib.import_module("anatrading.tdx_schedule")


@pytest.fixture
def plan(schedule, module, environment, tmp_path, monkeypatch):
    env = environment
    urls = ["https://www.sse.com.cn/disclosure/dealinstruc/closed/",
            "https://one.sse.com.cn/onething/gptz/"]
    references = []
    for index, url in enumerate(urls):
        path = tmp_path / f"synthetic-calendar-{index}.html"
        path.write_bytes(f"<p>Synthetic boundary source {index}</p>".encode())
        references.append({"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "source_url": url, "captured_at_utc": "2026-10-08T08:00:00Z"})
    monkeypatch.setattr(schedule, "_CALENDAR", [{"source_url": item["source_url"], "sha256": item["sha256"]}
                                               for item in references])
    monkeypatch.setattr(schedule, "_host_clock", lambda now: None)
    monkeypatch.setattr(schedule, "_owner", lambda: (9876, 134359200000000000))
    if hasattr(schedule, "_utc_now"):
        monkeypatch.setattr(schedule, "_utc_now", lambda: NOW)
    value = {"schema": 1, "root": str(env.root), "client_directory": str(env.client_directory),
             "port": 8765, "symbol": "600059.SH", "period": "1d",
             "exe_sha256": env.identity["exe_sha256"], "sdk_sha256": env.identity["sdk_sha256"],
             "start_at": "2026-10-08T00:00:00+08:00", "end_at": "2026-10-14T23:59:59+08:00",
             "days": [{"date": f"2026-10-{date:02}", "kind": "closed" if date in {10, 11} else "open",
                       "due_at": f"2026-10-{date:02}T18:00:00+08:00"} for date in range(8, 15)],
             "calendar": references}
    path = tmp_path / "private-plan.json"
    path.write_bytes(encoded(value))
    env.raw = day(20261008)
    return path, value


def read_control(environment):
    return json.loads((environment.state / "dispatch.json").read_bytes())


def write_control(environment, value):
    (environment.state / "dispatch.json").write_bytes(encoded(value))


def initialize(schedule, plan):
    schedule.due(plan[0], now=datetime(2026, 10, 8, 9, tzinfo=timezone.utc))


def no_posts(environment):
    assert environment.posts(17709) == environment.posts(8765) == []


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":1}', b'{"schema":NaN}',
                                 b'{"schema":Infinity}', b'{} trailing', b'\xff',
                                 b" " * (1024 * 1024 + 1)],
                         ids=["duplicate", "nan", "infinity", "trailing", "utf8", "size-limit"])
def test_plan_parser_rejects_ambiguous_or_unbounded_bytes(schedule, module, environment, plan, raw):
    plan[0].write_bytes(raw)
    with pytest.raises(module.AcquireError):
        schedule._load_plan(plan[0], NOW)
    assert environment.calls == []


@pytest.mark.parametrize("field,value", [("schema", True), ("symbol", "000001.SZ"), ("period", "1m"),
                                       ("root", "relative-root"), ("client_directory", "relative-client"),
                                       ("port", True), ("port", 17709), ("exe_sha256", "0" * 64),
                                       ("sdk_sha256", "0" * 64), ("unknown", "field")])
def test_invalid_plan_identity_never_initializes_or_requests(schedule, module, environment, plan, field, value):
    plan[1][field] = value
    plan[0].write_bytes(encoded(plan[1]))
    with pytest.raises(module.AcquireError):
        schedule.due(plan[0], now=NOW)
    assert not (environment.state / "dispatch.required").exists()
    assert environment.calls == []


@pytest.mark.parametrize("defect", ["hash", "future-capture", "unknown-calendar", "gap", "wrong-kind", "wrong-due"])
def test_calendar_evidence_and_exact_slot_dates_are_required(schedule, module, environment, plan, defect):
    value = plan[1]
    if defect == "hash":
        Path(value["calendar"][0]["path"]).write_bytes(b"tampered")
    elif defect == "future-capture":
        value["calendar"][0]["captured_at_utc"] = "2026-10-08T11:00:00Z"
    elif defect == "unknown-calendar":
        value["days"][-1] = {"date": "2026-10-15", "kind": "open", "due_at": "2026-10-15T18:00:00+08:00"}
    elif defect == "gap":
        value["days"].pop(1)
    elif defect == "wrong-kind":
        value["days"][2]["kind"] = "open"
    else:
        value["days"][0]["due_at"] = "2026-10-08T17:00:00+08:00"
    plan[0].write_bytes(encoded(value))
    with pytest.raises(module.AcquireError):
        schedule.due(plan[0], now=NOW)
    assert environment.calls == []


@pytest.mark.parametrize("side", ["marker-only", "dispatch-only", "bad-marker", "bad-dispatch"])
def test_one_sided_or_damaged_control_blocks_manual_cross_root_before_network(schedule, module, environment, side):
    env = environment
    if side in {"marker-only", "bad-marker", "bad-dispatch"}:
        (env.state / "dispatch.required").write_bytes(MARKER if side != "bad-marker" else b"bad")
    if side in {"dispatch-only", "bad-marker", "bad-dispatch"}:
        (env.state / "dispatch.json").write_bytes(b'{"broken":')
    before = {p.name: p.read_bytes() for p in env.state.iterdir() if p.suffix != ".lock"}
    for root in [env.root, env.root.parent / "other-root"]:
        with pytest.raises(module.AcquireError):
            module.acquire(root, env.client_directory, "600059.SH", "2026-09-30")
    assert env.calls == []
    assert before == {p.name: p.read_bytes() for p in env.state.iterdir() if p.suffix != ".lock"}


def test_reserved_after_process_interruption_blocks_all_unbound_acquisition(schedule, module, environment, plan, monkeypatch):
    env = environment
    original = schedule._save_control
    def interrupted(state, control):
        original(state, control)
        if control["active"] is not None and control["active"]["state"] == "reserved":
            raise KeyboardInterrupt
    monkeypatch.setattr(schedule, "_save_control", interrupted)
    with pytest.raises(KeyboardInterrupt):
        schedule.due(plan[0], now=NOW)
    control = read_control(env)
    assert control["active"]["state"] == "reserved"
    assert not (env.state / "current.json").exists()
    monkeypatch.setattr(schedule, "_save_control", original)
    for root, symbol, date in [(env.root, "600059.SH", "2026-10-08"),
                               (env.root.parent / "other", "000001.SZ", "2026-09-30")]:
        with pytest.raises(module.AcquireError) as caught:
            module.acquire(root, env.client_directory, symbol, date)
        assert caught.value.code == "schedule_dispatch_unresolved"
    schedule.due(plan[0], now=NOW)
    no_posts(env)
    assert read_control(env)["active"] == control["active"]


@pytest.mark.parametrize("defect", ["missing-slot", "fake-terminal", "active-null", "wrong-root", "wrong-plan", "owner-bool"])
def test_malformed_slot_or_active_identity_cannot_enable_post(schedule, module, environment, plan, monkeypatch, defect):
    env = environment
    original = schedule._save_control
    def interrupted(state, control):
        original(state, control)
        if control["active"] is not None:
            raise KeyboardInterrupt
    monkeypatch.setattr(schedule, "_save_control", interrupted)
    with pytest.raises(KeyboardInterrupt):
        schedule.due(plan[0], now=NOW)
    monkeypatch.setattr(schedule, "_save_control", original)
    control = read_control(env)
    if defect == "missing-slot":
        control["slots"].pop("2026-10-14")
    elif defect == "fake-terminal":
        control["slots"]["2026-10-08"]["status"] = "committed"
    elif defect == "active-null":
        control["active"] = None
    elif defect == "wrong-root":
        control["active"]["root"] = str(env.root.parent / "other")
    elif defect == "wrong-plan":
        control["active"]["plan_hash"] = "0" * 64
    else:
        control["active"]["owner_pid"] = True
    write_control(env, control)
    changed = (env.state / "dispatch.json").read_bytes()
    with pytest.raises(module.AcquireError) as caught:
        schedule.due(plan[0], now=NOW)
    assert caught.value.code == "invalid_schedule_control"
    assert env.calls == [] and (env.state / "dispatch.json").read_bytes() == changed


def test_success_uses_single_existing_writer_and_same_slot_never_reposts(schedule, environment, plan):
    env = environment
    with pytest.raises(StoreError) as caught:
        EvidenceStore(env.root)
    assert caught.value.code == "data_directory_busy"
    schedule.due(plan[0], now=NOW)
    first = read_control(env)
    assert first["active"] is None
    assert first["slots"]["2026-10-08"]["status"] == "committed"
    assert len(env.posts(17709)) == len(env.posts(8765)) == 1
    env.calls.clear()
    schedule.due(plan[0], now=NOW)
    assert read_control(env)["slots"] == first["slots"]
    no_posts(env)
    assert len(env.client.get("/api/attempts").json()["attempts"]) == 1
    assert len(env.client.get("/api/snapshots").json()["snapshots"]) == 1


def test_old_manual_publication_is_recovered_without_consuming_due_slot(schedule, environment, plan):
    env = environment
    env.raw = day()
    env.publication_fault = "query"
    old = env.acquire()
    assert old["status"] == "publication_unknown"
    env.publication_fault = None
    env.calls.clear()
    schedule.due(plan[0], now=NOW)
    current = json.loads((env.state / "current.json").read_bytes())
    assert current["run_id"] == old["run_id"] and current["status"] == "committed"
    assert all(item["status"] in {"pending", "closed_no_target"} for item in read_control(env)["slots"].values())
    no_posts(env)
    assert len(env.client.get("/api/attempts").json()["attempts"]) == 1


def test_old_unknown_refresh_blocks_due_even_after_client_identity_changes(schedule, module, environment, plan):
    env = environment
    env.refresh_fault = "timeout"
    assert env.acquire()["status"] == "refresh_unknown"
    current = (env.state / "current.json").read_bytes()
    env.identity["pid"] += 1
    env.calls.clear()
    try:
        schedule.due(plan[0], now=NOW)
    except module.AcquireError as error:
        assert error.code
    no_posts(env)
    assert (env.state / "current.json").read_bytes() == current


def test_linked_publication_recovery_closes_original_slot_without_new_post(schedule, environment, plan):
    env = environment
    env.publication_fault = "query"
    schedule.due(plan[0], now=NOW)
    pending = read_control(env)
    assert pending["active"] is not None
    original_id = pending["active"]["run_id"]
    env.publication_fault = None
    env.calls.clear()
    schedule.due(plan[0], now=NOW)
    done = read_control(env)
    assert done["active"] is None
    assert done["slots"]["2026-10-08"]["run_id"] == original_id
    assert done["slots"]["2026-10-08"]["status"] == "committed"
    no_posts(env)
    assert len(env.client.get("/api/attempts").json()["attempts"]) == 1


def test_preparing_crash_preserves_association_without_generic_journal_relaxation(schedule, module, environment, plan, monkeypatch):
    env = environment
    original = module._config
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(module, "_config", interrupted)
    with pytest.raises(KeyboardInterrupt):
        schedule.due(plan[0], now=NOW)
    current = (env.state / "current.json").read_bytes()
    record = json.loads(current)
    assert record["status"] == "preparing" and record["identity"] == {}
    assert read_control(env)["active"]["run_id"] == record["run_id"]
    with pytest.raises(module.AcquireError):
        module._journal(env.state / "current.json", env.client_directory)
    monkeypatch.setattr(module, "_config", original)
    try:
        schedule.due(plan[0], now=NOW)
    except module.AcquireError as error:
        assert error.code
    no_posts(env)
    assert (env.state / "current.json").read_bytes() == current


@pytest.mark.parametrize("defect", ["missing-receipt", "changed-receipt"])
def test_single_sided_or_disagreeing_acquisition_receipt_cannot_resume(schedule, module, environment, plan, defect):
    env = environment
    env.publication_fault = "query"
    schedule.due(plan[0], now=NOW)
    current = json.loads((env.state / "current.json").read_bytes())
    receipt = Path(current["evidence_directory"]) / "receipt.json"
    if defect == "missing-receipt":
        receipt.unlink()
    else:
        changed = json.loads(receipt.read_bytes())
        changed["run_id"] = "0" * 32
        receipt.write_bytes(encoded(changed))
    env.publication_fault = None
    env.calls.clear()
    try:
        schedule.due(plan[0], now=NOW)
    except module.AcquireError as error:
        assert error.code
    assert read_control(env)["active"] is not None
    assert read_control(env)["slots"]["2026-10-08"]["status"] != "committed"
    assert env.calls == []


def test_committed_journal_before_slot_close_is_reconciled_read_only(schedule, environment, plan, monkeypatch):
    env = environment
    original = schedule._save_control
    def interrupted(state, control):
        if control["active"] is None and control["slots"]["2026-10-08"]["status"] == "committed":
            raise KeyboardInterrupt
        original(state, control)
    monkeypatch.setattr(schedule, "_save_control", interrupted)
    with pytest.raises(KeyboardInterrupt):
        schedule.due(plan[0], now=NOW)
    current = json.loads((env.state / "current.json").read_bytes())
    assert current["status"] == "committed"
    assert read_control(env)["active"]["run_id"] == current["run_id"]
    monkeypatch.setattr(schedule, "_save_control", original)
    env.calls.clear()
    schedule.due(plan[0], now=NOW)
    assert read_control(env)["active"] is None
    assert read_control(env)["slots"]["2026-10-08"]["status"] == "committed"
    no_posts(env)


def test_wrong_returned_run_never_commits_selected_slot(schedule, module, environment, plan, monkeypatch):
    original = module._collect_locked
    def wrong(*args, **kwargs):
        result = original(*args, **kwargs)
        result["run_id"] = "0" * 32
        return result
    monkeypatch.setattr(module, "_collect_locked", wrong)
    schedule.due(plan[0], now=NOW)
    control = read_control(environment)
    assert control["active"] is not None
    assert control["slots"]["2026-10-08"]["status"] == "dispatch_unknown"


def test_clock_rollback_preserves_control_and_prevents_any_request(schedule, module, environment, plan):
    initialize(schedule, plan)
    before = (environment.state / "dispatch.json").read_bytes()
    with pytest.raises(module.AcquireError) as caught:
        schedule.due(plan[0], now=datetime(2026, 10, 8, 8, tzinfo=timezone.utc))
    assert caught.value.code == "clock_rollback"
    assert (environment.state / "dispatch.json").read_bytes() == before
    assert environment.calls == []


def test_expired_window_keeps_complete_backlog_and_closed_denominator(schedule, environment, plan):
    schedule.due(plan[0], now=datetime(2026, 10, 15, tzinfo=timezone.utc))
    control = read_control(environment)
    assert len(control["slots"]) == 7
    assert sum(item["status"] == "pending" for item in control["slots"].values()) == 5
    assert sum(item["status"] == "closed_no_target" for item in control["slots"].values()) == 2
    assert control["active"] is None and environment.calls == []


def test_changed_plan_cannot_replace_existing_client_control(schedule, module, environment, plan):
    initialize(schedule, plan)
    before = (environment.state / "dispatch.json").read_bytes()
    plan[1]["port"] = 8766
    plan[0].write_bytes(encoded(plan[1]))
    with pytest.raises(module.AcquireError):
        schedule.due(plan[0], now=NOW)
    assert (environment.state / "dispatch.json").read_bytes() == before
    assert environment.calls == []


@pytest.mark.parametrize("transition", ["expired", "rollback", "timezone"])
def test_civil_clock_is_rechecked_before_import_post(schedule, module, environment, plan, monkeypatch, transition):
    changed = datetime(2026, 10, 15, tzinfo=timezone.utc) if transition == "expired" else datetime(2026, 10, 8, 9, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(schedule, "_utc_now", lambda: changed if transition != "timezone"
                        and environment.posts(17709) else NOW)
    def host_clock(now):
        if transition == "timezone" and environment.posts(17709):
            raise module.AcquireError("schedule_timezone_mismatch")
    monkeypatch.setattr(schedule, "_host_clock", host_clock)
    schedule.due(plan[0])
    assert len(environment.posts(17709)) == 1
    assert environment.posts(8765) == []
    assert environment.client.get("/api/attempts").json()["attempts"] == []
    assert read_control(environment)["active"] is not None
    if transition == "rollback":
        assert datetime.fromisoformat(read_control(environment)["last_observed_utc"]) == NOW


def test_slow_host_probe_crossing_end_boundary_cannot_start_refresh(schedule, environment, plan, monkeypatch):
    clock = [NOW]
    monkeypatch.setattr(schedule, "_utc_now", lambda: clock[0])
    def host_clock(now):
        path = environment.state / "dispatch.json"
        if path.exists() and read_control(environment)["active"] is not None:
            clock[0] = datetime(2026, 10, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(schedule, "_host_clock", host_clock)
    schedule.due(plan[0])
    no_posts(environment)
    assert read_control(environment)["active"] is not None


@pytest.mark.parametrize("field", ["identity", "workbench_session_id"])
def test_incomplete_terminal_receipt_blocks_every_acquisition_entry(schedule, module, environment, plan, field):
    schedule.due(plan[0], now=NOW)
    control = read_control(environment)
    del control["slots"]["2026-10-08"]["result"][field]
    write_control(environment, control)
    environment.calls.clear()
    with pytest.raises(module.AcquireError, match="invalid_schedule_control"):
        module.acquire(environment.root, environment.client_directory, "600059.SH", "2026-09-30")
    assert environment.calls == []


@pytest.mark.parametrize("python,working,sid", [("relative.exe", None, "S-1-5-21-1-2-3-1001"),
                                              (None, "relative-directory", "S-1-5-21-1-2-3-1001"),
                                              (None, None, "S-1-5-18")])
def test_task_xml_rejects_ambiguous_actions_or_system_identity(schedule, module, plan, tmp_path, python, working, sid):
    with pytest.raises(module.AcquireError) as caught:
        schedule.task_xml(plan[0], python or tmp_path / "python.exe", working or tmp_path / "repo", sid)
    assert caught.value.code == "invalid_schedule_task"


def test_task_xml_is_finite_interactive_nonretrying_and_does_not_register(schedule, plan, tmp_path):
    python = tmp_path / "中文 & tools" / "python.exe"
    working = tmp_path / "repo & work"
    xml = schedule.task_xml(plan[0], python, working, "S-1-5-21-1-2-3-1001")
    assert not xml.lstrip().startswith("<?xml")
    root = ET.fromstring(xml)
    ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    def text(path):
        return root.find(path, ns).text
    assert text("t:Principals/t:Principal/t:LogonType") == "InteractiveToken"
    assert text("t:Principals/t:Principal/t:RunLevel") == "LeastPrivilege"
    assert text("t:Settings/t:MultipleInstancesPolicy") == "IgnoreNew"
    assert text("t:Settings/t:StartWhenAvailable") == "true"
    assert text("t:Settings/t:ExecutionTimeLimit") == "PT3M"
    assert root.find("t:Settings/t:RestartOnFailure", ns) is None
    assert root.find(".//t:Repetition", ns) is None
    assert root.find(".//t:EndBoundary", ns) is not None
    assert text("t:Actions/t:Exec/t:Command") == str(python)
    assert text("t:Actions/t:Exec/t:WorkingDirectory") == str(working)
    assert "acquire-tdx-due" in text("t:Actions/t:Exec/t:Arguments")
    assert str(plan[0]) in text("t:Actions/t:Exec/t:Arguments")
