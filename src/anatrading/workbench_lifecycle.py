"""Owned graceful exit and an unregistered Windows login-task definition."""
from copy import deepcopy
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET

import uvicorn

from . import tdx_acquisition as acquisition
from .store import StoreError
from .workbench import create_app


_PATH_CONTROLS = re.compile(r"[\x00-\x1f\x7f-\x9f\ufffe\uffff]")


def serve(root, *, port=8765):
    server = None

    def request_exit():
        server.should_exit = True

    try:
        app = create_app(root, port=port, on_shutdown=request_exit)
        config = uvicorn.Config(app, host="127.0.0.1", port=port, workers=1, loop="asyncio", http="h11",
                                reload=False, access_log=False, log_level="warning", use_colors=False,
                                lifespan="on", timeout_graceful_shutdown=None,
                                log_config=deepcopy(uvicorn.config.LOGGING_CONFIG))
        server = uvicorn.Server(config)
        print(f"准备启动 Anatrading：http://127.0.0.1:{port}", flush=True)
        server.run()
    except (SystemExit, Exception):
        started = server is not None and getattr(server, "started", None) is True
        raise StoreError("workbench_shutdown_failed" if started else "workbench_start_failed") from None
    if getattr(server, "started", None) is not True:
        raise StoreError("workbench_start_failed")
    try:
        life = server.lifespan
        complete = (server.force_exit is False
                    and all(getattr(life, flag, None) is False for flag in
                            ("startup_failed", "shutdown_failed", "error_occurred"))
                    and life.shutdown_event.is_set() is True)
    except Exception:
        complete = False
    if not complete:
        raise StoreError("workbench_shutdown_failed")
    return {"status": "stopped"}


def _control(root, port):
    if type(port) is not int or not 1 <= port <= 65535 or port == 17709:
        raise acquisition.AcquireError("invalid_workbench_control")
    try:
        root = Path(root).resolve()
        if _PATH_CONTROLS.search(str(root)):
            raise ValueError
        identity = acquisition.data_root_id(root)
    except (OSError, ValueError, TypeError):
        raise acquisition.AcquireError("invalid_workbench_control") from None
    return root, identity


def stop(root, *, port=8765):
    inherited = acquisition._deadline.get()
    deadline = time.monotonic() + 10
    deadline_token = acquisition._deadline.set(min(inherited, deadline) if inherited is not None else deadline)
    guard_token = acquisition._post_guard.set(None)
    try:
        root, root_id = _control(root, port)
        config = acquisition._config(root, port, budget=5)
        token = config["csrf_token"]
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", token) is None:
            raise acquisition.AcquireError("workbench_identity_mismatch")
        acquisition._remaining()
        unknown = {"status": "shutdown_unknown", "error_code": "shutdown_ack_unverified"}
        try:
            status, raw = acquisition._request(port, "POST", "/api/shutdown", b"",
                                               {"Origin": f"http://127.0.0.1:{port}",
                                                "X-Anatrading-Token": token}, budget=5)
            reply = acquisition._decode_json(raw)
        except acquisition.AcquireError as error:
            if error.code == "acquisition_deadline":
                raise
            return unknown
        except OSError:
            return unknown
        if (status == 202 and type(reply) is dict and set(reply) == {"status", "data_root_id"}
                and reply["status"] == "shutdown_requested" and reply["data_root_id"] == root_id):
            return reply
        if type(reply) is dict and set(reply) == {"error"} and type(reply["error"]) is str:
            code = reply["error"]
            if ((status == 403 and code in {"invalid_host", "invalid_origin", "invalid_token"})
                    or (status == 503 and code == "shutdown_unavailable")):
                raise acquisition.AcquireError(code)
        return unknown
    finally:
        acquisition._post_guard.reset(guard_token)
        acquisition._deadline.reset(deadline_token)


def task_xml(root, port, python, working_directory, user_sid):
    try:
        root, python, working_directory = (Path(value) for value in (root, python, working_directory))
        for path in (root, python, working_directory):
            text = str(path)
            text.encode("utf-8")
            if not path.is_absolute() or path.resolve() != path or _PATH_CONTROLS.search(text):
                raise ValueError
        _control(root, port)
        if (python.name.casefold() != "pythonw.exe" or type(user_sid) is not str
                or re.fullmatch(r"S-1-5-21-(?:[0-9]+-){3}[0-9]+", user_sid) is None):
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise acquisition.AcquireError("invalid_workbench_task") from None
    namespace = "http://schemas.microsoft.com/windows/2004/02/mit/task"
    ET.register_namespace("", namespace)
    task = ET.Element(f"{{{namespace}}}Task", version="1.2")

    def element(parent, name, text=None, **attributes):
        child = ET.SubElement(parent, f"{{{namespace}}}{name}", **attributes)
        child.text = text
        return child

    trigger = element(element(task, "Triggers"), "LogonTrigger")
    for name, value in (("Enabled", "true"), ("ExecutionTimeLimit", "PT0S"), ("UserId", user_sid)):
        element(trigger, name, value)
    principal = element(element(task, "Principals"), "Principal", id="CurrentUser")
    for name, value in (("UserId", user_sid), ("LogonType", "InteractiveToken"), ("RunLevel", "LeastPrivilege")):
        element(principal, name, value)
    settings = element(task, "Settings")
    for name, value in (("MultipleInstancesPolicy", "IgnoreNew"), ("AllowHardTerminate", "false"),
                        ("ExecutionTimeLimit", "PT0S"), ("DisallowStartIfOnBatteries", "false"),
                        ("StopIfGoingOnBatteries", "false"), ("RunOnlyIfIdle", "false"),
                        ("RunOnlyIfNetworkAvailable", "false"), ("WakeToRun", "false"),
                        ("StartWhenAvailable", "false"), ("Enabled", "true"), ("Hidden", "true")):
        element(settings, name, value)
    action = element(element(task, "Actions", Context="CurrentUser"), "Exec")
    element(action, "Command", str(python))
    element(action, "Arguments", subprocess.list2cmdline(["-X", "utf8", "-m", "anatrading.cli", "--root",
                                                         str(root), "serve", "--port", str(port)]))
    element(action, "WorkingDirectory", str(working_directory))
    return ET.tostring(task, encoding="unicode", xml_declaration=False)
