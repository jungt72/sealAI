"""POST /internal/rag/ingest — Paperless post-consume webhook target
(``paperless/scripts/sealai-rag-webhook.sh``).

Auto-ingests a NEWLY consumed document tagged ``rag:enabled`` as a DRAFT Fachkarte
(``core/fachkarte_extract.py``) directly into the live Qdrant index — so new knowledge uploaded via
Paperless becomes available (as ``review_state=draft``, rendered "vorläufig") WITHOUT a manual
``ops/ingest_fachkarte.py`` run. Untagged / non-knowledge documents (invoices, unrelated paperwork)
are a no-op — gated on the SAME ``rag:enabled`` tag convention the existing 14 source documents use.

DOCTRINE (unchanged from the manual CLI path): this endpoint can only ever ADD DRAFT claims — never
``reviewed`` (never gains L3 block/correct authority, always rendered "vorläufig" by L1). Promotion
draft->reviewed stays a SEPARATE, deliberate step (the periodic challenge process), never automatic.
Idempotent: the card id is derived from the document title, so re-consuming the same document
overwrites its own Qdrant points rather than duplicating them (``ingest_fachkarten``, uuid5 keys).

Auth: a static shared-secret header (``X-SeaLAI-Webhook-Token`` == ``PAPERLESS_WEBHOOK_TOKEN`` env) —
Paperless is a server, not a user, so this is NOT the tenant JWT flow. Fail-closed if the expected
token is unset or the presented one does not match.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.fachkarte_extract import FachkarteExtractor
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card
from sealai_v2.knowledge.paperless_client import (
    PaperlessConfigError,
    fetch_document_text_and_tags,
)
from sealai_v2.knowledge.qdrant_retrieval import ingest_fachkarten
from sealai_v2.llm.factory import build_client_factory
from sealai_v2.prompts.assembler import FachkarteExtractPromptAssembler

router = APIRouter(prefix="/internal/rag", tags=["rag-ingest"])
_log = logging.getLogger("sealai_v2.api.rag_ingest")

_RAG_TAG = "rag:enabled"


class IngestRequest(BaseModel):
    document_id: str


def _build_extractor(settings: Settings) -> FachkarteExtractor:
    factory = build_client_factory(settings)
    client = factory(settings.helper_provider or settings.provider)
    cfg = ModelConfig(
        model=settings.helper_model, temperature=settings.helper_temperature
    )
    return FachkarteExtractor(client, FachkarteExtractPromptAssembler(), cfg)


def _check_webhook_token(presented: str) -> None:
    expected = os.environ.get("PAPERLESS_WEBHOOK_TOKEN", "")
    if not expected or presented != expected:
        raise HTTPException(status_code=401, detail="invalid webhook token")


@router.post("/ingest")
async def ingest(
    req: IngestRequest,
    x_sealai_webhook_token: str = Header(default=""),
) -> dict:
    _check_webhook_token(x_sealai_webhook_token)

    try:
        text, source, tags = fetch_document_text_and_tags(req.document_id)
    except PaperlessConfigError:
        _log.error("rag_ingest: PAPERLESS_URL/TOKEN not configured")
        return {"ingested": False, "reason": "paperless_not_configured"}
    except Exception:  # noqa: BLE001 — a Paperless/network hiccup must never 500-loop the webhook
        _log.exception("rag_ingest: failed to fetch document %s", req.document_id)
        return {"ingested": False, "reason": "fetch_failed"}

    if _RAG_TAG not in tags:
        return {"ingested": False, "reason": f"missing tag {_RAG_TAG!r}"}
    if not text.strip():
        return {"ingested": False, "reason": "empty document"}

    settings = Settings()
    extractor = _build_extractor(settings)
    draft = await extractor.extract_document(text, source=source)
    if draft is None or draft.empty:
        return {"ingested": False, "reason": "no doc-grounded claims extracted"}

    try:
        card = _card(draft.to_seed_entry())
    except ValueError as exc:
        _log.warning("rag_ingest: draft failed card validation: %s", exc)
        return {"ingested": False, "reason": f"invalid draft: {exc}"}

    catalog = FachkartenCatalog(cards=(card,))
    n_points = ingest_fachkarten(settings, catalog=catalog)
    _log.info(
        "rag_ingest: card=%s claims=%d points=%d source=%s",
        card.id,
        len(card.claims),
        n_points,
        source,
    )
    return {
        "ingested": True,
        "card_id": card.id,
        "claims": len(card.claims),
        "points": n_points,
        "review_state": "draft",
    }
