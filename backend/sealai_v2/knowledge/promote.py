"""Fachkarte promotion — safely add ONE new/edited reviewed card to the seed, replacing the manual
JSON surgery the 2026-07-04 RAG audit found (hand-edit fachkarten_seed.json directly, then docker cp
+ docker exec a full re-ingest, with no validation before the edit landed).

Pure file I/O + the SAME validation ``load_fachkarten`` already enforces (circularity guard, schema,
duplicate-id check) — no network, no Qdrant, no LLM, so this is fully unit-testable without mocking
anything. This tool never decides WHAT to promote and never weakens the circularity guard: the
caller supplies an already-written, already-sourced reviewed card (see ``rag_ingest.py``'s own
doctrine — draft->reviewed stays a separate, deliberate, human-judgment step, never automatic). It
only makes the MECHANICAL merge safe (validated before a single byte is written), fast, and
git-diff-friendly (a normal JSON append, not a hand-edit that risks the circularity invariants).

Runtime publication is a separate, durable concern: ``ops/ingest_new_card.py`` imports the reviewed
seed into the Postgres ledger and drains its outbox. It never writes Qdrant directly.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card, load_fachkarten

_DEFAULT_SEED = Path(__file__).resolve().parent / "fachkarten_seed.json"


class PromotionError(ValueError):
    """A new-card JSON failed validation, or its id collides with an existing seed card."""


def merge_new_card(
    new_card_raw: dict,
    *,
    seed_path: Path | None = None,
    backup: bool = True,
) -> FachkartenCatalog:
    """Validate ``new_card_raw`` in the context of the FULL merged catalog (existing cards + the new
    one) and, only if that whole set is valid, write it to ``seed_path`` (default: the live seed).
    Raises ``PromotionError`` before touching the file at all on any failure — an id collision, a
    circularity-guard violation, or any other schema error. Writes a timestamped backup before the
    rewrite (mirrors ``ops/promote_seed.py``'s own safety pattern). Returns the freshly RE-LOADED
    catalog (from disk, not from memory) — proves the write itself round-trips cleanly, not just
    that the in-memory data looked right before writing."""
    path = seed_path or _DEFAULT_SEED
    existing_data = json.loads(path.read_text(encoding="utf-8"))
    existing_cards_raw = existing_data.get("cards", [])

    merged_cards_raw = existing_cards_raw + [new_card_raw]
    seen: set[str] = set()
    for raw in merged_cards_raw:
        try:
            card = _card(raw)
        except ValueError as exc:
            raise PromotionError(f"card failed validation: {exc}") from exc
        if card.id in seen:
            is_new = raw is new_card_raw
            raise PromotionError(
                f"card id {card.id!r} already exists in the seed — promotion is additive-only; "
                "edit the existing card directly if you mean to replace it"
                if is_new
                else f"duplicate Fachkarte id already present in the seed: {card.id!r}"
            )
        seen.add(card.id)

    if backup:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        shutil.copy(path, path.with_suffix(path.suffix + f".bak-pre-promote-{stamp}"))

    existing_data["cards"] = merged_cards_raw
    path.write_text(
        json.dumps(existing_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return load_fachkarten(path)
