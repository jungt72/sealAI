from app.langgraph_v2.state.sealai_state import SealAIState
from app.langgraph_v2.sealai_graph_v2 import _supervisor_policy_router

def test_router_maps_run_panel_calc_to_calc():
    s = SealAIState(tenant_id="t", user_id="u", thread_id="thr", messages=[], next_action="RUN_PANEL_CALC")
    assert _supervisor_policy_router(s) == "calc"

def test_router_maps_run_panel_norms_rag_to_knowledge():
    s = SealAIState(tenant_id="t", user_id="u", thread_id="thr", messages=[], next_action="RUN_PANEL_NORMS_RAG")
    assert _supervisor_policy_router(s) == "RUN_PANEL_NORMS_RAG"
