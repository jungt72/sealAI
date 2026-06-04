from __future__ import annotations

import os

import pytest
from fastapi import HTTPException

os.environ.setdefault("postgres_user", "test")
os.environ.setdefault("postgres_password", "test")
os.environ.setdefault("postgres_host", "localhost")
os.environ.setdefault("postgres_port", "5432")
os.environ.setdefault("postgres_db", "testdb")
os.environ["database_url"] = "postgresql+asyncpg://test:test@localhost:5432/testdb"
os.environ["DATABASE_URL"] = "postgresql+asyncpg://test:test@localhost:5432/testdb"
os.environ["POSTGRES_SYNC_URL"] = "postgresql://test:test@localhost:5432/testdb"
os.environ.setdefault("openai_api_key", "sk-test")
os.environ.setdefault("qdrant_url", "http://localhost:6333")
os.environ.setdefault("redis_url", "redis://localhost:6379/0")
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "test-secret")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_jwks_url", "http://localhost/.well-known/jwks.json")
os.environ.setdefault("keycloak_client_id", "test-client")
os.environ.setdefault("keycloak_client_secret", "test-secret")
os.environ.setdefault("keycloak_expected_azp", "test-client")

from app.common.redaction import safe_error_message
from app.services.rag.utils import validate_upload_signature


def test_backend_error_messages_redact_internal_paths() -> None:
    reason = safe_error_message(
        RuntimeError("failed for /app/data/uploads/tenant-1/doc-1/original.pdf")
    )

    assert "/app/data/uploads" not in reason
    assert "[REDACTED_PATH]" in reason


def test_upload_signature_accepts_pdf_magic() -> None:
    content_type = validate_upload_signature(
        extension=".pdf",
        content_type="application/pdf",
        sample=b"%PDF-1.7\nbody",
    )

    assert content_type == "application/pdf"


def test_upload_signature_rejects_pdf_spoofing() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_upload_signature(
            extension=".pdf",
            content_type="application/pdf",
            sample=b"not a pdf",
        )

    assert exc_info.value.status_code == 415
    assert exc_info.value.detail["error"] == "upload_signature_mismatch"


def test_upload_signature_rejects_binary_text_upload() -> None:
    with pytest.raises(HTTPException) as exc_info:
        validate_upload_signature(
            extension=".txt",
            content_type="text/plain",
            sample=b"hello\x00world",
        )

    assert exc_info.value.status_code == 415
    assert exc_info.value.detail["error"] == "upload_signature_mismatch"
