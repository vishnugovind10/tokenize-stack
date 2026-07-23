from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI
from web3 import Web3
from web3.contract import Contract

from services.common import chain
from services.common.deployment import Deployment, wait_for_deployment
from services.settlement.store import SettlementStore, TradeRow

app = FastAPI(title="tokenize-stack recon")
deployment: Deployment | None = None
escrow_contract: Contract | None = None
asset_contract: Contract | None = None
cash_contract: Contract | None = None
distributor_contract: Contract | None = None
store: SettlementStore | None = None
CUSTODY_DB = Path("/data/custody.db")

CHAIN_STATES = {
    0: "NONE",
    1: "LOCKED",
    2: "SETTLED",
    3: "UNWOUND",
}


@app.on_event("startup")
def load_deployment() -> None:
    global deployment, escrow_contract, asset_contract, cash_contract, distributor_contract, store
    deployment = wait_for_deployment()
    w3 = chain.get_w3(deployment)
    escrow_contract = chain.escrow(w3, deployment)
    asset_contract = chain.asset(w3, deployment)
    cash_contract = chain.cash(w3, deployment)
    distributor_contract = chain.distributor(w3, deployment)
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
    if (
        deployment is None
        or escrow_contract is None
        or asset_contract is None
        or cash_contract is None
        or distributor_contract is None
        or store is None
    ):
        raise RuntimeError("recon service not initialized")
    custody = _custody_intents(store.get_meta_int("reset_chain_ts", 0))
    settlement_trade_ids = {trade.trade_id for trade in store.list_trades()}
    rows: list[dict[str, object]] = []
    mismatches = 0
    for trade in store.list_trades():
        chain_view = _chain_trade(escrow_contract, trade.trade_id)
        custody_view = _trade_custody_view(custody, trade)
        status = (
            "MATCHED"
            if _matches(str(chain_view["state"]), trade.state) and custody_view["matched"]
            else "MISMATCH"
        )
        if status == "MISMATCH":
            mismatches += 1
        rows.append(
            {
                "subject": trade.trade_id,
                "type": "trade",
                "chain": chain_view,
                "settlement_view": trade.state,
                "custody_view": custody_view,
                "status": status,
            }
        )
    unexplained = 0
    for intent in custody:
        trade_id = str(_params(intent).get("trade_id", ""))
        if trade_id and trade_id not in settlement_trade_ids:
            unexplained += 1
            rows.append(
                {
                    "subject": trade_id,
                    "type": "custody_intent",
                    "chain": "unknown",
                    "settlement_view": "missing",
                    "custody_view": _intent_view(intent),
                    "status": "UNEXPLAINED",
                }
            )
    rows.extend(_balance_rows(deployment, asset_contract, cash_contract))
    coupon_row = _coupon_row(deployment, asset_contract, distributor_contract, store, custody)
    if coupon_row is not None:
        rows.append(coupon_row)
        if coupon_row["status"] == "MISMATCH":
            mismatches += 1
    marker = (
        "RECON: ALL MATCHED"
        if mismatches == 0 and unexplained == 0
        else f"RECON: MISMATCH ({mismatches + unexplained})"
    )
    return {
        "rows": rows,
        "matched": len(rows) - mismatches - unexplained,
        "mismatched": mismatches,
        "unexplained": unexplained,
        "marker": marker,
    }


def _chain_trade(escrow: Contract, trade_id: str) -> dict[str, object]:
    raw = escrow.functions.trades(chain.trade_key(trade_id)).call()
    return {
        "seller": str(raw[0]),
        "buyer": str(raw[1]),
        "asset_amount": int(raw[2]),
        "cash_amount": int(raw[3]),
        "expiry": int(raw[4]),
        "state": CHAIN_STATES.get(int(raw[5]), "UNKNOWN"),
    }


def _matches(chain_state: str, settlement_state: str) -> bool:
    if settlement_state in {"PENDING_LOCK", "PENDING_SETTLE", "UNWINDING"}:
        return False
    if settlement_state in {"FAILED_LOCK", "FAILED_SETTLE"}:
        return chain_state == "NONE"
    return chain_state == settlement_state


def _custody_intents(min_chain_ts: int) -> list[dict[str, object]]:
    if not CUSTODY_DB.exists():
        return []
    conn = sqlite3.connect(f"file:{CUSTODY_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return [
            {
                "intent_id": str(row["intent_id"]),
                "actor": str(row["actor"]),
                "destination": str(row["destination"]),
                "amount": int(row["amount"]),
                "action": str(row["action"]),
                "status": str(row["status"]),
                "tx_hash": str(row["tx_hash"]) if row["tx_hash"] else None,
                "created_chain_ts": int(row["created_chain_ts"]),
                "params": json.loads(str(row["params_json"])),
            }
            for row in conn.execute(
                """
                SELECT * FROM intents
                WHERE created_chain_ts >= ?
                ORDER BY created_chain_ts, intent_id
                """,
                (min_chain_ts,),
            )
        ]
    finally:
        conn.close()


def _trade_custody_view(custody: list[dict[str, object]], trade: TradeRow) -> dict[str, object]:
    lock_id = trade.lock_intent_id or ""
    settle_id = trade.settle_intent_id or ""
    unwind_id = trade.unwind_intent_id or ""
    by_id = {str(intent["intent_id"]): intent for intent in custody}
    required = [lock_id]
    state = trade.state
    if state in {"PENDING_SETTLE", "SETTLED", "FAILED_SETTLE", "UNWINDING", "UNWOUND"}:
        required.append(settle_id)
    if state in {"UNWINDING", "UNWOUND"}:
        required.append(unwind_id)
    missing = [intent_id for intent_id in required if not intent_id or intent_id not in by_id]
    invalid = [
        intent_id
        for role, intent_id in {
            "lock": lock_id,
            "settle": settle_id,
            "unwind": unwind_id,
        }.items()
        if intent_id in by_id and not _intent_status_matches(role, state, by_id[intent_id])
    ]
    return {
        "lock": _intent_view(by_id.get(lock_id)),
        "settle": _intent_view(by_id.get(settle_id)),
        "unwind": _intent_view(by_id.get(unwind_id)),
        "missing": missing,
        "matched": not missing and not invalid,
    }


def _intent_status_matches(role: str, state: str, intent: dict[str, object]) -> bool:
    status = str(intent["status"])
    if role == "settle" and state in {"FAILED_SETTLE", "UNWINDING", "UNWOUND"}:
        return status == "failed"
    if role == "unwind":
        return status in {"signed", "approved_signed"}
    if role == "lock":
        return status in {"signed", "approved_signed"}
    if state == "FAILED_SETTLE":
        return status in {"signed", "approved_signed", "failed"}
    return status in {"signed", "approved_signed"}


def _intent_view(intent: dict[str, object] | None) -> dict[str, object] | str:
    if intent is None:
        return "missing"
    return {
        "intent_id": intent["intent_id"],
        "action": intent["action"],
        "status": intent["status"],
        "tx_hash": intent["tx_hash"],
    }


def _balance_rows(
    deployment_obj: Deployment, asset: Contract, cash: Contract
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for persona, address in sorted(deployment_obj.personas.items()):
        account = Web3.to_checksum_address(address)
        rows.append(
            {
                "subject": persona,
                "type": "balance",
                "chain": {
                    "asset": int(asset.functions.balanceOf(account).call()),
                    "cash": int(cash.functions.balanceOf(account).call()),
                },
                "settlement_view": "observed",
                "custody_view": "n/a",
                "status": "MATCHED",
            }
        )
    return rows


def _coupon_row(
    deployment_obj: Deployment,
    asset: Contract,
    distributor: Contract,
    settlement_store: SettlementStore,
    custody: list[dict[str, object]],
) -> dict[str, object] | None:
    round_id = settlement_store.get_meta_int("coupon_round", 0)
    if round_id == 0:
        return None
    holders = [
        Web3.to_checksum_address(address)
        for name, address in sorted(deployment_obj.personas.items())
        if name != "issuer"
        and int(asset.functions.balanceOf(Web3.to_checksum_address(address)).call()) > 0
    ]
    paid = [
        holder for holder in holders if bool(distributor.functions.paid(round_id, holder).call())
    ]
    distribute_intents = [
        intent
        for intent in custody
        if intent["action"] == "distribute_coupon"
        and _int_param(intent, "round_id") == round_id
        and intent["status"] in {"signed", "approved_signed"}
    ]
    status = "MATCHED" if len(paid) == len(holders) and distribute_intents else "MISMATCH"
    return {
        "subject": f"coupon-round-{round_id}",
        "type": "coupon",
        "chain": {
            "round_id": round_id,
            "cursor": int(distributor.functions.cursor(round_id).call()),
            "holders": len(holders),
            "paid": len(paid),
        },
        "settlement_view": {"round_id": round_id},
        "custody_view": {
            "distribute_intents": [_intent_view(intent) for intent in distribute_intents]
        },
        "status": status,
    }


def _params(intent: dict[str, object]) -> dict[str, object]:
    params = intent.get("params")
    return params if isinstance(params, dict) else {}


def _int_param(intent: dict[str, object], key: str) -> int:
    value = _params(intent).get(key, 0)
    return value if isinstance(value, int) else 0
