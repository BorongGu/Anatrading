"""Bounded G1 evidence capture; not a production connector."""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import io
import json
import platform
from pathlib import Path
import socket
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1] / "artifacts" / "qualification"
CASES = {
    "daily-overlap": ("sz.000001", "2021-05-13", "2021-05-14", "d"),
    "minute-overlap": ("sh.601577", "2021-02-26", "2021-02-26", "5"),
    "minute-recent": ("sh.601577", "2026-09-30", "2026-09-30", "5"),
    "daily-bank-overlap": ("sh.601577", "2021-02-26", "2021-02-26", "d"),
    "daily-bank-recent": ("sh.601577", "2026-09-30", "2026-09-30", "d"),
}


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def save(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def sample_state(result, fields, page_limit):
    if result.error_code != "0":
        return "sdk_query_error"
    if result.fields != fields:
        return "field_mismatch"
    if not isinstance(result.data, list):
        return "invalid_rows"
    if not result.data:
        return "empty_result"
    if len(result.data) >= page_limit:
        return "pagination_unverified"
    if any(not isinstance(row, list) or len(row) != len(fields)
           or any(type(cell) is not str for cell in row) for row in result.data):
        return "non_string_or_invalid_cells"
    return "captured_sample_not_qualified"


def worker(case, dest):
    import baostock as bs
    import baostock.common.context as ctx
    import baostock.common.contants as cons
    import baostock.util.socketutil as transport

    code, start, end, frequency = CASES[case]
    fields = "date," + ("time," if frequency != "d" else "")
    fields += "code,open,high,low,close,volume,amount,adjustflag"
    request = dict(code=code, fields=fields, start_date=start, end_date=end,
                   frequency=frequency, adjustflag="3")
    save(dest / "request.json", request)
    sdk_dir = Path(bs.__file__).parent
    status = dict(case=case, started_at=utcnow(), phase="login", status="running",
                  python=platform.python_version(), sdk=importlib.metadata.version("baostock"),
                  endpoint=[cons.BAOSTOCK_SERVER_IP, cons.BAOSTOCK_SERVER_PORT],
                  evidence_kind="sdk_decoded_response_not_wire_bytes",
                  sdk_hashes={str(p.relative_to(sdk_dir)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in [sdk_dir / "util/socketutil.py", sdk_dir / "data/resultset.py",
                                        sdk_dir / "security/history.py", sdk_dir / "login/loginout.py"]})
    log = io.StringIO()
    connected = False
    original_send = transport.send_msg

    def capture_market(msg):
        method = msg[cons.MESSAGE_HEADER_LENGTH:].split(cons.MESSAGE_SPLIT)[0]
        if method != "query_history_k_data_plus":
            raise ValueError("method outside fixed market whitelist")
        response = original_send(msg)
        if isinstance(response, str):
            raw = response.encode("utf-8")
            (dest / "market-sdk-decoded.txt").write_bytes(raw)
            status["response_sha256"] = hashlib.sha256(raw).hexdigest()
        return response

    save(dest / "status.json", status)
    socket.setdefaulttimeout(8)
    try:
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            if getattr(ctx, "apiKey", "0") != "0":
                raise ValueError("this probe permits anonymous public access only")
            login = bs.login()
            status["login_error_code"] = login.error_code
            if login.error_code != "0":
                status["status"] = "login_failed"
                return
            connected = True
            status["phase"] = "market_query"
            save(dest / "status.json", status)
            transport.send_msg = capture_market
            result = bs.query_history_k_data_plus(**request)
            status["query_error_code"] = result.error_code
            status["status"] = sample_state(result, fields.split(","), cons.BAOSTOCK_PER_PAGE_COUNT)
            status["row_count"] = len(result.data) if isinstance(result.data, list) else None
            status["response_identity"] = {k: getattr(result, k) for k in
                                           ["code", "start_date", "end_date", "frequency", "adjustflag"]}
            save(dest / "sdk-cells.json", {"fields": result.fields, "rows": result.data})
    except Exception as exc:
        status["status"] = "exception"
        status["exception_type"] = type(exc).__name__
        status["errno"] = getattr(exc, "errno", None)
        status["winerror"] = getattr(exc, "winerror", None)
    finally:
        transport.send_msg = original_send
        # Persist the query outcome before logout can block.
        status["query_finished_at"] = utcnow()
        save(dest / "status.json", status)
        if connected:
            status["phase"] = "logout"
            save(dest / "status.json", status)
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                try:
                    logout = bs.logout()
                    status["logout_error_code"] = getattr(logout, "error_code", None)
                except Exception as exc:
                    status["logout_exception_type"] = type(exc).__name__
        sock = getattr(ctx, "default_socket", None)
        if sock is not None:
            sock.close()
        output = log.getvalue()
        status["diagnostic_flags"] = [label for label, text in [
            ("socket_timeout", "timed out"), ("connection_failed", "服务器连接失败"),
            ("receive_failed", "接收数据异常")] if text in output]
        status["finished_at"] = utcnow()
        save(dest / "status.json", status)


def run(cases):
    try:
        sdk_version = importlib.metadata.version("baostock")
    except importlib.metadata.PackageNotFoundError:
        raise SystemExit("Install qualification/requirements.txt in a virtual environment first.")
    if sdk_version != "0.9.4":
        raise SystemExit("This qualification protocol requires baostock==0.9.4.")
    run_dir = ROOT / "baostock" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir.mkdir(parents=True)
    for case in cases:
        dest = run_dir / case
        dest.mkdir()
        try:
            result = subprocess.run([sys.executable, "-X", "utf8", __file__, "--worker", case, str(dest)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=35)
            process_state = "exited" if result.returncode == 0 else "nonzero_exit"
        except subprocess.TimeoutExpired:
            process_state = "process_timeout"
        status_file = dest / "status.json"
        status = json.loads(status_file.read_text(encoding="utf-8")) if status_file.exists() else {}
        status["process_state"] = process_state
        if process_state != "exited":
            status["status"] = "incomplete_process"
        save(status_file, status)
        print(json.dumps({"case": case, "status": status, "directory": str(dest)}, ensure_ascii=False), flush=True)
        if status.get("login_error_code") != "0" or process_state != "exited":
            break


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--case", choices=CASES, action="append", help="Repeat to select fixed cases; default: all.")
        args = parser.parse_args()
        run(list(dict.fromkeys(args.case or CASES)))
