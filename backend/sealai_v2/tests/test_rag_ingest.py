"""POST /internal/rag/ingest — the Paperless auto-ingestion webhook. Proves: a wrong/missing token is
refused (401), an untagged document is a no-op, an empty/claim-less document is a no-op, a successful
extraction lands EXACTLY ONE draft card in Qdrant (never reviewed — doctrine), and a Paperless/network
hiccup fails safe (never 500s the webhook)."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sealai_v2.api.main import app
from sealai_v2.api.routes import rag_ingest
from sealai_v2.knowledge.paperless_client import PaperlessConfigError
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_TOKEN = "test-webhook-token"


def _client(
    monkeypatch,
    *,
    fetch_result=None,
    fetch_error=None,
    llm_responses=None,
    ingested_catalogs=None,
    find_tag_id_result=15,
    tag_calls=None,
    add_tag_error=None,
):
    monkeypatch.setenv("PAPERLESS_WEBHOOK_TOKEN", _TOKEN)
    monkeypatch.setattr(rag_ingest, "find_tag_id", lambda name: find_tag_id_result)

    def _fake_add_tag(doc_id, tag_id):
        if add_tag_error is not None:
            raise add_tag_error
        if tag_calls is not None:
            tag_calls.append((doc_id, tag_id))

    monkeypatch.setattr(rag_ingest, "add_tag_to_document", _fake_add_tag)

    def _fake_fetch(doc_id):
        if fetch_error is not None:
            raise fetch_error
        return fetch_result

    monkeypatch.setattr(rag_ingest, "fetch_document_text_and_tags", _fake_fetch)

    client = ScriptedFakeLlmClient(llm_responses or [])
    monkeypatch.setattr(
        rag_ingest,
        "_build_extractor",
        lambda settings: rag_ingest.FachkarteExtractor(
            client,
            rag_ingest.FachkarteExtractPromptAssembler(),
            rag_ingest.ModelConfig("fake-helper"),
        ),
    )

    captured = ingested_catalogs if ingested_catalogs is not None else []

    def _fake_ingest(settings, *, catalog=None, **_kw):
        captured.append(catalog)
        return sum(len(c.claims) for c in catalog.cards)

    monkeypatch.setattr(rag_ingest, "ingest_fachkarten", _fake_ingest)
    return TestClient(app)


def _headers(token: str = _TOKEN) -> dict:
    return {"X-SeaLAI-Webhook-Token": token}


def test_wrong_token_is_refused():
    from fastapi.testclient import TestClient as TC

    client = TC(app)
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers("nope")
    )
    assert r.status_code == 401


def test_missing_token_is_refused_even_if_env_unset(monkeypatch):
    monkeypatch.delenv("PAPERLESS_WEBHOOK_TOKEN", raising=False)
    client = TestClient(app)
    r = client.post("/internal/rag/ingest", json={"document_id": "5"})
    assert r.status_code == 401


def test_untagged_document_is_a_noop(monkeypatch):
    client = _client(
        monkeypatch,
        fetch_result=("some document text", "paperless#5:Doc", ("some:other:tag",)),
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is False and "sealai:ingest" in body["reason"]


def test_empty_document_is_a_noop(monkeypatch):
    client = _client(
        monkeypatch, fetch_result=("   ", "paperless#5:Doc", ("sealai:ingest",))
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200 and r.json() == {
        "ingested": False,
        "reason": "empty document",
    }


def test_no_claims_extracted_is_a_noop(monkeypatch):
    client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist ein Fluorpolymer.",
            "paperless#5:PTFE",
            ("sealai:ingest",),
        ),
        llm_responses=[
            json.dumps({"claims": [], "scope": {}, "titel_vorschlag": "PTFE"})
        ],
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    assert r.json()["ingested"] is False
    assert "no doc-grounded claims" in r.json()["reason"]


def test_fetch_failure_fails_safe_not_500(monkeypatch):
    client = _client(monkeypatch, fetch_error=PaperlessConfigError("no config"))
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200 and r.json() == {
        "ingested": False,
        "reason": "paperless_not_configured",
    }


def test_network_error_fails_safe_not_500(monkeypatch):
    client = _client(monkeypatch, fetch_error=RuntimeError("boom"))
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200 and r.json() == {
        "ingested": False,
        "reason": "fetch_failed",
    }


def test_llm_extraction_error_fails_safe_not_500(monkeypatch):
    """Regression: a live run hit this exact gap (Mistral 429 rate-limit propagated as an unhandled
    exception -> 500, silently dropping the document since Paperless never retries the webhook)."""
    client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr beständig.",
            "paperless#5:PTFE",
            ("sealai:ingest",),
        ),
        llm_responses=[],  # exhausted script -> ScriptedFakeLlmClient raises on the extractor's call
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    assert r.json() == {"ingested": False, "reason": "extraction_failed"}


def test_qdrant_upsert_error_fails_safe_not_500(monkeypatch):
    def _boom(settings, *, catalog=None, **_kw):
        raise RuntimeError("qdrant unreachable")

    client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr beständig. PTFE zeigt ausgeprägten Kaltfluss.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest",),
        ),
        llm_responses=[
            json.dumps(
                {
                    "titel_vorschlag": "PTFE Grundlagen",
                    "scope": {"material": ["PTFE"]},
                    "claims": [
                        "PTFE ist chemisch sehr beständig.",
                        "PTFE zeigt ausgeprägten Kaltfluss.",
                    ],
                }
            )
        ],
    )
    import sealai_v2.api.routes.rag_ingest as rag_ingest

    monkeypatch.setattr(rag_ingest, "ingest_fachkarten", _boom)
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is False and body["reason"] == "qdrant_upsert_failed"
    assert body["card_id"].startswith("FK-DRAFT-")


def test_successful_ingestion_lands_exactly_one_draft_card(monkeypatch):
    captured = []
    client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr beständig. PTFE zeigt ausgeprägten Kaltfluss.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest",),
        ),
        llm_responses=[
            json.dumps(
                {
                    "titel_vorschlag": "PTFE Grundlagen",
                    "scope": {"material": ["PTFE"]},
                    "claims": [
                        "PTFE ist chemisch sehr beständig.",
                        "PTFE zeigt ausgeprägten Kaltfluss.",
                    ],
                }
            )
        ],
        ingested_catalogs=captured,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is True
    assert body["claims"] == 2
    assert body["review_state"] == "draft"

    # exactly ONE card was handed to the Qdrant ingest — doctrine: draft-only, never reviewed
    assert len(captured) == 1
    catalog = captured[0]
    assert len(catalog.cards) == 1
    card = catalog.cards[0]
    assert card.review_state == "draft"
    assert all(c.review_state == "draft" for c in card.claims)
    assert (
        card.id == "FK-DRAFT-DOC-5"
    )  # stable on document_id, not the LLM-generated title
    assert card.provenance == ("paperless-draft:paperless#5:PTFE_Research",)


def test_card_id_is_stable_across_differently_phrased_titles_same_document(monkeypatch):
    """Regression: a live run showed the LLM can phrase titel_vorschlag differently across two
    extractions of the SAME document -> a different slug -> a DUPLICATE card instead of a clean
    idempotent overwrite. The card id must depend on document_id, never on the LLM titel."""
    captured = []
    fetch = (
        "PTFE ist chemisch sehr bestaendig.",
        "paperless#5:PTFE_Research",
        ("sealai:ingest",),
    )
    for titel in ("PTFE Grundlagen", "PTFE - chemische Bestaendigkeit (Uebersicht)"):
        client = _client(
            monkeypatch,
            fetch_result=fetch,
            llm_responses=[
                json.dumps(
                    {
                        "titel_vorschlag": titel,
                        "scope": {"material": ["PTFE"]},
                        "claims": ["PTFE ist chemisch sehr bestaendig."],
                    }
                )
            ],
            ingested_catalogs=captured,
        )
        r = client.post(
            "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
        )
        assert r.status_code == 200 and r.json()["ingested"] is True

    assert len(captured) == 2
    ids = {c.cards[0].id for c in captured}
    assert ids == {
        "FK-DRAFT-DOC-5"
    }  # same id both times despite the differently-phrased title


# ---------------------------------------------------------------------------
# sealai:status-draft auto-tagging (workflow visibility: which knowledge is ingested vs reviewed)
# ---------------------------------------------------------------------------


def test_successful_ingestion_auto_tags_the_document_status_draft(monkeypatch):
    tag_calls = []
    client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest",),
        ),
        llm_responses=[
            json.dumps(
                {
                    "titel_vorschlag": "PTFE",
                    "scope": {"material": ["PTFE"]},
                    "claims": ["PTFE ist chemisch sehr bestaendig."],
                }
            )
        ],
        find_tag_id_result=15,
        tag_calls=tag_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200 and r.json()["ingested"] is True
    assert tag_calls == [
        ("5", 15)
    ]  # the document was tagged sealai:status-draft (id 15 here)


def test_tagging_failure_never_undoes_a_successful_ingestion(monkeypatch):
    client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest",),
        ),
        llm_responses=[
            json.dumps(
                {
                    "titel_vorschlag": "PTFE",
                    "scope": {"material": ["PTFE"]},
                    "claims": ["PTFE ist chemisch sehr bestaendig."],
                }
            )
        ],
        add_tag_error=RuntimeError("paperless unreachable"),
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert (
        body["ingested"] is True
    )  # the Qdrant ingestion already succeeded — tagging is best-effort
    assert body["card_id"] == "FK-DRAFT-DOC-5"
