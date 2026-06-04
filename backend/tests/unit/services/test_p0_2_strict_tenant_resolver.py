"""P0-2: strict request-scoped tenant resolver (no silent tenant collapse).

Red-before-green contract for removing the `tenant_id` fallbacks. The single
source of truth is `app.services.auth.dependencies.require_tenant_id`:

* a missing/empty tenant claim is a hard 401 (never "default", never user_id);
* a present claim is returned verbatim (stripped) and routes behave unchanged.

The shared-knowledge path (RAG_SHARED_TENANT_ID, e.g. the Paperless webhook /
no-case knowledge) intentionally falls back to the shared tenant and must NOT
be affected — proven by the invariant test at the bottom.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.auth.dependencies import RequestUser


def _user(*, tenant=None, user_id="user-123") -> RequestUser:
    return RequestUser(
        user_id=user_id,
        username="tester",
        sub="sub-123",
        roles=[],
        scopes=["openid"],
        tenant_id=tenant,
    )


# --------------------------------------------------------------------------- #
# Central resolver
# --------------------------------------------------------------------------- #
def test_require_tenant_id_returns_present_claim():
    from app.services.auth.dependencies import require_tenant_id

    assert require_tenant_id(_user(tenant="sealai")) == "sealai"
    assert require_tenant_id(_user(tenant="  sealai  ")) == "sealai"


@pytest.mark.parametrize("tenant", [None, "", "   "])
def test_require_tenant_id_missing_claim_is_401(tenant):
    from app.services.auth.dependencies import require_tenant_id

    with pytest.raises(HTTPException) as exc:
        require_tenant_id(_user(tenant=tenant, user_id="user-9"))
    assert exc.value.status_code == 401


# --------------------------------------------------------------------------- #
# deps.py — canonical case scope (RED: today returns "default")
# --------------------------------------------------------------------------- #
def test_canonical_scope_requires_claim():
    from app.agent.api.deps import _canonical_scope

    with pytest.raises(HTTPException) as exc:
        _canonical_scope(_user(tenant=None, user_id="user-9"), case_id="c1")
    assert exc.value.status_code == 401


def test_canonical_scope_uses_claim_not_default():
    from app.agent.api.deps import _canonical_scope

    tenant_id, owner_id, key = _canonical_scope(
        _user(tenant="sealai", user_id="user-9"), case_id="c1"
    )
    assert tenant_id == "sealai"
    assert key.startswith("sealai:")


# --------------------------------------------------------------------------- #
# rfq.py — _request_tenant_id (RED: today returns user_id)
# --------------------------------------------------------------------------- #
def test_rfq_request_tenant_requires_claim():
    from app.api.v1.endpoints.rfq import _request_tenant_id

    with pytest.raises(HTTPException) as exc:
        _request_tenant_id(_user(tenant=None, user_id="user-9"))
    assert exc.value.status_code == 401


def test_rfq_request_tenant_returns_claim():
    from app.api.v1.endpoints.rfq import _request_tenant_id

    assert _request_tenant_id(_user(tenant="sealai", user_id="user-9")) == "sealai"


# --------------------------------------------------------------------------- #
# memory.py — _ltm_tenant_id (RED: today returns "default")
# --------------------------------------------------------------------------- #
def test_ltm_tenant_requires_claim():
    from app.api.v1.endpoints.memory import _ltm_tenant_id

    with pytest.raises(HTTPException) as exc:
        _ltm_tenant_id(_user(tenant=None, user_id="user-9"))
    assert exc.value.status_code == 401


def test_ltm_tenant_returns_claim():
    from app.api.v1.endpoints.memory import _ltm_tenant_id

    assert _ltm_tenant_id(_user(tenant="sealai")) == "sealai"


# --------------------------------------------------------------------------- #
# rag.py — private RAG _request_tenant_id (RED: today returns user_id)
# --------------------------------------------------------------------------- #
def test_rag_request_tenant_requires_claim():
    from app.api.v1.endpoints.rag import _request_tenant_id as rag_request_tenant_id

    with pytest.raises(HTTPException) as exc:
        rag_request_tenant_id(_user(tenant=None, user_id="user-9"))
    assert exc.value.status_code == 401


def test_rag_request_tenant_returns_claim():
    from app.api.v1.endpoints.rag import _request_tenant_id as rag_request_tenant_id

    assert rag_request_tenant_id(_user(tenant="sealai", user_id="user-9")) == "sealai"


# --------------------------------------------------------------------------- #
# INVARIANT: shared-knowledge path stays on RAG_SHARED_TENANT_ID — never 401
# --------------------------------------------------------------------------- #
def test_shared_knowledge_path_untouched_by_strict_resolver():
    from app.agent.api.knowledge_override import _rag_scope_from_user
    from app.services.rag.constants import RAG_SHARED_TENANT_ID

    # No tenant claim → shared tenant, NOT a 401 (knowledge dialogue must work).
    tenant_id, user_id = _rag_scope_from_user(_user(tenant=None, user_id="user-9"))
    assert tenant_id == RAG_SHARED_TENANT_ID
    # A real claim still flows through unchanged.
    tenant_id2, _ = _rag_scope_from_user(_user(tenant="sealai", user_id="user-9"))
    assert tenant_id2 == "sealai"
