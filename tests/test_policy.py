from __future__ import annotations

from pathlib import Path
from services.common.models import Intent
from services.custody.policy import Policy, PolicyContext


class Call:
    def __init__(self, value: object) -> None:
        self.value = value

    def call(self) -> object:
        return self.value


class RegistryFunctions:
    def __init__(self, allowed: bool) -> None:
        self.allowed = allowed

    def canTransfer(self, actor: str, destination: str, amount: int) -> Call:
        return Call((self.allowed, 0))


class Registry:
    def __init__(self, allowed: bool) -> None:
        self.functions = RegistryFunctions(allowed)


class AssetFunctions:
    def __init__(self, paused: bool) -> None:
        self._paused = paused

    def paused(self) -> Call:
        return Call(self._paused)


class Asset:
    def __init__(self, paused: bool) -> None:
        self.functions = AssetFunctions(paused)


def ctx(
    *,
    allowed: bool = True,
    paused: bool = False,
    now: int = 10_000,
    totals: dict[tuple[str, int], int] | None = None,
) -> PolicyContext:
    totals = totals or {}
    return PolicyContext(
        registry=Registry(allowed),
        asset=Asset(paused),
        actor_address="0x0000000000000000000000000000000000000001",
        destination_address="0x0000000000000000000000000000000000000002",
        now_chain_ts=now,
        recent_total=lambda actor, window_s: totals.get((actor, now - window_s), 0),
    )


def test_policy_queues_dual_tier() -> None:
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "investor-a", 125_000, "cash", "transfer_cash")

    decision = policy.evaluate(intent, ctx())

    assert decision.status == "pending_approvals"
    assert decision.tier == "dual"
    assert decision.approvals_required == 2


def test_policy_denies_unallowlisted_destination() -> None:
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "unknown", 1, "cash", "transfer_cash")

    decision = policy.evaluate(intent, ctx(allowed=False))

    assert decision.status == "denied"
    assert decision.reason == "destination_not_allowlisted"


def test_policy_denies_paused_token() -> None:
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "investor-a", 1, "cash", "transfer_cash")

    decision = policy.evaluate(intent, ctx(paused=True))

    assert decision.status == "denied"
    assert decision.reason == "token_paused"


def test_policy_velocity_uses_chain_time_window() -> None:
    policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
    intent = Intent("i1", "issuer", "investor-a", 125_000, "cash", "transfer_cash")

    blocked = policy.evaluate(intent, ctx(now=10_000, totals={("issuer", 6_400): 450_000}))
    admitted = policy.evaluate(intent, ctx(now=14_000, totals={("issuer", 10_400): 0}))

    assert blocked.status == "denied"
    assert blocked.reason == "velocity_exceeded"
    assert admitted.status == "pending_approvals"
