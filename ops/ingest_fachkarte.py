#!/usr/bin/env python3
"""Fachkarten-Ingestion CLI (Paperless path) — extract a DRAFT Fachkarte from a document into the
owner-review queue. It NEVER writes prod knowledge: drafts land in ops/fachkarten_drafts/ (OUTSIDE the
served-image tree_hash), and the owner reviews + promotes good claims into
backend/sealai_v2/knowledge/fachkarten_seed.json (flip review_state→reviewed, add a primary source).
That promotion is the vorläufig→reviewed gate; the grown seed ships on the next adjudicated eval-REPLAY.

Runs on the HOST against the working tree (uses the helper model from .env.prod) — no deploy needed to
USE it. Source-agnostic: feed any document TEXT.

Usage:
    set -a; . ./.env.prod; set +a
    python ops/ingest_fachkarte.py --file datenblatt.txt --source "paperless#42"
    pdftotext doc.pdf - | python ops/ingest_fachkarte.py --source "datenblatt-EPDM-2024"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from sealai_v2.config.settings import Settings  # noqa: E402
from sealai_v2.core.contracts import ModelConfig  # noqa: E402
from sealai_v2.core.fachkarte_extract import FachkarteExtractor  # noqa: E402
from sealai_v2.llm.factory import build_client_factory  # noqa: E402
from sealai_v2.prompts.assembler import FachkarteExtractPromptAssembler  # noqa: E402

_DRAFT_DIR = REPO_ROOT / "ops" / "fachkarten_drafts"


def _build_extractor() -> FachkarteExtractor:
    settings = Settings()
    factory = build_client_factory(settings)
    client = factory(settings.helper_provider or settings.provider)
    cfg = ModelConfig(
        model=settings.helper_model, temperature=settings.helper_temperature
    )
    return FachkarteExtractor(client, FachkarteExtractPromptAssembler(), cfg)


async def _run(text: str, source: str) -> int:
    draft = await _build_extractor().extract_document(text, source=source)
    if draft is None or draft.empty:
        print("no doc-grounded claims extracted — nothing written (fail-safe).")
        return 1
    _DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    out = _DRAFT_DIR / f"{draft.id}.json"
    out.write_text(
        json.dumps(draft.to_seed_entry(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"DRAFT written: {out.relative_to(REPO_ROOT)}")
    print(f"  titel : {draft.titel}")
    print(
        f"  claims: {len(draft.claims)} (all DRAFT — vorläufig, not yet in prod knowledge)"
    )
    print(f"  scope : { {k: v for k, v in draft.scope.items() if v} }")
    print(
        "\nREVIEW → PROMOTE: verify each claim against the source, then move the good ones into\n"
        "backend/sealai_v2/knowledge/fachkarten_seed.json with review_state='reviewed' + a primary\n"
        "source. The grown seed ships on the next adjudicated eval-REPLAY."
    )
    return 0


def _fetch_paperless(doc_id: str) -> tuple[str, str]:
    """Fetch a Paperless document's OCR/text ``content`` + title (shared client — the SAME fetch
    the auto-ingestion webhook route uses, api/routes/rag_ingest.py). URL + token from the env: use
    a host-reachable PAPERLESS_URL when running on the host (the in-stack ``paperless:8000`` is not
    host-resolvable) + PAPERLESS_TOKEN."""
    from sealai_v2.knowledge.paperless_client import fetch_document_text_and_tags

    text, source, _tags = fetch_document_text_and_tags(doc_id)
    return text, source


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Extract a DRAFT Fachkarte for owner review."
    )
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--file", help="document text file")
    src.add_argument(
        "--paperless-id", help="fetch the document text from Paperless by id"
    )
    src.add_argument(
        "--stdin", action="store_true", help="read the document text from stdin"
    )
    ap.add_argument(
        "--source", help="provenance label (auto-derived for --paperless-id)"
    )
    args = ap.parse_args(argv)
    if args.paperless_id:
        text, auto_source = _fetch_paperless(args.paperless_id)
        source = args.source or auto_source
    elif args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        source = args.source or args.file
    else:
        text = sys.stdin.read()
        source = args.source or "stdin"
    if not text.strip():
        print("empty document — nothing to do.", file=sys.stderr)
        return 2
    return asyncio.run(_run(text, source))


if __name__ == "__main__":
    raise SystemExit(main())
