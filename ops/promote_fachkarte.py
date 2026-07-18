"""ops/promote_fachkarte.py — thin CLI wrapper around ``knowledge.promote.merge_new_card`` (the
2026-07-04 RAG-audit fix for the "hand-edit the seed JSON" friction). Pure file operation, no network
— runs anywhere (host checkout or inside the container, doesn't matter which).

Usage:
    python ops/promote_fachkarte.py --card path/to/new_card.json
    python ops/promote_fachkarte.py --card path/to/new_card.json --seed path/to/fachkarten_seed.json

``new_card.json`` is ONE Fachkarte object (the same shape as one entry in ``fachkarten_seed.json``'s
``cards`` array) — already written, already sourced, review_state="reviewed" claims already carrying
real owner/trap provenance or a primary source. This tool validates and merges; it does not decide
what belongs in the card (see ``knowledge/promote.py``'s module docstring).

To publish the reviewed artifact before the next release, run ``ops/ingest_new_card.py`` inside the
backend-v2 container. It imports through Postgres and the durable outbox; Qdrant is never written
directly.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from sealai_v2.knowledge.promote import PromotionError, merge_new_card


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ops.promote_fachkarte")
    parser.add_argument("--card", required=True, help="path to the new card's JSON")
    parser.add_argument(
        "--seed",
        default=None,
        help="path to fachkarten_seed.json (default: the live seed)",
    )
    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="skip writing a .bak-pre-promote-* copy",
    )
    args = parser.parse_args(argv)

    new_card_raw = json.loads(Path(args.card).read_text(encoding="utf-8"))
    seed_path = Path(args.seed) if args.seed else None
    try:
        catalog = merge_new_card(
            new_card_raw, seed_path=seed_path, backup=not args.no_backup
        )
    except PromotionError as exc:
        print(f"promote_fachkarte: REFUSED — {exc}", file=sys.stderr)
        return 1

    new_id = str(new_card_raw["id"])
    card = catalog.by_id(new_id)
    print(
        f"promoted {new_id!r}: {len(card.claims)} claims "
        f"({len(card.reviewed_claims())} reviewed, {len(card.draft_claims())} draft) — "
        f"seed now has {len(catalog.cards)} cards / {len(catalog.reviewed())} reviewed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
