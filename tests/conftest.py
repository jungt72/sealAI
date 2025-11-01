import os
import sys
from pathlib import Path
import types
import pytest

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
