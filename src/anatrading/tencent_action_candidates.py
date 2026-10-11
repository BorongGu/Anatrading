"""只提取腾讯日线第6槽的源声明，不解释权益、单位或历史可得时间。"""
import hashlib

from .models import DecodeError
from .public_market import LEGACY_CAPTURE_VERSION, validate_capture


_FIELDS = ("nd", "fh_sh", "djr", "cqr", "FHcontent")


class UnsupportedSourceActionShape(DecodeError):
    """整份候选提取失败；保留首个未知对象的来源和位置，不返回部分结果。"""

    def __init__(self, context):
        self.context = context
        super().__init__("unsupported_tencent_action_shape")


def extract_tencent_action_candidates(raw: bytes) -> dict:
    """读取一个已保存的完整capture包，原样保留五字段、顺序与位置。

    空对象只计数；非空未知形状整份拒绝。仅接受既有腾讯校验范围，
    不读写文件或联网，也不从字符串推定经济事件、日期或现金单位。
    """
    capture = validate_capture(raw, "tencent-daily-capture-v1")
    if not capture.payload:
        raise DecodeError("empty_public_market_result")
    envelope = capture.envelope
    source_symbol = capture.symbol[-2:].lower() + capture.symbol[:6]
    identity = dict(
        method_id="tencent-action-candidates-v1", source=capture.source,
        requested_symbol=capture.symbol, source_symbol=source_symbol,
        response_identity="source_key", capture_version=envelope["capture_version"],
        capture_sha256=hashlib.sha256(raw).hexdigest(),
        body_sha256=envelope["body_sha256"], request_sha256=envelope["request_sha256"],
        response_headers_sha256=envelope["response_headers_sha256"],
        qualification="retrospective_source_candidates", economic_semantics="unverified",
        coverage="unknown", historical_known_at=None,
    )
    if envelope["capture_version"] == LEGACY_CAPTURE_VERSION:
        provenance = dict(envelope["provenance"])
        identity.update(provenance=provenance, provenance_hash_verification="syntax_only",
                        **{key: provenance[key] for key in
                           ("capture_mode", "header_cardinality", "transport_evidence")})
    candidates = []
    empty_count = 0
    for index, row in enumerate(capture.payload):
        obj = row[6]
        if not obj:
            empty_count += 1
            continue
        location = dict(ordinal=index + 1, source_date=row[0],
                        locator=f"body:$.data.{source_symbol}.day[{index}][6]")
        if set(obj) != set(_FIELDS) or any(type(value) is not str for value in obj.values()):
            raise UnsupportedSourceActionShape(dict(**identity, **location))
        candidates.append(dict(**location, **{key: obj[key] for key in _FIELDS}))
    return dict(**identity, source_row_count=len(capture.payload), empty_object_count=empty_count,
                candidate_count=len(candidates), candidates=candidates)
