from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class TradeState(StrEnum):
    PENDING_LOCK = "PENDING_LOCK"
    LOCKED = "LOCKED"
    PENDING_SETTLE = "PENDING_SETTLE"
    SETTLED = "SETTLED"
    UNWINDING = "UNWINDING"
    UNWOUND = "UNWOUND"
    FAILED = "FAILED"


class RestrictionReason(StrEnum):
    NONE = "None"
    NOT_ALLOWLISTED = "NotAllowlisted"
    TOKEN_PAUSED = "TokenPaused"
    LOCKUP_ACTIVE = "LockupActive"


@dataclass(frozen=True)
class Intent:
    intent_id: str
    actor: str
    destination: str
    amount: int
    asset: str
    action: str
    params: dict[str, object] = field(default_factory=dict)


@dataclass
class Trade:
    trade_id: str
    seller: str
    buyer: str
    asset_amount: int
    cash_amount: int
    state: TradeState = TradeState.PENDING_LOCK
    failure_reason: str | None = None
