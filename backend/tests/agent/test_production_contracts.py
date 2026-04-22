import pytest
import json
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock
from app.main import create_app
from app.services.auth.dependencies import RequestUser

@pytest.fixture
def client(mock_user):
    app = create_app()
    from app.services.auth.dependencies import get_current_request_user
    app.dependency_overrides[get_current_request_user] = lambda: mock_user
    return TestClient(app)

@pytest.fixture
def mock_user():
    from app.services.auth.dependencies import RequestUser
    return RequestUser(
        user_id="test-user",
        username="testuser",
        sub="test-sub",
        roles=["user"],
        tenant_id="test-tenant"
    )

def test_chat_stream_endpoint_contract(client, mock_user):
    """Verifies that /api/agent/chat/stream exists and has the correct SSE shape."""
    from app.agent.api.dispatch import RuntimeDispatchResolution
    
    mock_dispatch = RuntimeDispatchResolution(
        gate_route="CONVERSATION",
        gate_reason="test",
        runtime_mode="CONVERSATION",
        gate_applied=False,
        fast_response=MagicMock(content="Hello test")
    )
    
    # We patch the implementation function
    with patch("app.agent.api.routes.chat._resolve_runtime_dispatch", new=AsyncMock(return_value=mock_dispatch)):
        
        response = client.post("/api/agent/chat/stream", json={"message": "hi", "session_id": "s1"})
        
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        
        # Check first event
        lines = response.text.strip().split("\n\n")
        assert len(lines) >= 2
        first_event = lines[0]
        assert first_event.startswith("data: ")
        payload = json.loads(first_event[6:])
        assert payload["type"] == "state_update"
        assert "reply" in payload
        assert payload["reply"] == "Hello test"
        assert lines[-1] == "data: [DONE]"

def test_workspace_projection_contract(client, mock_user):
    """Verifies that /api/agent/workspace/{case_id} returns a valid projection."""
    with patch("app.agent.api.routes.workspace._load_governed_state_snapshot_projection_source", new=AsyncMock()) as mock_load:
        
        # Mock a minimal governed state
        from app.agent.state.models import GovernedSessionState
        mock_state = GovernedSessionState()
        mock_load.return_value = mock_state
        
        response = client.get("/api/agent/workspace/c1")
        
        assert response.status_code == 200
        data = response.json()
        assert "case_summary" in data
        assert "governance_status" in data

def test_chat_history_contract(client, mock_user):
    """Verifies that /api/agent/chat/history/{case_id} returns a valid list."""
    with patch("app.agent.api.routes.history.load_structured_case", new=AsyncMock(return_value=None)), \
         patch("app.agent.api.loaders._load_live_governed_state", new=AsyncMock()) as mock_load:
        
        from app.agent.state.models import GovernedSessionState, ConversationMessage
        mock_state = GovernedSessionState(
            conversation_messages=[ConversationMessage(role="user", content="hi")]
        )
        mock_load.return_value = mock_state
        
        response = client.get("/api/agent/chat/history/c1")
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        if len(data) > 0:
            assert "role" in data[0]
            assert "content" in data[0]

def test_dispatch_logic_isolation(client, mock_user):
    """Ensures dispatch.py correctly routes between FastResponder and Governed."""
    from app.agent.api.dispatch import _resolve_runtime_dispatch
    from app.agent.api.models import ChatRequest
    import asyncio
    
    request = ChatRequest(message="Hallo", session_id="s1")
    
    # We test the function directly to ensure no legacy imports leak
    with patch("app.services.pre_gate_classifier.PreGateClassifier.classify") as mock_classify:
        from app.domain.pre_gate_classification import PreGateClassification
        from app.services.pre_gate_classifier import ClassificationResult
        
        # Case 1: Greeting -> FastResponse
        mock_classify.return_value = ClassificationResult(
            classification=PreGateClassification.GREETING,
            confidence=1.0,
            reasoning="test",
            escalate_to_graph=False
        )
        
        res = asyncio.run(_resolve_runtime_dispatch(request, current_user=mock_user))
        assert res.runtime_mode == "CONVERSATION"
        assert res.fast_response is not None
        
        # Case 2: Domain Inquiry -> GOVERNED (failure to connect to redis/session manager should fail-open to governed)
        mock_classify.return_value = ClassificationResult(
            classification=PreGateClassification.DOMAIN_INQUIRY,
            confidence=1.0,
            reasoning="test",
            escalate_to_graph=True
        )
        
        res = asyncio.run(_resolve_runtime_dispatch(request, current_user=mock_user))
        assert res.runtime_mode == "GOVERNED"
