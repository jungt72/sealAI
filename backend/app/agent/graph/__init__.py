"""
backend/app/agent/graph — Phase F-C.1

New governed execution graph. Builds on the 4-layer Pydantic state from
state/models.py. Nodes have signature node(state: GraphState) → GraphState.

GraphState is the in-graph working state. It extends GovernedSessionState
with execution-context fields that are transient (not persisted to Redis):

    pending_message       — user message for the current turn (set by caller)
    rag_evidence          — evidence cards retrieved by evidence_node
    compute_results       — RWDR/calc results from compute_node
    output_reply          — assembled reply text (set by output_contract_node)
    output_response_class — outward response class string
    output_public         — public payload dict (only this surfaces in the API)
    output_answer_markdown — optional composed markdown answer (text-only)
    stream_visible_answer_composer — emits visible answer tokens through
                                     LangGraph custom stream events
    defer_visible_answer_composer — compatibility fallback for callers that
                                    intentionally compose outside the graph

Persistence: the caller strips execution-context fields before Redis save.
Use GovernedSessionState.model_validate(state.model_dump()) to extract
the persisted portion from a completed GraphState.

Architecture invariants enforced here:
  Invariant 4: LLM writes technical observations ONLY to ObservedState; the
               governed answer composer may write text-only answer_markdown.
  Invariant 8: Only output_public and explicit answer text surface in the API response.
"""
from __future__ import annotations

from typing import Any

from pydantic import Field

from app.agent.state.models import GovernedSessionState


class GraphState(GovernedSessionState):
    """Working state for the governed LangGraph pipeline.

    Extends GovernedSessionState with in-flight execution context.
    The four governed layers (observed / normalized / asserted / governance)
    are written only via the deterministic reducer chain — never directly.

    Execution-context fields are transient — set by the caller before graph
    invocation and cleared/ignored on Redis save.
    """

    tenant_id: str = Field(
        default="",
        description=(
            "Tenant identifier. Set by the caller before ainvoke(). "
            "Required for RAG retrieval — retrieve_with_tenant() aborts without it."
        ),
    )
    session_id: str = Field(
        default="",
        description="Session identifier for this governed run. Transient, not persisted.",
    )
    pending_message: str = Field(
        default="",
        description="User message for this turn. Set by the caller before ainvoke().",
    )
    v92_turn_boundary_decision: dict[str, Any] = Field(
        default_factory=dict,
        description="Canonical V9.2 turn-boundary decision for this invocation.",
    )
    v92_turn_envelope: dict[str, Any] = Field(
        default_factory=dict,
        description="Canonical V9.2 turn envelope created before graph execution.",
    )
    rag_evidence: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Evidence cards retrieved by evidence_node. Populated in-flight.",
    )
    rag_evidence_audit: dict[str, Any] = Field(
        default_factory=dict,
        description="Internal retrieval audit slice from evidence_node. Transient, not persisted.",
    )
    compute_results: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Deterministic compute results (RWDR etc) from compute_node.",
    )
    output_reply: str = Field(
        default="",
        description="Assembled reply text. Set by output_contract_node.",
    )
    output_response_class: str = Field(
        default="",
        description=(
            "Outward response class. One of: conversational_answer, "
            "structured_clarification, governed_state_update, technical_preselection, "
            "candidate_shortlist, inquiry_ready."
        ),
    )
    runtime_answer_mode: str = Field(
        default="",
        description="Answer mode selected by RuntimeAction for this invocation. Transient, not persisted.",
    )
    runtime_answer_mode_source: str = Field(
        default="",
        description="Source of runtime_answer_mode, usually runtime_action.answer_mode. Transient.",
    )
    output_public: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Final public payload. Only this dict surfaces in the API response. "
            "No internal state/governance artefacts (Invariant 8)."
        ),
    )
    output_answer_markdown: str = Field(
        default="",
        description="Optional composed answer markdown. Text-only, no governed truth.",
    )
    output_answer_markdown_source: str = Field(
        default="",
        description="Answer markdown source: deterministic_reply, governed_composer, or composer_fallback.",
    )
    governed_answer_prompt_trace: dict[str, Any] = Field(
        default_factory=dict,
        description="Hash-only prompt metadata for the governed answer composer. No rendered prompt text.",
    )
    governed_answer_composer_error: str = Field(
        default="",
        description="Safe composer fallback reason. No stack traces, secrets, prompts, or raw payloads.",
    )
    stream_visible_answer_composer: bool = Field(
        default=False,
        description=(
            "When true, governed_answer_composer_node streams visible answer "
            "tokens through LangGraph custom events while still writing the "
            "final validated answer_markdown into GraphState."
        ),
    )
    defer_visible_answer_composer: bool = Field(
        default=False,
        description=(
            "Compatibility fallback. When true, output_contract_node skips the "
            "graph-internal answer composer so legacy callers can compose the "
            "visible text outside the graph."
        ),
    )
