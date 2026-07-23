# Architecture

`tokenize-stack` is a local reference stack. v0.2 moves the default path toward a Docker-backed stack with Anvil, a Foundry deployer, FastAPI services, and a read-only console. Settlement state is a SQLite projection over deployed escrow events; sim mode is explicitly separate.

## Components

```mermaid
flowchart TB
    CLI["stackctl"] --> Custody["custody service"]
    CLI --> Compose["docker compose"]
    Compose --> Anvil["anvil"]
    Compose --> Deployer["Foundry deployer"]
    Deployer --> Volume["deployment volume"]
    Volume --> Custody
    Volume --> Settlement
    Volume --> Recon
    CLI --> Settlement["settlement service"]
    CLI --> Recon["recon service"]
    Custody --> Audit["auditlog service"]
    Settlement --> Audit
    Recon --> Audit
    Settlement --> Custody
    Custody --> Escrow["DvPEscrow"]
    Escrow --> Asset["RestrictedAssetToken"]
    Escrow --> Cash["CashToken"]
    Recon --> Asset
    Recon --> Cash
    Console["read-only console"] --> Custody
    Console --> Settlement
    Console --> Recon
    Console --> Audit
```

## DvP Happy Path

```mermaid
sequenceDiagram
    participant Seller
    participant Settlement
    participant Custody
    participant Escrow
    participant Buyer
    participant Recon
    Seller->>Settlement: create trade
    Settlement->>Custody: approve asset + lock intent
    Custody->>Escrow: lock asset
    Settlement->>Custody: approve cash + settle intent
    Custody->>Escrow: settle with cash
    Escrow-->>Seller: cash
    Escrow-->>Buyer: asset
    Recon->>Escrow: read settled state
    Recon-->>Seller: matched report
```

## DvP Unwind

```mermaid
sequenceDiagram
    participant Buyer
    participant Custody
    participant Escrow
    participant Settlement
    participant Recon
    Settlement->>Custody: buyer settle intent
    Custody->>Escrow: settle without enough cash
    Escrow-->>Buyer: revert
    Settlement->>Escrow: observe expiry
    Settlement->>Custody: unwind intent
    Custody->>Escrow: unwind
    Recon->>Settlement: compare projection
    Recon-->>Settlement: mismatch cleared
```

## Coupon Resume

```mermaid
sequenceDiagram
    participant Issuer
    participant Distributor
    participant Holder
    participant Audit
    Issuer->>Distributor: fund coupon round (P3)
    Distributor->>Holder: pay batch (P3)
    Distributor--xHolder: injected interruption
    Distributor->>Audit: record cursor
    Distributor->>Holder: resume from cursor
    Distributor->>Audit: record no duplicate payment
```

## Trust Boundaries

- Demo keys are deterministic local keys only.
- The console is read-only.
- The audit verifier detects missing, edited, or reordered records in the JSONL chain.
- The local signer interface is the replacement point for real custody infrastructure.
- Coupon markers are local service behavior until the distributor is wired through custody in P3.
