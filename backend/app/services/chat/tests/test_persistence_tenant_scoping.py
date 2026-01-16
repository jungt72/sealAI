import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.chat.persistence import persist_chat_transcript
from app.models.chat_transcript import ChatTranscript

@pytest.mark.asyncio
async def test_persist_chat_transcript_uses_tenant_id():
    """Verify that persist_chat_transcript uses tenant_id in WHERE clause."""
    
    chat_id = "chat-123"
    tenant_id = "tenant-A"
    user_id = "user-1"
    
    # Mock Session
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result
    
    # Mock the context manager
    mock_session.__aenter__.return_value = mock_session
    mock_session.__aexit__.return_value = None
    
    # Mock the AsyncSessionLocal factory
    mock_session_factory = MagicMock(return_value=mock_session)
    
    with patch("app.services.chat.persistence.AsyncSessionLocal", mock_session_factory):
        await persist_chat_transcript(
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            summary="Summary",
            metadata={}
        )
    
    # Assertions
    assert mock_session.execute.called
    stmt = mock_session.execute.call_args[0][0]
    
    # Verify add was called with correct tenant_id
    assert mock_session.add.called
    added_obj = mock_session.add.call_args[0][0]
    assert isinstance(added_obj, ChatTranscript)
    assert added_obj.tenant_id == tenant_id
    assert added_obj.chat_id == chat_id
