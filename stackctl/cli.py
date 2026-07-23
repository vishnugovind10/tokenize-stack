from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from stackctl import sim, stack

app = typer.Typer(help="tokenize-stack operator CLI.")
chain_app = typer.Typer(help="Local chain controls.")
app.add_typer(chain_app, name="chain")


Mode = Annotated[str, typer.Option("--mode", help="Execution mode: stack or sim.")]


@app.command("demo")
def demo(
    audit_out: Annotated[
        Path,
        typer.Option("--audit-out", help="Path for generated sim audit JSONL."),
    ] = Path("chain.jsonl"),
    mode: Mode = "stack",
) -> None:
    result = sim.run_demo(audit_out) if mode == "sim" else stack.run_demo()
    for line in result.lines:
        typer.echo(line)


@app.command("demo-failures")
def demo_failures(
    audit_out: Annotated[
        Path,
        typer.Option("--audit-out", help="Path for generated sim audit JSONL."),
    ] = Path("chain.jsonl"),
    mode: Mode = "stack",
) -> None:
    result = sim.run_failures(audit_out) if mode == "sim" else stack.run_failures()
    for line in result.lines:
        typer.echo(line)


@app.command("up")
def up() -> None:
    raise typer.Exit(stack.compose(["up", "--build", "-d"]))


@app.command("down")
def down(volumes: Annotated[bool, typer.Option("-v", "--volumes")] = False) -> None:
    args = ["down"]
    if volumes:
        args.append("--volumes")
    raise typer.Exit(stack.compose(args))


@app.command("status")
def status() -> None:
    stack.wait_ready(timeout_seconds=5)
    typer.echo("STACK: READY")


@app.command("verify-audit")
def verify_audit(output: Annotated[Path | None, typer.Option("--output")] = None) -> None:
    result = stack.verify_audit(output)
    for line in result.lines:
        typer.echo(line)


@chain_app.command("warp")
def chain_warp(seconds: int) -> None:
    result = stack.chain_warp(seconds)
    for line in result.lines:
        typer.echo(line)


if __name__ == "__main__":
    app()
