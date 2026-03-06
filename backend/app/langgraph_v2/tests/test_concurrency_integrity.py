from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

import app.langgraph_v2.nodes.answer_subgraph.node_draft_answer as draft_node_module
import pytest

from app.langgraph_v2.nodes.answer_subgraph.node_finalize import node_finalize
from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app.langgraph_v2.state.sealai_state import SealAIState, Source, WorkingProfile


def _contract_hash(contract: Any) -> str:
    return hashlib.sha256(contract.model_dump_json().encode()).hexdigest()


def _merge_patch(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_patch(merged[key], value)
        else:
            merged[key] = value
    return merged


def _state_for_pressure(pressure_bar: float, *, thread_id: str = "thread-race") -> SealAIState:
    return SealAIState(
        conversation={"thread_id": thread_id},
        working_profile=WorkingProfile(
            engineering_profile={"medium": "Kyrolon", "pressure_bar": pressure_bar},
            medium="Kyrolon",
            pressure_bar=pressure_bar,
        ),
        system={
            "sources": [
                Source(
                    snippet=f"Kyrolon ist fuer {pressure_bar} bar freigegeben.",
                    source="DIN",
                    metadata={"document_id": "din_norm", "chunk_id": "cidA"},
                )
            ]
        },
        reasoning={"flags": {"applied_patch_ids": []}},
    )


class _ContractEchoChunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _ContractEchoLLM:
    async def astream(self, messages, config=None):
        contract_text = ""
        if messages:
            candidate = getattr(messages[-1], "content", "") or ""
            prefix = "VERIFIED FACT SHEET:\n"
            if isinstance(candidate, str) and candidate.startswith(prefix):
                contract_text = candidate[len(prefix) :]
        yield _ContractEchoChunk(contract_text or "Resolved Parameters:\n- pressure_bar: 80.0")


@pytest.mark.asyncio
async def test_state_drift_collision_rejected_by_state_race_guard() -> None:
    request_1_state = _state_for_pressure(80.0, thread_id="thread-shared")
    request_2_state = _state_for_pressure(120.0, thread_id="thread-shared")

    patch_1 = node_prepare_contract(request_1_state)
    patch_2 = node_prepare_contract(request_2_state)
    contract_1 = patch_1["answer_contract"]
    contract_2 = patch_2["answer_contract"]

    assert contract_1.resolved_parameters["pressure_bar"] == 80.0
    assert contract_2.resolved_parameters["pressure_bar"] == 120.0

    drifted_state = SealAIState(
        conversation={"thread_id": "thread-shared"},
        system={
            "answer_contract": contract_2,
            "draft_base_hash": _contract_hash(contract_1),
            "draft_text": "Kyrolon 80.0 bar.",
        },
    )
    verify_patch = node_verify_claims(drifted_state)
    report = verify_patch["system"]["verification_report"]

    assert report.status == "fail"
    assert report.failure_type == "state_race_condition"
    assert all(span.get("reason") != "missing_number" for span in report.failed_claim_spans)


@pytest.mark.asyncio
async def test_parallel_subgraph_invokes_keep_flags_and_reports_isolated() -> None:
    shared_state = _state_for_pressure(80.0, thread_id="thread-parallel")

    async def _run_one(idx: int):
        return await _subgraph_like_invoke(
            shared_state,
            config={"configurable": {"thread_id": "thread-parallel", "run_id": f"run-{idx}"}},
        )

    with patch.object(draft_node_module, "_DRAFT_LLM", _ContractEchoLLM()):
        results = await asyncio.gather(*[_run_one(i) for i in range(10)])

    assert len(results) == 10
    for result in results:
        report = result.get("system", {}).get("verification_report")
        assert report is not None
        assert report.status == "pass"
        assert result.get("error") in (None, "")
        assert result["reasoning"]["flags"]["answer_subgraph_patch_attempts"] == 0
        assert result["reasoning"]["flags"].get("applied_patch_ids") == []
    # nested list isolation: each run gets its own list object
    assert len({id(result["reasoning"]["flags"]["applied_patch_ids"]) for result in results}) == 10


@dataclass
class _MockDelayedCheckpointer:
    delay_s: float = 0.05
    fail: bool = False
    writes: list[Any] | None = None

    def __post_init__(self) -> None:
        if self.writes is None:
            self.writes = []

    async def aput(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(self.delay_s)
        if self.fail:
            raise RuntimeError("simulated redis pool recreation failure")
        entry = {"args": args, "kwargs": kwargs}
        self.writes.append(entry)
        return {"ok": True}


async def _subgraph_like_invoke(state: SealAIState, *, config: dict[str, Any]) -> dict[str, Any]:
    prepare_patch = node_prepare_contract(state)
    prepared_state = SealAIState.model_validate(
        _merge_patch(state.model_dump(exclude_none=False), prepare_patch)
    )
    draft_patch = await draft_node_module.node_draft_answer(prepared_state, config=config)
    drafted_state = SealAIState.model_validate(
        _merge_patch(prepared_state.model_dump(exclude_none=False), draft_patch)
    )
    verify_patch = node_verify_claims(drafted_state)
    verified_state = SealAIState.model_validate(
        _merge_patch(drafted_state.model_dump(exclude_none=False), verify_patch)
    )
    patch_payload = _merge_patch(_merge_patch(prepare_patch, draft_patch), verify_patch)
    if verify_patch["system"]["verification_report"].status == "pass":
        patch_payload = _merge_patch(patch_payload, node_finalize(verified_state))
    return patch_payload


async def _run_subgraph_and_checkpoint(
    state: SealAIState,
    saver: _MockDelayedCheckpointer,
) -> dict[str, Any]:
    try:
        patch_payload = await _subgraph_like_invoke(
            state,
            config={"configurable": {"thread_id": state.conversation.thread_id or "thread-cp", "run_id": "checkpoint-run"}},
        )
        await saver.aput({"thread_id": state.conversation.thread_id}, patch_payload)
        return {"success": True, "state_corrupt": False, "patch": patch_payload}
    except Exception as exc:
        return {"success": False, "state_corrupt": False, "error": str(exc)}


@pytest.mark.asyncio
async def test_delayed_checkpointer_put_never_marks_partial_success() -> None:
    state = _state_for_pressure(80.0, thread_id="thread-checkpointer")
    ok_saver = _MockDelayedCheckpointer(delay_s=0.02, fail=False)
    fail_saver = _MockDelayedCheckpointer(delay_s=0.02, fail=True)

    with patch.object(draft_node_module, "_DRAFT_LLM", _ContractEchoLLM()):
        ok_result = await _run_subgraph_and_checkpoint(state, ok_saver)
    with patch.object(draft_node_module, "_DRAFT_LLM", _ContractEchoLLM()):
        fail_result = await _run_subgraph_and_checkpoint(state, fail_saver)

    assert ok_result["success"] is True
    assert ok_result["state_corrupt"] is False
    assert ok_result["patch"]["system"]["verification_report"].status == "pass"
    assert len(ok_saver.writes or []) == 1

    assert fail_result["success"] is False
    assert fail_result["state_corrupt"] is False
    assert "redis pool recreation failure" in fail_result["error"]
