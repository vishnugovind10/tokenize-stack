from __future__ import annotations

import json
import os
import threading
from typing import Any, cast
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel
from web3 import Web3
from web3.contract import Contract

from services.common import chain
from services.common.audit_client import post_event
from services.common.deployment import Deployment, wait_for_deployment
from services.settlement.store import SettlementStore, TradeRow

app = FastAPI(title="tokenize-stack settlement")
CUSTODY_URL = os.environ.get("CUSTODY_URL", "http://custody:8001")

deployment: Deployment | None = None
w3: Web3 | None = None
escrow_contract: Contract | None = None
asset_contract: Contract | None = None
cash_contract: Contract | None = None
distributor_contract: Contract | None = None
store: SettlementStore | None = None
stop_poller = threading.Event()
poller_thread: threading.Thread | None = None


class TradeIn(BaseModel):
    seller: str
    buyer: str
    asset_amount: int
    cash_amount: int
    failure_mode: str | None = None


class UnwindIn(BaseModel):
    trade_id: str


class CouponIn(BaseModel):
    interrupt_after: int | None = None


@app.on_event("startup")
def load_deployment() -> None:
    global deployment, w3, escrow_contract, asset_contract, cash_contract, distributor_contract
    global store, poller_thread
    deployment = wait_for_deployment()
    w3 = chain.get_w3(deployment)
    escrow_contract = chain.escrow(w3, deployment)
    asset_contract = chain.asset(w3, deployment)
    cash_contract = chain.cash(w3, deployment)
    distributor_contract = chain.distributor(w3, deployment)
    store = SettlementStore()
    stop_poller.clear()
    poller_thread = threading.Thread(target=_poll_loop, daemon=True)
    poller_thread.start()


@app.on_event("shutdown")
def shutdown() -> None:
    stop_poller.set()
    if poller_thread is not None:
        poller_thread.join(timeout=5)
    if store is not None:
        store.close()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "chain_id": str(deployment.chain_id if deployment else "unknown")}


@app.post("/reset")
def reset() -> dict[str, object]:
    _ctx()["store"].reset()
    post_event("settlement", "system", "reset", {"trades": 0})
    return {"status": "reset", "trades": []}


@app.post("/trades")
def create_trade(trade_in: TradeIn) -> dict[str, object]:
    ctx = _ctx()
    latest_ts = int(ctx["w3"].eth.get_block("latest")["timestamp"])
    trade_id = f"trade-{uuid4().hex[:10]}"
    expiry = latest_ts + 3600
    trade_key = Web3.to_hex(chain.trade_key(trade_id))
    approve_intent_id = f"{trade_id}-approve_asset_escrow-{uuid4().hex[:6]}"
    lock_intent_id = f"{trade_id}-lock_asset-{uuid4().hex[:6]}"
    trade = TradeRow(
        trade_id=trade_id,
        trade_key=trade_key,
        seller=trade_in.seller,
        buyer=trade_in.buyer,
        asset_amount=trade_in.asset_amount,
        cash_amount=trade_in.cash_amount,
        expiry=expiry,
        state="PENDING_LOCK",
        lock_intent_id=lock_intent_id,
        settle_intent_id=None,
        unwind_intent_id=None,
        revert_reason=None,
    )
    row = cast(SettlementStore, ctx["store"]).insert_trade(trade)
    _execute(
        trade_id,
        trade_in.seller,
        "approve_asset_escrow",
        "escrow",
        trade_in.asset_amount,
        {"trade_id": trade_id},
        intent_id=approve_intent_id,
    )
    lock = _execute(
        trade_id,
        trade_in.seller,
        "lock_asset",
        trade_in.buyer,
        trade_in.asset_amount,
        {"trade_id": trade_id, "cash_amount": trade_in.cash_amount, "expiry": expiry},
        intent_id=lock_intent_id,
    )
    if lock["status"] == "failed":
        ctx["store"].update_state(
            trade_id, "FAILED_LOCK", revert_reason=str(lock.get("reason", "transaction reverted"))
        )
        latest = ctx["store"].get_trade(trade_id)
        if latest is not None:
            row = latest
    post_event("settlement", trade_in.seller, "lock_submitted", row.payload())
    return row.payload()


@app.post("/unwind")
def unwind(unwind_in: UnwindIn) -> dict[str, object]:
    ctx = _ctx()
    trade = ctx["store"].get_trade(unwind_in.trade_id)
    if trade is None:
        return {"trade_id": unwind_in.trade_id, "state": "UNKNOWN"}
    response = _submit_unwind(trade)
    updated = ctx["store"].get_trade(trade.trade_id)
    return updated.payload() if updated is not None else response


@app.get("/trades")
def list_trades() -> list[dict[str, object]]:
    return [trade.payload() for trade in _ctx()["store"].list_trades()]


@app.post("/coupon")
def coupon(coupon_in: CouponIn) -> dict[str, object]:
    ctx = _ctx()
    holders = _holders_with_assets(ctx["deployment"], ctx["asset"])
    current_round = ctx["store"].get_meta_int("coupon_round", 0)
    if current_round > 0 and _coupon_cursor(ctx, current_round) < len(holders):
        round_id = current_round
    else:
        round_id = current_round + 1
        ctx["store"].set_meta("coupon_round", str(round_id))
    holder_addresses = [_address(ctx["deployment"], holder) for holder in holders]
    unpaid_at_start = {
        holder
        for holder, address in zip(holders, holder_addresses, strict=True)
        if not bool(ctx["distributor"].functions.paid(round_id, address).call())
    }
    expected = {
        holder: int(ctx["asset"].functions.balanceOf(_address(ctx["deployment"], holder)).call())
        // 100
        for holder in unpaid_at_start
    }
    before = _cash_balances(ctx["deployment"], ctx["cash"], holders)
    total_coupon = sum(expected.values())
    if total_coupon > 0 and _coupon_cursor(ctx, round_id) == 0:
        _execute(
            f"coupon-{round_id}",
            "issuer",
            "transfer_cash",
            ctx["deployment"].addresses["CouponDistributor"],
            total_coupon,
            {"round_id": round_id},
        )
    interrupted = False
    while _coupon_cursor(ctx, round_id) < len(holders):
        cursor_before = _coupon_cursor(ctx, round_id)
        if coupon_in.interrupt_after is not None and cursor_before >= coupon_in.interrupt_after:
            interrupted = True
            post_event("coupon", "system", "batch_interrupted", {"cursor": cursor_before})
            break
        _execute(
            f"coupon-{round_id}",
            "issuer",
            "distribute_coupon",
            "distributor",
            0,
            {"round_id": round_id, "holders": holder_addresses, "batch_size": 2},
        )
    after = _cash_balances(ctx["deployment"], ctx["cash"], holders)
    cursor = _coupon_cursor(ctx, round_id)
    if interrupted:
        return {
            "round_id": round_id,
            "paid": _paid_count(ctx, round_id, holder_addresses),
            "cursor": cursor,
            "interrupted": interrupted,
            "no_double_payment": False,
        }
    post_reinvoke = _cash_balances(ctx["deployment"], ctx["cash"], holders)
    if holders:
        _execute(
            f"coupon-{round_id}",
            "issuer",
            "distribute_coupon",
            "distributor",
            0,
            {"round_id": round_id, "holders": holder_addresses, "batch_size": 2},
        )
    final = _cash_balances(ctx["deployment"], ctx["cash"], holders)
    deltas_match = all(
        after[holder] - before[holder] == expected[holder] for holder in unpaid_at_start
    )
    no_reinvoke_movement = final == post_reinvoke
    no_double_payment = deltas_match and no_reinvoke_movement
    for holder in sorted(unpaid_at_start):
        post_event("coupon", "issuer", "paid", {"holder": holder, "amount": expected[holder]})
    return {
        "round_id": round_id,
        "paid": _paid_count(ctx, round_id, holder_addresses),
        "cursor": cursor,
        "interrupted": interrupted,
        "no_double_payment": no_double_payment,
    }


def _poll_loop() -> None:
    while not stop_poller.is_set():
        try:
            _poll_once()
        except Exception as exc:
            post_event("settlement", "system", "poller_error", {"error": str(exc)})
        stop_poller.wait(2)


def _poll_once() -> None:
    ctx = _ctx()
    _apply_escrow_events(ctx)
    _advance_locked_trades(ctx)
    _advance_failed_trades(ctx)


def _apply_escrow_events(ctx: dict[str, Any]) -> None:
    latest = int(ctx["w3"].eth.block_number)
    from_block = ctx["store"].get_meta_int("escrow_cursor", 0) + 1
    if from_block > latest:
        return
    for event_name, state in [
        ("AssetLocked", "LOCKED"),
        ("Settled", "SETTLED"),
        ("Unwound", "UNWOUND"),
    ]:
        event = getattr(ctx["escrow"].events, event_name)
        for log in event().get_logs(from_block=from_block, to_block=latest):
            trade_key = Web3.to_hex(log["args"]["tradeId"])
            trade = ctx["store"].get_by_key(trade_key)
            if trade is None:
                continue
            ctx["store"].update_state(trade.trade_id, state)
            post_event("settlement", "chain", state.lower(), {"trade_id": trade.trade_id})
    ctx["store"].set_meta("escrow_cursor", str(latest))


def _advance_locked_trades(ctx: dict[str, Any]) -> None:
    for trade in ctx["store"].by_states(("LOCKED",)):
        if trade.settle_intent_id is not None:
            continue
        _execute(
            trade.trade_id,
            trade.buyer,
            "approve_cash_escrow",
            "escrow",
            trade.cash_amount,
            {"trade_id": trade.trade_id},
        )
        response = _execute(
            trade.trade_id,
            trade.buyer,
            "settle_trade",
            trade.seller,
            trade.cash_amount,
            {"trade_id": trade.trade_id},
        )
        if response["status"] == "failed":
            ctx["store"].update_state(
                trade.trade_id,
                "FAILED_SETTLE",
                settle_intent_id=str(response["intent_id"]),
                revert_reason=str(response.get("reason", "transaction reverted")),
            )
            post_event("settlement", trade.buyer, "settle_failed", _trade_payload(trade, response))
        else:
            ctx["store"].update_state(
                trade.trade_id, "PENDING_SETTLE", settle_intent_id=str(response["intent_id"])
            )
            post_event(
                "settlement", trade.buyer, "settle_submitted", _trade_payload(trade, response)
            )


def _advance_failed_trades(ctx: dict[str, Any]) -> None:
    latest_ts = int(ctx["w3"].eth.get_block("latest")["timestamp"])
    for trade in ctx["store"].by_states(("FAILED_SETTLE",)):
        if latest_ts > trade.expiry and trade.unwind_intent_id is None:
            _submit_unwind(trade)


def _submit_unwind(trade: TradeRow) -> dict[str, object]:
    response = _execute(
        trade.trade_id,
        trade.seller,
        "unwind_trade",
        "escrow",
        trade.asset_amount,
        {"trade_id": trade.trade_id},
    )
    if response["status"] == "failed":
        _ctx()["store"].update_state(
            trade.trade_id,
            "FAILED_SETTLE",
            unwind_intent_id=str(response["intent_id"]),
            revert_reason=str(response.get("reason", "transaction reverted")),
        )
    else:
        _ctx()["store"].update_state(
            trade.trade_id, "UNWINDING", unwind_intent_id=str(response["intent_id"])
        )
        post_event("settlement", "system", "unwind_submitted", _trade_payload(trade, response))
    return response


def _execute(
    trade_id: str,
    actor: str,
    action: str,
    destination: str,
    amount: int,
    params: dict[str, object],
    *,
    intent_id: str | None = None,
) -> dict[str, object]:
    payload = {
        "intent_id": intent_id or f"{trade_id}-{action}-{uuid4().hex[:6]}",
        "actor": actor,
        "destination": destination,
        "amount": amount,
        "asset": "escrow",
        "action": action,
        "params": params,
    }
    return _post_json(f"{CUSTODY_URL}/execute", payload)


def _holders_with_assets(deployment_obj: Deployment, asset: Contract) -> list[str]:
    holders: list[str] = []
    for name, address in sorted(deployment_obj.personas.items()):
        if name == "issuer":
            continue
        balance = int(asset.functions.balanceOf(Web3.to_checksum_address(address)).call())
        if balance > 0:
            holders.append(name)
    return holders


def _address(deployment_obj: Deployment, persona: str) -> str:
    return Web3.to_checksum_address(deployment_obj.personas[persona])


def _cash_balances(
    deployment_obj: Deployment, cash: Contract, holders: list[str]
) -> dict[str, int]:
    return {
        holder: int(cash.functions.balanceOf(_address(deployment_obj, holder)).call())
        for holder in holders
    }


def _coupon_cursor(ctx: dict[str, Any], round_id: int) -> int:
    return int(ctx["distributor"].functions.cursor(round_id).call())


def _paid_count(ctx: dict[str, Any], round_id: int, holder_addresses: list[str]) -> int:
    return sum(
        1
        for address in holder_addresses
        if bool(ctx["distributor"].functions.paid(round_id, address).call())
    )


def _post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        return cast(dict[str, object], json.loads(response.read().decode("utf-8")))


def _trade_payload(trade: TradeRow, response: dict[str, object]) -> dict[str, object]:
    payload = trade.payload()
    payload["custody"] = response
    return payload


def _ctx() -> dict[str, Any]:
    if (
        deployment is None
        or w3 is None
        or escrow_contract is None
        or asset_contract is None
        or cash_contract is None
        or distributor_contract is None
        or store is None
    ):
        raise RuntimeError("settlement service not initialized")
    return {
        "deployment": deployment,
        "w3": w3,
        "escrow": escrow_contract,
        "asset": asset_contract,
        "cash": cash_contract,
        "distributor": distributor_contract,
        "store": store,
    }
