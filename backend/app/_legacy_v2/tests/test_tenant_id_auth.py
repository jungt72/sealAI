"""Tests for tenant_id extraction in Auth (Sprint 8).

Coverage:
  - JWT with tenant_id claim → RequestUser.tenant_id populated
  - Custom AUTH_TENANT_ID_CLAIM env var → uses that claim
  - JWT without tenant_id claim → None
  - RequestUser is frozen dataclass with tenant_id field
  - SealAIState accepts tenant_id field
"""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import HumanMessage

from app.services.auth.dependencies import RequestUser, _resolve_tenant_id
from app._legacy_v2.state.sealai_state import SealAIState


# ---------------------------------------------------------------------------
# _resolve_tenant_id unit tests
# ---------------------------------------------------------------------------


class TestResolveTenantId:
    def test_tenant_id_claim_present(self):
        payload = {"sub": "user-1", "tenant_id": "acme"}
        assert _resolve_tenant_id(payload) == "acme"

    def test_tenant_id_claim_missing_returns_none(self, monkeypatch):
        monkeypatch.delenv("AUTH_TENANT_ID_CLAIM", raising=False)
        payload = {"sub": "user-1"}
        assert _resolve_tenant_id(payload) is None

    def test_custom_claim_via_env_var(self, monkeypatch):
        monkeypatch.setenv("AUTH_TENANT_ID_CLAIM", "organization")
        payload = {"sub": "user-1", "organization": "globex"}
        assert _resolve_tenant_id(payload) == "globex"

    def test_empty_string_claim_returns_none(self, monkeypatch):
        monkeypatch.delenv("AUTH_TENANT_ID_CLAIM", raising=False)
        payload = {"sub": "user-1", "tenant_id": ""}
        assert _resolve_tenant_id(payload) is None

    def test_whitespace_only_claim_returns_none(self, monkeypatch):
        monkeypatch.delenv("AUTH_TENANT_ID_CLAIM", raising=False)
        payload = {"sub": "user-1", "tenant_id": "   "}
        assert _resolve_tenant_id(payload) is None

    def test_numeric_claim_value_coerced_to_str(self, monkeypatch):
        monkeypatch.delenv("AUTH_TENANT_ID_CLAIM", raising=False)
        payload = {"sub": "user-1", "tenant_id": 42}
        result = _resolve_tenant_id(payload)
        assert result == "42"


# ---------------------------------------------------------------------------
# RequestUser dataclass tests
# ---------------------------------------------------------------------------


class TestRequestUserTenantId:
    def test_request_user_has_tenant_id_field(self):
        user = RequestUser(
            user_id="u1",
            username="alice",
            sub="u1",
            roles=[],
            scopes=[],
            tenant_id="my-tenant",
        )
        assert user.tenant_id == "my-tenant"

    def test_request_user_tenant_id_defaults_to_none(self):
        user = RequestUser(
            user_id="u1",
            username="alice",
            sub="u1",
            roles=[],
            scopes=[],
        )
        assert user.tenant_id is None

    def test_request_user_is_frozen(self):
        user = RequestUser(
            user_id="u1",
            username="alice",
            sub="u1",
            roles=[],
            tenant_id="t1",
        )
        with pytest.raises((AttributeError, TypeError)):
            user.tenant_id = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SealAIState tenant_id field
# ---------------------------------------------------------------------------


class TestSealAIStateTenantId:
    def test_state_accepts_tenant_id(self):
        state = SealAIState(
            conversation={"messages": [HumanMessage(content="hello")]},
            tenant_id="test-corp",
        )
        assert state.system.tenant_id == "test-corp"

    def test_state_tenant_id_defaults_to_none(self):
        state = SealAIState(conversation={"messages": [HumanMessage(content="hello")]})
        assert state.system.tenant_id is None

    def test_state_tenant_id_is_in_model_fields(self):
        system_fields = SealAIState.model_fields["system"].annotation.model_fields
        assert "tenant_id" in system_fields
