from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Deployment:
    chain_id: int
    rpc_url: str
    addresses: dict[str, str]
    personas: dict[str, str]
    abi_dir: Path = Path("/deployment/abi")

    @classmethod
    def load(cls, path: Path = Path("/deployment/deployment.json")) -> "Deployment":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            chain_id=int(data["chain_id"]),
            rpc_url=str(data.get("rpc_url", "http://anvil:8545")),
            addresses={str(k): str(v) for k, v in data["addresses"].items()},
            personas={str(k): str(v) for k, v in data["personas"].items()},
        )


def wait_for_deployment(path: Path = Path("/deployment/deployment.json")) -> Deployment:
    for _ in range(30):
        if path.exists():
            return Deployment.load(path)
        time.sleep(2)
    raise RuntimeError(f"deployment file not found after 60s: {path}")
