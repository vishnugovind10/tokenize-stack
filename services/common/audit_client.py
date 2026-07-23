from __future__ import annotations

import json
import os
from urllib.request import Request, urlopen

AUDIT_URL = os.environ.get("AUDIT_URL", "http://auditlog:8004")


def post_event(service: str, actor: str, action: str, payload: dict[str, object]) -> None:
    data = json.dumps(
        {"service": service, "actor": actor, "action": action, "payload": payload}
    ).encode("utf-8")
    request = Request(
        f"{AUDIT_URL}/events",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=5) as response:
        response.read()
