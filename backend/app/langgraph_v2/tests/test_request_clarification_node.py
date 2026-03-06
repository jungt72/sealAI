from __future__ import annotations

import pytest

from app.langgraph_v2.nodes.request_clarification import request_clarification_node
from app.langgraph_v2.state import SealAIState


@pytest.mark.asyncio
async def test_request_clarification_handles_none_and_string_errors() -> None:
    state = SealAIState(system={"verification_error": None, "error": "generic failure"})

    result = await request_clarification_node(state)

    assert result["verification_status"] == "FAILED_REQUIRES_CLARIFICATION"
    assert result["requires_user_input"] is True
    assert "Hinweis zur Datenqualit" in result["system"]["final_answer"]
    assert "- **" not in result["system"]["final_answer"]


@pytest.mark.asyncio
async def test_request_clarification_prefers_dict_verification_error() -> None:
    state = SealAIState(
        system={
            "verification_error": {"unverified_values": [{"formatted": "120 bar"}]},
            "error": "fallback string error",
        }
    )

    result = await request_clarification_node(state)

    assert "- **120 bar**" in result["system"]["final_answer"]


@pytest.mark.asyncio
async def test_request_clarification_reads_unverified_from_dict_error_fallback() -> None:
    state = SealAIState(system={"verification_error": None, "error": None})
    state.system.error = {"unverified_values": [{"formatted": "85 C"}]}

    result = await request_clarification_node(state)

    assert "- **85 C**" in result["system"]["final_answer"]
