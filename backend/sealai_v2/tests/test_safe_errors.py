"""Tests for the client-visible V2 exception boundary."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sealai_v2.api.errors import install_safe_exception_mapper, safe_http_error


def test_safe_http_error_exposes_only_a_fixed_code() -> None:
    error = safe_http_error(409, "memory_transition_invalid")
    assert error.status_code == 409
    assert error.detail == {"code": "memory_transition_invalid"}


def test_safe_http_error_rejects_dynamic_public_text() -> None:
    with pytest.raises(ValueError):
        safe_http_error(400, "provider said: secret payload")


def test_unhandled_exception_does_not_expose_exception_text() -> None:
    canary = "".join(("s", "k", "-canary-unhandled-0123456789abcdef"))
    app = FastAPI()
    install_safe_exception_mapper(app)

    @app.get("/explode")
    def explode() -> None:
        raise RuntimeError(canary)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/explode")
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "internal_error"}}
    assert canary not in response.text


def test_v2_routes_never_map_exception_text_into_http_detail() -> None:
    routes = Path(__file__).resolve().parents[1] / "api" / "routes"
    for path in routes.glob("*.py"):
        assert "detail=str(" not in path.read_text(encoding="utf-8"), path.name
