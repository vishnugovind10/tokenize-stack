from __future__ import annotations

from dataclasses import dataclass

from services.common.models import Trade, TradeState


@dataclass(frozen=True)
class ReconReport:
    matched: int
    mismatched: int
    unexplained: int

    @property
    def marker(self) -> str:
        return (
            "RECON: ALL MATCHED"
            if self.mismatched == 0 and self.unexplained == 0
            else "RECON: MISMATCH"
        )


def build_report(locked_trade_ids: set[str], trades: list[Trade]) -> ReconReport:
    mismatched = 0
    for trade in trades:
        locked_on_chain = trade.trade_id in locked_trade_ids
        if trade.state == TradeState.SETTLED and locked_on_chain:
            mismatched += 1
        if trade.state == TradeState.LOCKED and not locked_on_chain:
            mismatched += 1
        if trade.state == TradeState.FAILED and locked_on_chain:
            mismatched += 1
    return ReconReport(matched=len(trades) - mismatched, mismatched=mismatched, unexplained=0)
