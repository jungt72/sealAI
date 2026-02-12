import pytest
from langchain_core.messages import HumanMessage
from app.langgraph_v2.nodes.nodes_resume import confirm_resume_node
from app.langgraph_v2.state.sealai_state import SealAIState

@pytest.mark.anyio
async def test_hitl_resume_clears_confirmation_and_resolves():
    s = SealAIState(
        tenant_id="t",
        user_id="u",
        thread_id="thr",
        messages=[HumanMessage(content="Bitte erkläre PTFE kurz und nenne 2 Einsatzgrenzen.")],
        awaiting_user_confirmation=True,
        confirm_decision="resume",
        pending_action="knowledge",
        next_action=None,
    )
    d = confirm_resume_node(s)

    assert d.get("awaiting_user_confirmation") is False
    assert d.get("confirm_decision") is None
    assert (d.get("confirm_status") or "") == "resolved"
    assert d.get("pending_action") is None
    assert any(x in (d.get("confirmed_actions") or []) for x in ("knowledge","RUN_KNOWLEDGE"))
