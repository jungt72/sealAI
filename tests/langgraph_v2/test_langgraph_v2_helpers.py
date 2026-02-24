from langchain_core.messages import AIMessage

from app.api.v1.endpoints import langgraph_v2
from app.langgraph_v2.io import AskMissingRequest
from app.langgraph_v2.constants import CHECKPOINTER_NAMESPACE_V2
from app.langgraph_v2.sealai_graph_v2 import build_v2_config
from app.langgraph_v2.state import Recommendation, SealAIState


def test_build_v2_config_sets_namespace_and_ids():
    cfg = build_v2_config(thread_id="thread-123", user_id="user-abc")

    # In v2, thread_id in configurable is a stable key: "user_id|thread_id"
    assert cfg["configurable"]["thread_id"] == "user-abc|thread-123"
    assert cfg["metadata"]["thread_id"] == "thread-123"
    assert cfg["metadata"]["user_id"] == "user-abc"
