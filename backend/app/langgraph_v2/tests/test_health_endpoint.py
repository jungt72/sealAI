from fastapi import FastAPI
import httpx
import pytest

from app.api.v1.endpoints.langgraph_health import router as langgraph_health_router


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_langgraph_health_endpoint_is_public() -> None:
    app = FastAPI()
    app.include_router(langgraph_health_router, prefix="/api/v1/langgraph")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/langgraph/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "graph": "v2"}
