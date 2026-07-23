# Limitations

This repository demonstrates architecture and testable interfaces. It is not audited and is not production custody software.

## Custody

- Uses deterministic local keys.
- Does not implement key ceremonies, operator authentication, or signer segregation.
- Approver names are demo identifiers.

## Settlement

- Models one asset leg and one cash leg.
- Does not implement net settlement, multiple venues, or counterparty exception workflow.
- Expiry unwind is intentionally simple.
- Stores the settlement projection in a local SQLite database and rebuilds no historical index beyond the persisted cursor.

## Reconciliation

- Compares local projections, chain-shaped state, and audit records.
- Does not ingest counterparty files, custodian files, or historical exception queues.

## Coupons

- Coupon demo markers remain service-local until the distributor path is routed through custody.

## Contracts

- Reference Solidity only.
- No proxy pattern, upgrade governance, formal verification, or external audit.

## Console

- Read-only.
- No authentication, roles, or write actions.

## Operations

- Docker Compose is the demo boundary.
- No Kubernetes, Terraform, or production deployment manifests are included.
- The local chain is a single Anvil node, so the demo does not model finality or reorg handling.
- Auto-mine hides gas, congestion, latency, and mempool dynamics.
- The current nonce strategy assumes one custody service instance.
- Demo approver names are unauthenticated local identities.
