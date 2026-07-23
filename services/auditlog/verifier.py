from __future__ import annotations

import json
import sys
from pathlib import Path

from services.common.audit import verify_records


def load_records(path: Path) -> list[dict[str, object]]:
    with path.open("r", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("usage: python -m services.auditlog.verifier <chain.jsonl>", file=sys.stderr)
        return 2
    ok, message = verify_records(load_records(Path(args[0])))
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
