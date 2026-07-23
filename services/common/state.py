from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from services.common.personas import PERSONAS

STATE_PATH = Path("/data/state.json")


def initial_state() -> dict[str, Any]:
    allowlist = {name: True for name in PERSONAS}
    allowlist["unknown-buyer"] = False
    return {
        "asset_balances": {
            "issuer": 1_000_000,
            "investor-a": 0,
            "investor-b": 0,
            "investor-c": 0,
            "investor-d": 0,
            "investor-e": 0,
        },
        "cash_balances": {
            "issuer": 0,
            "investor-a": 500_000,
            "investor-b": 500_000,
            "investor-c": 500_000,
            "investor-d": 500_000,
            "investor-e": 500_000,
            "unknown-buyer": 10_000,
        },
        "allowlist": allowlist,
        "locked_assets": {},
        "trades": [],
        "coupon_paid": {},
    }


def read_state(path: Path = STATE_PATH) -> dict[str, Any]:
    if not path.exists():
        write_state(initial_state(), path)
    return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))


def write_state(state: dict[str, Any], path: Path = STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")


def reset_state(path: Path = STATE_PATH) -> dict[str, Any]:
    state = initial_state()
    write_state(state, path)
    return state
