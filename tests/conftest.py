import os
import sys
from pathlib import Path
import types
import importlib.util
import inspect
import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, SystemMessage

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
os.environ.setdefault("LANGGRAPH_USE_FAKE_LLM", "1")

# Optional test deps (keep skips explicit and warning-free).
_HAS_PYTEST_ASYNCIO = importlib.util.find_spec("pytest_asyncio") is not None
_HAS_ASYNCPG = importlib.util.find_spec("asyncpg") is not None


def pytest_addoption(parser):
    if not _HAS_PYTEST_ASYNCIO:
        parser.addini("asyncio_mode", "asyncio mode for pytest-asyncio", default="auto")


def pytest_collection_modifyitems(config, items):
    if _HAS_PYTEST_ASYNCIO:
        return
    for item in items:
        func = getattr(item, "function", None)
        if func and inspect.iscoroutinefunction(func):
            item.add_marker(
                pytest.mark.skip(
                    reason="pytest-asyncio not installed; install backend/requirements-dev.txt"
                )
            )

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
    if not _HAS_ASYNCPG:
        pytest.skip("asyncpg not installed; install backend/requirements-lock.txt or backend/requirements-dev.txt")
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


@pytest.fixture(autouse=True)
def fake_chat_openai(monkeypatch):
    import langchain_openai
    from app.langgraph_v2.utils import llm_factory

    class FakeChatOpenAI:
        def __init__(self, *args, **kwargs):
            self.streaming = bool(kwargs.get("streaming"))

        def _response_text(self, messages):
            system = ""
            prompt = ""
            for msg in messages or []:
                if isinstance(msg, SystemMessage):
                    system = msg.content
                elif isinstance(msg, HumanMessage):
                    prompt = msg.content
            return llm_factory._run_fake_llm(model="fake", prompt=prompt, system=system)

        def invoke(self, messages, **_kwargs):
            return AIMessage(content=self._response_text(messages))

        async def ainvoke(self, messages, **_kwargs):
            return AIMessage(content=self._response_text(messages))

        def stream(self, messages, **_kwargs):
            text = self._response_text(messages)
            for part in llm_factory._fake_stream_parts(text):
                yield AIMessageChunk(content=part)

        async def astream(self, messages, **_kwargs):
            text = self._response_text(messages)
            for part in llm_factory._fake_stream_parts(text):
                yield AIMessageChunk(content=part)

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChatOpenAI)
    monkeypatch.setattr(llm_factory, "ChatOpenAI", FakeChatOpenAI)
    llm_factory._get_chat_model.cache_clear()
    llm_factory._get_streaming_chat_model.cache_clear()
