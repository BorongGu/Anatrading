"""Offline synthetic protocol boundaries; these tests do not qualify market data."""
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta
import json
import re

import pytest

from baostock_acquisition_probe import ProbeError, inspect_response, run_query


SEP = "\x01"
PRIVATE_MARKER = "SYNTHETIC_PRIVATE_MARKER_938"
HISTORY_METHOD = "query_history_k_data_plus"
BULK_METHOD = "query_daily_history_k_AStock"
DAILY_FIELDS = "date,code,open,high,low,close,volume,amount,adjustflag".split(",")
MINUTE_FIELDS = "date,time,code,open,high,low,close,volume,amount,adjustflag".split(",")
BULK_FIELDS = (
    "date,code,open,high,low,close,preclose,volume,amount,adjustflag,turn,"
    "tradestatus,pctChg,peTTM,pbMRQ,psTTM,pcfNcfTTM,isST"
).split(",")
FIELDS = {"P01": MINUTE_FIELDS, "P02": DAILY_FIELDS, "P03": BULK_FIELDS}
IDENTITY = {
    "P01": dict(code="sh.601577", start_date="2021-01-04", end_date="2021-03-31",
                frequency="5", adjustflag="3"),
    "P02": dict(code="sh.601577", start_date="2021-02-27", end_date="2021-02-27",
                frequency="d", adjustflag="3"),
    "P03": dict(date="2026-09-30"),
}


def minute_rows(count, start=0):
    # Deliberately includes non-session times: protocol tests infer no calendar.
    first = datetime(2021, 1, 4, 9, 35)
    rows = []
    for index in range(start, start + count):
        stamp = first + timedelta(minutes=5 * index)
        rows.append([stamp.strftime("%Y-%m-%d"), stamp.strftime("%Y%m%d%H%M%S") + "000",
                     "sh.601577", "10.0000", "11.0000", "9.0000", "10.0000",
                     "100", "1000.0000", "3"])
    return rows


def daily_rows():
    return [["2021-02-27", "sh.601577", "10", "11", "9", "10", "100", "1000", "3"]]


def bulk_rows(count):
    # Syntactically distinct codes, with no claim that these securities exist.
    return [["2026-09-30", f"sh.{600000 + index:06d}", "10", "11", "9", "10", "10",
             "100", "1000", "3", "", "1", "0", "", "", "", "", "0"]
            for index in range(count)]


def encode_body(message_type, parts):
    body = SEP.join(parts)
    return f"00.9.40{SEP}{message_type}{SEP}{len(body):010d}" + body


def response(case, rows, page=1, *, changes=None, message_type=None):
    record = json.dumps({"record": rows}, ensure_ascii=False, separators=(",", ":"))
    if case == "P03":
        parts = ["0", "success", BULK_METHOD, "anonymous", record, ",".join(BULK_FIELDS)]
        kind = "99"
    else:
        identity = IDENTITY[case]
        parts = ["0", "success", HISTORY_METHOD, "anonymous", str(page), "2000", record,
                 identity["code"], ",".join(FIELDS[case]), identity["start_date"],
                 identity["end_date"], identity["frequency"], identity["adjustflag"]]
        kind = "96"
    for index, value in (changes or {}).items():
        parts[index] = value
    return encode_body(message_type or kind, parts)


def safe_error(error):
    assert type(error.code) is str
    assert re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", error.code)
    assert str(error).isascii()
    assert PRIVATE_MARKER not in str(error)
    assert PRIVATE_MARKER not in repr(error)


@dataclass
class Page:
    raw: str
    data: object
    fields: object


def page(case, rows, number=1, **options):
    return Page(response(case, rows, number, **options), deepcopy(rows), list(FIELDS[case]))


class FakeResult:
    """Only models the SDK cursor and transport callback, never opens a socket."""

    def __init__(self, case, pending, captures):
        self.case, self.pending, self.captures = case, list(pending), captures
        self.error_code = "0"
        self.error_msg = ""
        self.data = []
        self.fields = list(FIELDS[case])
        self.cur_page_num = "1"
        self.cur_row_num = 0
        self.per_page_count = "20000" if case == "P03" else "2000"
        self.method = BULK_METHOD if case == "P03" else HISTORY_METHOD
        self.user_id = "anonymous"
        self.code = IDENTITY[case].get("code", "")
        self.start_date = IDENTITY[case].get("start_date", "")
        self.end_date = IDENTITY[case].get("end_date", "")
        self.frequency = IDENTITY[case].get("frequency", "")
        # The real history SDK slices the final character off a no-newline body.
        self.adjustflag = ""
        self.requested_pages = []
        self.next_calls = 0

    def receive(self):
        assert self.pending, "probe attempted an unplanned request"
        requested = None if self.case == "P03" else len(self.requested_pages) + 1
        self.requested_pages.append(requested)
        item = self.pending.pop(0)
        if item is None:
            # ResultData.next() leaves successful error_code and the old data.
            return False
        capture = inspect_response(item.raw, self.case, requested)
        self.captures.append(capture)
        self.data, self.fields = deepcopy(item.data), deepcopy(item.fields)
        self.cur_row_num = 0
        self.cur_page_num = str(capture["response_page"] or 1)
        return bool(self.data)

    def next(self):
        self.next_calls += 1
        assert self.case != "P03", "bulk response must never call next()"
        assert len(self.data) == 2000, "only a full history page may request another page"
        assert self.cur_row_num == len(self.data), "SDK cursor must be at this page's end"
        return self.receive()

    def get_data(self):
        raise AssertionError("unbounded SDK get_data() must never be called")


class FakeSDK:
    def __init__(self, case, pending, captures):
        self.result = FakeResult(case, pending, captures)
        self.calls = []

    def query_history_k_data_plus(self, code, fields, start_date=None, end_date=None,
                                  frequency="d", adjustflag="3"):
        self.calls.append((HISTORY_METHOD, dict(code=code, fields=fields, start_date=start_date,
                                              end_date=end_date, frequency=frequency,
                                              adjustflag=adjustflag)))
        self.result.receive()
        return self.result

    def query_daily_history_k_AStock(self, date=""):
        self.calls.append((BULK_METHOD, {"date": date}))
        self.result.receive()
        return self.result


def fake(case, pending):
    captures = []
    return FakeSDK(case, pending, captures), captures


@pytest.mark.parametrize("case,rows,requested", [
    ("P01", minute_rows(1), 1), ("P02", daily_rows(), 1), ("P03", bulk_rows(1), None),
])
def test_complete_frame_preserves_strings_and_identity_without_trailing_newline(case, rows, requested):
    result = inspect_response(response(case, rows), case, requested)
    assert result["rows"] == rows
    assert result["fields"] == FIELDS[case]
    assert result["response_page"] == requested
    assert result["source_identity"] == IDENTITY[case]


def test_raw_precision_and_empty_tokens_are_preserved():
    rows = bulk_rows(1)
    rows[0][2], rows[0][7] = "0.100000000000000001", "9007199254740993"
    result = inspect_response(response("P03", rows), "P03", None)
    assert result["rows"][0] == rows[0]
    assert result["rows"][0][10] == ""


@pytest.mark.parametrize("raw", [None, b"not text", "", "short", PRIVATE_MARKER])
def test_unrecognized_frames_have_only_safe_errors(raw, capsys):
    with pytest.raises(ProbeError) as caught:
        inspect_response(raw, "P01", 1)
    safe_error(caught.value)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("message_type,changes", [
    ("01", {}), ("03", {}), ("99", {}),
    ("96", {0: "10002007"}), ("96", {2: "login"}),
    ("96", {2: BULK_METHOD}), ("96", {3: PRIVATE_MARKER}),
    ("96", {8: ",".join(reversed(MINUTE_FIELDS))}),
    ("96", {8: ",".join([*MINUTE_FIELDS, "api_key"])}),
])
def test_history_auth_method_type_and_schema_are_rejected_without_echo(message_type, changes, capsys):
    raw = response("P01", minute_rows(1), changes={1: PRIVATE_MARKER, **changes},
                   message_type=message_type)
    with pytest.raises(ProbeError) as caught:
        inspect_response(raw, "P01", 1)
    safe_error(caught.value)
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("index,value", [
    (4, "0"), (4, "2"), (4, "x"), (5, "1999"), (7, "sz.000001"),
    (9, "2021-01-05"), (10, "2021-03-30"), (11, "d"), (12, "2"), (12, ""),
])
def test_history_request_identity_must_match_each_page(index, value):
    with pytest.raises(ProbeError) as caught:
        inspect_response(response("P01", minute_rows(1), changes={index: value}), "P01", 1)
    safe_error(caught.value)


@pytest.mark.parametrize("case", ["P01", "P03"])
@pytest.mark.parametrize("extra", [False, True])
def test_body_segment_count_is_exact(case, extra):
    raw = response(case, [])
    parts = raw[21:].split(SEP)
    parts = parts + ["unexpected"] if extra else parts[:-1]
    with pytest.raises(ProbeError) as caught:
        inspect_response(encode_body("99" if case == "P03" else "96", parts),
                         case, None if case == "P03" else 1)
    safe_error(caught.value)


@pytest.mark.parametrize("index,value", [(0, "2020-12-31"), (0, "2021-04-01"),
                                        (2, "sz.000001"), (9, "2")])
def test_history_row_identity_cannot_conflict_with_envelope(index, value):
    rows = minute_rows(1)
    rows[0][index] = value
    with pytest.raises(ProbeError) as caught:
        inspect_response(response("P01", rows), "P01", 1)
    safe_error(caught.value)


@pytest.mark.parametrize("index,value", [(0, "2026-09-29"), (1, "PRIVATE_MARKER_938"), (9, "2")])
def test_bulk_rows_enforce_fixed_date_code_shape_and_unadjusted_flag(index, value):
    rows = bulk_rows(1)
    rows[0][index] = value
    with pytest.raises(ProbeError) as caught:
        inspect_response(response("P03", rows), "P03", None)
    safe_error(caught.value)


def test_bulk_beijing_code_is_only_an_observed_source_label():
    rows = bulk_rows(1)
    rows[0][1] = "bj.430001"
    sdk, captures = fake("P03", [page("P03", rows)])
    result = run_query("P03", sdk, captures)
    assert result["query_state"] == "single_response_observed"
    assert result["coverage"] == "unverified"
    assert captures[0]["rows"][0][1] == "bj.430001"
    assert captures[0]["source_identity"] == {"date": "2026-09-30"}


@pytest.mark.parametrize("changes", [{0: "10002007"}, {2: HISTORY_METHOD},
                                    {3: PRIVATE_MARKER}, {5: ",".join(DAILY_FIELDS)}])
def test_bulk_envelope_has_its_own_whitelist(changes):
    with pytest.raises(ProbeError) as caught:
        inspect_response(response("P03", bulk_rows(1), changes=changes), "P03", None)
    safe_error(caught.value)


@pytest.mark.parametrize("value", [10, 10.0, True, None, ["10"], {"value": "10"}])
@pytest.mark.parametrize("case", ["P01", "P03"])
def test_every_cell_must_be_a_string(case, value):
    rows = minute_rows(1) if case == "P01" else bulk_rows(1)
    rows[0][3] = value
    with pytest.raises(ProbeError) as caught:
        inspect_response(response(case, rows), case, 1 if case == "P01" else None)
    safe_error(caught.value)


@pytest.mark.parametrize("rows", [None, {}, [None], [["too", "short"]]])
def test_record_container_and_width_are_validated(rows):
    with pytest.raises(ProbeError) as caught:
        inspect_response(response("P01", rows), "P01", 1)
    safe_error(caught.value)


@pytest.mark.parametrize("case,rows,state", [
    ("P01", minute_rows(1), "protocol_end_observed"),
    ("P02", [], "empty_observed"),
    ("P03", bulk_rows(1), "single_response_observed"),
])
def test_fixed_methods_and_request_arguments(case, rows, state):
    sdk, captures = fake(case, [page(case, rows)])
    result = run_query(case, sdk, captures)
    assert (result["query_state"], result["row_count"], result["page_count"]) == (state, len(rows), 1)
    assert result["coverage"] == "unverified"
    if case == "P03":
        assert sdk.calls == [(BULK_METHOD, IDENTITY[case])]
    else:
        assert sdk.calls == [(HISTORY_METHOD, {**IDENTITY[case], "fields": ",".join(FIELDS[case])})]
    assert sdk.result.next_calls == 0


@pytest.mark.parametrize("last_count", [0, 1, 1999])
def test_full_history_page_then_short_or_empty_page_is_protocol_end(last_count):
    sdk, captures = fake("P01", [page("P01", minute_rows(2000)),
                                 page("P01", minute_rows(last_count, 2000), 2)])
    result = run_query("P01", sdk, captures)
    assert result["query_state"] == "protocol_end_observed"
    assert result["row_count"] == 2000 + last_count
    assert result["page_count"] == 2
    assert sdk.result.requested_pages == [1, 2]
    assert sdk.result.next_calls == 1


def test_first_missing_capture_is_not_a_valid_empty_page():
    sdk, captures = fake("P02", [None])
    with pytest.raises(ProbeError) as caught:
        run_query("P02", sdk, captures)
    safe_error(caught.value)
    assert captures == []


def test_none_on_next_with_unchanged_success_code_is_not_protocol_end():
    sdk, captures = fake("P01", [page("P01", minute_rows(2000)), None])
    with pytest.raises(ProbeError) as caught:
        run_query("P01", sdk, captures)
    safe_error(caught.value)
    assert sdk.result.error_code == "0"
    assert sdk.result.requested_pages == [1, 2]
    assert len(captures) == 1


@pytest.mark.parametrize("wrong_number", [1, 3])
def test_repeated_or_skipped_response_page_cannot_end_the_query(wrong_number):
    sdk, captures = fake("P01", [page("P01", minute_rows(2000)),
                                 page("P01", minute_rows(1, 2000), wrong_number)])
    with pytest.raises(ProbeError) as caught:
        run_query("P01", sdk, captures)
    safe_error(caught.value)


@pytest.mark.parametrize("changes", [{8: ",".join(reversed(MINUTE_FIELDS))}, {12: "2"}])
def test_second_page_schema_or_flag_conflict_cannot_end_the_query(changes):
    sdk, captures = fake("P01", [page("P01", minute_rows(2000)),
                                 page("P01", minute_rows(1, 2000), 2, changes=changes)])
    with pytest.raises(ProbeError) as caught:
        run_query("P01", sdk, captures)
    safe_error(caught.value)


@pytest.mark.parametrize("change", ["row_token", "field_order", "non_string"])
@pytest.mark.parametrize("case", ["P01", "P03"])
def test_sdk_data_and_fields_must_match_the_captured_strings(case, change):
    item = page(case, minute_rows(1) if case == "P01" else bulk_rows(1))
    if change == "row_token":
        item.data[0][3] = item.data[0][3].split(".")[0] + ".00"  # Same number, different token.
    elif change == "field_order":
        item.fields = list(reversed(item.fields))
    else:
        item.data[0][3] = 11
    sdk, captures = fake(case, [item])
    with pytest.raises(ProbeError) as caught:
        run_query(case, sdk, captures)
    safe_error(caught.value)


def test_sdk_row_difference_on_second_page_is_detected():
    second = page("P01", minute_rows(1, 2000), 2)
    second.data[0][8] = "1000"
    sdk, captures = fake("P01", [page("P01", minute_rows(2000)), second])
    with pytest.raises(ProbeError) as caught:
        run_query("P01", sdk, captures)
    safe_error(caught.value)


@pytest.mark.parametrize("rows", [minute_rows(1) * 2, list(reversed(minute_rows(2)))])
def test_duplicate_or_reversed_row_keys_cannot_be_silently_accepted(rows):
    sdk, captures = fake("P01", [page("P01", rows)])
    with pytest.raises(ProbeError) as caught:
        run_query("P01", sdk, captures)
    safe_error(caught.value)


def test_duplicate_row_key_across_pages_is_rejected_without_deduplication():
    sdk, captures = fake("P01", [page("P01", minute_rows(2000)),
                                 page("P01", minute_rows(1, 1999), 2)])
    with pytest.raises(ProbeError) as caught:
        run_query("P01", sdk, captures)
    safe_error(caught.value)
    assert len(captures[0]["rows"]) + len(captures[1]["rows"]) == 2001


def test_three_full_pages_stop_before_an_unbounded_fourth_request():
    sdk, captures = fake("P01", [page("P01", minute_rows(2000, offset), number)
                                 for number, offset in enumerate((0, 2000, 4000), 1)])
    with pytest.raises(ProbeError) as caught:
        run_query("P01", sdk, captures)
    assert caught.value.code == "bounded_incomplete"
    safe_error(caught.value)
    assert sdk.result.requested_pages == [1, 2, 3]
    assert sdk.result.next_calls == 2
    assert sum(len(capture["rows"]) for capture in captures) == 6000


def test_short_third_page_may_end_within_both_limits():
    sdk, captures = fake("P01", [page("P01", minute_rows(2000)),
                                 page("P01", minute_rows(2000, 2000), 2),
                                 page("P01", minute_rows(1999, 4000), 3)])
    result = run_query("P01", sdk, captures)
    assert (result["query_state"], result["row_count"], result["page_count"]) == (
        "protocol_end_observed", 5999, 3)
    assert sdk.result.next_calls == 2


@pytest.mark.parametrize("count", [2000, 2001, 20000])
def test_bulk_boundary_uses_one_response_and_never_sdk_paging(count):
    sdk, captures = fake("P03", [page("P03", bulk_rows(count))])
    result = run_query("P03", sdk, captures)
    assert (result["query_state"], result["row_count"], result["page_count"]) == (
        "single_response_observed", count, 1)
    assert result["row_limit_reached"] is (count == 20000)
    assert result["coverage"] == "unverified"
    assert sdk.result.requested_pages == [None]
    assert sdk.result.next_calls == 0


@pytest.mark.parametrize("case,count", [("P01", 2001), ("P03", 20001)])
def test_oversized_page_is_rejected_before_any_more_requests(case, count):
    rows = minute_rows(count) if case == "P01" else bulk_rows(count)
    sdk, captures = fake(case, [page(case, rows)])
    with pytest.raises(ProbeError) as caught:
        run_query(case, sdk, captures)
    safe_error(caught.value)
    assert sdk.result.next_calls == 0
