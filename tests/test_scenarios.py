from __future__ import annotations

from pathlib import Path

from stackctl.sim import run_demo, run_failures


def test_demo_markers(tmp_path: Path) -> None:
    result = run_demo(tmp_path / "demo.jsonl")

    assert "RECON: ALL MATCHED" in result.lines
    assert "AUDIT: CHAIN INTACT" in result.lines


def test_failure_markers(tmp_path: Path) -> None:
    result = run_failures(tmp_path / "failures.jsonl")

    assert "RECON: MISMATCH" in result.lines
    assert "UNWIND: COMPLETE" in result.lines
    assert "RESTRICTED: SURFACED NotAllowlisted" in result.lines
    assert "COUPON: NO DOUBLE PAYMENT" in result.lines
    assert "AUDIT: CHAIN INTACT" in result.lines
