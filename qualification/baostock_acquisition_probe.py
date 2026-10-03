"""Approved bounded acquisition experiments; no product database writes."""
import argparse
import contextlib
from datetime import date, datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
RUNS = ROOT / "artifacts" / "qualification" / "baostock-acquisition"
PROTOCOL_SHA256 = "b63a57eb21a3a5ee57c8e7506363cee0b34e60989593f2bac3e1cd454ea87963"
TRAILER_PROTOCOL_SHA256 = "a9092de5cca0613dfa77822ad8157526496440b17b78da051d08cd44c1867fa3"
DAILY_FIELDS = "date,code,open,high,low,close,volume,amount,adjustflag".split(",")
MINUTE_FIELDS = ["date", "time", *DAILY_FIELDS[1:]]
ASTOCK_FIELDS = "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST".split(",")
CASES = {
    "P01": dict(method="query_history_k_data_plus", code="sh.601577", start_date="2021-01-04",
                end_date="2021-03-31", frequency="5", adjustflag="3", fields=MINUTE_FIELDS,
                request_type="95", response_type="96", max_pages=3, max_rows=6000, timeout=45),
    "P02": dict(method="query_history_k_data_plus", code="sh.601577", start_date="2021-02-27",
                end_date="2021-02-27", frequency="d", adjustflag="3", fields=DAILY_FIELDS,
                request_type="95", response_type="96", max_pages=1, max_rows=2000, timeout=35),
    "P03": dict(method="query_daily_history_k_AStock", date="2026-09-30", fields=ASTOCK_FIELDS,
                request_type="98", response_type="99", max_pages=1, max_rows=20000, timeout=45),
}


class ProbeError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def save(path, content):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _header(text):
    if not isinstance(text, str) or not re.fullmatch(r"[0-9]{2}\.[0-9]\.[0-9]{2}\x01[0-9A-Z]{2}\x01[0-9]{10}", text[:21]):
        raise ProbeError("invalid_envelope")
    return text[8:10]


def inspect_response(raw, case_name, requested_page):
    case = CASES[case_name]
    if _header(raw) != case["response_type"]:
        raise ProbeError("non_market_response")
    parts = raw[21:].split("\x01")
    history = case["response_type"] == "96"
    if len(parts) != (13 if history else 6):
        raise ProbeError("invalid_envelope")
    if parts[0] != "0" or parts[2] != case["method"] or parts[3] != "anonymous":
        raise ProbeError("non_market_response")
    fields = parts[8 if history else 5].split(",")
    if fields != case["fields"]:
        raise ProbeError("response_schema_mismatch")
    if history:
        if (type(requested_page) is not int or not 1 <= requested_page <= case["max_pages"]
                or parts[4] != str(requested_page) or parts[5] != "2000"):
            raise ProbeError("response_page_mismatch")
        identity = dict(zip(("code", "start_date", "end_date", "frequency", "adjustflag"),
                            (parts[7], parts[9], parts[10], parts[11], parts[12])))
        if any(identity[key] != case[key] for key in identity):
            raise ProbeError("response_identity_mismatch")
    else:
        if requested_page is not None:
            raise ProbeError("response_page_mismatch")
        identity = {"date": case["date"]}
    try:
        data = json.loads(parts[6 if history else 4])
    except (ValueError, RecursionError):
        raise ProbeError("invalid_record_body") from None
    if type(data) is not dict or set(data) != {"record"} or type(data["record"]) is not list:
        raise ProbeError("invalid_record_body")
    rows = data["record"]
    if len(rows) > (2000 if history else case["max_rows"]):
        raise ProbeError("row_limit")
    for row in rows:
        if type(row) is not list or len(row) != len(fields) or any(type(cell) is not str for cell in row):
            raise ProbeError("invalid_cells")
        cell = dict(zip(fields, row))
        try:
            parsed_date = date.fromisoformat(cell["date"])
            if parsed_date.isoformat() != cell["date"]:
                raise ValueError
        except ValueError:
            raise ProbeError("invalid_source_date") from None
        if cell["adjustflag"] != "3" or not re.fullmatch(r"(?:sh|sz|bj)\.[0-9]{6}", cell["code"]):
            raise ProbeError("row_identity_mismatch")
        if history:
            if cell["code"] != case["code"] or not case["start_date"] <= cell["date"] <= case["end_date"]:
                raise ProbeError("row_identity_mismatch")
            if case["frequency"] == "5":
                token = cell["time"]
                if not re.fullmatch(r"[0-9]{17}", token) or token[-5:] != "00000" or token[:8] != cell["date"].replace("-", ""):
                    raise ProbeError("invalid_source_time")
                try:
                    datetime.strptime(token[:12], "%Y%m%d%H%M")
                except ValueError:
                    raise ProbeError("invalid_source_time") from None
        elif cell["date"] != case["date"]:
            raise ProbeError("row_identity_mismatch")
    return dict(rows=rows, fields=fields, response_page=requested_page, source_identity=identity)


def inspect_request(message, case_name, expected_page):
    request_type = _header(message)
    body = message[21:].rsplit("\x01", 1)[0].split("\x01")
    if body[0] == "login":
        if request_type != "00" or body != ["login", "anonymous", "123456", "0"]:
            raise ProbeError("request_not_allowed")
        return "login"
    if body[0] == "logout":
        if request_type != "02" or len(body) != 3 or body[1] != "anonymous" or not re.fullmatch("[0-9]{14}", body[2]):
            raise ProbeError("request_not_allowed")
        return "logout"
    case = CASES[case_name]
    if case["response_type"] == "96":
        expected = [case["method"], "anonymous", str(expected_page), "2000", case["code"],
                    ",".join(case["fields"]), case["start_date"], case["end_date"], case["frequency"], "3"]
    else:
        expected = [case["method"], "anonymous", case["date"]]
    if request_type != case["request_type"] or body != expected or expected_page > case["max_pages"]:
        raise ProbeError("request_not_allowed")
    return "market"


def run_query(case_name, sdk, pages):
    case = CASES[case_name]
    if case["response_type"] == "96":
        arguments = {key: case[key] for key in ("code", "start_date", "end_date", "frequency", "adjustflag")}
        result = sdk.query_history_k_data_plus(fields=",".join(case["fields"]), **arguments)
    else:
        result = sdk.query_daily_history_k_AStock(date=case["date"])
    count, page_index, seen, previous = 0, 0, set(), None
    sdk_flags = []
    while True:
        if result is None or getattr(result, "error_code", None) != "0":
            raise ProbeError("sdk_query_error")
        if len(pages) != page_index + 1:
            raise ProbeError("missing_or_extra_response")
        page = pages[page_index]
        history = case["response_type"] == "96"
        if page["response_page"] != (page_index + 1 if history else None):
            raise ProbeError("response_page_mismatch")
        if result.fields != page["fields"] or result.data != page["rows"]:
            raise ProbeError("sdk_cells_mismatch")
        rows = page["rows"]
        sdk_flags.append(getattr(result, "adjustflag", None))
        count += len(rows)
        if count > case["max_rows"]:
            raise ProbeError("row_limit")
        for row in rows:
            cell = dict(zip(page["fields"], row))
            key = (cell["date"], cell.get("time", ""), cell["code"])
            if key in seen:
                raise ProbeError("duplicate_source_label")
            if history and previous is not None and key < previous:
                raise ProbeError("source_order")
            seen.add(key)
            previous = key
        page_index += 1
        if not history or len(rows) < 2000:
            state = "empty_observed" if count == 0 else "protocol_end_observed" if history else "single_response_observed"
            return dict(query_state=state, row_count=count, page_count=page_index, coverage="unverified",
                        row_limit_reached=count == case["max_rows"],
                        sdk_top_level_adjustflags=sdk_flags)
        if page_index >= case["max_pages"]:
            raise ProbeError("bounded_incomplete")
        result.cur_row_num = len(result.data)
        has_next = result.next()
        if len(pages) != page_index + 1:
            raise ProbeError("missing_or_extra_response")
        if not has_next and (pages[-1]["rows"] or getattr(result, "error_code", None) != "0"):
            raise ProbeError("unexpected_sdk_end")


def worker(case_name, destination):
    import baostock as sdk
    import baostock.common.context as context
    import baostock.common.contants as constants
    import baostock.util.socketutil as transport
    from baostock_transport import BoundedTransportError, bounded_send

    case = CASES[case_name]
    status = dict(case=case_name, status="running", phase="login", started_at=utcnow(),
                  sdk=importlib.metadata.version("baostock"), python=platform.python_version(), protocol_sha256=PROTOCOL_SHA256,
                  trailer_protocol_sha256=TRAILER_PROTOCOL_SHA256,
                  endpoint=[constants.BAOSTOCK_SERVER_IP, constants.BAOSTOCK_SERVER_PORT],
                  evidence_kind="decoded_response_bounded_transport_not_wire", requests=0, pages=[])
    status["code_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in (Path(__file__), Path(__file__).with_name("baostock_transport.py"))}
    sdk_root = Path(sdk.__file__).parent
    status["sdk_hashes"] = {relative: hashlib.sha256((sdk_root / relative).read_bytes()).hexdigest()
                            for relative in ("security/history.py", "data/resultset.py", "util/socketutil.py", "login/loginout.py",
                                             "common/contants.py", "common/context.py", "data/messageheader.py")}
    save(destination / "request.json", case)
    save(destination / "status.json", status)
    pages, log = [], io.StringIO()
    original_send, logged_in = transport.send_msg, False

    def exchange(message):
        expected_page = len(pages) + 1
        kind = inspect_request(message, case_name, expected_page)
        before = utcnow()
        if kind == "market":
            status["requests"] += 1
            save(destination / "status.json", status)
        response = bounded_send(getattr(context, "default_socket", None), message)
        after = utcnow()
        if kind != "market":
            if _header(response) != {"login": "01", "logout": "03"}[kind]:
                raise ProbeError("unexpected_control_response")
            return response
        page = inspect_response(response, case_name, expected_page if case["response_type"] == "96" else None)
        raw = response.encode("utf-8")
        path = destination / f"page-{expected_page:03d}-decoded.txt"
        path.write_bytes(raw)
        pages.append(page)
        status["pages"].append(dict(capture_ordinal=expected_page, response_page=page["response_page"],
                                    started_at=before, observed_at=after, bytes=len(raw),
                                    sha256=hashlib.sha256(raw).hexdigest(), row_count=len(page["rows"]),
                                    source_identity=page["source_identity"], filename=path.name))
        save(destination / "status.json", status)
        return response

    socket.setdefaulttimeout(8)
    try:
        if status["sdk"] != "0.9.4" or getattr(context, "apiKey", "0") != "0":
            raise ProbeError("unapproved_sdk_or_credentials")
        transport.send_msg = exchange
        with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
            login = sdk.login()
            if getattr(login, "error_code", None) != "0":
                raise ProbeError("login_failed")
            logged_in = True
            status["phase"] = "market"
            save(destination / "status.json", status)
            outcome = run_query(case_name, sdk, pages)
        status.update(outcome, status="captured")
    except (ProbeError, BoundedTransportError) as error:
        status.update(status="incomplete", error_code=error.code)
        if error.code == "bounded_incomplete":
            status["query_state"] = "bounded_incomplete"
    except Exception as error:
        status.update(status="incomplete", error_code="unexpected_worker_error", exception_type=type(error).__name__)
    finally:
        status["query_finished_at"] = utcnow()
        save(destination / "status.json", status)
        if logged_in:
            status["phase"] = "logout"
            save(destination / "status.json", status)
            with contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                try:
                    logout = sdk.logout()
                    if getattr(logout, "error_code", None) != "0":
                        status.update(status="incomplete", cleanup_error="logout_failed")
                except Exception:
                    status.update(status="incomplete", cleanup_error="logout_failed")
        transport.send_msg = original_send
        connection = getattr(context, "default_socket", None)
        if connection is not None:
            connection.close()
        status["phase"] = "finished"
        status["finished_at"] = utcnow()
        save(destination / "status.json", status)


def run(cases):
    if importlib.metadata.version("baostock") != "0.9.4":
        raise SystemExit("This protocol requires baostock==0.9.4.")
    protocol = ROOT / "docs" / "qualification" / "AUTOMATIC_ACQUISITION_PROTOCOL.md"
    if hashlib.sha256(protocol.read_bytes()).hexdigest() != PROTOCOL_SHA256:
        raise SystemExit("The reviewed acquisition protocol fingerprint changed.")
    amendment = ROOT / "docs" / "qualification" / "BOUNDED_TRAILER_AMENDMENT.md"
    if hashlib.sha256(amendment.read_bytes()).hexdigest() != TRAILER_PROTOCOL_SHA256:
        raise SystemExit("The reviewed trailer protocol fingerprint changed.")
    folder = RUNS / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder.mkdir(parents=True)
    for case_name in cases:
        destination = folder / case_name
        destination.mkdir()
        process = subprocess.Popen([sys.executable, "-X", "utf8", __file__, "--worker", case_name, str(destination)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            process.wait(timeout=CASES[case_name]["timeout"])
            process_state = "exited" if process.returncode == 0 else "nonzero_exit"
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
            process_state = "process_timeout"
        path = destination / "status.json"
        status = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        status["process_state"] = process_state
        if (process_state != "exited" or status.get("phase") != "finished"
                or status.get("status") not in {"captured", "incomplete"}):
            status.update(status="incomplete", error_code="worker_incomplete")
        save(path, status)
        print(json.dumps(dict(case=case_name, directory=str(destination), status=status), ensure_ascii=False), flush=True)
        if status.get("status") != "captured":
            break


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--worker":
        worker(sys.argv[2], Path(sys.argv[3]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument("--case", action="append", choices=CASES)
        arguments = parser.parse_args()
        run(list(dict.fromkeys(arguments.case or CASES)))
