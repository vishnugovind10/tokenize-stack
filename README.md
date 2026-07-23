# tokenize-stack

[![CI](https://github.com/vishnugovind10/tokenize-stack/actions/workflows/build.yml/badge.svg)](https://github.com/vishnugovind10/tokenize-stack/actions/workflows/build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![Solidity](https://img.shields.io/badge/solidity-0.8.x-black)

Run an institutional tokenization reference stack locally: restricted assets, custody policy enforcement, DvP settlement, reconciliation, and a verifiable audit trail.

![Demo placeholder](assets/demo.gif)

## Quickstart

```bash
git clone https://github.com/vishnugovind10/tokenize-stack.git
cd tokenize-stack
python -m stackctl up
python -m stackctl demo
```

Docker is required for the default stack mode. For quick exploration without Docker:

```bash
python -m stackctl demo --mode sim
python -m stackctl demo-failures --mode sim
```

Sim mode is a dependency-free simulation of the flow logic. It does not start services and does not touch a chain.

> Token-standard samples usually show contracts in isolation. The difficult wiring is custody policy, settlement failure handling, reconciliation, and audit evidence. This repository ships that wiring as a forkable template.

> [!CAUTION]
> Reference implementation for engineering study. Not audited. Not legal, investment, or production custody advice. Do not use it to safeguard real assets.

```mermaid
flowchart LR
    O["Operator"] --> C["stackctl CLI"]
    C --> K["Custody policy engine"]
    C --> S["Settlement state machine"]
    C --> R["Reconciliation worker"]
    K --> A["Hash-chained audit log"]
    S --> D["DvP escrow contract"]
    D --> T["Restricted asset + demo cash token"]
    R --> T
    R --> A
    A --> V["Offline verifier"]
    UI["Read-only console"] --> K
    UI --> S
    UI --> R
    UI --> A
```

## What Is Inside

| Component | What it does | Where production diverges |
|---|---|---|
| `contracts/` | Restricted asset, registry, demo cash token, DvP escrow, coupon distributor, Foundry deploy script | Audit, governance, upgrade planning, and deployment controls |
| `services/custody/` | Policy tiers and approval model | Real key ceremonies, HSM/MPC integration, identity-bound approvals |
| `services/settlement/` | SQLite DvP projection over the deployed escrow, failure states, auto-unwind path, custody-routed coupon batches | Multi-venue settlement, netting, production payment calendars |
| `services/recon/` | Chain, settlement SQLite, and custody-intent reconciliation with mismatch markers | Counterparty statements, historical exception workflow |
| `services/auditlog/` | Append-only JSONL records with service download and verifier endpoints | Durable retention, independent publication, operator separation |
| `stackctl/` | Operator CLI for compose, stack demos, sim demos, audit verification, and chain warp | Production runbooks and access controls |
| `console/` | Read-only live console polling service APIs through nginx | Authentication, roles, write actions |

## Failure Demos

`make demo-failures` runs three deterministic cases:

| Scenario | What appears | Final marker |
|---|---|---|
| Cash leg fails | A locked trade becomes mismatched, expires, then unwinds | `UNWIND: COMPLETE` |
| Restricted buyer | The restriction reason is surfaced as `NotAllowlisted` | `RESTRICTED: SURFACED` |
| Coupon interruption | A partial batch resumes from its cursor with no duplicate payment | `COUPON: NO DOUBLE PAYMENT` |

## Fork Guide

The template is designed around three seams:

| Seam | Local implementation | Replace with |
|---|---|---|
| `Signer` | Deterministic local dev key signer | HSM, MPC, or wallet policy backend |
| `CashToken` | Mock EUR cash token | Tokenized deposit, e-money, or sandbox payment rail |
| `ComplianceRegistry` | Allowlist, pause, and lockup mechanics | Your eligibility and transfer-control source |

Keep the interfaces stable and replace one seam at a time. The local demo remains useful as a regression harness after each replacement.

## Commands

```bash
python -m stackctl up
python -m stackctl status
python -m stackctl demo
python -m stackctl demo-failures
python -m stackctl verify-audit
python -m stackctl down --volumes
```

`python -m stackctl demo` prints:

```text
RECON: ALL MATCHED
AUDIT: CHAIN INTACT
```

`python -m stackctl demo-failures` prints:

```text
UNWIND: COMPLETE
RESTRICTED: SURFACED
COUPON: NO DOUBLE PAYMENT
AUDIT: CHAIN INTACT
```

## Implementation Status

| Surface | Status | Evidence |
|---|---|---|
| Stack lifecycle runner | In progress for v0.2 | `python -m stackctl demo` drives service APIs after compose startup |
| Sim lifecycle runner | Implemented | `python -m stackctl demo --mode sim` |
| Failure-path runner | In progress for v0.2 | `python -m stackctl demo-failures` drives service APIs after compose startup |
| Audit tamper detection | Implemented | `tests/test_auditlog.py` |
| Custody policy evaluation | Implemented | `tests/test_policy.py` |
| Reconciliation report | Chain/custody/settlement backed | `python -m stackctl demo-failures` shows mismatch then match after unwind |
| Solidity contracts | Hardened in v0.2 build branch | Foundry project under `contracts/` |
| HTTP services | Service-backed state and audit endpoints | FastAPI entry points under `services/` |
| Template distribution | Manual setting required after first publish | GitHub repository setting |

## Repository Map

- `stackctl/`: operator CLI, stack-mode HTTP driver, and explicitly labeled sim-mode runner.
- `services/common/`: shared models, audit writer, and in-memory ledger.
- `services/auditlog/`: append-only audit ingest and offline verifier.
- `services/custody/`: policy engine, approval queue, and signer interface.
- `services/settlement/`: trade state transitions and unwind handling.
- `services/recon/`: chain, settlement, and custody-intent report generation.
- `contracts/`: Solidity reference contracts and Foundry tests.
- `console/`: read-only status UI.
- `scenarios/`: declarative happy-path and failure-path scripts.

## Development

```bash
python -m pip install -e ".[dev]"
pytest
python -m stackctl demo --mode sim
python -m stackctl demo-failures --mode sim
```

See [ARCHITECTURE.md](ARCHITECTURE.md), [LIMITATIONS.md](LIMITATIONS.md), [ROADMAP.md](ROADMAP.md), and [SECURITY.md](SECURITY.md).

## Citing This Work

Use [CITATION.cff](CITATION.cff) or GitHub's **Cite this repository** button. The citation describes a reference implementation and does not imply audit assurance, production readiness, or deployment certification.

## Author

Vishnu Govind - [GitHub](https://github.com/vishnugovind10) | [Medium](https://medium.com/@vishnugovind10) | [LinkedIn](https://www.linkedin.com/in/vishnu-govind)

MIT licensed.
