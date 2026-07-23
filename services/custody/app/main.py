from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from services.common.deployment import Deployment, wait_for_deployment
from services.common.models import Intent
from services.custody.policy import Policy

app = FastAPI(title="tokenize-stack custody")
allowlist = {"investor-a", "investor-b", "issuer"}
policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))
pending: dict[str, Intent] = {}
deployment: Deployment | None = None


@app.on_event("startup")
def load_deployment() -> None:
    global deployment
    deployment = wait_for_deployment()


@app.get("/policy")
def get_policy() -> dict[str, object]:
    return {"tiers": [tier.__dict__ for tier in policy.tiers], "rules": policy.rules}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "chain_id": str(deployment.chain_id if deployment else "unknown")}


@app.post("/sign-intent")
def sign_intent(intent: Intent) -> dict[str, object]:
    decision = policy.evaluate(intent, allowlist)
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
