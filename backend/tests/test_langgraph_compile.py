import pytest

_SKIP_REASON = (
    "Legacy test targeting app.langgraph_v2; replacement arrives in "
    "Sprint 5 Patch 5.6 per Implementation Plan. "
    "See audits/gate_0_to_1_2026-04-19.md §7.2."
)
pytest.skip(_SKIP_REASON, allow_module_level=True)

from langgraph.checkpoint.memory import MemorySaver

from app.langgraph_v2.sealai_graph_v2 import create_sealai_graph_v2


def test_graph_compiles():
    graph = create_sealai_graph_v2(MemorySaver(), require_async=False)
    assert graph is not None
