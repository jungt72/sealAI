# MIGRATION: Phase-1 - E2E ohne RAG/Tools

from ..state import SealAIState, MetaInfo
from ..nodes.entry_frontend import entry_frontend
from ..nodes.discovery_intake import discovery_intake
from ..nodes.intent_projector import intent_projector
from ..nodes.supervisor import supervisor
from ..nodes.resolver import resolver
from ..nodes.exit_response import exit_response
from unittest.mock import patch

def test_single_flow():
    meta = MetaInfo(thread_id="t1", user_id="u1", trace_id="tr1")
    state = SealAIState(meta=meta, slots={"user_query": "Test material query"})
    
    # Mock LLM calls
    with patch('backend.app.langgraph.utils.llm.call_llm', return_value="Mocked response"):
        # Simulate flow
        state_dict = entry_frontend(state)
        state = state.update(state_dict)
        assert len(state.messages) == 1
        assert state.messages[0]["role"] == "user"
        
        state_dict = discovery_intake(state)
        state = state.update(state_dict)
        assert len(state.messages) == 2
        assert "What is the material?" in state.messages[1]["content"]
        
        state_dict = intent_projector(state)
        state = state.update(state_dict)
        assert state.routing.domains == ["material"]
        
        # Supervisor, Resolver, Exit - Dummy assertions
        state_dict = supervisor(state)
        state = state.update(state_dict)
        
        state_dict = resolver(state)
        state = state.update(state_dict)
        assert "Resolved:" in state.messages[-1]["content"]
        
        state_dict = exit_response(state)
        state = state.update(state_dict)
        assert len(state.messages) == 4  # Plus answer