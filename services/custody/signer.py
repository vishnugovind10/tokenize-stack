from __future__ import annotations

import hashlib
import json
from typing import Protocol


class Signer(Protocol):
    def sign(self, transaction: dict[str, object]) -> str:
        """Sign a transaction. Replace this interface with an HSM or MPC backend."""


class LocalKeySigner:
    def __init__(self, demo_key_id: str = "anvil-dev-key-0") -> None:
        self.demo_key_id = demo_key_id

    def sign(self, transaction: dict[str, object]) -> str:
        payload = json.dumps(transaction, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(f"{self.demo_key_id}:{payload}".encode("utf-8")).hexdigest()
