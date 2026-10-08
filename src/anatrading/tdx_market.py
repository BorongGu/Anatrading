"""Read a single minute series from the installed client's local interface."""
import json
from pathlib import Path

from .formats import _tdx_http_request
from . import tdx_acquisition as acquisition


def read_minutes(client_directory, symbol, *, count=720, end_time=""):
    request = dict(id=1, method="get_market_data", params=dict(stock_list=[symbol], period="1m",
                   end_time=end_time, count=count, dividend_type="none", fill_data=False))
    _tdx_http_request(request)
    acquisition._client_identity(Path(client_directory).resolve())
    body = json.dumps(request, separators=(",", ":")).encode("utf-8")
    status, response = acquisition._http(17709, "POST", "/", body,
                                         {"Content-Type": "application/json"}, budget=10)
    if status != 200:
        raise acquisition.AcquireError("http_result_unknown", response)
    try:
        bundle = dict(request_utf8=body.decode("utf-8"), response_utf8=response.decode("utf-8"))
    except UnicodeError:
        raise acquisition.AcquireError("invalid_response", response) from None
    return json.dumps(bundle, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
