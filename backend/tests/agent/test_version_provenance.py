"""0A.5: Version provenance — model/prompt/policy/projection tracking."""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage, HumanMessage

from app.agent.agent.prompts import (
    SYSTEM_PROMPT_TEMPLATE,
    REASONING_PROMPT_VERSION,
    REASONING_PROMPT_HASH,
)
from app.agent.case_state import (
    CASE_STATE_BUILDER_VERSION,
    PROJECTION_VERSION,
    VersionProvenance,
    build_case_state,
    sync_case_state_to_state,
)
from app.agent.runtime import INTERACTION_POLICY_VERSION, evaluate_interaction_policy
from app.agent.api.router import (
    SESSION_STORE,
    _build_fast_path_version_provenance,
    _build_structured_version_provenance,
    chat_endpoint,
    event_generator,
)
from app.agent.api.models import ChatRequest, ChatResponse
from app.agent.cli import create_initial_state
from app.agent.case_state import sync_case_state_to_state, sync_material_cycle_control
from app.services.auth.dependencies import RequestUser


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_sessions():
    SESSION_STORE.clear()


@pytest.fixture()
def user():
    return RequestUser(
        user_id="user-vp-test",
        username="tester",
        sub="user-vp-test",
        roles=[],
        scopes=[],
        tenant_id="tenant-vp-test",
    )


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    store = {}

    async def _load(*, owner_id, case_id):
        import copy
        s = store.get((owner_id, case_id))
        return copy.deepcopy(s) if s is not None else None

    async def _save(*, owner_id, case_id, state, runtime_path, binding_level):
        import copy
        store[(owner_id, case_id)] = copy.deepcopy(state)

    monkeypatch.setattr("app.agent.api.router.load_structured_case", _load)
    monkeypatch.setattr("app.agent.api.router.save_structured_case", _save)
    yield store


def _mock_state(revision=1):
    sealing_state = create_initial_state()
    sealing_state["cycle"]["state_revision"] = revision
    sealing_state["cycle"]["analysis_cycle_id"] = f"cycle-{revision}"
    sealing_state["governance"]["release_status"] = "inadmissible"
    return {
        "messages": [AIMessage(content="reply")],
        "sealing_state": sealing_state,
        "working_profile": {},
        "relevant_fact_cards": [],
    }


# ── Prompt hash tests ────────────────────────────────────────────────────────

def test_reasoning_prompt_hash_is_deterministic():
    import hashlib
    expected = hashlib.sha256(SYSTEM_PROMPT_TEMPLATE.encode()).hexdigest()[:12]
    assert REASONING_PROMPT_HASH == expected


def test_different_prompt_text_yields_different_hash():
    import hashlib
    other_hash = hashlib.sha256(b"totally different prompt").hexdigest()[:12]
    assert REASONING_PROMPT_HASH != other_hash


def test_reasoning_prompt_version_is_string():
    assert isinstance(REASONING_PROMPT_VERSION, str)
    assert len(REASONING_PROMPT_VERSION) > 0


def test_visible_reply_prompt_hash_is_deterministic():
    import hashlib
    from app.agent.agent.graph import _VISIBLE_REPLY_SYSTEM_PROMPT, VISIBLE_REPLY_PROMPT_HASH
    expected = hashlib.sha256(_VISIBLE_REPLY_SYSTEM_PROMPT.encode()).hexdigest()[:12]
    assert VISIBLE_REPLY_PROMPT_HASH == expected


# ── Policy version tests ─────────────────────────────────────────────────────

def test_interaction_policy_version_constant():
    assert INTERACTION_POLICY_VERSION == "interaction_policy_v1"


def test_policy_decision_carries_policy_version():
    decision = evaluate_interaction_policy("Was ist PTFE?")
    assert hasattr(decision, "policy_version")
    assert decision.policy_version == INTERACTION_POLICY_VERSION


def test_all_policy_branches_carry_version():
    messages = [
        "Was ist PTFE?",
        "50mm 1000rpm 10bar berechne",
        "empfehle ein Material",
        "Temperatur 120°C Druck 10 bar Wasser Dichtung",
    ]
    for msg in messages:
        decision = evaluate_interaction_policy(msg)
        assert decision.policy_version == INTERACTION_POLICY_VERSION, (
            f"policy_version missing for message: {msg!r}"
        )


# ── case_state builder version constants ────────────────────────────────────

def test_case_state_builder_version_is_string():
    assert isinstance(CASE_STATE_BUILDER_VERSION, str)
    assert len(CASE_STATE_BUILDER_VERSION) > 0


def test_projection_version_is_string():
    assert isinstance(PROJECTION_VERSION, str)
    assert len(PROJECTION_VERSION) > 0


# ── build_case_state with version_provenance ─────────────────────────────────

def _simple_agent_state():
    sealing_state = create_initial_state()
    return {
        "messages": [AIMessage(content="test reply")],
        "sealing_state": sealing_state,
        "working_profile": {},
        "relevant_fact_cards": [],
    }


def test_build_case_state_without_provenance_does_not_crash():
    state = _simple_agent_state()
    cs = build_case_state(state, session_id="s1", runtime_path="STRUCTURED_QUALIFICATION", binding_level="ORIENTATION")
    assert "case_meta" in cs
    assert "version_provenance" not in cs["case_meta"]


def test_build_case_state_with_provenance_populates_case_meta():
    vp: VersionProvenance = {
        "model_id": "gpt-4o-mini",
        "prompt_version": "reasoning_v1",
        "prompt_hash": "abc123def456",
        "policy_version": "interaction_policy_v1",
        "projection_version": "visible_case_narrative_v1",
        "case_state_builder_version": "case_state_builder_v1",
        "data_version_note": "not_yet_governed",
    }
    state = _simple_agent_state()
    cs = build_case_state(
        state,
        session_id="s1",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        version_provenance=vp,
    )
    assert cs["case_meta"]["version_provenance"]["model_id"] == "gpt-4o-mini"
    assert cs["case_meta"]["version_provenance"]["policy_version"] == "interaction_policy_v1"


def test_build_case_state_provenance_in_audit_trail():
    vp: VersionProvenance = {
        "model_id": "gpt-4o-mini",
        "prompt_version": "reasoning_v1",
        "prompt_hash": "abc123def456",
        "policy_version": "interaction_policy_v1",
        "projection_version": "visible_case_narrative_v1",
        "case_state_builder_version": "case_state_builder_v1",
        "data_version_note": "not_yet_governed",
    }
    state = _simple_agent_state()
    cs = build_case_state(
        state,
        session_id="s1",
        runtime_path="STRUCTURED_QUALIFICATION",
        binding_level="ORIENTATION",
        version_provenance=vp,
    )
    # First audit trail event should carry version_provenance
    first_event = cs["audit_trail"][0]
    assert first_event["event_type"] == "case_state_projection_built"
    assert "version_provenance" in first_event["details"]
    assert first_event["details"]["version_provenance"]["policy_version"] == "interaction_policy_v1"


# ── Router provenance helpers ────────────────────────────────────────────────

def test_structured_provenance_has_model_id():
    decision = evaluate_interaction_policy("empfehle ein Material")
    vp = _build_structured_version_provenance(decision=decision)
    assert vp["model_id"] == "gpt-4o-mini"


def test_structured_provenance_has_all_required_fields():
    decision = evaluate_interaction_policy("empfehle ein Material")
    vp = _build_structured_version_provenance(decision=decision)
    required = {
        "model_id", "prompt_version", "prompt_hash",
        "visible_reply_prompt_version", "visible_reply_prompt_hash",
        "policy_version", "projection_version", "case_state_builder_version",
        "data_version_note",
    }
    missing = required - set(vp.keys())
    assert not missing, f"Missing fields in structured provenance: {missing}"


def test_fast_path_provenance_has_no_model_id():
    """Fast paths must NOT claim an LLM model_id — no LLM is used for visible output."""
    decision = evaluate_interaction_policy("Was ist PTFE?")
    vp = _build_fast_path_version_provenance(decision=decision)
    assert vp["model_id"] is None


def test_fast_path_provenance_has_policy_version():
    decision = evaluate_interaction_policy("50mm 1000rpm berechne")
    vp = _build_fast_path_version_provenance(decision=decision)
    assert vp["policy_version"] == INTERACTION_POLICY_VERSION


def test_fast_path_provenance_missing_llm_fields():
    """Fast path provenance must not include prompt_version or visible_reply fields."""
    decision = evaluate_interaction_policy("Was ist FKM?")
    vp = _build_fast_path_version_provenance(decision=decision)
    assert "prompt_version" not in vp
    assert "visible_reply_prompt_version" not in vp
    assert "prompt_hash" not in vp


def test_structured_provenance_carries_rwdr_config_version_when_present():
    decision = evaluate_interaction_policy("empfehle ein Material")
    vp = _build_structured_version_provenance(decision=decision, rwdr_config_version="rwdr_selector_v1_1")
    assert vp.get("rwdr_config_version") == "rwdr_selector_v1_1"


def test_structured_provenance_no_rwdr_key_when_absent():
    decision = evaluate_interaction_policy("empfehle ein Material")
    vp = _build_structured_version_provenance(decision=decision, rwdr_config_version=None)
    assert "rwdr_config_version" not in vp


# ── chat_endpoint carries version_provenance ─────────────────────────────────

def test_chat_endpoint_guided_response_carries_version_provenance(user):
    state = _mock_state(revision=2)
    with patch("app.agent.api.router.execute_agent", new=AsyncMock(return_value=state)):
        response = asyncio.run(
            chat_endpoint(
                ChatRequest(message="Hallo", session_id="vp-guided"),
                current_user=user,
            )
        )
    assert response.version_provenance is not None
    # Guided path uses LLM — model_id must be present
    assert response.version_provenance.get("model_id") == "gpt-4o-mini"
    assert response.version_provenance.get("policy_version") == INTERACTION_POLICY_VERSION


def test_chat_endpoint_fast_path_has_no_model_id(user):
    """Fast knowledge path must not falsely attribute an LLM model."""
    with patch("app.agent.api.router.execute_fast_knowledge") as mock_fast:
        mock_fast.return_value = type("R", (), {"reply": "PTFE info", "working_profile": {}})()
        response = asyncio.run(
            chat_endpoint(
                ChatRequest(message="Was ist PTFE?", session_id="vp-fast"),
                current_user=user,
            )
        )
    assert response.version_provenance is not None
    assert response.version_provenance.get("model_id") is None


# ── SSE event_generator carries version_provenance ───────────────────────────

def test_sse_guided_payload_carries_version_provenance(user):
    session_id = "vp-sse-guided"
    final_state = _mock_state(revision=3)

    async def mock_astream(state, version):
        yield {
            "event": "on_chain_end",
            "name": "LangGraph",
            "data": {"output": {**final_state, "messages": state["messages"] + [AIMessage(content="guided reply")]}},
        }

    class _MockGraph:
        def astream_events(self, s, version="v2"):
            return mock_astream(s, version)

    with patch("app.agent.api.router.get_agent_graph", return_value=_MockGraph()):
        chunks = []

        async def _run():
            async for chunk in event_generator(
                ChatRequest(message="Was ist eine Dichtung?", session_id=session_id),
                current_user=user,
            ):
                chunks.append(chunk)

        asyncio.run(_run())

    content = "".join(chunks)
    # Find final payload
    final_payload = None
    for chunk in chunks:
        if chunk.startswith("data: ") and "version_provenance" in chunk:
            raw = chunk[len("data: "):].strip()
            try:
                parsed = json.loads(raw)
                if "version_provenance" in parsed:
                    final_payload = parsed
                    break
            except (json.JSONDecodeError, ValueError):
                continue

    assert final_payload is not None, "No SSE chunk with version_provenance found"
    vp = final_payload["version_provenance"]
    assert vp.get("policy_version") == INTERACTION_POLICY_VERSION
    assert "[DONE]" in content
