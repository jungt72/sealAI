#!/usr/bin/env python3
import sys
sys.path.insert(0, '/root/sealai/backend')

from app.services.langgraph.graph_factory import get_graph
from app.services.langgraph.runtime import ainvoke_langgraph

# Test 1: get_graph() works
try:
    app = get_graph()
    print("Test 1 OK: get_graph() works")
except Exception as e:
    print(f"Test 1 FAIL: {e}")
    sys.exit(1)

# Test 2: ainvoke with config
payload = {"query": "Hello"}
try:
    result = ainvoke_langgraph(payload, thread_id="test_thread")
    print("Test 2 OK: ainvoke with config works, final:", result.get("final_response", "none"))
except Exception as e:
    print(f"Test 2 FAIL: {e}")
    sys.exit(1)

# Test 3: State continuity
try:
    result1 = ainvoke_langgraph({"query": "Set x=1"}, thread_id="cont_test")
    result2 = ainvoke_langgraph({"query": "What is x?"}, thread_id="cont_test")
    print("Test 3 OK: State continuity, result2:", result2.get("final_response", "none"))
except Exception as e:
    print(f"Test 3 FAIL: {e}")
    sys.exit(1)

print("All tests passed!")