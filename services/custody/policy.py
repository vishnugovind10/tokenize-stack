from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from services.common.models import Intent, Ledger


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

    def evaluate(self, intent: Intent, ledger: Ledger) -> PolicyDecision:
        if self.rules.get("destination_allowlist") and intent.destination not in ledger.allowlist:
            return PolicyDecision("deny", "none", 0, "destination_not_allowlisted")
        for tier in self.tiers:
            if tier.max_amount is None or intent.amount <= tier.max_amount:
                status = "allow" if tier.approvals_required == 0 else "queue"
                return PolicyDecision(status, tier.name, tier.approvals_required, "matched_tier")
        raise ValueError("policy has no unbounded tier")
