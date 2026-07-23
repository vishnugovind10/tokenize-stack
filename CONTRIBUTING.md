# Contributing

## Setup

```bash
python -m pip install -e ".[dev]"
pytest
make demo
```

Docker users can run:

```bash
make up
```

## Rules

- Keep demos deterministic.
- Keep interfaces stable unless the change is explicitly about an interface.
- Add or update tests for core logic.
- Do not add token economics, valuation, or named regime logic.
- Do not commit secrets. Anvil-style demo keys must be labeled as demo material.

Use conventional commit messages when practical.
