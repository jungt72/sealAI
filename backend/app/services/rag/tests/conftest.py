"""Conftest for app/services/rag/tests — sets dummy env vars for offline runs.

The app.services.rag package eagerly imports rag_orchestrator → config.
Without env vars, pydantic-settings raises ValidationError on import.
This conftest sets minimal dummy values before any collection happens.
"""

import os
import sys
import types

import pytest

_DUMMY_ENV = {
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "test",
    "DATABASE_URL": "postgresql://test:test@localhost/test",
    "POSTGRES_SYNC_URL": "postgresql://test:test@localhost/test",
    "OPENAI_API_KEY": "sk-test",
    "QDRANT_URL": "http://localhost:6333",
    "REDIS_URL": "redis://localhost:6379",
    "NEXTAUTH_URL": "http://localhost:3000",
    "NEXTAUTH_SECRET": "test-secret",
    "KEYCLOAK_ISSUER": "http://localhost:8080/realms/test",
    "KEYCLOAK_JWKS_URL": "http://localhost:8080/realms/test/protocol/openid-connect/certs",
    "KEYCLOAK_CLIENT_ID": "test-client",
    "KEYCLOAK_CLIENT_SECRET": "test-secret",
    "KEYCLOAK_EXPECTED_AZP": "test-client",
}

for _key, _val in _DUMMY_ENV.items():
    os.environ.setdefault(_key, _val)

if "pypdf" not in sys.modules:
    pypdf_stub = types.ModuleType("pypdf")

    class _StubPdfPage:
        def extract_text(self) -> str:
            return "Hello PDF"

    class _StubPdfReader:
        def __init__(self, *_args, **_kwargs) -> None:
            self.is_encrypted = False
            self.pages = [_StubPdfPage()]

        def decrypt(self, *_args, **_kwargs) -> int:
            return 1

    pypdf_stub.PdfReader = _StubPdfReader
    sys.modules["pypdf"] = pypdf_stub


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"

# Pre-import to ensure WorkingProfile is available in module namespace
# (sealai_state.py uses try/except import; running conftest first ensures
# env vars are set before that import chain fires).
from app.services.rag.state import WorkingProfile as _WP  # noqa: F401, E402
try:
    from app._legacy_v2.state.sealai_state import SealAIState as _SS  # noqa: F401, E402
except ModuleNotFoundError:
    _SS = None  # type: ignore[assignment]
