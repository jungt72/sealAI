"""Idempotently import the governed repository seed into the Postgres ledger."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.fachkarten import _DEFAULT_FILE, load_fachkarten
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    KnowledgeDocumentInput,
    PostgresKnowledgeLedger,
    build_knowledge_ledger,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def bootstrap_seed(
    ledger: PostgresKnowledgeLedger,
    *,
    seed_path: Path = _DEFAULT_FILE,
    now: str | None = None,
):
    catalog = load_fachkarten(seed_path)
    return ledger.replace_catalog(
        KnowledgeDocumentInput(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            source_type="git_seed",
            source_id="fachkarten_seed",
            source_uri=f"repo://{seed_path.name}",
            object_key=f"image://sealai_v2/knowledge/{seed_path.name}",
            title="sealingAI curated Fachkarten seed",
            content=seed_path.read_bytes(),
            authority="per_claim_evidence_policy",
        ),
        catalog,
        now=now or _utc_now(),
        actor="release-bootstrap",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sealai_v2.knowledge.bootstrap")
    parser.add_argument("--seed", type=Path, default=_DEFAULT_FILE)
    args = parser.parse_args(argv)
    result = bootstrap_seed(build_knowledge_ledger(Settings()), seed_path=args.seed)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
