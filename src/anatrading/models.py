"""Source observations; unknown semantics are not normalized market facts."""
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal

VALUE_FIELDS = ("open", "high", "low", "close", "volume", "amount")
VERSIONS = {"schema": "1", "decode": "1", "normalization": "disabled-1", "quality": "1", "numeric": "decimal38.18-bigint-v1"}


@dataclass(frozen=True)
class Check:
    name: str
    outcome: Literal["pass", "fail", "not_evaluated"]
    reason: str | None = None
    assumption: str | None = None

    def __post_init__(self):
        if self.outcome not in {"pass", "fail", "not_evaluated"}:
            raise ValueError("Unknown check outcome")
        if self.outcome == "not_evaluated" and not self.reason:
            raise ValueError("An unevaluated check needs a reason")


@dataclass
class SourceRow:
    ordinal: int
    locator: str
    source_label: str | None
    label: str | None
    tokens: dict[str, str | None]
    values: dict[str, Decimal | int | None]
    checks: list[Check] = field(default_factory=list)
    volume_shares: int | None = None
    amount_cny: Decimal | None = None


@dataclass
class Decoded:
    contract: dict[str, Any]
    metadata: dict[str, Any]
    rows: list[SourceRow]
    checks: list[Check] = field(default_factory=list)


class DecodeError(ValueError):
    """Recognized market material cannot form a decoded snapshot."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class NonMarketPayload(DecodeError):
    """Reject before any payload bytes are persisted."""
