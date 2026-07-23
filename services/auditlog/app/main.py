from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from services.common.audit import AuditChain, verify_records

app = FastAPI(title="tokenize-stack auditlog")
chain = AuditChain(path=__import__("pathlib").Path("/data/chain.jsonl"))


class EventIn(BaseModel):
    service: str
    actor: str
    action: str
    payload: dict[str, object]


@app.post("/events")
def append_event(event: EventIn) -> dict[str, object]:
    record = chain.append(event.service, event.actor, event.action, event.payload)
    chain.write()
    return record


@app.get("/events")
def list_events() -> list[dict[str, object]]:
    return chain.records


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/tail")
def tail(n: int = 50) -> list[dict[str, object]]:
    return chain.records[-n:]


@app.get("/chain.jsonl", response_class=PlainTextResponse)
def chain_jsonl() -> str:
    return "\n".join(json.dumps(record, sort_keys=True) for record in chain.records) + "\n"


@app.get("/verify")
def verify() -> dict[str, object]:
    ok, message = verify_records(chain.records)
    return {"ok": ok, "message": message, "marker": "AUDIT: CHAIN INTACT" if ok else message}
