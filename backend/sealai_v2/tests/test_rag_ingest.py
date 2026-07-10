"""POST /internal/rag/ingest — the Paperless auto-ingestion webhook. Proves: a wrong/missing token is
    refused (401), an untagged document is a no-op, an empty document is a no-op but tagged
    sealai:status-failed, a successful extraction lands EXACTLY ONE draft card in the Postgres
    ledger and queues its Qdrant projection (never
reviewed — doctrine), the endpoint RETRIES a failed extraction attempt (the real 2026-07-01
incident: attempt 1 returned zero claims, a manual retry succeeded — this is now automatic), and
every terminal failure is tagged sealai:status-failed so a silent drop is visible in Paperless."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from sealai_v2.api.main import app
from sealai_v2.api.routes import rag_ingest
from sealai_v2.knowledge.ledger import LedgerWriteResult
from sealai_v2.knowledge.paperless_client import PaperlessConfigError
from sealai_v2.tests._fakes import ScriptedFakeLlmClient

_TOKEN = "test-webhook-token"
_EMPTY_CLAIMS = json.dumps({"claims": [], "scope": {}, "titel_vorschlag": "x"})


def _valid_claims(text: str = "PTFE ist chemisch sehr bestaendig.") -> str:
    return json.dumps(
        {
            "titel_vorschlag": "PTFE",
            "scope": {"material": ["PTFE"]},
            "claims": [text],
        }
    )


def _client(
    monkeypatch,
    *,
    fetch_result=None,
    fetch_error=None,
    llm_responses=None,
    ingested_catalogs=None,
    ledger_error=None,
    find_tag_id_result=15,
    add_calls=None,
    add_error=None,
    remove_calls=None,
    remove_error=None,
):
    monkeypatch.setenv("PAPERLESS_WEBHOOK_TOKEN", _TOKEN)
    monkeypatch.setattr(rag_ingest, "find_tag_id", lambda name: find_tag_id_result)

    def _fake_add(doc_id, tag_id):
        if add_error is not None:
            raise add_error
        if add_calls is not None:
            add_calls.append((doc_id, tag_id))

    def _fake_remove(doc_id, tag_id):
        if remove_error is not None:
            raise remove_error
        if remove_calls is not None:
            remove_calls.append((doc_id, tag_id))

    monkeypatch.setattr(rag_ingest, "add_tag_to_document", _fake_add)
    monkeypatch.setattr(rag_ingest, "remove_tag_from_document", _fake_remove)

    def _fake_fetch(doc_id):
        if fetch_error is not None:
            raise fetch_error
        return fetch_result

    monkeypatch.setattr(rag_ingest, "fetch_document_text_and_tags", _fake_fetch)

    llm_client = ScriptedFakeLlmClient(llm_responses or [])
    monkeypatch.setattr(
        rag_ingest,
        "_build_extractor",
        lambda settings: rag_ingest.FachkarteExtractor(
            llm_client,
            rag_ingest.FachkarteExtractPromptAssembler(),
            rag_ingest.ModelConfig("fake-helper"),
        ),
    )

    captured = ingested_catalogs if ingested_catalogs is not None else []

    class _FakeLedger:
        def replace_catalog(self, document, catalog, *, now, actor):
            if ledger_error is not None:
                raise ledger_error
            captured.append(catalog)
            claims = sum(len(c.claims) for c in catalog.cards)
            return LedgerWriteResult(
                document_id=f"ledger-{document.source_id}",
                document_version=1,
                claims_total=claims,
                claims_created=claims,
                claims_updated=0,
                claims_retired=0,
                outbox_enqueued=claims,
            )

    monkeypatch.setattr(
        rag_ingest, "build_knowledge_ledger", lambda _settings: _FakeLedger()
    )
    return TestClient(app), llm_client


def _headers(token: str = _TOKEN) -> dict:
    return {"X-SeaLAI-Webhook-Token": token}


# ---------------------------------------------------------------------------
# auth
# ---------------------------------------------------------------------------


def test_wrong_token_is_refused():
    client = TestClient(app)
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers("nope")
    )
    assert r.status_code == 401


def test_missing_token_is_refused_even_if_env_unset(monkeypatch):
    monkeypatch.delenv("PAPERLESS_WEBHOOK_TOKEN", raising=False)
    client = TestClient(app)
    r = client.post("/internal/rag/ingest", json={"document_id": "5"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# no-op paths (not failures — no status-failed tag)
# ---------------------------------------------------------------------------


def test_untagged_document_is_a_noop_no_status_tag(monkeypatch):
    add_calls = []
    client, _ = _client(
        monkeypatch,
        fetch_result=("some document text", "paperless#5:Doc", ("some:other:tag",)),
        add_calls=add_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is False and "sealai:ingest" in body["reason"]
    assert (
        add_calls == []
    )  # a document that was never meant for sealingAI is never tagged


# ---------------------------------------------------------------------------
# failures — tagged sealai:status-failed, no silent drop
# ---------------------------------------------------------------------------


def test_empty_document_is_a_noop_but_tagged_failed(monkeypatch):
    add_calls = []
    client, _ = _client(
        monkeypatch,
        fetch_result=("   ", "paperless#5:Doc", ("sealai:ingest",)),
        add_calls=add_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200 and r.json() == {
        "ingested": False,
        "reason": "empty document",
    }
    assert add_calls == [("5", 15)]  # tagged sealai:status-failed (id 15 in this test)


def test_fetch_failure_retries_then_fails_safe_tagged_failed(monkeypatch):
    add_calls = []
    client, _ = _client(
        monkeypatch, fetch_error=RuntimeError("boom"), add_calls=add_calls
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {"ingested": False, "reason": "fetch_failed", "attempts": 3}
    assert add_calls == [("5", 15)]


def test_fetch_config_error_fails_closed_without_retry_or_tag(monkeypatch):
    # PaperlessConfigError means PAPERLESS_URL/TOKEN aren't set AT ALL — retrying or trying to
    # tag-back (which needs the SAME config) cannot possibly help; fail closed immediately.
    add_calls = []
    client, _ = _client(
        monkeypatch,
        fetch_error=PaperlessConfigError("no config"),
        add_calls=add_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200 and r.json() == {
        "ingested": False,
        "reason": "paperless_not_configured",
    }
    assert add_calls == []


def test_no_claims_after_all_attempts_fails_tagged_failed(monkeypatch):
    add_calls = []
    client, llm_client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig.",
            "paperless#5:PTFE",
            ("sealai:ingest",),
        ),
        llm_responses=[_EMPTY_CLAIMS, _EMPTY_CLAIMS, _EMPTY_CLAIMS],
        add_calls=add_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is False
    assert "no doc-grounded claims" in body["reason"]
    assert body["attempts"] == 3
    assert (
        len(llm_client.calls) == 3
    )  # every attempt actually ran the LLM, none skipped
    assert add_calls == [("5", 15)]


def test_llm_exception_retries_then_fails_safe_tagged_failed(monkeypatch):
    """Regression: the ORIGINAL live bug (Mistral 429) propagated as an unhandled exception -> 500.
    Now: caught per-attempt, retried, and only tagged failed once ALL attempts are exhausted."""
    add_calls = []
    client, llm_client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig.",
            "paperless#5:PTFE",
            ("sealai:ingest",),
        ),
        llm_responses=[],  # exhausted script -> ScriptedFakeLlmClient raises on every call
        add_calls=add_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is False
    assert "extraction_error" in body["reason"]
    assert body["attempts"] == 3
    assert add_calls == [("5", 15)]


def test_ledger_commit_error_retries_then_fails_safe_tagged_failed(monkeypatch):
    add_calls = []
    client, llm_client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest",),
        ),
        llm_responses=[_valid_claims(), _valid_claims(), _valid_claims()],
        ledger_error=RuntimeError("postgres unavailable"),
        add_calls=add_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is False
    assert "knowledge_ledger_commit_failed" in body["reason"]
    assert body["attempts"] == 3
    assert len(llm_client.calls) == 3  # retried the full extraction+commit attempt
    assert add_calls == [("5", 15)]


# ---------------------------------------------------------------------------
# THE regression: fails once, recovers on retry — the actual 2026-07-01 incident, now automatic
# ---------------------------------------------------------------------------


def test_recovers_automatically_after_a_failed_first_attempt(monkeypatch):
    captured = []
    add_calls = []
    client, llm_client = _client(
        monkeypatch,
        fetch_result=(
            "PTFE GF25: Zugfestigkeit 15-19 N/mm2 (DIN 53455).",
            "paperless#18:sealingAI_wissenskarte_ptfe_gf25",
            ("sealai:ingest",),
        ),
        llm_responses=[
            _EMPTY_CLAIMS,
            _valid_claims("Die Zugfestigkeit betraegt 15 bis 19 N/mm2."),
        ],
        ingested_catalogs=captured,
        add_calls=add_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "18"}, headers=_headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ingested"] is True
    assert body["card_id"] == "FK-DRAFT-DOC-18"
    assert (
        len(llm_client.calls) == 2
    )  # attempt 1 (empty) + attempt 2 (succeeded) — no 3rd call
    assert (
        len(captured) == 1
    )  # exactly one ledger commit, from the successful attempt only
    # success tags status-draft — NOT status-failed (recovered before exhausting retries)
    assert add_calls == [("18", 15)]


def test_success_after_a_prior_failed_document_clears_the_failed_tag(monkeypatch):
    remove_calls = []
    client, _ = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest",),
        ),
        llm_responses=[_valid_claims()],
        remove_calls=remove_calls,
    )
    r = client.post(
        "/internal/rag/ingest", json={"document_id": "5"}, headers=_headers()
    )
    assert r.status_code == 200 and r.json()["ingested"] is True
    assert remove_calls == [("5", 15)]  # sealai:status-failed removed on this success


# ---------------------------------------------------------------------------
# successful ingestion — first-attempt success unchanged from before
# ---------------------------------------------------------------------------


def test_successful_ingestion_lands_exactly_one_draft_card(monkeypatch):
    captured = []
    client, _ = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig. PTFE zeigt ausgeprägten Kaltfluss.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest", "sealai:source-deep-research"),
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
    assert body["index_status"] == "queued" and body["points_queued"] == 2

    # exactly ONE card was handed to the ledger — doctrine: draft-only, never reviewed
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
        client, _ = _client(
            monkeypatch,
            fetch_result=fetch,
            llm_responses=[_valid_claims()],
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


def test_tagging_failure_never_undoes_a_successful_ingestion(monkeypatch):
    client, _ = _client(
        monkeypatch,
        fetch_result=(
            "PTFE ist chemisch sehr bestaendig.",
            "paperless#5:PTFE_Research",
            ("sealai:ingest",),
        ),
        llm_responses=[_valid_claims()],
        add_error=RuntimeError("paperless unreachable"),
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
