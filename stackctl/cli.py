from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from stackctl.scenarios import run_demo, run_failures

app = typer.Typer(help="Deterministic tokenize-stack demo runner.")


@app.command("demo")
def demo(
    audit_out: Annotated[
        Path,
        typer.Option("--audit-out", help="Path for the generated audit JSONL file."),
    ] = Path("chain.jsonl"),
) -> None:
    result = run_demo(audit_out)
    for line in result.lines:
        typer.echo(line)


@app.command("demo-failures")
def demo_failures(
    audit_out: Annotated[
        Path,
        typer.Option("--audit-out", help="Path for the generated audit JSONL file."),
    ] = Path("chain.jsonl"),
) -> None:
    result = run_failures(audit_out)
    for line in result.lines:
        typer.echo(line)


if __name__ == "__main__":
    app()
