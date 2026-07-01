"""POST /internal/rag/ingest — Paperless post-consume webhook target
(``paperless/scripts/sealai-rag-webhook.sh``).

Auto-ingests a NEWLY consumed document tagged ``sealai:ingest`` as a DRAFT Fachkarte
(``core/fachkarte_extract.py``) directly into the live Qdrant index — so new knowledge uploaded via
Paperless becomes available (as ``review_state=draft``, rendered "vorläufig") WITHOUT a manual
``ops/ingest_fachkarte.py`` run. Untagged / non-knowledge documents (invoices, unrelated paperwork)
are a no-op — a document simply never gets ``sealai:ingest`` if it should stay out of sealingAI's
knowledge (build-spec §3 tag taxonomy: ``sealai:ingest`` gate, ``sealai:status-draft`` /
``sealai:status-reviewed`` / ``sealai:status-failed`` review state, ``sealai:source-*`` provenance
kind).

RELIABILITY (2026-07-01 incident): a live document was silently dropped — the LLM extractor
returned zero claims on the first (and only) attempt, no error was raised, so the fail-safe path
returned a clean 200 with no visible signal; a manual retry of the IDENTICAL call succeeded. Two
fixes: (1) the extraction+upsert step now retries up to ``_MAX_ATTEMPTS`` times before giving up —
a transient LLM sampling miss on one attempt is exactly the failure mode observed; (2) EVERY
terminal failure (not just exceptions) now tags the Paperless document ``sealai:status-failed`` so
a silent drop is visible in Paperless itself, not just in a log nobody is watching. A later success
(e.g. after a manual retry) clears that tag again — the status tags never lie about the live state.

DOCTRINE (unchanged from the manual CLI path): this endpoint can only ever ADD DRAFT claims — never
``reviewed`` (never gains L3 block/correct authority, always rendered "vorläufig" by L1). Promotion
draft->reviewed stays a SEPARATE, deliberate step (the periodic challenge process), never automatic.
Idempotent: the card id is derived from the Paperless document id, so re-consuming (or retrying) the
same document overwrites its own Qdrant points rather than duplicating them (``ingest_fachkarten``,
uuid5 keys) — retrying is therefore safe with no side effects from a partial/failed prior attempt.

Auth: a static shared-secret header (``X-SeaLAI-Webhook-Token`` == ``PAPERLESS_WEBHOOK_TOKEN`` env) —
Paperless is a server, not a user, so this is NOT the tenant JWT flow. Fail-closed if the expected
token is unset or the presented one does not match.
"""

from __future__ import annotations

import logging
import os
from dataclasses import replace

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from sealai_v2.config.settings import Settings
from sealai_v2.core.contracts import ModelConfig
from sealai_v2.core.fachkarte_extract import FachkarteExtractor
from sealai_v2.knowledge.fachkarten import FachkartenCatalog, _card
from sealai_v2.knowledge.paperless_client import (
    PaperlessConfigError,
    add_tag_to_document,
    fetch_document_text_and_tags,
    find_tag_id,
    remove_tag_from_document,
)
from sealai_v2.knowledge.qdrant_retrieval import ingest_fachkarten
from sealai_v2.llm.factory import build_client_factory
from sealai_v2.prompts.assembler import FachkarteExtractPromptAssembler

router = APIRouter(prefix="/internal/rag", tags=["rag-ingest"])
_log = logging.getLogger("sealai_v2.api.rag_ingest")

_RAG_TAG = "sealai:ingest"
_STATUS_DRAFT_TAG = "sealai:status-draft"
_STATUS_FAILED_TAG = "sealai:status-failed"
# A transient LLM sampling miss (no-claims / rate-limit / a momentarily malformed completion) on
# ONE attempt is the observed failure mode — empirically, the SAME document failed on attempt 1 and
# succeeded cleanly on a lone manual retry. 3 keeps worst-case cost bounded (Mistral Small, cheap)
# while making a repeat-on-every-attempt failure genuinely mean something is wrong with the DOCUMENT,
# not just LLM variance.
_MAX_ATTEMPTS = 3


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
    # Same precedence the webhook SCRIPT itself uses (paperless/scripts/sealai-rag-webhook.sh):
    # SEALAI_RAG_WEBHOOK_TOKEN first, else PAPERLESS_WEBHOOK_TOKEN — so this side never drifts out
    # of sync with whichever name the script's env actually carries the shared secret under.
    expected = os.environ.get("SEALAI_RAG_WEBHOOK_TOKEN") or os.environ.get(
        "PAPERLESS_WEBHOOK_TOKEN", ""
    )
    if not expected or presented != expected:
        raise HTTPException(status_code=401, detail="invalid webhook token")


def _mark_status(document_id: str, add: str, *, remove: tuple[str, ...] = ()) -> None:
    """Best-effort Paperless status tagging — NEVER raises. A tagging hiccup must never mask, undo,
    or turn into a reported failure for the real ingestion result; it is logged and swallowed."""
    try:
        tag_id = find_tag_id(add)
        if tag_id is not None:
            add_tag_to_document(document_id, tag_id)
        for old_name in remove:
            old_id = find_tag_id(old_name)
            if old_id is not None:
                remove_tag_from_document(document_id, old_id)
    except Exception:  # noqa: BLE001
        _log.exception(
            "rag_ingest: failed to update status tags for document %s (add=%s remove=%s)",
            document_id,
            add,
            remove,
        )


async def _attempt(
    settings: Settings, text: str, source: str, document_id: str
) -> tuple[dict | None, str]:
    """One extraction+upsert attempt. Returns (success_body, "") on success, or (None, reason) on
    failure — never raises (every internal error is caught and turned into a reason string so the
    caller's retry loop can keep going)."""
    extractor = _build_extractor(settings)
    try:
        draft = await extractor.extract_document(text, source=source)
    except Exception as exc:  # noqa: BLE001 — an LLM hiccup (rate limit/timeout) must not abort the loop
        return None, f"extraction_error: {exc}"
    if draft is None or draft.empty:
        return None, "no doc-grounded claims extracted"

    # Stable id: the LLM's own titel_vorschlag can vary across runs of the SAME document, which
    # would otherwise slug into a DIFFERENT card id each time -> duplicate cards instead of a
    # clean idempotent overwrite. The Paperless document_id is the one thing guaranteed stable.
    draft = replace(draft, id=f"FK-DRAFT-DOC-{document_id}")

    try:
        card = _card(draft.to_seed_entry())
    except ValueError as exc:
        return None, f"invalid draft: {exc}"

    catalog = FachkartenCatalog(cards=(card,))
    try:
        n_points = ingest_fachkarten(settings, catalog=catalog)
    except Exception as exc:  # noqa: BLE001 — a Qdrant/embedder hiccup must not abort the loop
        return None, f"qdrant_upsert_failed: {exc}"

    return {
        "ingested": True,
        "card_id": card.id,
        "claims": len(card.claims),
        "points": n_points,
        "review_state": "draft",
    }, ""


@router.post("/ingest")
async def ingest(
    req: IngestRequest,
    x_sealai_webhook_token: str = Header(default=""),
) -> dict:
    _check_webhook_token(x_sealai_webhook_token)

    text = source = ""
    tags: tuple[str, ...] = ()
    fetch_ok = False
    for fetch_attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            text, source, tags = fetch_document_text_and_tags(req.document_id)
            fetch_ok = True
            break
        except PaperlessConfigError:
            _log.error("rag_ingest: PAPERLESS_URL/TOKEN not configured")
            return {"ingested": False, "reason": "paperless_not_configured"}
        except Exception:  # noqa: BLE001 — a Paperless/network hiccup must never 500-loop the webhook
            _log.warning(
                "rag_ingest: fetch attempt %d/%d failed for document %s",
                fetch_attempt,
                _MAX_ATTEMPTS,
                req.document_id,
                exc_info=True,
            )
    if not fetch_ok:
        _mark_status(req.document_id, _STATUS_FAILED_TAG)
        return {
            "ingested": False,
            "reason": "fetch_failed",
            "attempts": _MAX_ATTEMPTS,
        }

    if _RAG_TAG not in tags:
        # not an error — this document was never meant to feed sealingAI. No status tag either way.
        return {"ingested": False, "reason": f"missing tag {_RAG_TAG!r}"}
    if not text.strip():
        _mark_status(req.document_id, _STATUS_FAILED_TAG)
        return {"ingested": False, "reason": "empty document"}

    settings = Settings()
    last_reason = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        result, last_reason = await _attempt(settings, text, source, req.document_id)
        if result is not None:
            _log.info(
                "rag_ingest: card=%s claims=%d points=%d source=%s attempt=%d/%d",
                result["card_id"],
                result["claims"],
                result["points"],
                source,
                attempt,
                _MAX_ATTEMPTS,
            )
            _mark_status(
                req.document_id, _STATUS_DRAFT_TAG, remove=(_STATUS_FAILED_TAG,)
            )
            return result
        _log.warning(
            "rag_ingest: attempt %d/%d failed for document %s (%s): %s",
            attempt,
            _MAX_ATTEMPTS,
            req.document_id,
            source,
            last_reason,
        )

    _log.error(
        "rag_ingest: all %d attempts failed for document %s (%s): %s",
        _MAX_ATTEMPTS,
        req.document_id,
        source,
        last_reason,
    )
    _mark_status(req.document_id, _STATUS_FAILED_TAG)
    return {"ingested": False, "reason": last_reason, "attempts": _MAX_ATTEMPTS}
