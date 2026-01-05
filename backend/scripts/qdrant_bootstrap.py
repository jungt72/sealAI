from __future__ import annotations

import sys

from app.services.rag.qdrant_bootstrap import bootstrap_rag_collection


def main() -> int:
    try:
        result = bootstrap_rag_collection()
        print(f"[qdrant_bootstrap] result={result}")
        return 0 if result in {"ok", "created", "skipped"} else 1
    except Exception as exc:
        print(f"[qdrant_bootstrap] ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

