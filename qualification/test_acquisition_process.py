"""Real child-process boundaries without importing an SDK or opening a socket."""
import json
import subprocess
import sys

import pytest

from qualification import baostock_acquisition_probe as probe


CHILD = """
import json
from pathlib import Path
import sys
import time

destination = Path(sys.argv[1])
payload = json.loads(sys.argv[2])
if payload is not None:
    (destination / 'status.json').write_text(json.dumps(payload), encoding='utf-8')
time.sleep(float(sys.argv[3]))
"""


@pytest.fixture
def launch_children(monkeypatch, tmp_path):
    original_popen = subprocess.Popen
    children, calls = [], []
    monkeypatch.setattr(probe, "RUNS", tmp_path / "runs")

    def configure(payload, *, delay=0, timeout=5):
        monkeypatch.setitem(probe.CASES, "P01", {**probe.CASES["P01"], "timeout": timeout})

        def launch(command, **kwargs):
            case_name, destination = command[-2:]
            child = original_popen(
                [sys.executable, "-B", "-c", CHILD, destination, json.dumps(payload), str(delay)],
                **kwargs,
            )
            children.append((case_name, child))
            original_wait, original_kill = child.wait, child.kill

            def wait(*args, **options):
                calls.append((case_name, "wait", options.get("timeout")))
                try:
                    code = original_wait(*args, **options)
                except subprocess.TimeoutExpired:
                    calls.append((case_name, "timeout", None))
                    raise
                calls.append((case_name, "waited", code))
                return code

            def kill():
                calls.append((case_name, "kill", None))
                return original_kill()

            child.wait, child.kill = wait, kill
            return child

        monkeypatch.setattr(probe.subprocess, "Popen", launch)
        return children, calls

    yield configure
    for _, child in children:
        if child.poll() is None:
            child.kill()
            child.wait(timeout=5)


def read_status(case_name="P01"):
    runs = list(probe.RUNS.iterdir())
    assert len(runs) == 1
    return json.loads((runs[0] / case_name / "status.json").read_text(encoding="utf-8"))


def test_timeout_kills_waits_for_exit_and_stops_later_cases(launch_children):
    children, calls = launch_children({"status": "running", "phase": "market"}, delay=30, timeout=0.5)
    probe.run(["P01", "P02"])

    assert [name for name, _ in children] == ["P01"]
    assert [event for _, event, _ in calls] == ["wait", "timeout", "kill", "wait", "waited"]
    assert children[0][1].poll() is not None
    assert calls[-1][2] != 0
    status = read_status()
    assert status["process_state"] == "process_timeout"
    assert status["status"] == "incomplete"
    assert status["error_code"] == "worker_incomplete"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "running", "phase": "market"},
        None,
        {"status": "captured"},
        {"status": "captured", "phase": "market"},
    ],
    ids=["running", "missing_status_file", "missing_finished_phase", "unfinished_capture"],
)
def test_zero_exit_without_worker_terminal_is_incomplete(payload, launch_children):
    children, _ = launch_children(payload)
    probe.run(["P01", "P02"])

    assert [name for name, _ in children] == ["P01"]
    assert children[0][1].returncode == 0
    status = read_status()
    assert status["process_state"] == "exited"
    assert status["status"] == "incomplete"
    assert status["error_code"] == "worker_incomplete"


def test_finished_capture_allows_next_case(launch_children):
    children, _ = launch_children({"status": "captured", "phase": "finished"})
    probe.run(["P01", "P02"])

    assert [name for name, _ in children] == ["P01", "P02"]
    assert all(child.returncode == 0 for _, child in children)
    for name in ("P01", "P02"):
        assert read_status(name)["status"] == "captured"


def test_finished_incomplete_preserves_failure_and_stops(launch_children):
    children, _ = launch_children(
        {"status": "incomplete", "phase": "finished", "error_code": "injected_failure"}
    )
    probe.run(["P01", "P02"])

    assert [name for name, _ in children] == ["P01"]
    assert children[0][1].returncode == 0
    status = read_status()
    assert status["status"] == "incomplete"
    assert status["error_code"] == "injected_failure"
