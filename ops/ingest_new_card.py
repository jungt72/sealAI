"""Publish a newly reviewed seed card through the knowledge ledger.

The complete seed is imported because it is one versioned review artifact; the
ledger hashes it, writes only changed claims and queues only required index
operations. ``--delete-draft-id`` is retained as a compatibility spelling, but
now performs an audited Postgres retirement instead of a raw Qdrant deletion.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import sys

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.bootstrap import bootstrap_seed
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.ledger import (
    GLOBAL_KNOWLEDGE_TENANT,
    build_knowledge_ledger,
)
from sealai_v2.knowledge.outbox_worker import main as outbox_main


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ops.ingest_new_card")
    parser.add_argument("--card-id", required=True)
    parser.add_argument(
        "--delete-draft-id",
        default=None,
        help="compatibility name: auditably retire this draft card in Postgres",
    )
    args = parser.parse_args(argv)
    if load_fachkarten().by_id(args.card_id) is None:
        print(
            f"ingest_new_card: {args.card_id!r} not found in the reviewed seed",
            file=sys.stderr,
        )
        return 1

    ledger = build_knowledge_ledger(Settings())
    print("ledger import   :", bootstrap_seed(ledger))
    if args.delete_draft_id:
        retired = ledger.retire_card(
            tenant_id=GLOBAL_KNOWLEDGE_TENANT,
            card_id=args.delete_draft_id,
            actor="knowledge-publisher",
            now=_now(),
            note=f"Superseded by reviewed card {args.card_id}",
        )
        print(f"retired drafts : {retired} claim(s) from {args.delete_draft_id}")
    return outbox_main(["drain-all", "--batch-size", "50"])


if __name__ == "__main__":
    raise SystemExit(main())
