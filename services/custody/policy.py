from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml

from services.common.models import Intent


@dataclass(frozen=True)
class Tier:
    name: str
    max_amount: int | None
    approvals_required: int


@dataclass(frozen=True)
class PolicyDecision:
    status: str
    tier: str
    approvals_required: int
    reason: str
    matched_rule: str


@dataclass(frozen=True)
class PolicyContext:
    registry: Any
    asset: Any
    actor_address: str
    destination_address: str
    now_chain_ts: int
    recent_total: Callable[[str, int], int]


class Policy:
    def __init__(self, tiers: list[Tier], rules: dict[str, Any], approvers: list[str]) -> None:
        self.tiers = tiers
        self.rules = rules
        self.approvers = approvers

    @classmethod
    def from_file(cls, path: Path) -> "Policy":
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tiers = [
            Tier(
                name=str(item["name"]),
                max_amount=item["max_amount"],
                approvals_required=int(item["approvals_required"]),
            )
            for item in data["tiers"]
        ]
        return cls(tiers=tiers, rules=data["rules"], approvers=list(data["approvers"]))

    def evaluate(self, intent: Intent, ctx: PolicyContext) -> PolicyDecision:
        if self.rules.get("deny_when_paused") and bool(ctx.asset.functions.paused().call()):
            return PolicyDecision("denied", "none", 0, "token_paused", "deny_when_paused")
        if self.rules.get("destination_allowlist"):
            can_transfer = ctx.registry.functions.canTransfer(
                ctx.actor_address, ctx.destination_address, intent.amount
            ).call()[0]
            if not bool(can_transfer):
                return PolicyDecision(
                    "denied", "none", 0, "destination_not_allowlisted", "destination_allowlist"
                )
        velocity = self.rules.get("velocity")
        if isinstance(velocity, dict):
            window_s = int(velocity["window_minutes"]) * 60
            max_total = int(velocity["max_total_amount"])
            recent_total = ctx.recent_total(intent.actor, window_s)
            if recent_total + intent.amount > max_total:
                return PolicyDecision("denied", "none", 0, "velocity_exceeded", "velocity")
        for tier in self.tiers:
            if tier.max_amount is None or intent.amount <= tier.max_amount:
                status = "signed" if tier.approvals_required == 0 else "pending_approvals"
                return PolicyDecision(
                    status, tier.name, tier.approvals_required, "matched_tier", "tier"
                )
        raise ValueError("policy has no unbounded tier")
