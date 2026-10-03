"""Regression preconditions for safe capture of additional market methods."""
import json
import sys
from types import SimpleNamespace

import pytest

from qualification.baostock_acquisition_probe import ProbeError, inspect_response


def history_response(*, user="anonymous", fields=None, record=None, flag="3"):
    fields = fields or ["date", "code", "open", "high", "low", "close", "volume", "amount", "adjustflag"]
    rows = [] if record is None else [record]
    body = "\x01".join(["0", "success", "query_history_k_data_plus", user, "1", "2000",
                          json.dumps({"record": rows}), "sh.601577", ",".join(fields),
                          "2021-02-27", "2021-02-27", "d", flag])
    return "00.9.10\x0196\x01" + f"{len(body):010d}" + body


def test_private_user_response_is_rejected_without_echo():
    with pytest.raises(ProbeError) as caught:
        inspect_response(history_response(user="PRIVATE_AUTH_MARKER"), "P02", 1)
    assert "PRIVATE_AUTH_MARKER" not in str(caught.value)
    assert caught.value.code.isascii()


def test_missing_final_flag_is_not_recovered_from_the_request():
    with pytest.raises(ProbeError):
        inspect_response(history_response(flag=""), "P02", 1)


def test_null_cell_is_not_silently_converted_to_zero():
    row = ["2021-02-27", "sh.601577", "10", "11", "9", "10", None, "1000", "3"]
    with pytest.raises(ProbeError):
        inspect_response(history_response(record=row), "P02", 1)


def test_an_empty_valid_response_preserves_unknown_coverage():
    response = inspect_response(history_response(), "P02", 1)
    assert response["rows"] == []
    assert response["response_page"] == 1


@pytest.mark.parametrize("channel", ["login", "logout", "history", "batch"])
def test_worker_never_persists_control_payload_or_sdk_console_text(tmp_path, monkeypatch, capsys, channel):
    import baostock as sdk
    import baostock.common.context as context
    import baostock.util.socketutil as transport
    from qualification import baostock_transport, baostock_acquisition_probe as probe

    marker = "SYNTHETIC_CONTROL_MARKER_NEVER_ARCHIVE"
    monkeypatch.setitem(sys.modules, "baostock_transport", baostock_transport)
    monkeypatch.setattr(context, "apiKey", "0", raising=False)
    monkeypatch.setattr(context, "default_socket", SimpleNamespace(close=lambda: None), raising=False)

    def envelope(kind, fields):
        body = "\x01".join(fields)
        return f"00.9.10\x01{kind}\x01{len(body):010d}" + body

    def send(_socket, message):
        method = message[21:].split("\x01")[0]
        if method in {"login", "logout"}:
            return envelope("01" if method == "login" else "03", ["0", "success", method, "anonymous", marker])
        if channel in {"history", "batch"}:
            return envelope("01", ["0", "success", "login", "anonymous", marker])
        return history_response()

    monkeypatch.setattr(baostock_transport, "bounded_send", send)

    def control(method):
        print(marker)
        body = ["login", "anonymous", "123456", "0"] if method == "login" else ["logout", "anonymous", "20261004020000"]
        transport.send_msg(envelope("00" if method == "login" else "02", body) + "\x011")
        return SimpleNamespace(error_code="0")

    def historical(**request):
        body = ["query_history_k_data_plus", "anonymous", "1", "2000", request["code"], request["fields"],
                request["start_date"], request["end_date"], request["frequency"], request["adjustflag"]]
        transport.send_msg(envelope("95", body) + "\x011")
        return SimpleNamespace(error_code="0", fields=probe.DAILY_FIELDS, data=[], adjustflag="")

    def batch(**request):
        transport.send_msg(envelope("98", ["query_daily_history_k_AStock", "anonymous", request["date"]]) + "\x011")
        raise AssertionError("The control response must be rejected before SDK processing")

    monkeypatch.setattr(sdk, "login", lambda: control("login"))
    monkeypatch.setattr(sdk, "logout", lambda: control("logout"))
    monkeypatch.setattr(sdk, "query_history_k_data_plus", historical)
    monkeypatch.setattr(sdk, "query_daily_history_k_AStock", batch)
    probe.worker("P03" if channel == "batch" else "P02", tmp_path)
    status = json.loads((tmp_path / "status.json").read_bytes())
    assert status["status"] == ("incomplete" if channel in {"history", "batch"} else "captured")
    assert len(list(tmp_path.glob("page-*-decoded.txt"))) == (0 if channel in {"history", "batch"} else 1)
    output = capsys.readouterr()
    assert marker not in output.out + output.err
    for path in tmp_path.rglob("*"):
        if path.is_file():
            assert marker.encode("ascii") not in path.read_bytes(), path.name
