import pytest
from langgraph.checkpoint.memory import MemorySaver

pytest.skip(
    "Legacy LangGraph v2 compile test disabled during agent-path canonization.",
    allow_module_level=True,
)

from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2


def test_graph_compiles():
    graph = create_sealai_graph_v2(MemorySaver(), require_async=False)
    assert graph is not None
