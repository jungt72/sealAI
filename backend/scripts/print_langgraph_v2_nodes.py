"""
Print LangGraph v2 node names for contract/debugging.

Usage:
  python backend/scripts/print_langgraph_v2_nodes.py
"""

from __future__ import annotations

import asyncio
import os

from app.langgraph_v2.contracts import STABLE_V2_NODE_CONTRACT, get_compiled_graph_node_names
from app.langgraph_v2.sealai_graph_v2 import get_sealai_graph_v2


async def _main() -> None:
    os.environ.setdefault("CHECKPOINTER_BACKEND", "memory")
    graph = await get_sealai_graph_v2()
    nodes = sorted(get_compiled_graph_node_names(graph))

    print("stable_contract:", ", ".join(sorted(STABLE_V2_NODE_CONTRACT)))
    print("nodes_count:", len(nodes))
    for name in nodes:
        print(name)


if __name__ == "__main__":
    asyncio.run(_main())

