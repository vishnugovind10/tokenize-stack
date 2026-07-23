from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TradeRow:
    trade_id: str
    trade_key: str
    seller: str
    buyer: str
    asset_amount: int
    cash_amount: int
    expiry: int
    state: str
    lock_intent_id: str | None
    settle_intent_id: str | None
    unwind_intent_id: str | None
    revert_reason: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "TradeRow":
        return cls(
            trade_id=str(row["trade_id"]),
            trade_key=str(row["trade_key"]),
            seller=str(row["seller"]),
            buyer=str(row["buyer"]),
            asset_amount=int(row["asset_amount"]),
            cash_amount=int(row["cash_amount"]),
            expiry=int(row["expiry"]),
            state=str(row["state"]),
            lock_intent_id=str(row["lock_intent_id"]) if row["lock_intent_id"] else None,
            settle_intent_id=str(row["settle_intent_id"]) if row["settle_intent_id"] else None,
            unwind_intent_id=str(row["unwind_intent_id"]) if row["unwind_intent_id"] else None,
            revert_reason=str(row["revert_reason"]) if row["revert_reason"] else None,
        )

    def payload(self) -> dict[str, object]:
        return asdict(self)


class SettlementStore:
    def __init__(self, path: Path = Path("/data/settlement.db")) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                trade_id TEXT PRIMARY KEY,
                trade_key TEXT NOT NULL UNIQUE,
                seller TEXT NOT NULL,
                buyer TEXT NOT NULL,
                asset_amount INTEGER NOT NULL,
                cash_amount INTEGER NOT NULL,
                expiry INTEGER NOT NULL,
                state TEXT NOT NULL,
                lock_intent_id TEXT NULL,
                settle_intent_id TEXT NULL,
                unwind_intent_id TEXT NULL,
                revert_reason TEXT NULL
            )
            """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """)
        self.conn.commit()

    def reset(self) -> None:
        self.conn.execute("DELETE FROM trades")
        self.set_meta("escrow_cursor", "0")
        self.set_meta("coupon_round", "0")
        self.conn.commit()

    def insert_trade(self, trade: TradeRow) -> TradeRow:
        self.conn.execute(
            """
            INSERT INTO trades (
                trade_id, trade_key, seller, buyer, asset_amount, cash_amount, expiry,
                state, lock_intent_id, settle_intent_id, unwind_intent_id, revert_reason
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                trade.trade_id,
                trade.trade_key,
                trade.seller,
                trade.buyer,
                trade.asset_amount,
                trade.cash_amount,
                trade.expiry,
                trade.state,
                trade.lock_intent_id,
                trade.settle_intent_id,
                trade.unwind_intent_id,
                trade.revert_reason,
            ),
        )
        self.conn.commit()
        row = self.get_trade(trade.trade_id)
        if row is None:
            raise RuntimeError(f"trade insert failed: {trade.trade_id}")
        return row

    def get_trade(self, trade_id: str) -> TradeRow | None:
        row = self.conn.execute("SELECT * FROM trades WHERE trade_id = ?", (trade_id,)).fetchone()
        return TradeRow.from_row(row) if row is not None else None

    def get_by_key(self, trade_key: str) -> TradeRow | None:
        row = self.conn.execute("SELECT * FROM trades WHERE trade_key = ?", (trade_key,)).fetchone()
        return TradeRow.from_row(row) if row is not None else None

    def list_trades(self) -> list[TradeRow]:
        rows = self.conn.execute("SELECT * FROM trades ORDER BY rowid").fetchall()
        return [TradeRow.from_row(row) for row in rows]

    def by_states(self, states: tuple[str, ...]) -> list[TradeRow]:
        placeholders = ",".join("?" for _ in states)
        rows = self.conn.execute(
            f"SELECT * FROM trades WHERE state IN ({placeholders}) ORDER BY rowid", states
        ).fetchall()
        return [TradeRow.from_row(row) for row in rows]

    def update_state(
        self,
        trade_id: str,
        state: str,
        *,
        settle_intent_id: str | None = None,
        unwind_intent_id: str | None = None,
        revert_reason: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE trades
            SET state = ?,
                settle_intent_id = COALESCE(?, settle_intent_id),
                unwind_intent_id = COALESCE(?, unwind_intent_id),
                revert_reason = COALESCE(?, revert_reason)
            WHERE trade_id = ?
            """,
            (state, settle_intent_id, unwind_intent_id, revert_reason, trade_id),
        )
        self.conn.commit()

    def get_meta_int(self, key: str, default: int) -> int:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return int(row["value"]) if row is not None else default

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
