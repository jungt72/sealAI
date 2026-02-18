import os
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
STUB_PATH = ROOT.parent / "langchain_core_stub"

# Ensure backend package root is importable in tests
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Optional stub path used in this repo
if STUB_PATH.exists() and str(STUB_PATH) not in sys.path:
    sys.path.insert(0, str(STUB_PATH))


# ---------------------------------------------------------------------------
# Optional deps: provide minimal stubs so test collection is hermetic
# ---------------------------------------------------------------------------

if "asyncpg" not in sys.modules:
    asyncpg_stub = types.ModuleType("asyncpg")

    async def _stub_connect(*_args, **_kwargs):
        raise RuntimeError("asyncpg stub (tests)")

    asyncpg_stub.connect = _stub_connect
    asyncpg_stub.create_pool = _stub_connect
    sys.modules["asyncpg"] = asyncpg_stub

# Some FastAPI / Starlette stacks import multipart helpers (python-multipart)
if "multipart" not in sys.modules:
    multipart_stub = types.ModuleType("multipart")
    multipart_module = types.ModuleType("multipart.multipart")

    def _parse_options_header(_value):
        return {}

    multipart_module.parse_options_header = _parse_options_header
    multipart_stub.__version__ = "0.0.13"
    sys.modules["multipart"] = multipart_stub
    sys.modules["multipart.multipart"] = multipart_module

if "python_multipart" not in sys.modules:
    python_multipart = types.ModuleType("python_multipart")
    python_multipart.__version__ = "0.0.13"
    sys.modules["python_multipart"] = python_multipart


# ---------------------------------------------------------------------------
# Global test env defaults (hermetic/offline)
# ---------------------------------------------------------------------------

# NextAuth / Keycloak envs (tests should never require real IdP)
os.environ.setdefault("nextauth_url", "http://localhost:3000")
os.environ.setdefault("nextauth_secret", "dummy")
os.environ.setdefault("keycloak_issuer", "http://localhost/realms/test")
os.environ.setdefault("keycloak_client_id", "dummy")
os.environ.setdefault("keycloak_client_secret", "dummy")

# Keep LLM usage offline/deterministic by default
os.environ.setdefault("OPENAI_API_KEY", "test")

# LangGraph v2: keep tests hermetic even when redis checkpointer package is absent.
# IMPORTANT: Do NOT set LANGGRAPH_V2_CHECKPOINTER_BACKEND here, because it overrides
# CHECKPOINTER_BACKEND in code and breaks tests that intentionally set redis.
os.environ.setdefault("LANGGRAPH_V2_ALLOW_MEMORY_FALLBACK", "1")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _clear_langgraph_v2_graph_cache() -> None:
    """
    Ensure graph compilation picks up env defaults per test.
    This avoids cross-test contamination from cached graphs/checkpointers.
    """
    try:
        from app.langgraph_v2 import sealai_graph_v2

        sealai_graph_v2._GRAPH_CACHE = None
        yield
        sealai_graph_v2._GRAPH_CACHE = None
    except Exception:
        # If module import fails for a specific unit test collection scenario,
        # do not make the entire test suite error out here.
        yield
