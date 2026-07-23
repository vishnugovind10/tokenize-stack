from __future__ import annotations

from pathlib import Path
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from services.common.deployment import Deployment
from services.custody.app import main
from services.custody.store import CustodyStore


class Call:
    def __init__(self, value: object) -> None:
        self.value = value

    def call(self) -> object:
        return self.value


class RegistryFunctions:
    def canTransfer(self, actor: str, destination: str, amount: int) -> Call:
        return Call((True, 0))

    def paused(self) -> Call:
        return Call(False)


class Registry:
    functions = RegistryFunctions()


class AssetFunctions:
    def paused(self) -> Call:
        return Call(False)


class Asset:
    functions = AssetFunctions()


class Eth:
    def get_block(self, block: str) -> dict[str, int]:
        return {"timestamp": 10_000}


class W3:
    eth = Eth()


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    main.deployment = Deployment(
        chain_id=31337,
        rpc_url="http://unused",
        addresses={},
        personas={
            "issuer": "0xf39fd6e51aad88f6f4ce6ab8827279cfffb92266",
            "investor-a": "0x70997970c51812dc3a010c7d01b50e0d17dc79c8",
        },
        abi_dir=tmp_path,
    )
    main.w3 = W3()  # type: ignore[assignment]
    main.registry_contract = Registry()  # type: ignore[assignment]
    main.asset_contract = Asset()  # type: ignore[assignment]
    main.cash_contract = object()  # type: ignore[assignment]
    main.escrow_contract = object()  # type: ignore[assignment]
    main.store = CustodyStore(tmp_path / "custody.db")
    monkeypatch.setattr(main, "post_event", lambda *args, **kwargs: None)
    yield TestClient(main.app)
    main.store.close()
    main.deployment = None
    main.w3 = None
    main.registry_contract = None
    main.asset_contract = None
    main.cash_contract = None
    main.escrow_contract = None
    main.store = None


def pending_intent(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/sign-intent",
        json={
            "intent_id": "dual-1",
            "actor": "issuer",
            "destination": "investor-a",
            "amount": 125_000,
            "asset": "cash",
            "action": "transfer_cash",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending_approvals"
    return payload


def test_approve_unknown_intent_returns_404(client: TestClient) -> None:
    response = client.post("/approvals/missing/approve", json={"approver": "ops-1"})

    assert response.status_code == 404


def test_approve_unknown_approver_returns_403(client: TestClient) -> None:
    pending_intent(client)

    response = client.post("/approvals/dual-1/approve", json={"approver": "unknown"})

    assert response.status_code == 403


def test_duplicate_approval_returns_409(client: TestClient) -> None:
    pending_intent(client)
    assert client.post("/approvals/dual-1/approve", json={"approver": "ops-1"}).status_code == 200

    response = client.post("/approvals/dual-1/approve", json={"approver": "ops-1"})

    assert response.status_code == 409


def test_threshold_broadcasts_once(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def broadcast(intent: object) -> str:
        calls.append("broadcast")
        return "0xtx"

    monkeypatch.setattr(main, "_broadcast", broadcast)
    pending_intent(client)
    assert client.post("/approvals/dual-1/approve", json={"approver": "ops-1"}).status_code == 200
    response = client.post("/approvals/dual-1/approve", json={"approver": "ops-2"})

    assert response.status_code == 200
    assert response.json()["status"] == "approved_signed"
    assert calls == ["broadcast"]
    assert client.post("/approvals/dual-1/approve", json={"approver": "risk-1"}).status_code == 409
