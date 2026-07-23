from __future__ import annotations

from typing import Any, cast
from uuid import uuid4

from fastapi import FastAPI
from pydantic import BaseModel

from services.common.audit_client import post_event
from services.common.deployment import Deployment, wait_for_deployment
from services.common.state import read_state, reset_state, write_state

app = FastAPI(title="tokenize-stack settlement")
deployment: Deployment | None = None


@app.on_event("startup")
def load_deployment() -> None:
    global deployment
    deployment = wait_for_deployment()


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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "chain_id": str(deployment.chain_id if deployment else "unknown")}


@app.post("/reset")
def reset() -> dict[str, object]:
    state = reset_state()
    post_event("settlement", "system", "reset", {"trades": 0})
    return {"status": "reset", "state": state}


@app.post("/trades")
def create_trade(trade_in: TradeIn) -> dict[str, object]:
    state = read_state()
    allowlist = cast(dict[str, bool], state["allowlist"])
    cash_balances = cast(dict[str, int], state["cash_balances"])
    trades = cast(list[dict[str, object]], state["trades"])
    trade_id = f"trade-{uuid4().hex[:10]}"
    trade = {
        "trade_id": trade_id,
        "seller": trade_in.seller,
        "buyer": trade_in.buyer,
        "asset_amount": trade_in.asset_amount,
        "cash_amount": trade_in.cash_amount,
        "state": "PENDING_LOCK",
        "revert_reason": None,
    }
    _lock_asset(state, trade)
    post_event("settlement", trade_in.seller, "asset_locked", trade)

    if trade_in.failure_mode == "restricted_buyer" or not allowlist.get(trade_in.buyer, False):
        trade["state"] = "FAILED_SETTLE"
        trade["revert_reason"] = "NotAllowlisted"
        post_event("settlement", trade_in.buyer, "restriction_revert", trade)
    elif cash_balances.get(trade_in.buyer, 0) < trade_in.cash_amount:
        trade["state"] = "FAILED_SETTLE"
        trade["revert_reason"] = "cash_leg_insufficient"
        post_event("settlement", trade_in.buyer, "settle_failed", trade)
    else:
        _settle(state, trade)
        post_event("settlement", trade_in.buyer, "settled", trade)

    trades.append(trade)
    write_state(state)
    return trade


@app.post("/unwind")
def unwind(unwind_in: UnwindIn) -> dict[str, object]:
    state = read_state()
    trades = cast(list[dict[str, object]], state["trades"])
    locked_assets = cast(dict[str, dict[str, object]], state["locked_assets"])
    asset_balances = cast(dict[str, int], state["asset_balances"])
    for trade in trades:
        if trade["trade_id"] == unwind_in.trade_id:
            locked = locked_assets.pop(unwind_in.trade_id, None)
            if locked is not None:
                seller = str(trade["seller"])
                asset_balances[seller] += cast(int, locked["amount"])
            trade["state"] = "UNWOUND"
            write_state(state)
            post_event("settlement", "system", "unwound", trade)
            return trade
    return {"trade_id": unwind_in.trade_id, "state": "UNKNOWN"}


@app.get("/trades")
def list_trades() -> list[dict[str, object]]:
    return list(cast(list[dict[str, object]], read_state()["trades"]))


@app.post("/coupon")
def coupon(coupon_in: CouponIn) -> dict[str, object]:
    state = read_state()
    asset_balances = cast(dict[str, int], state["asset_balances"])
    cash_balances = cast(dict[str, int], state["cash_balances"])
    coupon_paid = cast(dict[str, int], state["coupon_paid"])
    holders = [
        holder
        for holder, balance in sorted(asset_balances.items())
        if holder != "issuer" and int(balance) > 0
    ]
    cursor = 0
    interrupted = False
    while cursor < len(holders):
        holder = holders[cursor]
        if (
            coupon_in.interrupt_after is not None
            and cursor == coupon_in.interrupt_after
            and not interrupted
        ):
            interrupted = True
            post_event("coupon", "system", "batch_interrupted", {"cursor": cursor})
            continue
        if holder not in coupon_paid:
            coupon_paid[holder] = 100
            cash_balances[holder] += 100
            post_event("coupon", "issuer", "paid", {"holder": holder, "amount": 100})
        cursor += 1
    write_state(state)
    return {
        "paid": len(coupon_paid),
        "cursor": cursor,
        "interrupted": interrupted,
        "no_double_payment": len(coupon_paid) == len(set(coupon_paid)),
    }


def _lock_asset(state: dict[str, Any], trade: dict[str, object]) -> None:
    balances = cast(dict[str, int], state["asset_balances"])
    locked_assets = cast(dict[str, dict[str, object]], state["locked_assets"])
    seller = str(trade["seller"])
    amount = cast(int, trade["asset_amount"])
    if balances[seller] < amount:
        raise ValueError("seller asset balance too low")
    balances[seller] -= amount
    locked_assets[str(trade["trade_id"])] = {"seller": seller, "amount": amount}
    trade["state"] = "LOCKED"


def _settle(state: dict[str, Any], trade: dict[str, object]) -> None:
    locked_assets = cast(dict[str, dict[str, object]], state["locked_assets"])
    cash_balances = cast(dict[str, int], state["cash_balances"])
    asset_balances = cast(dict[str, int], state["asset_balances"])
    locked_assets.pop(str(trade["trade_id"]))
    seller = str(trade["seller"])
    buyer = str(trade["buyer"])
    asset_amount = cast(int, trade["asset_amount"])
    cash_amount = cast(int, trade["cash_amount"])
    cash_balances[buyer] -= cash_amount
    cash_balances[seller] += cash_amount
    asset_balances[buyer] += asset_amount
    trade["state"] = "SETTLED"
