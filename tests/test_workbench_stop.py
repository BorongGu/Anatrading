"""Local control never retries an uncertain stop or opens the data writer."""
import importlib
import json
from copy import deepcopy
from types import SimpleNamespace
import sys
import threading
import shlex
import xml.etree.ElementTree as ET

import pytest

from anatrading import tdx_acquisition as acquisition
from anatrading.store import StoreError


def config(root, token="A" * 43):
    return {"data_root_id": acquisition.data_root_id(root), "csrf_token": token,
            "formats": ["tdx-public-day-v1"], "mode": "retrospective", "max_upload_bytes": 16 * 1024 * 1024}


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


@pytest.fixture
def transport(module, tmp_path, monkeypatch):
    root = tmp_path / "unused"
    env = SimpleNamespace(root=root, calls=[], get=(200, encoded(config(root))), get_error=None,
                          post=(202, encoded({"status": "shutdown_requested", "data_root_id": acquisition.data_root_id(root)})), post_error=None)
    def http(port, method, path, body=b"", headers=None, *, budget=15):
        env.calls.append({"port": port, "method": method, "path": path, "body": body,
                          "headers": headers, "budget": budget})
        error = env.get_error if method == "GET" else env.post_error
        if error is not None:
            raise error
        return env.get if method == "GET" else env.post
    def forbidden(*args, **kwargs):
        raise AssertionError("control may not open Store or access client state")
    monkeypatch.setattr(acquisition, "_http", http)
    monkeypatch.setattr(acquisition, "_client_identity", forbidden)
    monkeypatch.setattr(acquisition, "_state_directory", forbidden)
    from anatrading import store
    monkeypatch.setattr(store.EvidenceStore, "__init__", forbidden)
    return env


@pytest.fixture
def module():
    return importlib.import_module("anatrading.workbench_lifecycle")


@pytest.mark.parametrize("port", [True, 0, -1, 65536, 17709, 1.0, "8765"])
def test_invalid_stop_port_never_issues_http(module, tmp_path, monkeypatch, port):
    calls = []
    monkeypatch.setattr(acquisition, "_http", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(acquisition.AcquireError) as caught:
        module.stop(tmp_path / "unused", port=port)
    assert caught.value.code == "invalid_workbench_control" and calls == []
    assert not (tmp_path / "unused").exists()


def test_wrong_root_config_never_issues_shutdown_post(module, tmp_path, monkeypatch):
    calls = []
    def http(port, method, path, *args, **kwargs):
        calls.append((method, path))
        return 200, b'{"data_root_id":"wrong"}'
    monkeypatch.setattr(acquisition, "_http", http)
    with pytest.raises(acquisition.AcquireError):
        module.stop(tmp_path / "unused")
    assert calls == [("GET", "/api/config")]
    assert not (tmp_path / "unused").exists()


def test_expiry_inside_post_request_before_http_is_typed_not_unknown(module, tmp_path, monkeypatch):
    calls, clock, remaining_calls = [], [100.0], [0]
    original_remaining = acquisition._remaining
    def remaining(*args):
        remaining_calls[0] += 1
        if remaining_calls[0] == 4:
            clock[0] = 111.0
        return original_remaining(*args)
    def http(port, method, path, *args, **kwargs):
        calls.append((method, path))
        return 200, encoded(config(tmp_path))
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acquisition, "_remaining", remaining)
    monkeypatch.setattr(acquisition, "_http", http)
    with pytest.raises(acquisition.AcquireError) as caught:
        module.stop(tmp_path)
    assert caught.value.code == "acquisition_deadline"
    assert calls == [("GET", "/api/config")]


@pytest.mark.parametrize("char", ["\x7f", "\x80", "\x9f", "\ufffe", "\uffff"],
                         ids=["del", "c1-low", "c1-high", "fffe", "ffff"])
def test_task_xml_rejects_control_and_xml_noncharacters(module, tmp_path, char):
    with pytest.raises(acquisition.AcquireError) as caught:
        module.task_xml(tmp_path / ("bad" + char), 8765, tmp_path / "pythonw.exe", tmp_path, "S-1-5-21-100-200-300-1001")
    assert caught.value.code == "invalid_workbench_task"


@pytest.mark.parametrize("token", [None, True, 123, "", "A" * 42, "A" * 44, "?" * 43, "é" * 43, "A" * 42 + "\n"])
def test_bad_config_token_never_posts(module, transport, token):
    transport.get = (200, encoded(config(transport.root, token)))
    with pytest.raises(acquisition.AcquireError):
        module.stop(transport.root)
    assert [c["method"] for c in transport.calls] == ["GET"]
    assert not transport.root.exists()


@pytest.mark.parametrize("raw", [b"{}", b"[]", b"null", b'{"x":1,"x":2}', b'{"nested":{"x":1,"x":2}}',
                              b'{"x":NaN}', b"{} trailing", b"\xff", b" " * (1024 * 1024 + 1)],
                         ids=["empty", "list", "null", "duplicate", "nested-duplicate", "nan", "trailing", "utf8", "limit"])
def test_bad_get_json_never_posts(module, transport, raw):
    transport.get = (200, raw)
    with pytest.raises(acquisition.AcquireError):
        module.stop(transport.root)
    assert [c["method"] for c in transport.calls] == ["GET"]


@pytest.mark.parametrize("status", [301, 403, 503])
def test_unsuccessful_config_status_never_posts(module, transport, status):
    transport.get = (status, transport.get[1])
    with pytest.raises(acquisition.AcquireError):
        module.stop(transport.root)
    assert [c["method"] for c in transport.calls] == ["GET"]


def test_get_connection_error_remains_typed_with_zero_post(module, transport):
    transport.get_error = acquisition.AcquireError("http_result_unknown", b"private")
    with pytest.raises(acquisition.AcquireError) as caught:
        module.stop(transport.root)
    assert caught.value.code == "http_result_unknown"
    assert [c["method"] for c in transport.calls] == ["GET"]


@pytest.mark.parametrize("status,value", [
    (200, {"status": "shutdown_requested", "data_root_id": "bound"}),
    (202, {"status": "stopped", "data_root_id": "bound"}),
    (202, {"status": "shutdown_requested", "data_root_id": "wrong"}),
    (202, {"status": "shutdown_requested", "data_root_id": "bound", "extra": "private"}),
    (202, []), (204, None), (301, {}), (403, {"error": "unknown_private"}),
    (403, {"error": "invalid_token", "extra": "private"}), (500, {"error": "private"}),
])
def test_unverified_post_ack_is_unknown_without_retry(module, transport, status, value):
    if isinstance(value, dict) and value.get("data_root_id") == "bound":
        value = {**value, "data_root_id": acquisition.data_root_id(transport.root)}
    transport.post = (status, encoded(value))
    assert module.stop(transport.root) == {"status": "shutdown_unknown", "error_code": "shutdown_ack_unverified"}
    assert [c["method"] for c in transport.calls] == ["GET", "POST"]
    assert not transport.root.exists()


@pytest.mark.parametrize("raw", [b"", b"\xff", b'{"x":1,"x":2}', b"{} trailing", b'{"x":NaN}', b" " * (1024 * 1024 + 1)],
                         ids=["empty", "utf8", "duplicate", "trailing", "nan", "limit"])
def test_invalid_post_bytes_remain_unknown_without_retry(module, transport, raw):
    transport.post = (202, raw)
    assert module.stop(transport.root)["status"] == "shutdown_unknown"
    assert [c["method"] for c in transport.calls] == ["GET", "POST"]


@pytest.mark.parametrize("error", [acquisition.AcquireError("http_result_unknown", b"private"),
                                 acquisition.AcquireError("response_limit", b"private"), OSError("private"), TimeoutError("private")])
def test_post_connection_failure_is_unknown_without_retry(module, transport, error):
    transport.post_error = error
    assert module.stop(transport.root) == {"status": "shutdown_unknown", "error_code": "shutdown_ack_unverified"}
    assert [c["method"] for c in transport.calls] == ["GET", "POST"]


@pytest.mark.parametrize("status,code", [(403, "invalid_host"), (403, "invalid_origin"), (403, "invalid_token"), (503, "shutdown_unavailable")])
def test_explicit_safe_post_refusal_remains_typed(module, transport, status, code):
    transport.post = (status, encoded({"error": code}))
    with pytest.raises(acquisition.AcquireError) as caught:
        module.stop(transport.root)
    assert caught.value.code == code
    assert [c["method"] for c in transport.calls] == ["GET", "POST"]


def test_stop_sends_one_bound_empty_post_and_only_reports_requested(module, transport):
    outcome = module.stop(transport.root, port=8877)
    assert outcome == {"status": "shutdown_requested", "data_root_id": acquisition.data_root_id(transport.root)}
    assert len(transport.calls) == 2
    post = transport.calls[1]
    assert (post["port"], post["method"], post["path"], post["body"]) == (8877, "POST", "/api/shutdown", b"")
    assert post["headers"] == {"Origin": "http://127.0.0.1:8877", "X-Anatrading-Token": "A" * 43}
    assert post["budget"] <= 5 and not transport.root.exists()


@pytest.mark.parametrize("inherited,advance,budgets", [(None, 9.0, [5.0, 1.0]), (103.0, 2.0, [3.0, 1.0])])
def test_stop_uses_one_deadline_and_restores_inherited_context(module, transport, monkeypatch, inherited, advance, budgets):
    clock, guarded = [100.0], []
    original = acquisition._http
    def http(*args, **kwargs):
        assert acquisition._post_guard.get() is None
        result = original(*args, **kwargs)
        if args[1] == "GET": clock[0] += advance
        return result
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acquisition, "_http", http)
    guard = lambda: guarded.append("forbidden")
    deadline_token = acquisition._deadline.set(inherited)
    guard_token = acquisition._post_guard.set(guard)
    try:
        assert module.stop(transport.root)["status"] == "shutdown_requested"
        assert [c["budget"] for c in transport.calls] == budgets
        assert guarded == [] and acquisition._post_guard.get() is guard and acquisition._deadline.get() == inherited
    finally:
        acquisition._post_guard.reset(guard_token)
        acquisition._deadline.reset(deadline_token)


@pytest.mark.parametrize("stage", ["parameter", "get", "post", "refusal"])
def test_context_restored_when_stop_is_rejected_or_unknown(module, transport, stage):
    sentinel = lambda: None
    deadline = acquisition.time.monotonic() + 60
    deadline_token, guard_token = acquisition._deadline.set(deadline), acquisition._post_guard.set(sentinel)
    try:
        if stage == "parameter":
            with pytest.raises(acquisition.AcquireError): module.stop(transport.root, port=17709)
        elif stage == "get":
            transport.get_error = acquisition.AcquireError("http_result_unknown")
            with pytest.raises(acquisition.AcquireError): module.stop(transport.root)
        elif stage == "post":
            transport.post_error = acquisition.AcquireError("http_result_unknown")
            assert module.stop(transport.root)["status"] == "shutdown_unknown"
        else:
            transport.post = (403, encoded({"error": "invalid_token"}))
            with pytest.raises(acquisition.AcquireError): module.stop(transport.root)
        assert acquisition._deadline.get() == deadline and acquisition._post_guard.get() is sentinel
    finally:
        acquisition._post_guard.reset(guard_token)
        acquisition._deadline.reset(deadline_token)


def test_expired_inherited_deadline_never_gets_or_posts(module, transport, monkeypatch):
    monkeypatch.setattr(module.time, "monotonic", lambda: 100.0)
    token = acquisition._deadline.set(99.0)
    try:
        with pytest.raises(acquisition.AcquireError) as caught: module.stop(transport.root)
        assert caught.value.code == "acquisition_deadline" and transport.calls == []
        assert acquisition._deadline.get() == 99.0
    finally:
        acquisition._deadline.reset(token)


def test_get_consumes_total_deadline_so_post_is_not_started(module, transport, monkeypatch):
    clock, original = [100.0], acquisition._http
    def http(*args, **kwargs):
        result = original(*args, **kwargs)
        clock[0] = 111.0
        return result
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(acquisition, "_http", http)
    with pytest.raises(acquisition.AcquireError) as caught: module.stop(transport.root)
    assert caught.value.code == "acquisition_deadline"
    assert [c["method"] for c in transport.calls] == ["GET"]


def test_same_root_new_session_rejects_old_token_without_reauthentication(module, transport, monkeypatch):
    original, closed_b = acquisition._http, []
    def http(port, method, path, body=b"", headers=None, **kwargs):
        if method == "POST":
            assert headers["X-Anatrading-Token"] == "A" * 43
            if headers["X-Anatrading-Token"] == "B" * 43: closed_b.append(True)
            original(port, method, path, body, headers, **kwargs)
            return 403, encoded({"error": "invalid_token"})
        return original(port, method, path, body, headers, **kwargs)
    monkeypatch.setattr(acquisition, "_http", http)
    with pytest.raises(acquisition.AcquireError) as caught: module.stop(transport.root)
    assert caught.value.code == "invalid_token" and closed_b == []
    assert [c["method"] for c in transport.calls] == ["GET", "POST"]


@pytest.mark.parametrize("status,exit_code", [("shutdown_requested", 0), ("shutdown_unknown", 2)])
def test_cli_stop_runs_before_store_and_has_correct_exit_code(module, tmp_path, monkeypatch, capsys, status, exit_code):
    from anatrading import cli
    calls = []
    expected = {"status": status}
    def stop(root, *, port):
        calls.append((root, port))
        return expected
    def forbidden(*args, **kwargs):
        raise AssertionError("stop command must not construct EvidenceStore")
    monkeypatch.setattr(module, "stop", stop)
    monkeypatch.setattr(cli, "EvidenceStore", forbidden)
    assert cli.main(["--root", str(tmp_path / "unused"), "stop-workbench", "--port", "8877"]) == exit_code
    assert calls == [(tmp_path / "unused", 8877)]
    assert json.loads(capsys.readouterr().out) == expected and not (tmp_path / "unused").exists()


@pytest.fixture
def runner(module, monkeypatch):
    event = threading.Event()
    event.set()
    life = SimpleNamespace(startup_failed=False, shutdown_failed=False, error_occurred=False, shutdown_event=event)
    state = SimpleNamespace(started=True, force_exit=False, lifespan=life, should_exit=False)
    env = SimpleNamespace(server=state, callback=None, config=None, create=None, run_error=None)
    def create_app(root, *, port, on_shutdown):
        env.create = (root, port)
        env.callback = on_shutdown
        return lambda *args: None
    def config(app, **options):
        env.config = options
        return SimpleNamespace(app=app, **options)
    def server(config):
        state.config = config
        def run():
            env.callback()
            if env.run_error is not None:
                raise env.run_error
        state.run = run
        return state
    monkeypatch.setattr(module, "create_app", create_app)
    monkeypatch.setattr(module.uvicorn, "Config", config)
    monkeypatch.setattr(module.uvicorn, "Server", server)
    return env


@pytest.mark.parametrize("flag,value,code", [
    ("started", False, "workbench_start_failed"), ("started", 1, "workbench_start_failed"),
    ("force_exit", True, "workbench_shutdown_failed"), ("force_exit", 0, "workbench_shutdown_failed"),
    ("startup_failed", True, "workbench_shutdown_failed"), ("shutdown_failed", True, "workbench_shutdown_failed"),
    ("error_occurred", True, "workbench_shutdown_failed"), ("shutdown_failed", 0, "workbench_shutdown_failed"),
])
def test_serve_failure_flags_cannot_report_stopped(module, runner, tmp_path, flag, value, code):
    target = runner.server if flag in {"started", "force_exit"} else runner.server.lifespan
    setattr(target, flag, value)
    with pytest.raises(StoreError) as caught: module.serve(tmp_path)
    assert caught.value.code == code


@pytest.mark.parametrize("missing", ["force_exit", "lifespan", "startup_failed", "shutdown_failed", "error_occurred", "shutdown_event"])
def test_missing_lifecycle_evidence_cannot_report_stopped(module, runner, tmp_path, missing):
    target = runner.server if missing in {"force_exit", "lifespan"} else runner.server.lifespan
    delattr(target, missing)
    with pytest.raises(StoreError) as caught: module.serve(tmp_path)
    assert caught.value.code == "workbench_shutdown_failed"


@pytest.mark.parametrize("event", [None, object(), SimpleNamespace(is_set=lambda: False), SimpleNamespace(is_set=lambda: 1)])
def test_uncompleted_or_unreadable_shutdown_event_cannot_report_stopped(module, runner, tmp_path, event):
    runner.server.lifespan.shutdown_event = event
    with pytest.raises(StoreError) as caught: module.serve(tmp_path)
    assert caught.value.code == "workbench_shutdown_failed"


@pytest.mark.parametrize("started,error,code", [
    (False, SystemExit(0), "workbench_start_failed"), (False, SystemExit(3), "workbench_start_failed"),
    (False, OSError("private failure"), "workbench_start_failed"),
    (True, SystemExit(0), "workbench_shutdown_failed"), (True, SystemExit(3), "workbench_shutdown_failed"),
    (True, RuntimeError("private failure"), "workbench_shutdown_failed"),
])
def test_abnormal_server_exit_remains_typed(module, runner, tmp_path, started, error, code):
    runner.server.started, runner.run_error = started, error
    with pytest.raises(StoreError) as caught: module.serve(tmp_path)
    assert caught.value.code == code and "private" not in str(caught.value)


def test_keyboard_interrupt_is_not_claimed_as_normal_drain(module, runner, tmp_path):
    runner.run_error = KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt): module.serve(tmp_path)


def test_owned_serve_requests_same_server_exit_and_checks_complete_lifespan(module, runner, tmp_path):
    assert module.serve(tmp_path, port=8877) == {"status": "stopped"}
    assert runner.server.should_exit is True and runner.server.force_exit is False
    assert runner.create == (tmp_path, 8877)
    assert {key: runner.config[key] for key in ("host", "port", "workers", "loop", "http", "reload", "access_log",
                                               "log_level", "use_colors", "lifespan", "timeout_graceful_shutdown")} == {
        "host": "127.0.0.1", "port": 8877, "workers": 1, "loop": "asyncio", "http": "h11", "reload": False,
        "access_log": False, "log_level": "warning", "use_colors": False, "lifespan": "on", "timeout_graceful_shutdown": None}


def test_real_config_with_none_stdio_uses_explicit_false_without_polluting_default(module, runner, tmp_path, monkeypatch):
    real_config = importlib.import_module("uvicorn.config").Config
    defaults = module.uvicorn.config.LOGGING_CONFIG
    before = deepcopy(defaults)
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    with pytest.raises(ValueError, match="Unable to configure formatter"):
        real_config(lambda *args: None, log_config=deepcopy(defaults), use_colors=None)
    monkeypatch.setattr(module.uvicorn, "Config", real_config)
    assert module.serve(tmp_path) == {"status": "stopped"}
    assert runner.server.config.use_colors is False and defaults == before


@pytest.mark.parametrize("stage", ["app", "config", "server"])
def test_server_initialization_failure_is_start_failed(module, runner, tmp_path, monkeypatch, stage):
    def failed(*args, **kwargs):
        raise ValueError("synthetic private initialization failure")
    if stage == "app": monkeypatch.setattr(module, "create_app", failed)
    elif stage == "config": monkeypatch.setattr(module.uvicorn, "Config", failed)
    else: monkeypatch.setattr(module.uvicorn, "Server", failed)
    with pytest.raises(StoreError) as caught: module.serve(tmp_path)
    assert caught.value.code == "workbench_start_failed"


@pytest.mark.parametrize("code", ["workbench_start_failed", "workbench_shutdown_failed"])
def test_cli_serve_failure_has_safe_nonzero_result(module, tmp_path, monkeypatch, capsys, code):
    from anatrading import cli
    def failed(*args, **kwargs): raise StoreError(code)
    monkeypatch.setattr(module, "serve", failed)
    assert cli.main(["--root", str(tmp_path), "serve"]) == 2
    assert json.loads(capsys.readouterr().out) == {"status": "error", "error_code": code}


@pytest.mark.parametrize("field,value", [
    ("root", "relative"), ("python", "pythonw.exe"), ("working_directory", "relative"),
    ("python", "console"), ("port", True), ("port", 17709), ("port", 0), ("port", 65536),
    ("user_sid", None), ("user_sid", "S-1-5-18"), ("user_sid", "S-1-5-21-1-2-3"),
    ("user_sid", "S-1-5-21-1-2-3-4 trailing"), ("root", "noncanonical"), ("root", "\x00"),
    ("root", "surrogate"),
])
def test_invalid_task_definition_is_typed_without_side_effects(module, tmp_path, field, value):
    arguments = dict(root=tmp_path / "data", port=8765, python=tmp_path / "pythonw.exe",
                     working_directory=tmp_path, user_sid="S-1-5-21-100-200-300-1001")
    if value == "console": value = tmp_path / "python.exe"
    elif value == "noncanonical": value = tmp_path / "middle" / ".." / "data"
    elif value == "surrogate": value = tmp_path / "bad\ud800"
    elif value == "\x00": value = tmp_path / "bad\x00"
    arguments[field] = value
    before = list(tmp_path.iterdir())
    with pytest.raises(acquisition.AcquireError) as caught: module.task_xml(**arguments)
    assert caught.value.code == "invalid_workbench_task" and list(tmp_path.iterdir()) == before


def test_task_xml_is_unregistered_login_definition_with_safe_arguments(module, tmp_path, monkeypatch):
    def forbidden(*args, **kwargs): raise AssertionError("XML must not start processes or issue HTTP")
    monkeypatch.setattr(module.subprocess, "Popen", forbidden)
    monkeypatch.setattr(acquisition, "_http", forbidden)
    root, python = tmp_path / "数据 & Local Root", tmp_path / "Python & Runtime" / "pythonw.exe"
    sid = "S-1-5-21-100-200-300-1001"
    before = list(tmp_path.iterdir())
    xml = module.task_xml(root, 8877, python, tmp_path, sid)
    assert not xml.startswith("<?xml") and "&amp;" in xml
    task, ns = ET.fromstring(xml), {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert task.tag == "{" + ns["t"] + "}Task" and task.attrib == {"version": "1.2"}
    triggers = list(task.find("t:Triggers", ns))
    assert len(triggers) == 1 and triggers[0].tag.endswith("}LogonTrigger")
    assert [(node.tag.split("}")[1], node.text) for node in triggers[0]] == [
        ("Enabled", "true"), ("ExecutionTimeLimit", "PT0S"), ("UserId", sid)]
    principal = task.find("t:Principals/t:Principal", ns)
    assert principal.find("t:UserId", ns).text == sid
    assert principal.find("t:LogonType", ns).text == "InteractiveToken" and principal.find("t:RunLevel", ns).text == "LeastPrivilege"
    settings = {node.tag.split("}")[1]: node.text for node in task.find("t:Settings", ns)}
    assert settings == {"MultipleInstancesPolicy": "IgnoreNew", "AllowHardTerminate": "false", "ExecutionTimeLimit": "PT0S",
        "DisallowStartIfOnBatteries": "false", "StopIfGoingOnBatteries": "false", "RunOnlyIfIdle": "false",
        "RunOnlyIfNetworkAvailable": "false", "WakeToRun": "false", "StartWhenAvailable": "false", "Enabled": "true", "Hidden": "true"}
    action = task.find("t:Actions/t:Exec", ns)
    assert action.find("t:Command", ns).text == str(python) and action.find("t:WorkingDirectory", ns).text == str(tmp_path)
    args = [piece.strip('"') for piece in shlex.split(action.find("t:Arguments", ns).text, posix=False)]
    assert args == ["-X", "utf8", "-m", "anatrading.cli", "--root", str(root), "serve", "--port", "8877"]
    assert list(tmp_path.iterdir()) == before
