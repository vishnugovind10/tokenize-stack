from __future__ import annotations

from fastapi import FastAPI
from web3.contract import Contract

from services.common import chain
from services.common.deployment import Deployment, wait_for_deployment
from services.settlement.store import SettlementStore

app = FastAPI(title="tokenize-stack recon")
deployment: Deployment | None = None
escrow_contract: Contract | None = None
store: SettlementStore | None = None

CHAIN_STATES = {
    0: "NONE",
    1: "LOCKED",
    2: "SETTLED",
    3: "UNWOUND",
}


@app.on_event("startup")
def load_deployment() -> None:
    global deployment, escrow_contract, store
    deployment = wait_for_deployment()
    w3 = chain.get_w3(deployment)
    escrow_contract = chain.escrow(w3, deployment)
    store = SettlementStore()


@app.on_event("shutdown")
def close_store() -> None:
    if store is not None:
        store.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "chain_id": str(deployment.chain_id if deployment else "unknown")}


@app.get("/report")
def get_report() -> dict[str, object]:
    if escrow_contract is None or store is None:
        raise RuntimeError("recon service not initialized")
    rows: list[dict[str, object]] = []
    mismatches = 0
    for trade in store.list_trades():
        chain_state = _chain_state(escrow_contract, trade.trade_id)
        status = "MATCHED" if _matches(chain_state, trade.state) else "MISMATCH"
        if status == "MISMATCH":
            mismatches += 1
        rows.append(
            {
                "subject": trade.trade_id,
                "chain": chain_state,
                "settlement_view": trade.state,
                "custody_view": trade.lock_intent_id or "missing",
                "status": status,
            }
        )
    marker = "RECON: ALL MATCHED" if mismatches == 0 else f"RECON: MISMATCH ({mismatches})"
    return {
        "rows": rows,
        "matched": len(rows) - mismatches,
        "mismatched": mismatches,
        "unexplained": 0,
        "marker": marker,
    }


def _chain_state(escrow: Contract, trade_id: str) -> str:
    raw = escrow.functions.trades(chain.trade_key(trade_id)).call()
    return CHAIN_STATES.get(int(raw[5]), "UNKNOWN")


def _matches(chain_state: str, settlement_state: str) -> bool:
    if settlement_state in {"PENDING_LOCK", "PENDING_SETTLE", "UNWINDING"}:
        return False
    if settlement_state in {"FAILED_LOCK", "FAILED_SETTLE"}:
        return chain_state == "NONE"
    return chain_state == settlement_state
