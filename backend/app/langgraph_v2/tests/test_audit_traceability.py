from __future__ import annotations

import hashlib
import logging
import re
from unittest.mock import patch

import app.langgraph_v2.nodes.answer_subgraph.node_draft_answer as draft_node_module
import pytest
from langchain_core.messages import HumanMessage

from app.langgraph_v2.nodes.answer_subgraph.node_finalize import node_finalize
from app.langgraph_v2.nodes.answer_subgraph.node_prepare_contract import node_prepare_contract
from app.langgraph_v2.nodes.answer_subgraph.state import AnswerSubgraphState
from app.langgraph_v2.nodes.answer_subgraph.node_targeted_patch import node_targeted_patch
from app.langgraph_v2.nodes.answer_subgraph.node_verify_claims import node_verify_claims
from app.langgraph_v2.state.sealai_state import AnswerContract, SealAIState, Source, WorkingProfile


_NUMBER_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?\b")


class _Chunk:
    def __init__(self, content: str) -> None:
        self.content = content


class _ContractEchoLLM:
    async def astream(self, messages, config=None):
        contract_text = ""
        if messages:
            content = getattr(messages[-1], "content", "") or ""
            prefix = "VERIFIED FACT SHEET:\n"
            if isinstance(content, str) and content.startswith(prefix):
                contract_text = content[len(prefix) :]
        yield _Chunk(contract_text)


def _merge_patch(base: dict, patch: dict) -> dict:
    merged = dict(base)
    for key, value in patch.items():
        if isinstance(merged.get(key), dict) and isinstance(value, dict):
            merged[key] = _merge_patch(merged[key], value)
        else:
            merged[key] = value
    return merged


async def _run_subgraph_like(state: SealAIState) -> dict:
    prepare_patch = node_prepare_contract(state)
    prepared_state = SealAIState.model_validate(
        _merge_patch(state.model_dump(exclude_none=False), prepare_patch)
    )
    draft_patch = await draft_node_module.node_draft_answer(
        prepared_state,
        config={"configurable": {"thread_id": state.conversation.thread_id or "audit-thread"}},
    )
    drafted_state = SealAIState.model_validate(
        _merge_patch(prepared_state.model_dump(exclude_none=False), draft_patch)
    )
    verify_patch = node_verify_claims(drafted_state)
    verified_state = SealAIState.model_validate(
        _merge_patch(drafted_state.model_dump(exclude_none=False), verify_patch)
    )
    finalize_patch = node_finalize(verified_state)
    combined = {}
    for patch in (prepare_patch, draft_patch, verify_patch, finalize_patch):
        combined = _merge_patch(combined, patch)
    return combined


@pytest.mark.asyncio
async def test_contract_to_log_persistence_contains_digital_twin() -> None:
    state = SealAIState(
        conversation={"thread_id": "audit-1"},
        working_profile=WorkingProfile(medium="Kyrolon", pressure_bar=80.0, temperature_c=260.0),
        system={
            "sources": [
                Source(
                    snippet="Kyrolon Freigabe bis 80 bar.",
                    source="DIN",
                    metadata={"document_id": "din_press", "chunk_id": "chunkA"},
                ),
                Source(
                    snippet="Temperaturgrenze 260 C.",
                    source="DIN",
                    metadata={"document_id": "din_temp", "chunk_id": "chunkB"},
                ),
            ]
        },
    )

    with patch.object(draft_node_module, "_DRAFT_LLM", _ContractEchoLLM()):
        patch_payload = await _run_subgraph_like(state)

    contract = patch_payload["system"]["answer_contract"]
    contract_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()

    assert contract.selected_fact_ids
    assert patch_payload["system"]["final_prompt_metadata"]["contract_hash"] == contract_hash
    assert patch_payload["system"]["final_prompt_metadata"]["contract_first"] is True
    assert patch_payload["messages"][-1].content == patch_payload["final_text"]


def test_verification_transparency_records_wrong_value_and_patch_action() -> None:
    contract = AnswerContract(
        resolved_parameters={"pressure_bar": 80.0},
        selected_fact_ids=["din_press:chunkA"],
    )
    base_hash = hashlib.sha256(contract.model_dump_json().encode()).hexdigest()
    bad_state = SealAIState(
        system={
            "answer_contract": contract,
            "draft_base_hash": base_hash,
            "draft_text": "Kyrolon ist fuer 100 bar geeignet.",
        },
        reasoning={"flags": {}},
    )

    verify_patch = node_verify_claims(bad_state)
    report = verify_patch["system"]["verification_report"]
    patched = node_targeted_patch(
        SealAIState(
            system={
                "answer_contract": contract,
                "draft_base_hash": base_hash,
                "draft_text": bad_state.system.draft_text,
                "verification_report": report,
            },
            reasoning={"flags": {}},
        )
    )

    assert report.status == "fail"
    assert report.failure_type == "render_mismatch"
    assert any(span.get("wrong_span") == "100" for span in report.failed_claim_spans)
    assert patched["system"]["draft_text"] == "Kyrolon ist fuer 80.0 bar geeignet."
    assert patched["reasoning"]["flags"]["answer_subgraph_patch_attempts"] == 1


@pytest.mark.asyncio
async def test_source_attribution_integrity_for_final_numbers() -> None:
    state = SealAIState(
        conversation={"thread_id": "audit-2"},
        working_profile=WorkingProfile(medium="Kyrolon", pressure_bar=80.0, temperature_c=260.0),
        system={
            "sources": [
                Source(
                    snippet="Max Druck 80 bar gemaess DIN.",
                    source="DIN",
                    metadata={"document_id": "din_press", "chunk_id": "chunkA"},
                ),
                Source(
                    snippet="Max Temperatur 260 C gemaess DIN.",
                    source="DIN",
                    metadata={"document_id": "din_temp", "chunk_id": "chunkB"},
                ),
            ]
        },
    )

    with patch.object(draft_node_module, "_DRAFT_LLM", _ContractEchoLLM()):
        patch_payload = await _run_subgraph_like(state)

    contract = patch_payload["system"]["answer_contract"]
    selected_ids = set(contract.selected_fact_ids)
    id_to_snippet = {
        f"{src.metadata.get('document_id')}:{src.metadata.get('chunk_id')}": str(src.snippet or "")
        for src in state.system.sources
    }
    final_numbers = {_normalize_number_token(token) for token in _NUMBER_PATTERN.findall(patch_payload["final_text"])}
    source_numbers_by_id = {
        source_id: {_normalize_number_token(token) for token in _NUMBER_PATTERN.findall(text)}
        for source_id, text in id_to_snippet.items()
    }

    assert final_numbers
    for number in final_numbers:
        assert any(
            source_id in selected_ids and number in source_numbers_by_id.get(source_id, set())
            for source_id in id_to_snippet
        )


@pytest.mark.asyncio
async def test_answer_subgraph_material_flow_keeps_contract_and_working_profile(caplog: pytest.LogCaptureFixture) -> None:
    state = AnswerSubgraphState(
        conversation={
            "thread_id": "audit-kyrolon-subgraph",
            "messages": [HumanMessage(content="Was kannst du mir ueber Kyrolon sagen?")],
            "intent": {"goal": "explanation_or_comparison"},
        },
        working_profile={
            "engineering_profile": {"medium": "Kyrolon"},
            "live_calc_tile": {"status": "ok", "v_surface_m_s": 3.2},
            "calc_results": {},
        },
        reasoning={
            "flags": {"frontdoor_intent_category": "MATERIAL_RESEARCH"},
            "context": "Kyrolon ist ein technischer Werkstoff.",
        },
        system={
            "sources": [
                {
                    "snippet": "Kyrolon ist ein technischer Werkstoff mit dokumentierten Materialeigenschaften.",
                    "source": "DIN",
                    "metadata": {"document_id": "kyrolon_doc", "chunk_id": "chunkA"},
                }
            ]
        },
    )

    caplog.set_level(logging.INFO)

    prepare_patch = node_prepare_contract(state)
    assert prepare_patch["system"]["answer_contract"] is not None

    prepared_state = SealAIState.model_validate(
        _merge_patch(state.model_dump(exclude_none=False), prepare_patch)
    )

    with patch.object(draft_node_module, "_DRAFT_LLM", _ContractEchoLLM()):
        draft_patch = await draft_node_module.node_draft_answer(
            prepared_state,
            config={"configurable": {"thread_id": "audit-kyrolon-subgraph"}},
        )

    drafted_state = SealAIState.model_validate(
        _merge_patch(prepared_state.model_dump(exclude_none=False), draft_patch)
    )
    verify_patch = node_verify_claims(drafted_state)
    verified_state = SealAIState.model_validate(
        _merge_patch(drafted_state.model_dump(exclude_none=False), verify_patch)
    )
    finalize_patch = node_finalize(verified_state)

    assert prepared_state.system.answer_contract is not None
    assert verify_patch["system"]["verification_report"].status == "pass"
    assert finalize_patch["final_text"]
    assert "keinen exakten Treffer gefunden" not in finalize_patch["final_text"]
    assert "draft_answer.missing_contract" not in caplog.text
    assert "verify_claims.state_race_condition" not in caplog.text
    assert "DRAFT_ANSWER_BLIND_SPOT" not in caplog.text


def _normalize_number_token(value: str) -> str:
    try:
        parsed = float(str(value).replace(",", "."))
    except ValueError:
        return str(value)
    if parsed.is_integer():
        return str(int(parsed))
    return str(parsed)
