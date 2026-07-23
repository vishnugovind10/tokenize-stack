from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, cast


def _canonical(value: Any) -> str:
    if is_dataclass(value):
        value = asdict(cast(Any, value))
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class AuditChain:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._records: list[dict[str, Any]] = []

    @property
    def records(self) -> list[dict[str, Any]]:
        return list(self._records)

    def append(self, service: str, actor: str, action: str, payload: Any) -> dict[str, Any]:
        prev_hash = self._records[-1]["hash"] if self._records else "0" * 64
        record = {
            "seq": len(self._records) + 1,
            "ts": "2026-01-01T00:00:00Z",
            "service": service,
            "actor": actor,
            "action": action,
            "payload_hash": digest(payload),
            "prev_hash": prev_hash,
        }
        record["hash"] = digest(record)
        self._records.append(record)
        return record

    def write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as handle:
            for record in self._records:
                handle.write(json.dumps(record, sort_keys=True) + "\n")


def verify_records(records: list[dict[str, Any]]) -> tuple[bool, str]:
    prev_hash = "0" * 64
    for index, record in enumerate(records, start=1):
        if record.get("seq") != index:
            return False, f"bad seq at {index}"
        if record.get("prev_hash") != prev_hash:
            return False, f"bad prev_hash at {index}"
        candidate = dict(record)
        observed_hash = candidate.pop("hash", None)
        expected_hash = digest(candidate)
        if observed_hash != expected_hash:
            return False, f"bad hash at {index}"
        prev_hash = observed_hash
    return True, f"OK, {len(records)} events, chain intact"
