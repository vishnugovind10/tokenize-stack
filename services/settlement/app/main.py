from __future__ import annotations

from fastapi import FastAPI

from services.common.models import Trade, TradeState

app = FastAPI(title="tokenize-stack settlement")
trades: dict[str, Trade] = {}


@app.post("/trades")
def create_trade(trade: Trade) -> dict[str, object]:
    trade.state = TradeState.PENDING_LOCK
    trades[trade.trade_id] = trade
    return trade.__dict__


@app.get("/trades")
def list_trades() -> list[dict[str, object]]:
    return [trade.__dict__ for trade in trades.values()]


@app.post("/trades/{trade_id}/inject-failure")
def inject_failure(trade_id: str, mode: str) -> dict[str, object]:
    trade = trades[trade_id]
    trade.failure_reason = mode
    trade.state = TradeState.FAILED
    return trade.__dict__
