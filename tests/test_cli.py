"""Exercise the same installed-module command boundary used from PowerShell."""
import json
import os
from pathlib import Path
import subprocess
import sys


PROJECT = Path(__file__).resolve().parents[1]


def run_cli(*args):
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(PROJECT / "src")
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "anatrading.cli", *map(str, args)],
                          cwd=PROJECT, env=environment, capture_output=True, text=True,
                          encoding="utf-8", timeout=20)


def test_import_query_export_backup_and_restore_from_cli(tmp_path):
    source = tmp_path / "synthetic.txt"
    source.write_bytes(("601577 合成测试 1分钟线 不复权\r\n"
                        "日期\t时间\t开盘\t最高\t最低\t收盘\t成交量\t成交额\r\n"
                        "2021/02/26,0931,10.00,11.00,9.00,10.01,101,1011.01\r\n"
                        "数据来源:通达信\r\n").encode("gbk"))
    root = tmp_path / "local"
    imported = run_cli("--root", root, "import", source, "--format", "tdx-public-text-v1")
    assert imported.returncode == 0, imported.stderr
    attempt = json.loads(imported.stdout)
    assert attempt["status"] == "committed"
    snapshot = attempt["snapshot_id"]
    query = run_cli("--root", root, "query", snapshot, "--cutoff", "2021-02-26T09:31")
    assert query.returncode == 0, query.stderr
    expected = json.loads(query.stdout)
    assert expected["rows"][0]["values"]["volume"] == "101"
    exported = run_cli("--root", root, "export", snapshot, "--format", "json", "--cutoff", "2021-02-26T09:31")
    assert exported.returncode == 0, exported.stderr
    path = Path(json.loads(exported.stdout)["path"])
    assert json.loads(path.read_bytes()) == expected
    backup = tmp_path / "backup"
    backed_up = run_cli("--root", root, "backup", backup)
    assert backed_up.returncode == 0, backed_up.stderr
    restored_root = tmp_path / "restored"
    restored = run_cli("restore", backup, restored_root)
    assert restored.returncode == 0, restored.stderr
    restored_view = run_cli("--root", restored_root, "query", snapshot, "--cutoff", "2021-02-26T09:31")
    assert restored_view.returncode == 0, restored_view.stderr
    assert json.loads(restored_view.stdout) == expected
    assert json.loads(run_cli("--root", root, "snapshots").stdout)[0]["snapshot_id"] == snapshot
    assert json.loads(run_cli("--root", root, "attempts").stdout)[0]["status"] == "committed"


def test_rejected_input_has_nonzero_exit_and_machine_readable_reason(tmp_path):
    source = tmp_path / "bad.day"
    source.write_bytes(b"truncated")
    result = run_cli("--root", tmp_path / "local", "import", source, "--format", "tdx-public-day-v1")
    assert result.returncode == 2
    assert json.loads(result.stdout)["status"] == "rejected"
    assert json.loads(result.stdout)["error_code"] == "invalid_day_length"
    assert not result.stderr


def test_unknown_snapshot_is_a_typed_error_without_traceback(tmp_path):
    result = run_cli("--root", tmp_path / "local", "query", "0" * 64)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "error", "error_code": "snapshot_not_found"}
    assert "Traceback" not in result.stdout + result.stderr


def test_acquisition_rejects_future_target_before_creating_data_root(tmp_path):
    root = tmp_path / "unused"
    result = run_cli("--root", root, "acquire-tdx", "--client-directory", tmp_path / "no-client",
                     "--symbol", "600059.SH", "--target-date", "2999-01-01")
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "error", "error_code": "invalid_target_date"}
    assert not root.exists() and not result.stderr


def test_acquisition_help_describes_explicit_daily_task(tmp_path):
    result = run_cli("acquire-tdx", "--help")
    assert result.returncode == 0
    assert all(option in result.stdout for option in ("--client-directory", "--symbol", "--target-date", "--port"))


def test_schedule_rejects_duplicate_plan_without_opening_store(tmp_path):
    plan = tmp_path / "ambiguous-plan.json"
    plan.write_bytes(b'{"schema":1,"schema":1}')
    root = tmp_path / "unused"
    result = run_cli("--root", root, "acquire-tdx-due", "--plan", plan)
    assert result.returncode == 2
    assert json.loads(result.stdout) == {"status": "error", "error_code": "invalid_response"}
    assert not root.exists() and not result.stderr
