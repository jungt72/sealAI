import os

import pytest


def _truthy(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


RUN_INTEGRATION = _truthy(os.getenv("RUN_INTEGRATION"))


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_INTEGRATION=1 to run compose wiring tests.")
def test_compose_backend_health_200() -> None:
    import httpx

    base = (os.getenv("BACKEND_BASE_URL") or "http://localhost:8000").rstrip("/")
    r = httpx.get(f"{base}/api/v1/langgraph/health", timeout=5.0)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_INTEGRATION=1 to run compose wiring tests.")
def test_compose_backend_patch_unauth_401_not_500() -> None:
    import httpx

    base = (os.getenv("BACKEND_BASE_URL") or "http://localhost:8000").rstrip("/")
    r = httpx.post(
        f"{base}/api/v1/langgraph/parameters/patch",
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
        timeout=5.0,
    )
    assert r.status_code == 401


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_INTEGRATION=1 to run compose wiring tests.")
def test_compose_nginx_routes_langgraph_health_200() -> None:
    import httpx

    base = (os.getenv("NGINX_BASE_URL") or "https://localhost").rstrip("/")
    # Local nginx often runs with a self-signed/LE cert; allow opt-out.
    verify = not _truthy(os.getenv("NGINX_INSECURE_SKIP_VERIFY") or "1")
    r = httpx.get(f"{base}/api/v1/langgraph/health", timeout=5.0, verify=verify)
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


@pytest.mark.skipif(not RUN_INTEGRATION, reason="Set RUN_INTEGRATION=1 to run compose wiring tests.")
def test_compose_nginx_backend_forwarding_keeps_401() -> None:
    import httpx

    base = (os.getenv("NGINX_BASE_URL") or "https://localhost").rstrip("/")
    verify = not _truthy(os.getenv("NGINX_INSECURE_SKIP_VERIFY") or "1")
    r = httpx.post(
        f"{base}/api/v1/langgraph/parameters/patch",
        json={"chat_id": "default", "parameters": {"medium": "oil"}},
        timeout=5.0,
        verify=verify,
    )
    assert r.status_code == 401

