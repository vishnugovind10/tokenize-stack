from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from web3 import Web3
from web3.contract import Contract

from services.common import chain
from services.common.audit_client import post_event
from services.common.deployment import Deployment, wait_for_deployment
from services.common.models import Intent
from services.custody.actions import build_transaction, resolve_address
from services.custody.policy import Policy, PolicyContext
from services.custody.signer import signer_for
from services.custody.store import CustodyStore, IntentRow, required_counts_from_tiers

app = FastAPI(title="tokenize-stack custody")
policy = Policy.from_file(Path("services/custody/policies/policy.yaml"))

deployment: Deployment | None = None
w3: Web3 | None = None
registry_contract: Contract | None = None
asset_contract: Contract | None = None
cash_contract: Contract | None = None
escrow_contract: Contract | None = None
store: CustodyStore | None = None


class ApprovalIn(BaseModel):
    approver: str


@app.on_event("startup")
def load_deployment() -> None:
    global deployment, w3, registry_contract, asset_contract, cash_contract, escrow_contract, store
    deployment = wait_for_deployment()
    w3 = chain.get_w3(deployment)
    registry_contract = chain.registry(w3, deployment)
    asset_contract = chain.asset(w3, deployment)
    cash_contract = chain.cash(w3, deployment)
    escrow_contract = chain.escrow(w3, deployment)
    store = CustodyStore()


@app.on_event("shutdown")
def close_store() -> None:
    if store is not None:
        store.close()


@app.get("/policy")
def get_policy() -> dict[str, object]:
    return {"tiers": [tier.__dict__ for tier in policy.tiers], "rules": policy.rules}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "chain_id": str(deployment.chain_id if deployment else "unknown")}


@app.post("/sign-intent")
def sign_intent(intent: Intent) -> dict[str, object]:
    custody = _ctx()
    now_chain_ts = _chain_timestamp(custody["w3"])
    decision = policy.evaluate(intent, _policy_context(intent, now_chain_ts))
    status = decision.status
    tx_hash: str | None = None
    reason = decision.reason
    if status == "signed":
        try:
            tx_hash = _broadcast(intent)
        except Exception as exc:
            status = "failed"
            reason = chain.decode_revert(exc)
    row = custody["store"].insert_intent(
        intent,
        decision.tier,
        status,
        tx_hash,
        now_chain_ts,
        decision.matched_rule,
    )
    post_event(
        "custody",
        intent.actor,
        "intent_evaluated",
        {
            "intent_id": intent.intent_id,
            "status": status,
            "tier": decision.tier,
            "matched_rule": decision.matched_rule,
            "reason": reason,
            "tx_hash": tx_hash,
        },
    )
    if tx_hash is not None:
        post_event(
            "custody",
            intent.actor,
            "intent_broadcast",
            {"intent_id": intent.intent_id, "status": status, "tx_hash": tx_hash},
        )
    if status == "denied":
        return {**_row_payload(row), "reason": reason}
    if status == "failed":
        return {**_row_payload(row), "reason": reason}
    if status == "pending_approvals":
        return {**_row_payload(row), "approvals_required": decision.approvals_required}
    return _row_payload(row)


@app.post("/execute")
def execute(intent: Intent) -> dict[str, object]:
    custody = _ctx()
    now_chain_ts = _chain_timestamp(custody["w3"])
    status = "signed"
    reason: str | None = None
    tx_hash: str | None = None
    try:
        tx_hash = _broadcast(intent)
    except Exception as exc:
        status = "failed"
        reason = chain.decode_revert(exc)
    row = custody["store"].insert_intent(
        intent,
        "service",
        status,
        tx_hash,
        now_chain_ts,
        "service_execution",
    )
    post_event(
        "custody",
        intent.actor,
        "intent_evaluated",
        {
            "intent_id": intent.intent_id,
            "status": status,
            "tier": "service",
            "matched_rule": "service_execution",
            "reason": reason,
            "tx_hash": tx_hash,
        },
    )
    if tx_hash is not None:
        post_event(
            "custody",
            intent.actor,
            "intent_broadcast",
            {"intent_id": intent.intent_id, "status": status, "tx_hash": tx_hash},
        )
    if reason is not None:
        return {**_row_payload(row), "reason": reason}
    return _row_payload(row)


@app.get("/approvals/pending")
def approvals_pending() -> list[dict[str, object]]:
    custody = _ctx()
    required_counts = required_counts_from_tiers(policy.tiers)
    return [
        {
            **_row_payload(pending.intent),
            "collected": pending.collected,
            "required": pending.required,
        }
        for pending in custody["store"].pending(required_counts)
    ]


@app.post("/approvals/{intent_id}/approve")
def approve(intent_id: str, approval: ApprovalIn) -> dict[str, object]:
    custody = _ctx()
    row = custody["store"].get_intent(intent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown intent")
    if row.status != "pending_approvals":
        raise HTTPException(status_code=409, detail=f"intent is {row.status}")
    if approval.approver not in policy.approvers:
        raise HTTPException(status_code=403, detail="unknown approver")
    now_chain_ts = _chain_timestamp(custody["w3"])
    try:
        custody["store"].add_approval(intent_id, approval.approver, now_chain_ts)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="duplicate approval") from exc
    approvers = custody["store"].approvals_for(intent_id)
    required = required_counts_from_tiers(policy.tiers)[row.tier]
    post_event(
        "custody",
        approval.approver,
        "approval_recorded",
        {"intent_id": intent_id, "collected": len(approvers), "required": required},
    )
    if len(approvers) >= required:
        tx_hash = _broadcast(row.to_intent())
        custody["store"].update_status(intent_id, "approved_signed", tx_hash)
        post_event(
            "custody",
            row.actor,
            "intent_broadcast",
            {"intent_id": intent_id, "status": "approved_signed", "tx_hash": tx_hash},
        )
        updated = custody["store"].get_intent(intent_id)
        if updated is None:
            raise RuntimeError(f"intent vanished after approval: {intent_id}")
        return {**_row_payload(updated), "approvers": approvers, "required": required}
    return {**_row_payload(row), "approvers": approvers, "required": required}


@app.get("/intents/{intent_id}")
def get_intent(intent_id: str) -> dict[str, object]:
    row = _ctx()["store"].get_intent(intent_id)
    if row is None:
        raise HTTPException(status_code=404, detail="unknown intent")
    return _row_payload(row)


def _ctx() -> dict[str, Any]:
    if (
        deployment is None
        or w3 is None
        or registry_contract is None
        or asset_contract is None
        or cash_contract is None
        or escrow_contract is None
        or store is None
    ):
        raise RuntimeError("custody service not initialized")
    return {
        "deployment": deployment,
        "w3": w3,
        "registry": registry_contract,
        "asset": asset_contract,
        "cash": cash_contract,
        "escrow": escrow_contract,
        "store": store,
    }


def _policy_context(intent: Intent, now_chain_ts: int) -> PolicyContext:
    custody = _ctx()
    deployment_obj = custody["deployment"]
    return PolicyContext(
        registry=custody["registry"],
        asset=custody["registry"],
        actor_address=resolve_address(deployment_obj, intent.actor),
        destination_address=resolve_address(deployment_obj, intent.destination),
        now_chain_ts=now_chain_ts,
        recent_total=lambda actor, window_s: custody["store"].recent_total(
            actor, now_chain_ts - window_s
        ),
    )


def _chain_timestamp(w3_obj: Web3) -> int:
    return int(w3_obj.eth.get_block("latest")["timestamp"])


def _broadcast(intent: Intent) -> str:
    custody = _ctx()
    tx_params = build_transaction(
        intent,
        custody["deployment"],
        custody["asset"],
        custody["cash"],
        custody["escrow"],
    )
    receipt = asyncio.run(
        chain.send(custody["w3"], custody["deployment"], signer_for(intent.actor), tx_params)
    )
    return str(receipt["transactionHash"].to_0x_hex())


def _row_payload(row: IntentRow) -> dict[str, object]:
    return asdict(row)
