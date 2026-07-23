from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from services.common.audit import AuditChain, verify_records
from services.common.models import Intent, RestrictionReason, Trade, TradeState
from services.custody.policy import Policy
from services.recon.report import build_report

PERSONAS = ["issuer", "investor-a", "investor-b", "investor-c", "investor-d", "investor-e"]


@dataclass(frozen=True)
class ScenarioResult:
    lines: list[str]
    audit_path: Path


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


def _base_ledger() -> Ledger:
    ledger = Ledger()
    for persona in PERSONAS:
        ledger.allow(persona)
        ledger.mint_cash(persona, 500_000)
    ledger.mint_asset("issuer", 1_000_000)
    return ledger


def run_demo(audit_path: Path) -> ScenarioResult:
    ledger = _base_ledger()
    audit = AuditChain(audit_path)
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    trades: list[Trade] = []
    lines = ["[SIM] ISSUE: 1000000 asset units to issuer"]
    audit.append("contracts", "issuer", "issue", {"amount": 1_000_000})

    trade_sizes = [5_000, 25_000, 50_000, 125_000, 250_000]
    for index, amount in enumerate(trade_sizes, start=1):
        buyer = PERSONAS[index]
        intent = Intent(
            intent_id=f"intent-{index}",
            actor="issuer",
            destination=buyer,
            amount=amount,
            asset="RestrictedAssetToken",
            action="lock_asset",
        )
        decision = policy.evaluate(intent, ledger.allowlist)
        audit.append("custody", "issuer", decision.status, decision)
        if decision.status == "queue":
            lines.append(
                f"[SIM] APPROVALS: {intent.intent_id} tier={decision.tier} approvals=complete"
            )
            audit.append("custody", "ops", "approve", {"intent_id": intent.intent_id})
        trade = Trade(
            trade_id=f"trade-{index}",
            seller="issuer",
            buyer=buyer,
            asset_amount=amount,
            cash_amount=amount,
        )
        ledger.lock_asset(trade)
        audit.append("settlement", "issuer", "asset_locked", trade)
        ledger.settle(trade)
        audit.append("settlement", buyer, "settled", trade)
        trades.append(trade)

    paid = _run_coupon_round(ledger, audit, interrupt_after=None)
    lines.append(f"[SIM] COUPON: PAID {paid} HOLDERS")
    report = build_report(set(ledger.locked_assets), trades)
    lines.append(report.marker)
    audit.write()
    ok, message = verify_records(audit.records)
    lines.append("AUDIT: CHAIN INTACT" if ok else f"AUDIT: {message}")
    lines.append("[SIM] CONSOLE: unavailable in sim mode")
    return ScenarioResult(lines, audit_path)


def run_failures(audit_path: Path) -> ScenarioResult:
    ledger = _base_ledger()
    audit = AuditChain(audit_path)
    lines: list[str] = ["[SIM] FAILURE DEMOS"]

    trade = Trade(
        trade_id="failure-cash",
        seller="issuer",
        buyer="investor-a",
        asset_amount=25_000,
        cash_amount=600_000,
    )
    ledger.lock_asset(trade)
    audit.append("settlement", "issuer", "asset_locked", trade)
    try:
        ledger.settle(trade)
    except ValueError as exc:
        trade.failure_reason = str(exc)
        trade.state = TradeState.FAILED
        audit.append("settlement", trade.buyer, "settle_failed", {"reason": str(exc)})
    mismatch = build_report(set(ledger.locked_assets), [trade])
    lines.append(mismatch.marker)
    ledger.unwind(trade)
    audit.append("settlement", "system", "unwound", trade)
    lines.append("UNWIND: COMPLETE")

    restricted = Trade(
        trade_id="failure-restricted",
        seller="issuer",
        buyer="unknown-buyer",
        asset_amount=5_000,
        cash_amount=5_000,
    )
    ledger.mint_cash("unknown-buyer", 10_000)
    ledger.lock_asset(restricted)
    try:
        ledger.settle(restricted)
    except PermissionError as exc:
        audit.append("settlement", restricted.buyer, "restriction_revert", {"reason": str(exc)})
        lines.append(f"RESTRICTED: SURFACED {exc}")
    ledger.unwind(restricted)

    paid = _run_coupon_round(ledger, audit, interrupt_after=2)
    if paid == len([holder for holder, balance in ledger.asset_balances.items() if balance > 0]):
        lines.append("COUPON: NO DOUBLE PAYMENT")

    audit.write()
    ok, message = verify_records(audit.records)
    lines.append("AUDIT: CHAIN INTACT" if ok else f"AUDIT: {message}")
    return ScenarioResult(lines, audit_path)


def _run_coupon_round(ledger: Ledger, audit: AuditChain, interrupt_after: int | None) -> int:
    holders = [holder for holder, balance in sorted(ledger.asset_balances.items()) if balance > 0]
    cursor = 0
    while cursor < len(holders):
        holder = holders[cursor]
        if interrupt_after is not None and cursor == interrupt_after:
            audit.append("coupon", "system", "batch_interrupted", {"cursor": cursor})
            interrupt_after = None
            continue
        if holder not in ledger.coupon_paid:
            ledger.coupon_paid[holder] = 100
            audit.append("coupon", "issuer", "paid", {"holder": holder, "amount": 100})
        cursor += 1
    return len(ledger.coupon_paid)
