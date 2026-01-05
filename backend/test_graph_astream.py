#!/usr/bin/env python3

import asyncio
import sys
import os
sys.path.append('/root/sealai/backend')

async def main():
    try:
        from app.langgraph.compile import create_main_graph
        from app.langgraph.state import SealAIState, MetaInfo, Routing
        from uuid import uuid4

        print("Creating graph...")
        graph = await create_main_graph()
        print("Graph created successfully")

        initial_state = SealAIState(
            messages=[],
            slots={"user_query": "Test query"},
            routing=Routing(),
            context_refs=[],
            meta=MetaInfo(thread_id="test", user_id="test_user", trace_id=str(uuid4())),
        )

        config = {"configurable": {"thread_id": "test", "checkpoint_ns": "test"}}

        print("Running astream...")
        async for event in graph.astream(initial_state, config=config):
            for node, state in event.items():
                print(f"Node: {node}")
                if state and 'messages' in state:
                    messages = state['messages']
                    if messages:
                        last_msg = messages[-1]
                        if hasattr(last_msg, 'role') and last_msg.role == 'assistant':
                            print(f"Assistant: {last_msg.get('content', '')[:100]}...")
        print("Astream completed")

    except Exception as e:
        print(f"Error: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
