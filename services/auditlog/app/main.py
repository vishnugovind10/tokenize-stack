from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from services.common.audit import AuditChain

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
