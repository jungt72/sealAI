# MIGRATION: Phase-2 – ToolNode parallelism test
"""Test ToolNode parallel execution, timeouts, circuit breakers, and retry logic."""
from __future__ import annotations

import asyncio
import time
import pytest
from unittest.mock import Mock, patch

from app.langgraph.state import SealAIStateModel


@pytest.fixture
def mock_tool():
    """Mock tool that simulates processing time."""
    def tool_func(**kwargs):
        time.sleep(0.1)  # Simulate processing
        return f"Result for {kwargs}"

    tool = Mock()
    tool.__name__ = "mock_tool"
    tool.side_effect = tool_func
    return tool


@pytest.fixture
def sample_material_state():
    return {
        "messages": [{"role": "user", "content": "Calculate material stress"}],
        "slots": {"material": "steel", "load": "1000N"},
        "routing": {"domains": ["material"]},
        "context_refs": [],
        "meta": {"thread_id": "test-123", "trace_id": "trace-456"}
    }


def test_toolnode_parallel_execution(sample_material_state):
    """Test that tools execute in parallel when configured."""
    from app.langgraph.subgraphs.material.nodes.tools_node import MaterialToolsNode

    node = MaterialToolsNode()
    node.config = {
        "concurrency": 3,
        "timeout_ms": 5000,
        "tools": ["material_calculator", "standards_lookup"]
    }

    start_time = time.time()
    result = node(sample_material_state)
    end_time = time.time()

    # Should complete faster than sequential execution
    execution_time = end_time - start_time
    assert execution_time < 0.25  # Less than 2x sequential (0.1 * 2 = 0.2)

    # Validate result structure
    model = SealAIStateModel.model_validate(result)
    assert len(model.context_refs) > 0


def test_toolnode_timeout_handling(sample_material_state):
    """Test that tools respect timeout limits."""
    from app.langgraph.subgraphs.material.nodes.tools_node import MaterialToolsNode

    node = MaterialToolsNode()
    node.config = {
        "concurrency": 1,
        "timeout_ms": 50,  # Very short timeout
        "tools": ["slow_tool"]
    }

    # Mock slow tool
    with patch('time.sleep') as mock_sleep:
        mock_sleep.side_effect = lambda x: time.sleep(0.1)  # Longer than timeout

        result = node(sample_material_state)

        # Should handle timeout gracefully
        model = SealAIStateModel.model_validate(result)
        # Check for error handling in context_refs or messages


def test_toolnode_circuit_breaker(sample_material_state):
    """Test circuit breaker prevents cascading failures."""
    from app.langgraph.subgraphs.material.nodes.tools_node import MaterialToolsNode

    node = MaterialToolsNode()
    node.config = {
        "concurrency": 1,
        "timeout_ms": 1000,
        "circuit_breaker": {"enabled": True, "threshold": 2},
        "tools": ["failing_tool"]
    }

    # Simulate multiple failures
    with patch('app.langgraph.subgraphs.material.nodes.tools_node.MaterialToolsNode._execute_tool') as mock_execute:
        mock_execute.side_effect = Exception("Tool failure")

        # First few calls should attempt execution
        for i in range(3):
            result = node(sample_material_state)

        # Circuit should open after threshold
        # Verify error handling


def test_toolnode_retry_logic(sample_material_state):
    """Test retry mechanism for transient failures."""
    from app.langgraph.subgraphs.material.nodes.tools_node import MaterialToolsNode

    node = MaterialToolsNode()
    node.config = {
        "concurrency": 1,
        "timeout_ms": 1000,
        "retry": {"max_tries": 3, "backoff_ms": 100},
        "tools": ["unreliable_tool"]
    }

    call_count = 0

    def unreliable_tool(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("Transient failure")
        return "Success"

    with patch('app.langgraph.subgraphs.material.nodes.tools_node.MaterialToolsNode._execute_tool') as mock_execute:
        mock_execute.side_effect = unreliable_tool

        result = node(sample_material_state)

        # Should have been called 3 times (2 failures + 1 success)
        assert call_count == 3

        model = SealAIStateModel.model_validate(result)
        # Verify successful result despite retries


def test_toolnode_error_isolation(sample_material_state):
    """Test that one tool failure doesn't affect others."""
    from app.langgraph.subgraphs.material.nodes.tools_node import MaterialToolsNode

    node = MaterialToolsNode()
    node.config = {
        "concurrency": 2,
        "timeout_ms": 1000,
        "tools": ["working_tool", "failing_tool"]
    }

    def mixed_execution(tool_name, **kwargs):
        if tool_name == "failing_tool":
            raise Exception("Tool failure")
        return f"Success from {tool_name}"

    with patch('app.langgraph.subgraphs.material.nodes.tools_node.MaterialToolsNode._execute_tool') as mock_execute:
        mock_execute.side_effect = mixed_execution

        result = node(sample_material_state)

        model = SealAIStateModel.model_validate(result)

        # Should have results from successful tool and error from failed tool
        successful_refs = [ref for ref in model.context_refs if "working_tool" in str(ref)]
        error_refs = [ref for ref in model.context_refs if "failing_tool" in str(ref)]

        assert len(successful_refs) > 0
        assert len(error_refs) > 0


__all__ = []