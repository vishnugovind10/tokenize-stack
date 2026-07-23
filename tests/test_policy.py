from __future__ import annotations

from pathlib import Path

from services.common.models import Intent, Ledger
from services.custody.policy import Policy


def test_policy_queues_dual_tier() -> None:
    ledger = Ledger(allowlist={"investor-a"})
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "investor-a", 125_000, "asset", "lock")

    decision = policy.evaluate(intent, ledger)

    assert decision.status == "queue"
    assert decision.tier == "dual"
    assert decision.approvals_required == 2


def test_policy_denies_unallowlisted_destination() -> None:
    ledger = Ledger()
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "unknown", 1, "asset", "lock")

    decision = policy.evaluate(intent, ledger)

    assert decision.status == "deny"
    assert decision.reason == "destination_not_allowlisted"
