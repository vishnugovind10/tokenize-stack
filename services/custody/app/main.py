from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from services.common.models import Intent, Ledger
from services.custody.policy import Policy

app = FastAPI(title="tokenize-stack custody")
ledger = Ledger(allowlist={"investor-a", "investor-b", "issuer"})
policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
pending: dict[str, Intent] = {}


@app.get("/policy")
def get_policy() -> dict[str, object]:
    return {"tiers": [tier.__dict__ for tier in policy.tiers], "rules": policy.rules}


@app.post("/sign-intent")
def sign_intent(intent: Intent) -> dict[str, object]:
    decision = policy.evaluate(intent, ledger)
    if decision.status == "queue":
        pending[intent.intent_id] = intent
    return decision.__dict__


@app.get("/approvals/pending")
def approvals_pending() -> list[dict[str, object]]:
    return [intent.__dict__ for intent in pending.values()]


@app.post("/approvals/{intent_id}/approve")
def approve(intent_id: str) -> dict[str, object]:
    pending.pop(intent_id, None)
    return {"intent_id": intent_id, "status": "approved"}
