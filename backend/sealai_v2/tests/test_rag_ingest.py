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
):
    monkeypatch.setenv("PAPERLESS_WEBHOOK_TOKEN", _TOKEN)

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
    assert body["ingested"] is False and "rag:enabled" in body["reason"]


def test_empty_document_is_a_noop(monkeypatch):
    client = _client(
        monkeypatch, fetch_result=("   ", "paperless#5:Doc", ("rag:enabled",))
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
            ("rag:enabled",),
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


def test_successful_ingestion_lands_exactly_one_draft_card(monkeypatch):
    captured = []
    client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr beständig. PTFE zeigt ausgeprägten Kaltfluss.",
            "paperless#5:PTFE_Research",
            ("rag:enabled", "sealai:rag"),
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
    assert card.id.startswith("FK-DRAFT-")
    assert card.provenance == ("paperless-draft:paperless#5:PTFE_Research",)
