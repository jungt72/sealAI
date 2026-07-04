"""ops/ingest_new_card.py — push ONE (already-merged, already-in-the-seed) Fachkarte live into
Qdrant with a single incremental upsert, instead of re-embedding the whole catalog every time
(the 2026-07-04 RAG audit's "iterativ erweiterbar?" finding: ``ops/ingest_prod_qdrant.py`` always
reloads + re-embeds all ~47 cards, which is safe but wasteful for a single new card, and only gets
more so as the seed grows).

Run INSIDE the backend-v2 container (same as ops/ingest_prod_qdrant.py — needs the prod env: Qdrant
URL on the docker network, OpenAI key):

    docker cp fachkarten_seed.json backend-v2:/app/sealai_v2/knowledge/fachkarten_seed.json  # if
                                                                                                # promoted on the host first
    docker exec -i backend-v2 python ops/ingest_new_card.py --card-id FK-NEWCARD-ID

Optionally cleans up a stale DRAFT card's points in the same run (``--delete-draft-id``) — e.g. after
promoting a Paperless-sourced draft (``FK-DRAFT-DOC-<paperless_id>``) into a proper reviewed card
under a new, permanent id, the old draft's points would otherwise sit in Qdrant forever (nothing else
ever removes them — see the audit's draft-accumulation finding).
"""

from __future__ import annotations

import argparse
import sys

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, load_fachkarten
from sealai_v2.knowledge.qdrant_retrieval import (
    _make_client,
    delete_card_points,
    ingest_fachkarten,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ops.ingest_new_card")
    parser.add_argument(
        "--card-id", required=True, help="the seed card id to push live"
    )
    parser.add_argument(
        "--delete-draft-id",
        default=None,
        help="optional: also delete this OTHER card_id's stale points (e.g. the draft being promoted)",
    )
    args = parser.parse_args(argv)

    settings = Settings()
    client = _make_client(settings)
    catalog = load_fachkarten()
    card = catalog.by_id(args.card_id)
    if card is None:
        print(
            f"ingest_new_card: {args.card_id!r} not found in the seed — promote it first",
            file=sys.stderr,
        )
        return 1

    print("collection      :", settings.qdrant_collection)
    if client.collection_exists(settings.qdrant_collection):
        print("baseline points :", client.count(settings.qdrant_collection).count)
    else:
        print(
            "baseline points : 0 (collection does not exist yet — ensure_collection will create it)"
        )

    n = ingest_fachkarten(
        settings, client=client, catalog=FachkartenCatalog(cards=(card,))
    )
    print(f"upserted {n} point(s) for {args.card_id!r} ({len(card.claims)} claims)")

    if args.delete_draft_id:
        deleted = delete_card_points(
            client, settings.qdrant_collection, args.delete_draft_id
        )
        print(f"deleted {deleted} stale point(s) for {args.delete_draft_id!r}")

    print("final points    :", client.count(settings.qdrant_collection).count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
