from __future__ import annotations

from pathlib import Path

from services.common.models import Intent
from services.custody.policy import Policy


def test_policy_queues_dual_tier() -> None:
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "investor-a", 125_000, "asset", "lock")

    decision = policy.evaluate(intent, {"investor-a"})

    assert decision.status == "queue"
    assert decision.tier == "dual"
    assert decision.approvals_required == 2


def test_policy_denies_unallowlisted_destination() -> None:
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "unknown", 1, "asset", "lock")

    decision = policy.evaluate(intent, set())

    assert decision.status == "deny"
    assert decision.reason == "destination_not_allowlisted"
