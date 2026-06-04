from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agent.api.routes.workspace import get_workspace_rfq_document
from app.api.v1.endpoints.state import get_rfq_document
from app.services.auth.dependencies import RequestUser


_TEST_USER = RequestUser(
    user_id="user-1",
    username="tester",
    sub="user-1",
    roles=[],
    scopes=[],
    tenant_id="tenant-1",
)


def _assert_legacy_document_disabled(response) -> None:
    assert response.status_code == 410
    assert response.headers["content-type"].startswith("application/json")
    body = json.loads(response.body)
    assert body["error"]["code"] == "rfq_document_legacy_disabled"
    assert "governed RFQ preview/export flow" in body["error"]["message"]
    assert body["dispatch_allowed"] is False
    assert body["external_contact_allowed"] is False
    assert body["export_requires_consent"] is True
    assert body["final_approval_claim_allowed"] is False
    assert (
        body["preview_service_boundary"] == "RfqPreviewService.create_preview_for_case"
    )
    assert "<html" not in response.body.decode("utf-8").lower()
    return body


@pytest.mark.asyncio
async def test_agent_workspace_rfq_document_route_is_disabled_and_safe() -> None:
    response = await get_workspace_rfq_document("case-1", current_user=_TEST_USER)

    _assert_legacy_document_disabled(response)


@pytest.mark.asyncio
async def test_state_workspace_rfq_document_route_is_disabled_and_safe() -> None:
    response = await get_rfq_document(
        raw_request=SimpleNamespace(
            headers={"X-Request-Id": "state-rfq-document-boundary"}
        ),
        thread_id="case-1",
        user=_TEST_USER,
    )

    body = _assert_legacy_document_disabled(response)
    assert body["request_id"] == "state-rfq-document-boundary"
