import os
import sys
from pathlib import Path
import types
import pytest

# Provide safe defaults so settings can initialize during test collection.
_TEST_ENV_DEFAULTS = {
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_HOST": "localhost",
    "POSTGRES_PORT": "5432",
    "POSTGRES_DB": "test",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "POSTGRES_SYNC_URL": "postgresql+psycopg2://test:test@localhost:5432/test",
    "OPENAI_API_KEY": "test-key",
    "QDRANT_URL": "http://localhost",
    "QDRANT_COLLECTION": "test",
    "REDIS_URL": "redis://localhost:6379/0",
    "NEXTAUTH_URL": "http://localhost",
    "NEXTAUTH_SECRET": "secret",
    "KEYCLOAK_ISSUER": "http://localhost/realms/test",
    "KEYCLOAK_JWKS_URL": "http://localhost/realms/test/protocol/openid-connect/certs",
    "KEYCLOAK_CLIENT_ID": "test-client",
    "KEYCLOAK_CLIENT_SECRET": "secret",
    "KEYCLOAK_EXPECTED_AZP": "test",
}
for key, value in _TEST_ENV_DEFAULTS.items():
    os.environ.setdefault(key, value)
os.environ.setdefault("ANYIO_BACKEND", "asyncio")

# Ensure backend/ is on sys.path so "from app.main import app" works
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# FastAPI TestClient
from fastapi.testclient import TestClient

@pytest.fixture(scope="session")
def fastapi_app():
    """
    Importiert die FastAPI-App aus backend/app/main.py
    """
    try:
        from app.main import app  # type: ignore
    except Exception as e:
        pytest.skip(f"Konnte app nicht importieren (app.main:app): {e}")
    return app


@pytest.fixture()
def app(fastapi_app):
    return fastapi_app

@pytest.fixture()
def client(fastapi_app):
    return TestClient(fastapi_app)

@pytest.fixture()
def mock_run_stream(monkeypatch):
    """
    Mockt app.langgraph.compile.run_langgraph_stream so, dass keine externen
    Abhängigkeiten (Redis/Qdrant) benötigt werden.
    """
    try:
        import app.langgraph.compile as compile_mod  # type: ignore
    except Exception as e:
        pytest.skip(f"compile-Modul nicht importierbar: {e}")

    async def _fake_run(request):
        # extrahiere Body falls möglich
        try:
            body = await request.json()
        except Exception:
            body = None
        # packe Pfad (zur Verifikation welcher Endpoint aufgerufen wurde)
        path = getattr(request, "url", None)
        if path:
            path = str(path)
        return {"ok": True, "echo": body, "path": path}

    monkeypatch.setattr(compile_mod, "run_langgraph_stream", _fake_run, raising=True)
    return _fake_run
