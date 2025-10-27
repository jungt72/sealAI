#!/usr/bin/env python3

import sys
import os
sys.path.append('/root/sealai/backend')

try:
    from app.langgraph.compile import create_main_graph
    from app.langgraph.state import SealAIState, MetaInfo, Routing
    from uuid import uuid4

    print("Creating graph...")
    graph = create_main_graph()
    print("Graph created successfully")

    initial_state = SealAIState(
        messages=[],
        slots={"user_query": "Test query"},
        routing=Routing(),
        context_refs=[],
        meta=MetaInfo(thread_id="test", user_id="test_user", trace_id=str(uuid4())),
    )

    config = {"configurable": {"thread_id": "test", "checkpoint_ns": "test"}}

    print("Running graph...")
    result = graph.invoke(initial_state, config=config)
    print("Graph run successfully")
    print("Result:", result)

except Exception as e:
    print(f"Error: {type(e).__name__}: {str(e)}")
    import traceback
    traceback.print_exc()