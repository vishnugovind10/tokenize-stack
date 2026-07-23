from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from services.common.models import Intent


@dataclass(frozen=True)
class IntentRow:
    intent_id: str
    actor: str
    destination: str
    amount: int
    asset: str
    action: str
    tier: str
    status: str
    tx_hash: str | None
    created_chain_ts: int
    matched_rule: str

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "IntentRow":
        return cls(
            intent_id=str(row["intent_id"]),
            actor=str(row["actor"]),
            destination=str(row["destination"]),
            amount=int(row["amount"]),
            asset=str(row["asset"]),
            action=str(row["action"]),
            tier=str(row["tier"]),
            status=str(row["status"]),
            tx_hash=str(row["tx_hash"]) if row["tx_hash"] is not None else None,
            created_chain_ts=int(row["created_chain_ts"]),
            matched_rule=str(row["matched_rule"]),
        )

    def to_intent(self) -> Intent:
        return Intent(
            self.intent_id,
            self.actor,
            self.destination,
            self.amount,
            self.asset,
            self.action,
        )


@dataclass(frozen=True)
class PendingApproval:
    intent: IntentRow
    collected: int
    required: int


class CustodyStore:
    def __init__(self, path: Path = Path("/data/custody.db")) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS intents (
                intent_id TEXT PRIMARY KEY,
                actor TEXT NOT NULL,
                destination TEXT NOT NULL,
                amount INTEGER NOT NULL,
                asset TEXT NOT NULL,
                action TEXT NOT NULL,
                tier TEXT NOT NULL,
                status TEXT NOT NULL,
                tx_hash TEXT NULL,
                created_chain_ts INTEGER NOT NULL,
                matched_rule TEXT NOT NULL
            )
            """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS approvals (
                intent_id TEXT NOT NULL,
                approver TEXT NOT NULL,
                chain_ts INTEGER NOT NULL,
                PRIMARY KEY(intent_id, approver),
                FOREIGN KEY(intent_id) REFERENCES intents(intent_id)
            )
            """)
        self.conn.commit()

    def insert_intent(
        self,
        intent: Intent,
        tier: str,
        status: str,
        tx_hash: str | None,
        created_chain_ts: int,
        matched_rule: str,
    ) -> IntentRow:
        self.conn.execute(
            """
            INSERT INTO intents (
                intent_id, actor, destination, amount, asset, action, tier, status,
                tx_hash, created_chain_ts, matched_rule
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                intent.intent_id,
                intent.actor,
                intent.destination,
                intent.amount,
                intent.asset,
                intent.action,
                tier,
                status,
                tx_hash,
                created_chain_ts,
                matched_rule,
            ),
        )
        self.conn.commit()
        row = self.get_intent(intent.intent_id)
        if row is None:
            raise RuntimeError(f"intent insert failed: {intent.intent_id}")
        return row

    def get_intent(self, intent_id: str) -> IntentRow | None:
        row = self.conn.execute(
            "SELECT * FROM intents WHERE intent_id = ?",
            (intent_id,),
        ).fetchone()
        return IntentRow.from_row(row) if row is not None else None

    def update_status(self, intent_id: str, status: str, tx_hash: str | None = None) -> None:
        self.conn.execute(
            "UPDATE intents SET status = ?, tx_hash = COALESCE(?, tx_hash) WHERE intent_id = ?",
            (status, tx_hash, intent_id),
        )
        self.conn.commit()

    def recent_total(self, actor: str, since_chain_ts: int) -> int:
        value = self.conn.execute(
            """
            SELECT COALESCE(SUM(amount), 0) AS total
            FROM intents
            WHERE actor = ? AND status != 'denied' AND created_chain_ts >= ?
            """,
            (actor, since_chain_ts),
        ).fetchone()["total"]
        return int(value)

    def add_approval(self, intent_id: str, approver: str, chain_ts: int) -> None:
        self.conn.execute(
            "INSERT INTO approvals (intent_id, approver, chain_ts) VALUES (?, ?, ?)",
            (intent_id, approver, chain_ts),
        )
        self.conn.commit()

    def approvals_for(self, intent_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT approver FROM approvals WHERE intent_id = ? ORDER BY chain_ts, approver",
            (intent_id,),
        ).fetchall()
        return [str(row["approver"]) for row in rows]

    def pending(self, required_counts: dict[str, int]) -> list[PendingApproval]:
        rows = self.conn.execute(
            "SELECT * FROM intents WHERE status = 'pending_approvals' ORDER BY created_chain_ts"
        ).fetchall()
        return [
            PendingApproval(
                intent=IntentRow.from_row(row),
                collected=len(self.approvals_for(str(row["intent_id"]))),
                required=required_counts[str(row["tier"])],
            )
            for row in rows
        ]

    def close(self) -> None:
        self.conn.close()


def required_counts_from_tiers(tiers: Iterable[object]) -> dict[str, int]:
    return {str(getattr(tier, "name")): int(getattr(tier, "approvals_required")) for tier in tiers}
