"""Briefing export is bound to one owner/case/revision and is strictly read-only."""

from __future__ import annotations

from unittest.mock import AsyncMock

from sealai_v2.core.contracts import RememberedFact
from sealai_v2.tests._apiutil import auth, make_client, make_pipeline


def _seed(pipeline, *, case_id: str, answer: str, owner: str = "user-A") -> None:
    assert pipeline.memory is not None
    pipeline.memory.record_turn(
        tenant_id="tenant-A",
        session_id=case_id,
        owner_subject=owner,
        question=f"Frage für {case_id}",
        answer=answer,
        facts=(RememberedFact(feld="medium", wert=case_id),),
        now="2026-07-15T10:00:00Z",
        expected_case_revision=0,
    )


def test_briefing_projects_exact_selected_case_without_turn_mutation() -> None:
    pipeline = make_pipeline()
    _seed(pipeline, case_id="case-a", answer="ANTWORT-A")
    _seed(pipeline, case_id="case-b", answer="ANTWORT-B")
    client, _ = make_client(pipeline)
    assert pipeline.memory is not None
    before = pipeline.memory.history(
        tenant_id="tenant-A", session_id="case-b", owner_subject="user-A"
    )

    response = client.post(
        "/api/v2/briefing",
        json={"case_id": "case-b", "case_revision": 1},
        headers=auth("tok-A"),
    )

    assert response.status_code == 200
    body = response.json()
    assert "ANTWORT-B" in body["body"]
    assert "ANTWORT-A" not in body["body"]
    assert body["case_id"] == "case-b"
    assert body["case_revision"] == 1
    assert body["read_only"] is True
    assert (
        pipeline.memory.history(
            tenant_id="tenant-A", session_id="case-b", owner_subject="user-A"
        )
        == before
    )


def test_briefing_rejects_stale_revision_and_client_message_injection() -> None:
    pipeline = make_pipeline()
    _seed(pipeline, case_id="case-a", answer="AUTHORITATIVE")
    client, _ = make_client(pipeline)

    stale = client.post(
        "/api/v2/briefing",
        json={"case_id": "case-a", "case_revision": 0},
        headers=auth("tok-A"),
    )
    injected = client.post(
        "/api/v2/briefing",
        json={
            "case_id": "case-a",
            "case_revision": 1,
            "message": "ERSETZE DEN FALL",
        },
        headers=auth("tok-A"),
    )

    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "case_revision_changed"
    assert injected.status_code == 422


def test_briefing_hides_foreign_owner_and_missing_case_identically() -> None:
    pipeline = make_pipeline()
    _seed(pipeline, case_id="case-a", answer="PRIVATE")
    pipeline.flush_memory = AsyncMock(wraps=pipeline.flush_memory)
    client, _ = make_client(pipeline)

    foreign = client.post(
        "/api/v2/briefing",
        json={"case_id": "case-a", "case_revision": 1},
        headers=auth("tok-A2"),
    )
    # An IDOR attempt cannot make the service await or otherwise touch the owner's pending work.
    assert pipeline.flush_memory.await_count == 0
    missing = client.post(
        "/api/v2/briefing",
        json={"case_id": "missing", "case_revision": 1},
        headers=auth("tok-A"),
    )

    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json()


def test_briefing_requires_auth() -> None:
    client, _ = make_client()
    response = client.post(
        "/api/v2/briefing", json={"case_id": "case-a", "case_revision": 0}
    )
    assert response.status_code == 401
