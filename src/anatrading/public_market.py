"""Pure, bounded Tencent/Sina capture contracts; no network or source execution.

Request shape, capture bytes and interpretation are separate from acquisition
clock/budget diagnostics. This module never reads a clock, environment or file.
"""
import base64
import binascii
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import hashlib
import json
import math
import re
from urllib.parse import urlencode

from .models import DecodeError, NonMarketPayload, VERSIONS


PUBLIC_FORMAT_IDS = ("tencent-daily-capture-v1", "sina-minute-capture-v1")
CAPTURE_VERSION = "public-market-capture-v1"
LEGACY_CAPTURE_VERSION = "public-market-legacy-reconstruction-v1"
DECODE_CONTRACT_VERSION = "1"
MAX_BODY_BYTES = 1024 * 1024
MAX_CAPTURE_BYTES = 2 * 1024 * 1024
MAX_HEADER_BYTES = 64 * 1024
MAX_HEADER_FIELDS = 100
MAX_JSON_DEPTH = 32
SOURCE_URLS = {
    "tencent": "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
    "sina": "https://quotes.sina.cn/cn/api/jsonp_v2.php/=/CN_MarketDataService.getKLineData",
}
REQUEST_HEADERS = {"Accept": "*/*", "Accept-Encoding": "identity"}
_TENCENT_R = "0.8205512681390605"
_SINA_PREFIX = "/*<script>location.href='//sina.com';</script>*/\n=("
_CAPTURE_KEYS = {"capture_version", "source", "request", "request_sha256", "response",
                 "response_headers_sha256", "body_base64", "body_sha256"}
_HASH = re.compile(r"[0-9a-f]{64}")
_SYMBOL = re.compile(r"([0-9]{6})\.(SH|SZ)")
_SOURCE_SYMBOL = re.compile(r"(sh|sz)([0-9]{6})")
_COUNT = re.compile(r"[1-9][0-9]{0,3}")
_LEGACY_FLAGS = {"capture_mode": "legacy_reconstruction", "header_cardinality": "unrecorded",
                 "transport_evidence": "not_established"}
_PROVENANCE_KEYS = {*_LEGACY_FLAGS, "original_manifest_sha256", "capture_script_sha256"}
_TENCENT_ATTRIBUTE_KEYS = {"NoProfit", "WeightedVotingRights", "IsVIE", "IsRegistration"}


@dataclass(frozen=True)
class ValidatedCapture:
    envelope: dict
    body: bytes
    source: str
    symbol: str
    period: str
    count: int
    start: str | None
    end: str | None
    payload: list


def _error(code="invalid_public_capture"):
    raise DecodeError(code) from None


def _walk_json(value, depth=0):
    if depth > MAX_JSON_DEPTH:
        _error("public_json_depth")
    if type(value) is str:
        try:
            value.encode("utf-8", "strict")
        except UnicodeError:
            _error("invalid_public_json")
    elif type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                _error("invalid_public_json")
            _walk_json(key, depth + 1)
            _walk_json(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _walk_json(item, depth + 1)
    elif type(value) not in (int, bool, type(None), Decimal, float):
        _error("invalid_public_json")
    elif (type(value) is Decimal and not value.is_finite()
          or type(value) is float and not math.isfinite(value)):
        _error("invalid_public_json")


def canonical_json(value) -> bytes:
    """Canonical JSON for envelopes/plans; never canonicalize source entities."""
    try:
        _walk_json(value)
        return json.dumps(value, sort_keys=True, ensure_ascii=False,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (TypeError, ValueError, UnicodeError, RecursionError, ArithmeticError):
        _error("invalid_public_json")


def _strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite")

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_float=Decimal,
                           parse_constant=constant)
        _walk_json(value)
        return value
    except (TypeError, ValueError, UnicodeError, RecursionError, ArithmeticError):
        _error("invalid_public_json")


def _iso_date(value):
    try:
        if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            raise ValueError
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        _error("invalid_public_request_date")


def build_request(source, symbol, period, *, start=None, end=None, count=None) -> dict:
    """Build a format-bounded request. Smaller CLI policies live in acquisition."""
    if type(source) is not str or source not in SOURCE_URLS or type(symbol) is not str:
        _error("invalid_public_request")
    match = _SYMBOL.fullmatch(symbol)
    if match is None:
        _error("invalid_public_symbol")
    source_symbol = match[2].lower() + match[1]
    if source == "tencent":
        if period != "1d" or type(period) is not str:
            _error("invalid_public_period")
        first, last = _iso_date(start), _iso_date(end)
        if not 1 <= (last - first).days + 1 <= 366:
            _error("invalid_public_request_range")
        count = 64 if count is None else count
        if type(count) is not int or not 1 <= count <= 640:
            _error("invalid_public_count")
        parameters = {"_var": "kline_day" + start[:4],
                      "param": f"{source_symbol},day,{start},{end},{count},", "r": _TENCENT_R}
    else:
        if type(period) is not str or period not in {"1m", "5m"} or start is not None or end is not None:
            _error("invalid_public_period")
        count = 10 if count is None else count
        if type(count) is not int or not 1 <= count <= 1970:
            _error("invalid_public_count")
        parameters = {"symbol": source_symbol, "scale": period[:-1], "ma": "no", "datalen": str(count)}
    return {"method": "GET", "url": SOURCE_URLS[source] + "?" + urlencode(parameters),
            "parameters": parameters, "headers": dict(REQUEST_HEADERS)}


def _request_spec(request, source):
    if (type(request) is not dict or set(request) != {"method", "url", "parameters", "headers"}
            or type(request["parameters"]) is not dict
            or any(type(k) is not str or type(v) is not str for k, v in request["parameters"].items())
            or type(request["headers"]) is not dict or request["headers"] != REQUEST_HEADERS
            or type(request["url"]) is not str or request["method"] != "GET"):
        _error("invalid_public_request")
    params = request["parameters"]
    if source == "tencent":
        if set(params) != {"_var", "param", "r"}:
            _error("invalid_public_request")
        parts = params["param"].split(",")
        if len(parts) != 6 or parts[1] != "day" or parts[5] != "" or not _COUNT.fullmatch(parts[4]):
            _error("invalid_public_request")
        source_symbol, _, start, end, count, _ = parts
        period = "1d"
    else:
        if (set(params) != {"symbol", "scale", "ma", "datalen"} or params["scale"] not in {"1", "5"}
                or params["ma"] != "no" or not _COUNT.fullmatch(params["datalen"])):
            _error("invalid_public_request")
        source_symbol, count = params["symbol"], params["datalen"]
        period, start, end = params["scale"] + "m", None, None
    match = _SOURCE_SYMBOL.fullmatch(source_symbol)
    if match is None:
        _error("invalid_public_symbol")
    symbol = match[2] + "." + match[1].upper()
    expected = build_request(source, symbol, period, start=start, end=end, count=int(count))
    if request != expected:
        _error("public_request_mismatch")
    return dict(source=source, symbol=symbol, period=period, start=start, end=end, count=int(count))


def validate_request(request, source) -> dict:
    """Validate exact canonical request and return its bounded source parameters."""
    if type(source) is not str or source not in SOURCE_URLS:
        _error("invalid_public_source")
    return _request_spec(request, source)


def _content_type(value, source):
    if type(value) is not str or len(value) > MAX_HEADER_BYTES or "\r" in value or "\n" in value:
        _error("invalid_public_content_type")
    parts = [part.strip() for part in value.split(";")]
    allowed = {"text/html", "application/json"} if source == "tencent" else {"application/javascript"}
    if len(parts) != 2 or parts[0].lower() not in allowed:
        _error("invalid_public_content_type")
    match = re.fullmatch(r'charset\s*=\s*(?:"([A-Za-z0-9_-]+)"|([A-Za-z0-9_-]+))', parts[1], re.IGNORECASE)
    if match is None or (match[1] or match[2]).lower() != ("utf-8" if source == "tencent" else "gbk"):
        _error("invalid_public_content_type")


def _selected_headers(headers, source):
    """Accept actual received header pairs, preserving selected value strings."""
    if type(headers) not in (list, tuple) or len(headers) > MAX_HEADER_FIELDS:
        _error("invalid_public_headers")
    selected, seen, total = {}, set(), 0
    critical = {"content-type", "content-encoding", "content-length", "transfer-encoding"}
    for item in headers:
        if type(item) not in (list, tuple) or len(item) != 2 or any(type(x) is not str for x in item):
            _error("invalid_public_headers")
        name, value = item
        try:
            total += len(name.encode("ascii")) + len(value.encode("latin-1")) + 4
        except UnicodeError:
            _error("invalid_public_headers")
        if (total > MAX_HEADER_BYTES or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
                or any(ord(char) < 32 and char != "\t" or ord(char) == 127 for char in value)):
            _error("invalid_public_headers")
        key = name.lower()
        if key in critical:
            if key in seen:
                _error("duplicate_public_header")
            seen.add(key)
            selected[key] = value
    if "content-length" in selected and "transfer-encoding" in selected:
        _error("conflicting_public_lengths")
    if "content-length" in selected and not re.fullmatch(r"[0-9]{1,10}", selected["content-length"]):
        _error("invalid_public_length")
    if "transfer-encoding" in selected and selected["transfer-encoding"].lower() != "chunked":
        _error("invalid_public_transfer_encoding")
    if "content-type" not in selected:
        _error("invalid_public_content_type")
    _content_type(selected["content-type"], source)
    encoding = selected.get("content-encoding", "")
    if encoding not in ("", "identity"):
        _error("unsupported_public_content_encoding")
    return {"content-type": selected["content-type"], "content-encoding": encoding}


def build_capture(source, request, *, status, response_url, response_headers, body) -> bytes:
    """Preserve entity bytes; supplied headers must be actual received pairs.

    This constructor validates the envelope, not the market body. Call
    preflight_capture before persisting and validate_capture before publishing.
    """
    if type(source) is not str or source not in SOURCE_URLS:
        _error("invalid_public_source")
    _request_spec(request, source)
    if type(status) is not int or status != 200 or response_url != request["url"]:
        _error("invalid_public_response")
    if type(body) is not bytes or len(body) > MAX_BODY_BYTES:
        _error("public_body_limit")
    headers = _selected_headers(response_headers, source)
    lengths = [v for k, v in response_headers if k.lower() == "content-length"]
    if lengths and int(lengths[0]) != len(body):
        _error("public_body_length_mismatch")
    envelope = dict(capture_version=CAPTURE_VERSION, source=source, request=request,
                    request_sha256=hashlib.sha256(canonical_json(request)).hexdigest(),
                    response=dict(status=status, url=response_url, headers=headers),
                    response_headers_sha256=hashlib.sha256(canonical_json(headers)).hexdigest(),
                    body_base64=base64.b64encode(body).decode("ascii"),
                    body_sha256=hashlib.sha256(body).hexdigest())
    raw = canonical_json(envelope)
    if len(raw) > MAX_CAPTURE_BYTES:
        _error("public_capture_limit")
    return raw



def _legacy_provenance(provenance):
    if (type(provenance) is not dict or set(provenance) != _PROVENANCE_KEYS
            or any(type(value) is not str for value in provenance.values())
            or any(provenance[key] != expected for key, expected in _LEGACY_FLAGS.items())
            or any(not _HASH.fullmatch(provenance[key]) for key in ("original_manifest_sha256", "capture_script_sha256"))):
        _error("invalid_legacy_provenance")
    return dict(provenance)


def _legacy_selected_headers(headers, source):
    # Recorded selected values cannot prove how many header fields were sent.
    if (type(headers) is not dict or set(headers) != {"content-type", "content-encoding"}
            or any(type(value) is not str for value in headers.values())):
        _error("invalid_legacy_selected_headers")
    try:
        length = sum(len(key) + len(value.encode("latin-1")) + 4 for key, value in headers.items())
    except UnicodeError:
        _error("invalid_legacy_selected_headers")
    if length > MAX_HEADER_BYTES or any(ord(char) < 32 and char != "\t" or ord(char) == 127
                                        for value in headers.values() for char in value):
        _error("invalid_legacy_selected_headers")
    _content_type(headers["content-type"], source)
    if headers["content-encoding"] not in ("", "identity"):
        _error("unsupported_public_content_encoding")
    return dict(headers)


def build_legacy_capture(source, request, *, status, response_url, selected_headers, body, provenance) -> bytes:
    """Build an explicitly limited offline reconstruction from recorded values.

    The converter must hash and check original manifest/script/body files and
    the recorded request correspondence. This pure function validates their
    declarations, not external artifacts, header cardinality or transport.
    """
    if type(source) is not str or source not in SOURCE_URLS:
        _error("invalid_public_source")
    _request_spec(request, source)
    if type(status) is not int or status != 200 or response_url != request["url"]:
        _error("invalid_public_response")
    if type(body) is not bytes or len(body) > MAX_BODY_BYTES:
        _error("public_body_limit")
    headers = _legacy_selected_headers(selected_headers, source)
    provenance = _legacy_provenance(provenance)
    envelope = dict(capture_version=LEGACY_CAPTURE_VERSION, source=source, request=request,
                    request_sha256=hashlib.sha256(canonical_json(request)).hexdigest(),
                    response=dict(status=status, url=response_url, headers=headers),
                    response_headers_sha256=hashlib.sha256(canonical_json(headers)).hexdigest(),
                    body_base64=base64.b64encode(body).decode("ascii"), body_sha256=hashlib.sha256(body).hexdigest(),
                    provenance=provenance)
    raw = canonical_json(envelope)
    if len(raw) > MAX_CAPTURE_BYTES:
        _error("public_capture_limit")
    return raw

def _envelope(raw, format_id):
    if format_id not in PUBLIC_FORMAT_IDS:
        _error("unsupported_format")
    if type(raw) is not bytes or len(raw) > MAX_CAPTURE_BYTES:
        _error("public_capture_limit")
    try:
        envelope = _strict_json(raw.decode("utf-8", "strict"))
    except UnicodeError:
        _error("invalid_public_json")
    if type(envelope) is not dict:
        _error("noncanonical_public_capture")
    version = envelope.get("capture_version")
    if version not in (CAPTURE_VERSION, LEGACY_CAPTURE_VERSION):
        _error("unsupported_public_capture_version")
    expected_keys = _CAPTURE_KEYS | {"provenance"} if version == LEGACY_CAPTURE_VERSION else _CAPTURE_KEYS
    if set(envelope) != expected_keys or canonical_json(envelope) != raw:
        _error("noncanonical_public_capture")
    if version == LEGACY_CAPTURE_VERSION:
        _legacy_provenance(envelope["provenance"])
    source = "tencent" if format_id == PUBLIC_FORMAT_IDS[0] else "sina"
    if envelope["source"] != source:
        _error("public_source_mismatch")
    for key in ("request_sha256", "response_headers_sha256", "body_sha256"):
        if type(envelope[key]) is not str or not _HASH.fullmatch(envelope[key]):
            _error("invalid_public_hash")
    spec = _request_spec(envelope["request"], source)
    if hashlib.sha256(canonical_json(envelope["request"])).hexdigest() != envelope["request_sha256"]:
        _error("public_request_hash_mismatch")
    response = envelope["response"]
    if (type(response) is not dict or set(response) != {"status", "url", "headers"}
            or type(response["status"]) is not int or response["status"] != 200
            or type(response["url"]) is not str or response["url"] != envelope["request"]["url"]
            or type(response["headers"]) is not dict
            or set(response["headers"]) != {"content-type", "content-encoding"}
            or any(type(v) is not str for v in response["headers"].values())):
        _error("invalid_public_response")
    headers = response["headers"]
    if version == LEGACY_CAPTURE_VERSION:
        _legacy_selected_headers(headers, source)
    else:
        _selected_headers(list(headers.items()), source)
    if hashlib.sha256(canonical_json(headers)).hexdigest() != envelope["response_headers_sha256"]:
        _error("public_header_hash_mismatch")
    try:
        encoded = envelope["body_base64"]
        if type(encoded) is not str or len(encoded) > 4 * ((MAX_BODY_BYTES + 2) // 3):
            _error("public_body_limit")
        body = base64.b64decode(encoded, validate=True)
        if len(body) > MAX_BODY_BYTES or base64.b64encode(body).decode("ascii") != encoded:
            _error("invalid_public_base64")
    except (ValueError, UnicodeError, binascii.Error):
        _error("invalid_public_base64")
    if hashlib.sha256(body).hexdigest() != envelope["body_sha256"]:
        _error("public_body_hash_mismatch")
    return envelope, body, spec


def preflight_capture(raw, format_id) -> ValidatedCapture:
    """Recognize source market identity before any capture/raw persistence.

    Recognizable field sets/tuple arity are required here; control arrays are
    not market data. Market field-type/date/count errors remain for validation,
    allowing their exact capture in the existing rejected-import ledger.
    """
    envelope, body, spec = _envelope(raw, format_id)
    source = spec["source"]
    try:
        text = body.decode("utf-8" if source == "tencent" else "gbk", "strict")
    except UnicodeError:
        raise NonMarketPayload("non_market_payload") from None
    if source == "tencent":
        prefix = envelope["request"]["parameters"]["_var"] + "="
        if not text.startswith(prefix):
            raise NonMarketPayload("non_market_payload") from None
        root = _strict_json(text[len(prefix):])
        source_symbol = spec["symbol"][-2:].lower() + spec["symbol"][:6]
        if (type(root) is not dict or set(root) != {"code", "msg", "data"}
                or type(root["code"]) is not int or type(root["msg"]) is not str
                or type(root["data"]) is not dict):
            raise NonMarketPayload("non_market_payload") from None
        if root["code"] != 0 or root["msg"] != "":
            raise NonMarketPayload("public_source_error") from None
        if set(root["data"]) != {source_symbol}:
            raise NonMarketPayload("non_market_payload") from None
        stock = root["data"][source_symbol]
        if (type(stock) is not dict or "day" not in stock
                or not set(stock) <= {"day", "qt", "mx_price", "prec", "fsStartDate", "version", "attribute"}
                or type(stock["day"]) is not list):
            raise NonMarketPayload("non_market_payload") from None
        if "attribute" in stock:
            attribute = stock["attribute"]
            if (type(attribute) is not dict or set(attribute) != _TENCENT_ATTRIBUTE_KEYS
                    or any(type(value) is not str or value not in {"0", "1"} for value in attribute.values())):
                raise NonMarketPayload("non_market_payload") from None
        payload = stock["day"]
        if any(type(row) is not list or len(row) != 11 for row in payload):
            raise NonMarketPayload("non_market_payload") from None
    else:
        if not text.startswith(_SINA_PREFIX) or not text.endswith(");"):
            raise NonMarketPayload("non_market_payload") from None
        payload = _strict_json(text[len(_SINA_PREFIX):-2])
        if (type(payload) is not list or any(type(row) is not dict
                or set(row) != {"day", "open", "high", "low", "close", "volume", "amount"}
                for row in payload)):
            raise NonMarketPayload("non_market_payload") from None
    return ValidatedCapture(envelope=envelope, body=body, payload=payload, **spec)


def _minute_label(value):
    try:
        if type(value) is not str or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:00", value):
            raise ValueError
        moment = datetime.fromisoformat(value)
        return moment.isoformat(timespec="minutes")
    except (TypeError, ValueError):
        _error("invalid_public_source_label")


def validate_capture(raw, format_id) -> ValidatedCapture:
    """Validate deterministic row shape and labels; quantity errors stay rows."""
    capture = preflight_capture(raw, format_id)
    if len(capture.payload) > capture.count:
        _error("public_row_limit")
    for row in capture.payload:
        if capture.source == "tencent":
            if (type(row) is not list or len(row) != 11 or type(row[6]) is not dict
                    or any(type(row[i]) is not str for i in (0, 1, 2, 3, 4, 5, 7, 8, 9, 10))):
                _error("invalid_public_rows")
            try:
                _iso_date(row[0])
            except DecodeError:
                _error("invalid_public_source_label")
            if row[0] > capture.end:
                _error("public_source_after_end")
        else:
            if (type(row) is not dict or set(row) != {"day", "open", "high", "low", "close", "volume", "amount"}
                    or any(type(value) is not str for value in row.values())):
                _error("invalid_public_rows")
            _minute_label(row["day"])
    return capture


def capture_rows(capture):
    """Return source row specifications and clock-free, unqualified metadata."""
    rows, dates = [], []
    source_symbol = capture.symbol[-2:].lower() + capture.symbol[:6]
    for index, item in enumerate(capture.payload):
        if capture.source == "tencent":
            tokens = dict(open=item[1], close=item[2], high=item[3], low=item[4], volume=item[5], amount=item[8],
                          source_date=item[0], source_extra_7=item[7], source_extra_9=item[9], source_extra_10=item[10])
            label = source_label = item[0]
            locator = f"body:$.data.{source_symbol}.day[{index}]"
            tokens["source_object_6_locator"] = locator + "[6]"
        else:
            source_label = item["day"]
            label = _minute_label(source_label)
            tokens = {key: value for key, value in item.items() if key != "day"}
            tokens.update(source_day=source_label, source_date=source_label[:10], source_time=source_label[11:])
            locator = f"body:$[{index}]"
        rows.append(dict(ordinal=index + 1, locator=locator, source_label=source_label, label=label, tokens=tokens))
        dates.append(label)
    metadata = dict(source=capture.source, period=capture.period, requested_symbol=capture.symbol,
                    requested_period=capture.period, requested_adjustment="none", source_requested_count=capture.count,
                    period_evidence="request_declared", quantity_normalization="unstandardized",
                    response_identity="source_key" if capture.source == "tencent" else "absent",
                    body_sha256=capture.envelope["body_sha256"], request_sha256=capture.envelope["request_sha256"],
                    response_headers_sha256=capture.envelope["response_headers_sha256"],
                    actual_range={"start": min(dates), "end": max(dates)} if dates else None,
                    count_saturated=len(rows) == capture.count, coverage="unverified", acquisition_clock="unavailable",
                    price_representation="received_decimal_strings",
                    source_units={"volume": {"status": "unstandardized", "value": None},
                                  "amount": {"status": "unknown", "value": None,
                                             "candidate": "ten_thousand_CNY" if capture.source == "tencent" else None}})
    if capture.source == "tencent":
        before = sum(day < capture.start for day in dates)
        metadata.update(source_symbol=source_symbol, source_code=capture.symbol, source_venue=capture.symbol[-2:],
                        response_key_mapping="sh/sz+six_digits_to_six_digits.SH/SZ", response_branch="day",
                        requested_range={"start": capture.start, "end": capture.end}, before_start_count=before,
                        in_request_count=len(rows) - before, after_end_count=0, request_range_mismatch=before > 0,
                        truncated_possible=len(rows) == capture.count)
    else:
        metadata.update(requested_range=None, window_kind="recent_window")
    if capture.envelope["capture_version"] == LEGACY_CAPTURE_VERSION:
        metadata.update(capture_version=LEGACY_CAPTURE_VERSION, **_LEGACY_FLAGS,
                        provenance=dict(capture.envelope["provenance"]), provenance_hash_verification="syntax_only")
    return metadata, rows


def public_contract(format_id, *, capture_version=CAPTURE_VERSION):
    """Static version-specific contract; default strict-v1 identity is fixed."""
    if format_id not in PUBLIC_FORMAT_IDS:
        _error("unsupported_format")
    if capture_version not in (CAPTURE_VERSION, LEGACY_CAPTURE_VERSION):
        _error("unsupported_public_capture_version")
    fields = {name: dict(value=None, status="unknown", reason=reason, evidence=[]) for name, reason in {
        "price_unit": "source_price_unit_unverified", "volume_unit": "source_quantity_not_normalized",
        "amount_unit": "source_amount_unit_unverified", "volume_accumulation": "source_volume_accumulation_unverified",
        "amount_accumulation": "source_amount_accumulation_unverified",
        "volume_amount_same_coverage": "source_trade_coverage_unverified", "adjustment": "request_only_adjustment_unverified",
        "label_definition": "bar_label_definition_unverified", "period_start": "bar_start_unverified",
        "period_end": "bar_end_unverified", "closed": "bar_closure_unverified",
        "trading_phase": "trading_phase_unverified", "first_published_at": "first_publication_not_evidenced",
        "known_at": "historical_availability_not_evidenced",
    }.items()}
    contract = dict(format_id=format_id, version=DECODE_CONTRACT_VERSION, capture_version=CAPTURE_VERSION,
                raw_kind="http_capture_bundle", interpretation_evidence="assumed", source_claims_evidence="assumed",
                standard_units=dict(status="unknown", reason="security_master_and_applicable_units_unverified"),
                temporal_semantics=dict(status="unknown", reason="bar_boundaries_closure_and_known_at_unverified"),
                conditional_diagnostic=dict(status="not_evaluated", reason="source_quantity_not_normalized",
                                            cent_diagnostic_is_acceptance_tolerance=False),
                source_semantics=dict(scope="all_records", fields=fields),
                source_token_mapping=dict(source_date="source_date", source_time=None if format_id == PUBLIC_FORMAT_IDS[0] else "source_time"),
                quantity_policy="unstandardized", coverage="unverified")
    if capture_version == LEGACY_CAPTURE_VERSION:
        contract.update(capture_version=LEGACY_CAPTURE_VERSION, raw_kind="legacy_http_capture_reconstruction",
                        **_LEGACY_FLAGS, provenance_hash_verification="syntax_only")
    return contract


def decoder_identity(format_id):
    contract = public_contract(format_id)
    return dict(format_id=format_id, capture_version=CAPTURE_VERSION,
                decode_contract_version=DECODE_CONTRACT_VERSION,
                source_contract_id=hashlib.sha256(canonical_json(contract)).hexdigest(), versions=dict(VERSIONS))
