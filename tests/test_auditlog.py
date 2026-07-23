from __future__ import annotations

import json
from pathlib import Path

from services.auditlog.verifier import load_records
from services.common.audit import AuditChain, verify_records


def test_audit_chain_detects_tamper(tmp_path: Path) -> None:
    path = tmp_path / "chain.jsonl"
    chain = AuditChain(path)
    chain.append("custody", "issuer", "allow", {"amount": 1})
    chain.append("settlement", "buyer", "settled", {"trade_id": "t1"})
    chain.write()

    ok, _ = verify_records(load_records(path))
    assert ok

    records = load_records(path)
    records[0]["payload_hash"] = "bad"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")
    ok, message = verify_records(load_records(path))
    assert not ok
    assert "bad hash at 1" == message
