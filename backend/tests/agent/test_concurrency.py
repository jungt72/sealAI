import pytest
import asyncio
import copy
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.cli import create_initial_state
from app.services.history.persist import save_structured_case, build_structured_case_storage_key, ConcurrencyConflictError
from app.services.auth.dependencies import RequestUser

@pytest.fixture
def agent_request_user():
    return RequestUser(
        user_id="user-test",
        username="tester",
        sub="user-test",
        roles=[],
        scopes=[],
        tenant_id="tenant-test",
    )

def _mock_state(revision: int, parent_revision: int, cycle_id: str = None):
    sealing_state = create_initial_state()
    sealing_state["cycle"]["state_revision"] = revision
    sealing_state["cycle"]["snapshot_parent_revision"] = parent_revision
    sealing_state["cycle"]["analysis_cycle_id"] = cycle_id or str(uuid.uuid4())
    return {
        "messages": [],
        "sealing_state": sealing_state,
        "working_profile": {},
        "relevant_fact_cards": [],
    }

def test_concurrency_conflict_detected(agent_request_user):
    """
    Simuliert Last-write-wins:
    1. User A lädt Rev 5 (Cycle X).
    2. User B lädt Rev 5 (Cycle X).
    3. User A speichert Rev 6 (basiert auf 5, neuer Cycle A). -> Erfolg.
    4. User B speichert Rev 6 (basiert auf 5, neuer Cycle B). -> Conflict.
    """
    async def _run():
        session_id = "concurrency-test"
        owner_id = agent_request_user.user_id
        tenant_id = agent_request_user.tenant_id or owner_id
        
        # Beide starten von derselben Basis Rev 5
        state_a = _mock_state(revision=6, parent_revision=5, cycle_id="cycle-A")
        state_b = _mock_state(revision=6, parent_revision=5, cycle_id="cycle-B")
        
        mock_session = MagicMock()
        mock_session.get = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        # Wichtig: __aexit__ muss False zurückgeben (oder None), damit Exceptions propagiert werden.
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        
        mock_transcript = SimpleNamespace(
            chat_id=f"agent_case:{owner_id}:{session_id}",
            user_id=owner_id,
            metadata_json={
                "sealing_state": {
                    "cycle": {
                        "state_revision": 5,
                        "snapshot_parent_revision": 4,
                        "analysis_cycle_id": "cycle-initial"
                    }
                }
            }
        )
        
        mock_session.get.side_effect = [None, mock_transcript]
        
        with patch("app.database.AsyncSessionLocal", return_value=mock_session_ctx):
            # Write A (erfolg)
            await save_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=session_id, state=state_a, runtime_path="test", binding_level="ORIENTATION")
            
            # DB simulieren nach A
            mock_transcript.metadata_json["sealing_state"]["cycle"]["state_revision"] = 6
            mock_transcript.metadata_json["sealing_state"]["cycle"]["analysis_cycle_id"] = "cycle-A"
            mock_transcript.metadata_json["sealing_state"]["cycle"]["snapshot_parent_revision"] = 5
            
            # Write B (Conflict)
            await save_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=session_id, state=state_b, runtime_path="test", binding_level="ORIENTATION")

    with pytest.raises(ConcurrencyConflictError) as exc_info:
        asyncio.run(_run())
    assert "State revision conflict" in str(exc_info.value)

def test_concurrency_resave_success(agent_request_user):
    """
    Simuliert einen Resave desselben Cycles (z.B. nachfolgende Nachricht ohne Tool-Call):
    1. DB hat Rev 5 (Cycle X).
    2. Incoming hat Rev 5 (Cycle X).
    3. Save sollte erfolgreich sein.
    """
    async def _run():
        session_id = "concurrency-resave"
        owner_id = agent_request_user.user_id
        tenant_id = agent_request_user.tenant_id or owner_id
        
        state = _mock_state(revision=5, parent_revision=4, cycle_id="cycle-X")
        
        mock_session = MagicMock()
        mock_session.get = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.add = MagicMock()
        mock_session_ctx = MagicMock()
        mock_session_ctx.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_ctx.__aexit__ = AsyncMock(return_value=False)
        
        mock_transcript = SimpleNamespace(
            chat_id=f"agent_case:{owner_id}:{session_id}",
            user_id=owner_id,
            metadata_json={
                "sealing_state": {
                    "cycle": {
                        "state_revision": 5,
                        "snapshot_parent_revision": 4,
                        "analysis_cycle_id": "cycle-X"
                    }
                }
            }
        )
        mock_session.get.return_value = mock_transcript
        
        with patch("app.database.AsyncSessionLocal", return_value=mock_session_ctx):
            await save_structured_case(tenant_id=tenant_id, owner_id=owner_id, case_id=session_id, state=state, runtime_path="test", binding_level="ORIENTATION")
            # Erfolg (keine Exception)

    asyncio.run(_run())
