"""Decode audited source shapes without granting market-data qualification."""
from collections import Counter
from datetime import date, datetime
from decimal import Context, Decimal, Inexact, InvalidOperation, Overflow, ROUND_HALF_EVEN, Rounded, localcontext
import hashlib
import json
import re
import struct

from .models import Check, Decoded, DecodeError, NonMarketPayload, SourceRow, VALUE_FIELDS
from .numeric import NumericError, decimal_value, integer_value
from .public_market import PUBLIC_FORMAT_IDS, capture_rows, preflight_capture, public_contract, validate_capture

FORMAT_IDS = ("tdx-public-text-v1", "tdx-public-day-v1", "baostock-decoded-v0.9.4", "tdx-http-market-v1", *PUBLIC_FORMAT_IDS)
_DECLARATIONS = {"instrument", "venue", "asset_type", "volume_unit", "amount_unit"}
_BAO_FIELDS = {"date", "time", "code", *VALUE_FIELDS, "adjustflag"}
_NEGATIVE_DAY = "aa27dfce8bd24a75f4d07697c4c787f905a26b7a3999a3c76cf30b24ef9c2357"
_NEGATIVE_MINUTES = {
    "ef8435e32669e3bd4fd2572376c2be1a466867aa9a46ffad440e0522803fc8df",
    "d69d96de605e5f8efa03cf06044e666584c57d443668395d323fbb6ef199cacf",
}
_ASSUMPTION = "shares_cny_same_coverage"
_EXACT = Context(prec=128, rounding=ROUND_HALF_EVEN,
                 traps=[Inexact, Rounded, Overflow, InvalidOperation])


def _bao_envelope(raw):
    # The header length describes the original compressed body, not this decoded text.
    text = None
    if isinstance(raw, bytes):
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            pass
    parts = text[21:].split("\x01") if text is not None else []
    header_ok = bool(text and re.fullmatch(r"[0-9]{2}\.[0-9]\.[0-9]{2}\x0196\x01[0-9]{10}", text[:21]))
    if not header_ok or len(parts) != 13:
        raise NonMarketPayload("non_market_payload")
    fields = parts[8].split(",")
    if (parts[0] != "0" or parts[2] != "query_history_k_data_plus"
            or parts[3] != "anonymous" or not fields
            or len(set(fields)) != len(fields) or not set(fields) <= _BAO_FIELDS):
        raise NonMarketPayload("non_market_payload")
    return parts, fields


def preflight(raw: bytes, format_id: str) -> None:
    """Reject non-market BaoStock material before its bytes may be persisted."""
    if format_id not in FORMAT_IDS:
        raise DecodeError("unsupported_format")
    if (format_id == FORMAT_IDS[2]
            or isinstance(raw, bytes) and re.match(rb"[0-9]{2}\.[0-9]\.[0-9]{2}\x01", raw)):
        _bao_envelope(raw)
    if format_id == FORMAT_IDS[3]:
        _tdx_http_envelope(raw)
    if format_id in PUBLIC_FORMAT_IDS:
        preflight_capture(raw, format_id)


def _http_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_key")
            result[key] = value
        return result

    def constant(value):
        raise ValueError("nonfinite")

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs, parse_float=Decimal,
                            parse_constant=constant)
        if type(result) is not dict:
            raise ValueError("object_required")
        return result
    except (ValueError, UnicodeError, AttributeError, RecursionError, ArithmeticError):
        raise DecodeError("invalid_tdx_http_capture") from None


def _tdx_http_request(request):
    if request.get("method") != "get_market_data":
        raise NonMarketPayload("non_market_payload")
    params = request.get("params")
    if (type(request.get("id")) is not int or type(params) is not dict
            or type(params.get("stock_list")) is not list or len(params["stock_list"]) != 1
            or type(params["stock_list"][0]) is not str
            or not re.fullmatch(r"[0-9]{6}\.(?:SH|SZ|BJ)", params["stock_list"][0])
            or params.get("period") != "1m" or params.get("dividend_type") != "none"
            or params.get("fill_data") is not False or type(params.get("count")) is not int
            or not 1 <= params["count"] <= 24000 or type(params.get("end_time")) is not str):
        raise DecodeError("invalid_tdx_http_capture")
    if params["end_time"]:
        try:
            if not re.fullmatch(r"[0-9]{14}", params["end_time"]):
                raise ValueError
            datetime.strptime(params["end_time"], "%Y%m%d%H%M%S")
        except ValueError:
            raise DecodeError("invalid_tdx_http_capture") from None
    return params


def _tdx_http_envelope(raw):
    bundle = _http_json(raw)
    if set(bundle) != {"request_utf8", "response_utf8"} or any(type(v) is not str for v in bundle.values()):
        raise DecodeError("invalid_tdx_http_capture")
    request = _http_json(bundle["request_utf8"].encode("utf-8"))
    params = _tdx_http_request(request)
    response = _http_json(bundle["response_utf8"].encode("utf-8"))
    result = response.get("result")
    symbol = params["stock_list"][0]
    if (type(response.get("id")) is not int or response["id"] != request["id"]
            or type(result) is not dict or result.get("ErrorId") != "0"
            or type(result.get("Value")) is not dict or set(result["Value"]) != {symbol}
            or type(result["Value"][symbol]) is not dict or result["Value"][symbol].get("ErrorId") != "0"):
        raise DecodeError("invalid_tdx_http_response")
    return bundle, params, result["Value"][symbol]


def _tdx_http(raw):
    bundle, params, stock = _tdx_http_envelope(raw)
    fields = ("Date", "Time", "Open", "High", "Low", "Close", "Volume", "Amount")
    if ("Value" in stock or any(type(stock.get(f)) is not list for f in fields)
            or not 1 <= len(stock["Date"]) <= params["count"]
            or any(len(stock[f]) != len(stock["Date"]) for f in fields)
            or any(type(v) is not str for f in fields for v in stock[f])):
        raise DecodeError("invalid_tdx_http_rows")
    symbol, rows = params["stock_list"][0], []
    for index in range(len(stock["Date"])):
        source_date, source_time = stock["Date"][index], stock["Time"][index]
        label = None
        if re.fullmatch(r"[0-9]{8}", source_date) and re.fullmatch(r"[0-9]{5,6}", source_time):
            clock = int(source_time)
            try:
                moment = datetime(int(source_date[:4]), int(source_date[4:6]), int(source_date[6:]),
                                  clock // 10000, clock // 100 % 100, clock % 100)
                if moment.second == 0:
                    label = moment.isoformat(timespec="minutes")
            except ValueError:
                pass
        tokens = {field.lower(): stock[field][index] for field in fields[2:]}
        tokens.update(source_date=source_date, source_time=source_time)
        row = _row(index + 1, f"response:$.result.Value.{symbol}:index:{index}",
                   f"{source_date} {source_time}", label, tokens)
        if params["end_time"]:
            row.checks.append(Check("source_date_range", "not_evaluated", "invalid_source_label")
                              if label is None else Check("source_date_range", "pass" if
                                  label.replace("-", "").replace(":", "").replace("T", "") + "00"
                                  <= params["end_time"] else "fail"))
        rows.append(row)
    return dict(period="1m", source_code=symbol, source_venue=symbol[-2:],
                source_adjustment=params["dividend_type"], source_end_time=params["end_time"],
                source_requested_count=params["count"], price_representation="received_http_decimal_strings",
                request_sha256=hashlib.sha256(bundle["request_utf8"].encode("utf-8")).hexdigest(),
                response_sha256=hashlib.sha256(bundle["response_utf8"].encode("utf-8")).hexdigest()), rows


def _date_label(token, separator="-"):
    pattern = rf"[0-9]{{4}}{re.escape(separator)}[0-9]{{2}}{re.escape(separator)}[0-9]{{2}}"
    if not re.fullmatch(pattern, token):
        return None
    try:
        return date.fromisoformat(token.replace(separator, "-")).isoformat()
    except ValueError:
        return None


def _minute_label(date_token, time_token, *, bao=False):
    if bao:
        if not re.fullmatch(r"[0-9]{17}", time_token) or time_token[-5:] != "00000":
            return None
        if time_token[:8] != date_token.replace("-", ""):
            return None
        date_part, clock = _date_label(date_token), time_token[8:12]
    else:
        date_part, clock = _date_label(date_token, "/"), time_token
    if date_part is None or not re.fullmatch(r"[0-9]{4}", clock):
        return None
    try:
        return datetime.fromisoformat(f"{date_part}T{clock[:2]}:{clock[2:]}").isoformat(timespec="minutes")
    except ValueError:
        return None


def _row(ordinal, locator, source_label, label, tokens, inputs=None, *, volume_policy=None):
    values, checks = {}, []
    for field in VALUE_FIELDS:
        value = (inputs if inputs is not None else tokens).get(field)
        if field == "volume" and volume_policy == "unstandardized":
            values[field] = None
            outcome, reason = "pass", None
            if value is None or isinstance(value, str) and not value.strip():
                outcome, reason = "not_evaluated", "missing"
            else:
                try:
                    if decimal_value(value) < 0:
                        raise NumericError("negative_source_quantity")
                except NumericError as error:
                    outcome, reason = "fail", error.code
            checks.append(Check("source_quantity_decimal", outcome, reason))
            checks.append(Check("numeric.volume", "not_evaluated" if outcome == "pass" else outcome,
                                "source_quantity_not_normalized" if outcome == "pass" else reason))
            continue
        if value is None or isinstance(value, str) and not value.strip():
            values[field] = None
            checks.append(Check(f"numeric.{field}", "not_evaluated", "missing"))
            continue
        try:
            values[field] = integer_value(value) if field == "volume" else decimal_value(value)
        except NumericError as error:
            values[field] = None
            checks.append(Check(f"numeric.{field}", "fail", error.code))
        else:
            checks.append(Check(f"numeric.{field}", "pass"))
    checks.append(Check("label", "pass" if label is not None else "fail",
                        None if label is not None else "invalid_source_label"))
    row = SourceRow(ordinal, locator, source_label, label, tokens, values, checks)
    _quality(row, volume_policy=volume_policy)
    return row


def _quality(row, *, volume_policy=None):
    values, checks = row.values, row.checks
    prices = [values[field] for field in ("open", "high", "low", "close")]
    if all(value is not None for value in prices):
        opening, high, low, close = prices
        checks.append(Check("ohlc_bounds", "pass" if low <= opening <= high and low <= close <= high else "fail"))
        checks.append(Check("nonnegative_prices", "pass" if min(prices) >= 0 else "fail"))
    else:
        checks.extend(Check(name, "not_evaluated", "invalid_or_missing_price")
                      for name in ("ohlc_bounds", "nonnegative_prices"))
    volume, amount = values["volume"], values["amount"]
    checks.append(Check("nonnegative_amount", "not_evaluated", "invalid_or_missing_amount")
                  if amount is None else Check("nonnegative_amount", "pass" if amount >= 0 else "fail"))
    if volume_policy == "unstandardized":
        checks.extend(Check(name, "not_evaluated", "source_quantity_not_normalized")
                      for name in ("zero_volume_amount", "conditional_price_bounds", "conditional_price_bounds_cent"))
        checks.append(Check("standard_units", "not_evaluated", "instrument_identity_and_source_semantics_unverified"))
        return
    checks.append(Check("zero_volume_amount", "not_evaluated", "invalid_or_missing_volume_or_amount")
                  if volume is None or amount is None else
                  Check("zero_volume_amount", "fail" if volume == 0 and amount != 0 else "pass"))
    reason = "invalid_or_missing_field" if any(value is None for value in values.values()) else None
    if reason is None and volume == 0:
        reason = "zero_volume"
    if reason:
        checks.extend(Check(name, "not_evaluated", reason, _ASSUMPTION)
                      for name in ("conditional_price_bounds", "conditional_price_bounds_cent"))
    else:
        with localcontext(_EXACT):
            gap = max(values["low"] * volume - amount, amount - values["high"] * volume, Decimal(0))
            cent = Decimal("0.01") * volume
        checks.append(Check("conditional_price_bounds", "pass" if gap == 0 else "fail", assumption=_ASSUMPTION))
        checks.append(Check("conditional_price_bounds_cent", "pass" if gap <= cent else "fail", assumption=_ASSUMPTION))
    checks.append(Check("standard_units", "not_evaluated", "instrument_identity_and_source_semantics_unverified"))


def _text(raw):
    encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "gbk"
    text = None
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        pass
    if text is None:
        raise DecodeError("invalid_text_encoding")
    lines = text.splitlines()
    title = re.fullmatch(r"([0-9]{6}) (.+) ([15])分钟线 不复权", lines[0]) if lines else None
    columns = ["日期", "时间", "开盘", "最高", "最低", "收盘", "成交量", "成交额"]
    if len(lines) < 3 or title is None or lines[1].split() != columns or lines[-1] != "数据来源:通达信":
        raise DecodeError("invalid_text_structure")
    rows = []
    for line_number, line in enumerate(lines[2:-1], 3):
        parts = line.split() if encoding == "utf-8-sig" else line.split(",")
        if len(parts) != 8:
            raise DecodeError("invalid_text_row_width")
        tokens = dict(zip(VALUE_FIELDS, parts[2:]))
        tokens.update(source_date=parts[0], source_time=parts[1])
        rows.append(_row(len(rows) + 1, f"line:{line_number}", f"{parts[0]} {parts[1]}",
                         _minute_label(parts[0], parts[1]), tokens))
    metadata = dict(period=f"{title[3]}m", source_code=title[1], source_name=title[2],
                    source_adjustment="不复权", encoding=encoding, title=lines[0],
                    column_header=lines[1], footer=lines[-1])
    return metadata, rows


def _day(raw):
    if not raw or len(raw) % 32:
        raise DecodeError("invalid_day_length")
    if hashlib.sha256(raw).hexdigest() in _NEGATIVE_MINUTES:
        raise DecodeError("unsupported_known_minute_binary")
    rows = []
    for offset in range(0, len(raw), 32):
        record = raw[offset:offset + 32]
        day, opening, high, low, close = struct.unpack_from("<5I", record)
        volume = int.from_bytes(record[24:28], "little")
        quote_values = (opening, high, low, close)
        tokens = dict(zip(VALUE_FIELDS[:4], map(str, quote_values)))
        tokens.update(volume=str(volume), amount=record[20:24].hex(), reserved=record[28:32].hex(),
                      source_date=str(day))
        inputs = dict(zip(VALUE_FIELDS[:4], (f"{value // 100}.{value % 100:02d}" for value in quote_values)))
        # Every binary32 widens exactly to Python's binary64 before this exact Decimal constructor.
        inputs.update(volume=volume, amount=Decimal.from_float(struct.unpack_from("<f", record, 20)[0]))
        label = _date_label(f"{str(day)[:4]}-{str(day)[4:6]}-{str(day)[6:]}") if len(str(day)) == 8 else None
        rows.append(_row(len(rows) + 1, f"byte:{offset}", str(day), label, tokens, inputs))
    return dict(period="1d", record_bytes=32, amount_byte_offset=20, reserved_byte_offset=28,
                quote_interpretation="candidate_A_share_uint32_divided_by_100",
                amount_representation="exact_received_IEEE754_binary32"), rows


def _bao(raw):
    parts, fields = _bao_envelope(raw)
    period = {"d": "1d", "5": "5m"}.get(parts[11])
    if period is None:
        raise DecodeError("unsupported_bao_period")
    expected = {"date", "code", *VALUE_FIELDS, "adjustflag"} | ({"time"} if period == "5m" else set())
    if set(fields) != expected:
        raise DecodeError("invalid_bao_fields")
    records = None
    try:
        content = json.loads(parts[6], parse_float=Decimal)
        if isinstance(content, dict) and set(content) == {"record"} and isinstance(content["record"], list):
            records = content["record"]
    except (ValueError, RecursionError):
        pass
    if records is None:
        raise DecodeError("invalid_bao_records")
    rows = []
    for ordinal, record in enumerate(records, 1):
        if not isinstance(record, list) or len(record) != len(fields) or any(type(cell) is not str for cell in record):
            raise DecodeError("invalid_bao_cells")
        tokens = dict(zip(fields, record))
        source_label = tokens["date"] if period == "1d" else tokens["time"]
        label = _date_label(tokens["date"]) if period == "1d" else _minute_label(tokens["date"], tokens["time"], bao=True)
        row = _row(ordinal, f"record:{ordinal}", source_label, label, tokens)
        row.checks.extend([
            Check("source_code", "pass" if tokens["code"] == parts[7] else "fail", "compares_source_claims"),
            Check("source_adjustflag", "pass" if tokens["adjustflag"] == parts[12] == "3" else "fail", "compares_source_claims"),
        ])
        source_date = _date_label(tokens["date"])
        start, end = _date_label(parts[9]), _date_label(parts[10])
        row.checks.append(Check("source_date_range", "not_evaluated", "invalid_source_date")
                          if None in (source_date, start, end) else
                          Check("source_date_range", "pass" if start <= source_date <= end else "fail"))
        rows.append(row)
    venue = parts[7].split(".")[0] if re.fullmatch(r"(?:sh|sz|bj)\.[0-9]{6}", parts[7]) else None
    return dict(period=period, source_frequency=parts[11], source_code=parts[7], source_venue=venue, source_adjustflag=parts[12],
                source_start_date=parts[9], source_end_date=parts[10], source_fields=fields,
                protocol_version=raw[:7].decode("ascii"), source_page=parts[4], source_page_size=parts[5]), rows


def _source_semantics(format_id, metadata):
    reasons = {
        "price_unit": "source_price_unit_unverified",
        "volume_unit": "source_volume_unit_unverified",
        "amount_unit": "source_amount_unit_unverified",
        "volume_accumulation": "source_volume_accumulation_unverified",
        "amount_accumulation": "source_amount_accumulation_unverified",
        "volume_amount_same_coverage": "volume_amount_trade_coverage_unverified",
        "adjustment": "adjustment_not_provided_by_format",
        "label_definition": "bar_label_definition_unverified",
        "period_start": "bar_start_unverified",
        "period_end": "bar_end_unverified",
        "closed": "bar_closure_unverified",
        "trading_phase": "trading_phase_unverified",
        "first_published_at": "first_publication_not_evidenced",
        "known_at": "historical_availability_not_evidenced",
    }
    fields = {name: {"value": None, "status": "unknown", "reason": reason, "evidence": []}
              for name, reason in reasons.items()}
    adjustment = {FORMAT_IDS[0]: "source_adjustment", FORMAT_IDS[2]: "source_adjustflag",
                  FORMAT_IDS[3]: "source_adjustment"}.get(format_id)
    if adjustment is not None:
        fields["adjustment"] = {"value": metadata[adjustment], "status": "assumed",
                                "reason": "source_claim_unverified", "evidence": [f"metadata.{adjustment}"]}
    if format_id == FORMAT_IDS[2]:
        documentation = {
            "url": "https://www.baostock.com/mainContent?file=stockKData.md",
            "path": "artifacts/qualification/docs/stockKData.md",
            "sha256": "2a6db3b24ab21a199aa17bd949dfbe545d3279007bea1664854f9b7c20542aac",
            "lines": [202, 208] if metadata["period"] == "1d" else [242, 247],
        }
        documented = {"price_unit": "CNY", "volume_unit": "shares", "amount_unit": "CNY"}
        # The saved document explicitly defines interval accumulation for minute bars.
        if metadata["period"] == "5m":
            documented.update(volume_accumulation="per_bar_total", amount_accumulation="per_bar_total")
        for name, value in documented.items():
            fields[name] = {"value": value, "status": "known", "reason": "documented_meaning_only",
                            "evidence": [documentation], "applicability": "unverified"}
    return {"scope": "all_records", "fields": fields}


def decode(raw: bytes, format_id: str, interpretation: dict | None = None) -> Decoded:
    preflight(raw, format_id)
    if interpretation is None:
        interpretation = {}
    if (type(interpretation) is not dict or not set(interpretation) <= _DECLARATIONS
            or any(type(value) is not str for value in interpretation.values())):
        raise DecodeError("invalid_interpretation")
    if type(raw) is not bytes:
        raise DecodeError("invalid_raw_type")
    if format_id in PUBLIC_FORMAT_IDS:
        capture = validate_capture(raw, format_id)
        if not capture.payload:
            raise DecodeError("empty_public_market_result")
        expected = {"instrument": capture.symbol, "venue": capture.symbol[-2:], "asset_type": "stock"}
        if any(key not in expected or value != expected[key] for key, value in interpretation.items()):
            raise DecodeError("conflicting_public_interpretation")
        metadata, specifications = capture_rows(capture)
        rows = [_row(**specification, volume_policy="unstandardized") for specification in specifications]
    else:
        metadata, rows = {FORMAT_IDS[0]: _text, FORMAT_IDS[1]: _day, FORMAT_IDS[2]: _bao,
                          FORMAT_IDS[3]: _tdx_http}[format_id](raw)
    raw_hash = hashlib.sha256(raw).hexdigest()
    metadata.update(instrument_id=None, interpretation=dict(interpretation), interpretation_status="assumed",
                    source_claims_status="assumed", raw_sha256=raw_hash, quarantined=raw_hash == _NEGATIVE_DAY)
    if metadata["quarantined"]:
        metadata["quarantine_reason"] = "known_negative_sample_identity_and_units"
    checks = [Check("structure", "pass"), Check("instrument_identity", "not_evaluated", "security_master_not_verified"),
              Check("source_units_and_coverage", "not_evaluated", "source_applicability_not_verified")]
    if metadata["quarantined"]:
        checks.append(Check("known_negative_sample", "fail", metadata["quarantine_reason"]))
    for declared, source in (("instrument", "source_code"), ("venue", "source_venue")):
        if declared in interpretation:
            checks.append(Check(f"declared_{declared}", "not_evaluated", "source_claim_unavailable")
                          if metadata.get(source) is None else
                          Check(f"declared_{declared}", "pass" if interpretation[declared] == metadata[source] else "fail",
                                "compares_declared_text_not_permanent_identity"))
    counts = Counter(row.label for row in rows if row.label is not None)
    previous = None
    for row in rows:
        if row.label is None:
            row.checks.extend(Check(name, "not_evaluated", "invalid_source_label")
                              for name in ("duplicate_label", "source_order"))
        else:
            row.checks.extend([
                Check("duplicate_label", "fail" if counts[row.label] > 1 else "pass"),
                Check("source_order", "fail" if previous is not None and row.label < previous else "pass"),
            ])
            previous = row.label
    if format_id in PUBLIC_FORMAT_IDS:
        return Decoded(public_contract(format_id, capture_version=capture.envelope["capture_version"]), metadata, rows, checks)
    contract = dict(format_id=format_id, version="2",
                    raw_kind="http_capture_bundle" if format_id == FORMAT_IDS[3] else
                             "sdk_decoded_text" if format_id == FORMAT_IDS[2] else "original_file",
                    interpretation_evidence="assumed", source_claims_evidence="assumed",
                    standard_units={"status": "unknown", "reason": "security_master_and_applicable_units_unverified"},
                    temporal_semantics={"status": "unknown", "reason": "bar_boundaries_closure_and_known_at_unverified"},
                    conditional_diagnostic={"assumption": _ASSUMPTION, "status": "assumed",
                                            "cent_diagnostic_is_acceptance_tolerance": False})
    contract["source_semantics"] = _source_semantics(format_id, metadata)
    contract["source_token_mapping"] = {
        "source_date": "date" if format_id == FORMAT_IDS[2] else "source_date",
        "source_time": None if metadata["period"] == "1d" else
                       ("time" if format_id == FORMAT_IDS[2] else "source_time"),
    }
    if format_id == FORMAT_IDS[1]:
        contract["price_scaling"] = {"value": "raw_uint32/100", "status": "assumed", "reason": "A_share_candidate_only"}
    elif format_id == FORMAT_IDS[2]:
        contract["documented_units"] = {"volume": "shares", "amount": "CNY", "status": "known",
                                        "evidence": "docs/qualification/baostock-samples.md#3", "applicability": "unverified"}
    return Decoded(contract, metadata, rows, checks)
