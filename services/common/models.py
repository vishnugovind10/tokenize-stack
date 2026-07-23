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


@dataclass
class Trade:
    trade_id: str
    seller: str
    buyer: str
    asset_amount: int
    cash_amount: int
    state: TradeState = TradeState.PENDING_LOCK
    failure_reason: str | None = None


@dataclass
class Ledger:
    asset_balances: dict[str, int] = field(default_factory=dict)
    cash_balances: dict[str, int] = field(default_factory=dict)
    allowlist: set[str] = field(default_factory=set)
    locked_assets: dict[str, tuple[str, int]] = field(default_factory=dict)
    coupon_paid: dict[str, int] = field(default_factory=dict)

    def allow(self, address: str) -> None:
        self.allowlist.add(address)

    def restriction_for(self, destination: str) -> RestrictionReason:
        if destination not in self.allowlist:
            return RestrictionReason.NOT_ALLOWLISTED
        return RestrictionReason.NONE

    def mint_asset(self, address: str, amount: int) -> None:
        self.asset_balances[address] = self.asset_balances.get(address, 0) + amount

    def mint_cash(self, address: str, amount: int) -> None:
        self.cash_balances[address] = self.cash_balances.get(address, 0) + amount

    def lock_asset(self, trade: Trade) -> None:
        seller_balance = self.asset_balances.get(trade.seller, 0)
        if seller_balance < trade.asset_amount:
            raise ValueError("seller asset balance too low")
        self.asset_balances[trade.seller] = seller_balance - trade.asset_amount
        self.locked_assets[trade.trade_id] = (trade.seller, trade.asset_amount)
        trade.state = TradeState.LOCKED

    def settle(self, trade: Trade) -> None:
        reason = self.restriction_for(trade.buyer)
        if reason is not RestrictionReason.NONE:
            raise PermissionError(reason.value)
        buyer_cash = self.cash_balances.get(trade.buyer, 0)
        if buyer_cash < trade.cash_amount:
            raise ValueError("cash_leg_insufficient")
        locked = self.locked_assets.pop(trade.trade_id, None)
        if locked is None:
            raise ValueError("asset_not_locked")
        self.cash_balances[trade.buyer] = buyer_cash - trade.cash_amount
        self.cash_balances[trade.seller] = (
            self.cash_balances.get(trade.seller, 0) + trade.cash_amount
        )
        self.asset_balances[trade.buyer] = (
            self.asset_balances.get(trade.buyer, 0) + trade.asset_amount
        )
        trade.state = TradeState.SETTLED

    def unwind(self, trade: Trade) -> None:
        locked = self.locked_assets.pop(trade.trade_id, None)
        if locked is None:
            raise ValueError("asset_not_locked")
        seller, amount = locked
        self.asset_balances[seller] = self.asset_balances.get(seller, 0) + amount
        trade.state = TradeState.UNWOUND
