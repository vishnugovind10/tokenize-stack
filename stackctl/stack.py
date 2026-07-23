from __future__ import annotations

import json
import subprocess
import time
from uuid import uuid4
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE_URLS = {
    "custody": "http://localhost:8001",
    "settlement": "http://localhost:8002",
    "recon": "http://localhost:8003",
    "audit": "http://localhost:8004",
}


@dataclass(frozen=True)
class StackResult:
    lines: list[str]


def compose(args: list[str]) -> int:
    return subprocess.call(["docker", "compose", *args])


def wait_ready(timeout_seconds: int = 120) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            statuses = [get_json(f"{url}/health") for url in BASE_URLS.values()]
            if all(status.get("status") == "ok" for status in statuses):
                return
        except (OSError, URLError):
            time.sleep(2)
    raise RuntimeError("stack services did not become healthy")


def run_demo() -> StackResult:
    wait_ready()
    post_json(f"{BASE_URLS['settlement']}/reset", {})
    for amount, buyer in [
        (5_000, "investor-a"),
        (25_000, "investor-b"),
        (50_000, "investor-c"),
        (125_000, "investor-a"),
        (250_000, "investor-b"),
    ]:
        post_json(
            f"{BASE_URLS['settlement']}/trades",
            {
                "seller": "issuer",
                "buyer": buyer,
                "asset_amount": amount,
                "cash_amount": amount,
                "failure_mode": None,
            },
        )
    wait_trades({"SETTLED"}, count=5)
    coupon = post_json(f"{BASE_URLS['settlement']}/coupon", {"interrupt_after": None})
    report = get_json(f"{BASE_URLS['recon']}/report")
    audit = get_json(f"{BASE_URLS['audit']}/verify")
    return StackResult(
        [
            "ISSUE: 1000000 asset units to issuer",
            f"COUPON: PAID {coupon['paid']} HOLDERS",
            str(report["marker"]),
            str(audit["marker"]),
            "CONSOLE: http://localhost:8080",
        ]
    )


def run_failures() -> StackResult:
    wait_ready()
    post_json(f"{BASE_URLS['settlement']}/reset", {})
    mismatch = post_json(
        f"{BASE_URLS['settlement']}/trades",
        {
            "seller": "issuer",
            "buyer": "investor-e",
            "asset_amount": 25_000,
            "cash_amount": 600_000,
            "failure_mode": "cash_leg_insufficient",
        },
    )
    wait_trade_state(str(mismatch["trade_id"]), "FAILED_SETTLE")
    report_before = get_json(f"{BASE_URLS['recon']}/report")
    chain_warp(3700)
    wait_trade_state(str(mismatch["trade_id"]), "UNWOUND")
    restricted = post_json(
        f"{BASE_URLS['settlement']}/trades",
        {
            "seller": "issuer",
            "buyer": "investor-f",
            "asset_amount": 5_000,
            "cash_amount": 5_000,
            "failure_mode": "restricted_buyer",
        },
    )
    wait_trade_state(str(restricted["trade_id"]), "FAILED_SETTLE")
    chain_warp(3700)
    wait_trade_state(str(restricted["trade_id"]), "UNWOUND")
    coupon = post_json(f"{BASE_URLS['settlement']}/coupon", {"interrupt_after": 2})
    report_after = get_json(f"{BASE_URLS['recon']}/report")
    audit = get_json(f"{BASE_URLS['audit']}/verify")
    return StackResult(
        [
            str(report_before["marker"]),
            "UNWIND: COMPLETE",
            f"RESTRICTED: SURFACED {trade_by_id(str(restricted['trade_id']))['revert_reason']}",
            str(report_after["marker"]),
            (
                "COUPON: NO DOUBLE PAYMENT"
                if coupon["no_double_payment"]
                else "COUPON: DUPLICATE PAYMENT"
            ),
            str(audit["marker"]),
        ]
    )


def verify_audit(output_path: Path | None = None) -> StackResult:
    chain = get_text(f"{BASE_URLS['audit']}/chain.jsonl")
    if output_path is not None:
        output_path.write_text(chain, encoding="utf-8")
    result = get_json(f"{BASE_URLS['audit']}/verify")
    return StackResult([str(result["message"]), str(result["marker"])])


def chain_warp(seconds: int) -> StackResult:
    response = post_json(
        "http://localhost:8545",
        {"jsonrpc": "2.0", "id": 1, "method": "evm_increaseTime", "params": [seconds]},
    )
    post_json(
        "http://localhost:8545", {"jsonrpc": "2.0", "id": 2, "method": "evm_mine", "params": []}
    )
    return StackResult([f"CHAIN: WARPED {seconds} SECONDS", json.dumps(response, sort_keys=True)])


def wait_trades(states: set[str], count: int, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        trades = get_list(f"{BASE_URLS['settlement']}/trades")
        if len(trades) >= count and all(str(trade["state"]) in states for trade in trades):
            return
        time.sleep(2)
    raise RuntimeError(f"trades did not reach states {sorted(states)}")


def wait_trade_state(trade_id: str, state: str, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        trade = trade_by_id(trade_id)
        if str(trade.get("state")) == state:
            return
        time.sleep(2)
    raise RuntimeError(f"{trade_id} did not reach {state}")


def trade_by_id(trade_id: str) -> dict[str, object]:
    for trade in get_list(f"{BASE_URLS['settlement']}/trades"):
        if str(trade["trade_id"]) == trade_id:
            return trade
    raise RuntimeError(f"unknown trade: {trade_id}")


def pay(actor: str, destination: str, amount: int) -> StackResult:
    wait_ready()
    response = post_json(
        f"{BASE_URLS['custody']}/sign-intent",
        {
            "intent_id": f"pay-{uuid4().hex[:10]}",
            "actor": actor,
            "destination": destination,
            "amount": amount,
            "asset": "cash",
            "action": "transfer_cash",
        },
    )
    return StackResult([json.dumps(response, sort_keys=True)])


def get_json(url: str) -> dict[str, object]:
    return cast(dict[str, object], json.loads(get_text(url)))


def get_list(url: str) -> list[dict[str, Any]]:
    return cast(list[dict[str, Any]], json.loads(get_text(url)))


def get_text(url: str) -> str:
    with urlopen(url, timeout=10) as response:
        return str(response.read().decode("utf-8"))


def post_json(url: str, payload: dict[str, object]) -> dict[str, object]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(request, timeout=30) as response:
        return cast(dict[str, object], json.loads(response.read().decode("utf-8")))
