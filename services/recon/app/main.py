from __future__ import annotations

from fastapi import FastAPI

from services.common.state import read_state

app = FastAPI(title="tokenize-stack recon")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/report")
def get_report() -> dict[str, object]:
    state = read_state()
    rows: list[dict[str, object]] = []
    mismatches = 0
    for trade in state["trades"]:
        locked_on_chain = trade["trade_id"] in state["locked_assets"]
        status = "MATCHED"
        if trade["state"] == "FAILED_SETTLE" and locked_on_chain:
            status = "MISMATCH"
        if trade["state"] == "SETTLED" and locked_on_chain:
            status = "MISMATCH"
        if status == "MISMATCH":
            mismatches += 1
        rows.append(
            {
                "subject": trade["trade_id"],
                "chain": "LOCKED" if locked_on_chain else trade["state"],
                "settlement_view": trade["state"],
                "custody_view": "intent_recorded",
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
