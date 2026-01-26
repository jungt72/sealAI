import pytest
import uuid
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import Request
from app.api.v1.endpoints.langgraph_v2 import langgraph_chat_v2_endpoint, LangGraphV2Request
from app.api.v1.endpoints.state import get_state, _resolve_state_snapshot
from app.services.auth.dependencies import RequestUser
from app.langgraph_v2.utils.threading import resolve_checkpoint_thread_id

def _fake_user(user_id="user-123", tenant_id="tenant-1"):
    return RequestUser(
        user_id=user_id,
        username="tester",
        sub="sub-123",
        roles=[],
        tenant_id=tenant_id
    )

def _fake_request(request_id="req-123"):
    req = AsyncMock(spec=Request)
    req.headers = {"X-Request-Id": request_id}
    return req

@pytest.mark.anyio
async def test_chat_v2_resolves_stable_key():
    chat_id = str(uuid.uuid4())
    user = _fake_user()
    body = LangGraphV2Request(chat_id=chat_id, message="hello")
    
    expected_stable_key = resolve_checkpoint_thread_id(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        chat_id=chat_id
    )
    
    # Mock graph and snapshot
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {}
    mock_snapshot.config = {"configurable": {"thread_id": expected_stable_key}}
    mock_graph.aget_state.return_value = mock_snapshot
    
    with patch("app.api.v1.endpoints.langgraph_v2._build_graph_config", new_callable=AsyncMock) as mock_build:
        # Return mocked graph and config
        mock_build.return_value = (mock_graph, {"configurable": {}})
        
        with patch("app.api.v1.endpoints.langgraph_v2._event_stream_v2") as mock_stream:
            # _event_stream_v2 returns a StreamingResponse, mock that too to avoid errors if endpoint awaits response
            mock_stream.return_value = AsyncMock() 
            
            await langgraph_chat_v2_endpoint(body, _fake_request(), user=user)
            
            # Check arguments to _event_stream_v2
            args, kwargs = mock_stream.call_args
            assert kwargs["checkpoint_thread_id"] == expected_stable_key
            assert kwargs["checkpoint_thread_id"] != chat_id

@pytest.mark.anyio
async def test_state_get_resolves_stable_key():
    chat_id = str(uuid.uuid4())
    user = _fake_user()
    
    expected_stable_key = resolve_checkpoint_thread_id(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        chat_id=chat_id
    )
    
    # Setup mock return for _resolve_state_snapshot
    # It returns (graph, config, snapshot, is_privileged)
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {"messages": []} # Minimal state content
    mock_snapshot.config = {"configurable": {"thread_id": expected_stable_key}}
    mock_snapshot.created_at = "2024-01-01T00:00:00Z"
    
    with patch("app.api.v1.endpoints.state._resolve_state_snapshot", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = (mock_graph, {}, mock_snapshot, False)
        
        await get_state(_fake_request(), thread_id=chat_id, user=user)
        
        args, kwargs = mock_resolve.call_args
        assert kwargs["checkpoint_thread_id"] == expected_stable_key
        # Verify it's not the raw chat_id
        assert kwargs["checkpoint_thread_id"] != chat_id


@pytest.mark.anyio
async def test_resolve_state_snapshot_uses_checkpoint_thread_id():
    chat_id = "test2"
    user = _fake_user()
    expected_stable_key = resolve_checkpoint_thread_id(
        tenant_id=user.tenant_id,
        user_id=user.user_id,
        chat_id=chat_id,
    )
    mock_graph = AsyncMock()
    mock_snapshot = MagicMock()
    mock_snapshot.values = {"messages": []}
    mock_graph.aget_state.return_value = mock_snapshot

    with patch(
        "app.api.v1.endpoints.state._build_state_config_with_checkpointer",
        new_callable=AsyncMock,
    ) as mock_build:
        mock_build.return_value = (mock_graph, {"configurable": {"thread_id": expected_stable_key}})
        await _resolve_state_snapshot(
            thread_id=chat_id,
            user=user,
            checkpoint_thread_id=expected_stable_key,
        )
        args, kwargs = mock_build.call_args
        assert kwargs["checkpoint_thread_id"] == expected_stable_key

@pytest.mark.anyio
async def test_resolve_checkpoint_thread_id_invariant():
    # Direct check: raw chat_id != stable key when tenant present
    chat_id = str(uuid.uuid4())
    stable = resolve_checkpoint_thread_id(tenant_id="t1", user_id="u1", chat_id=chat_id)
    assert stable == f"t1:u1:{chat_id}"
    assert stable != chat_id
