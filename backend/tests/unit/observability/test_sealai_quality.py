from __future__ import annotations

from dataclasses import dataclass

from app.observability.sealai_quality import (
    build_quality_metadata,
    evaluator_catalog,
    identity_trace_metadata,
    redact_trace_metadata,
    redact_trace_value,
    sanitize_trace_inputs,
    stable_trace_hash,
)


@dataclass(frozen=True)
class _User:
    user_id: str
    sub: str
    tenant_id: str


@dataclass(frozen=True)
class _Request:
    session_id: str
    message: str


def test_identity_metadata_hashes_raw_ids(monkeypatch) -> None:
    monkeypatch.setenv("SEALAI_TRACE_HASH_SALT", "unit-test-salt")

    metadata = identity_trace_metadata(
        request=_Request(session_id="session-123", message="raw user text"),
        current_user=_User(user_id="user-123", sub="sub-123", tenant_id="tenant-123"),
        case_id="case-123",
    )

    rendered = str(metadata)
    assert metadata["tenant_metadata_present"] is True
    assert metadata["user_metadata_present"] is True
    assert metadata["case_metadata_present"] is True
    assert "tenant-123" not in rendered
    assert "user-123" not in rendered
    assert "session-123" not in rendered
    assert "case-123" not in rendered
    assert metadata["tenant_id_hash"] == stable_trace_hash("tenant-123")


def test_sanitize_trace_inputs_redacts_content_and_secrets(monkeypatch) -> None:
    monkeypatch.setenv("SEALAI_TRACE_HASH_SALT", "unit-test-salt")

    safe = sanitize_trace_inputs(
        {
            "request": {
                "message": "Bitte Thomas Mueller unter thomas@example.com mit sk-secret1234567890 anrufen.",
                "session_id": "session-456",
            },
            "headers": {"authorization": "Bearer abc.def.ghi"},
            "temperature": 80,
        }
    )

    rendered = str(safe)
    assert "thomas@example.com" not in rendered
    assert "sk-secret" not in rendered
    assert "abc.def.ghi" not in rendered
    assert "session-456" not in rendered
    assert safe["request"]["message"]["redacted"] is True
    assert safe["temperature"] == 80


def test_redact_trace_value_keeps_trace_hashes_stable(monkeypatch) -> None:
    monkeypatch.setenv("SEALAI_TRACE_HASH_SALT", "unit-test-salt")
    first_hash = stable_trace_hash("session-789")

    safe = redact_trace_value(
        {
            "session_id_hash": first_hash,
            "thread_id": first_hash,
            "fallback_reason_hash": first_hash,
        }
    )

    assert safe["session_id_hash"] == first_hash
    assert safe["thread_id"] == first_hash
    assert safe["fallback_reason_hash"] == first_hash


def test_quality_metadata_preserves_v92_top_level_fields() -> None:
    values = {f"extra_{index}": index for index in range(40)}
    values.update(
        {
            "v92_present": True,
            "v92_engineering_status": "partial",
            "v92_dossier_status": "blocked",
            "medium_intelligence_status": "registry_grounded",
        }
    )

    safe = redact_trace_metadata(values)
    metadata = build_quality_metadata(component="governed_graph", **values)

    assert safe["v92_present"] is True
    assert safe["v92_engineering_status"] == "partial"
    assert safe["v92_dossier_status"] == "blocked"
    assert safe["medium_intelligence_status"] == "registry_grounded"
    assert "_truncated_items" not in safe
    assert metadata["v92_present"] is True
    assert metadata["v92_engineering_status"] == "partial"
    assert metadata["v92_dossier_status"] == "blocked"
    assert metadata["medium_intelligence_status"] == "registry_grounded"


def test_evaluator_catalog_is_review_only_v92_and_contains_core_checks() -> None:
    catalog = evaluator_catalog()
    names = {entry["name"] for entry in catalog}

    assert {
        "no_final_approval_claims",
        "rfq_boundary_guard",
        "asks_one_next_useful_question",
        "tenant_metadata_present",
        "rag_claim_level_respected",
    }.issubset(names)
    assert all(entry["auto_merge_allowed"] is False for entry in catalog)
    assert all(entry["engine_action_policy"] == "suggest_only_human_review_required" for entry in catalog)
