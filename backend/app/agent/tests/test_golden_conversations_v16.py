"""Patch 10 — V1.6 Golden Conversation regression suite (Blueprint §26/§27.5/§31).

One golden per scenario. Each test is marked:
  [E2E]      runs through the real pipeline (dispatch / override endpoint /
             RFQ brief endpoint) — the wires landed in Patch 9.5.
  [ISOLATED] exercises the canonical builder/contract directly, with a stated
             reason why the live path is not asserted here.

Test-only and additive. No production logic is changed; existing golden/scenario
suites are untouched.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.agent.api.dispatch import _MobileTriageFastResponse, _resolve_v8_turn_decision
from app.agent.api.loaders import (
    _load_live_governed_state,
    persist_mobile_triage_pending_question,
)
from app.agent.api.models import ChatRequest, OverrideItem, OverrideRequest
from app.agent.api.router import _resolve_runtime_dispatch, session_override_endpoint
from app.agent.api.sse_contract import SSEEventBuilder
from app.agent.api.streaming import _stream_fast_response
from app.agent.api.routes.chat import _rwdr_p0_leakage_guidance_reply
from app.agent.runtime.conversation_runtime import run_conversation
from app.agent.communication.knowledge_modes import (
    apply_knowledge_turn,
    resolve_knowledge_mode,
)
from app.agent.communication.mobile_triage import (
    build_mobile_leakage_triage,
    build_visual_low_confidence_guidance,
    mobile_triage_pending_question,
)
from app.agent.communication.rfq_one_pager import (
    RFQ_READINESS_DRAFT,
    RFQ_READINESS_WITH_OPEN_POINTS,
    evaluate_rfq_readiness,
)
from app.agent.graph.slot_answer_binding import resolve_slot_answer_binding
from app.agent.state.models import GovernedSessionState, PendingQuestion
from app.agent.templates.no_go_guard import (
    FORBIDDEN_NORMAL_TURN_PHRASES,
    detect_no_go_phrases,
)
from app.agent.templates.registry import render_chat_reply
from app.agent.v92.dashboard_contract import extract_case_revision
from app.services.auth.dependencies import RequestUser
from app.services.pre_gate_classifier import PreGateClassifier
from app.services.rwdr_mvp_brief import (
    build_rwdr_p0_leakage_guidance,
    build_rwdr_p0_pocket_cockpit_patch,
)


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="tester",
        sub="user-1",
        roles=[],
        scopes=[],
        tenant_id="tenant-1",
    )


class _FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def __aenter__(self):  # noqa: ANN204
        return self

    async def __aexit__(self, *_a) -> bool:
        return False

    async def set(self, key: str, value: str, *, ex: int | None = None) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)


class _FakeRedisFactory:
    def __init__(self, client: _FakeRedisClient) -> None:
        self._client = client

    def from_url(self, *_a, **_k) -> _FakeRedisClient:
        return self._client


@pytest.fixture
def _override_env(monkeypatch: pytest.MonkeyPatch) -> _FakeRedisClient:
    fake = _FakeRedisClient()
    monkeypatch.setenv("REDIS_URL", "redis://fake")
    import redis.asyncio as redis_asyncio

    monkeypatch.setattr(redis_asyncio, "Redis", _FakeRedisFactory(fake))
    import app.agent.api.loaders as loaders_module

    async def _skip(*_a, **_k):
        return None

    monkeypatch.setattr(loaders_module, "save_governed_state_snapshot_async", _skip)
    return fake


# === Golden A — RWDR 45x62x8 Getriebe Öl 1500 rpm Staub undicht =============


@pytest.mark.asyncio
async def test_golden_rwdr_case_recognized_no_final_release() -> None:
    # [E2E] real /rwdr/brief endpoint.
    from app.api.v1.endpoints.rfq import RwdrBriefRequest, generate_rwdr_brief

    result = await generate_rwdr_brief(
        body=RwdrBriefRequest(
            raw_inquiry="RWDR 45x62x8, Getriebe, Öl, 1500 rpm, staubig, undicht",
            fields=[],
        ),
        user=_user(),
    )
    blob = str(result)
    assert "45" in blob and "62" in blob  # recognized dimensions surfaced
    assert result["no_final_technical_release"] is True
    assert "keine finale" in result["disclaimer"].lower()


def test_golden_rwdr_chat_reply_is_not_an_ai_protocol() -> None:
    # [ISOLATED] senior_engineer_short style — the full governed chat wording is
    # produced deep in the runtime; the style contract is the No-Go boundary.
    reply = render_chat_reply(
        "senior_engineer_short",
        {
            "opening": "Okay, damit kann man arbeiten.",
            "technical_hint": "Bei einem undichten Altteil zuerst die Wellenlauffläche prüfen.",
            "primary_question": "Siehst du auf der Welle eine Rille, Korrosion oder eine blanke Spur?",
        },
    )
    assert detect_no_go_phrases(reply.markdown, FORBIDDEN_NORMAL_TURN_PHRASES) == []
    assert (
        reply.disclaimer_mode == "suppress_normal_turn"
    )  # no liability block in a normal turn


# === Golden G — Mobile Foto + "sifft" ======================================


@pytest.mark.asyncio
async def test_golden_mobile_foto_sifft_immediate_pocket_output() -> None:
    # [E2E] real dispatch (Patch 9.5 wire 2).
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="sifft", session_id="g-mobile", has_attachment=True),
        current_user=_user(),
    )
    assert dispatch.gate_reason == "mobile_leakage_triage"
    envelope = dispatch.fast_response.mobile_triage_envelope
    assert envelope["pocket_cockpit_patch"]["next_step"]  # pocket-first output
    assert envelope["action_chips"]  # action chips offered
    assert (
        envelope["trace"]["rag_used"] is False
        and envelope["trace"]["graph_used"] is False
    )


def test_golden_mobile_triage_builder_offers_chips() -> None:
    # [ISOLATED] confirms the chip labels of the immediate triage envelope.
    envelope = build_mobile_leakage_triage(has_attachment=True)
    assert [c.label for c in envelope.action_chips][:3] == [
        "Ja",
        "Nein",
        "Weiß ich nicht",
    ]


# === Golden H — Low-confidence photo → measurement guidance =================


def test_golden_low_confidence_photo_gives_guidance_not_identification() -> None:
    # [ISOLATED] vision backend is optional/deferred (Patch 6); the guidance
    # builder is the contract for an unreadable photo.
    envelope = build_visual_low_confidence_guidance()
    md = envelope.chat_reply.markdown
    assert "messe" in md.lower() or "miss" in md.lower()
    for forbidden in ("Das ist sicher ein", "Material ist", "Artikelnummer ist"):
        assert forbidden not in md


# === Golden B — pending slot "jo ca 3000" ==================================


def test_golden_pending_slot_tolerant_parse() -> None:
    # [ISOLATED] deterministic Tier-0 binder (no RAG/graph by construction).
    binding = resolve_slot_answer_binding(
        pending_question=PendingQuestion(
            target_field="speed_rpm",
            expected_answer_type="rotational_speed_value",
            status="open",
        ),
        message="jo ca 3000",
        turn_index=1,
    )
    assert (
        binding is not None
        and binding.normalized_value == 3000.0
        and binding.approximate is True
    )


# === Golden C — why-question (no mutation) ==================================


def test_golden_why_question_no_mutation() -> None:
    # [ISOLATED] knowledge mode contract; case_revision must be unchanged.
    state = GovernedSessionState()
    mode = resolve_knowledge_mode(
        "Warum fragst du nach der Welle?", has_active_case=True
    )
    result = apply_knowledge_turn(
        state, "Warum fragst du nach der Welle?", has_active_case=True
    )
    assert mode == "why_question_active_case"
    assert result is state and extract_case_revision(result) == extract_case_revision(
        state
    )


# === Golden D/E/F — knowledge modes =========================================


def test_golden_knowledge_general_no_mutation() -> None:
    # [ISOLATED]
    state = GovernedSessionState()
    assert (
        resolve_knowledge_mode("Was ist FFKM?", has_active_case=False)
        == "knowledge_general"
    )
    assert apply_knowledge_turn(state, "Was ist FFKM?", has_active_case=False) is state


def test_golden_knowledge_case_aware_no_mutation() -> None:
    # [ISOLATED]
    state = GovernedSessionState()
    assert (
        resolve_knowledge_mode("Was bedeutet FKM in meinem Fall?", has_active_case=True)
        == "knowledge_case_aware"
    )
    assert (
        apply_knowledge_turn(
            state, "Was bedeutet FKM in meinem Fall?", has_active_case=True
        )
        is state
    )


def test_golden_knowledge_case_mutating_applies_only_supplied_facts() -> None:
    # [ISOLATED] only the new facts flow through the State Gate.
    state = GovernedSessionState()
    result = apply_knowledge_turn(
        state, "Wir verwenden FKM, Öltemperatur 100 °C", has_active_case=True
    )
    assert result is not state
    assert result.normalized.parameters["temperature_c"].value == 100


# === Golden I/J — sheet field edit / bulk input =============================


@pytest.mark.asyncio
async def test_golden_sheet_field_edit_temp_90(_override_env: _FakeRedisClient) -> None:
    # [E2E] real override endpoint (Patch 9.5 wire 3).
    response = await session_override_endpoint(
        session_id="g-sheet",
        request=OverrideRequest(
            overrides=[OverrideItem(field_name="temperature_c", value=90, unit="°C")],
            client_event_id="g-sheet-1",
        ),
        current_user=_user(),
    )
    assert response.applied_fields == ["temperature_c"]
    from app.agent.state.persistence import load_governed_state_async

    persisted = await load_governed_state_async(
        tenant_id="tenant-1", session_id="g-sheet", redis_client=_override_env
    )
    assert persisted.normalized.parameters["temperature_c"].value == 90


@pytest.mark.asyncio
async def test_golden_sheet_bulk_input(_override_env: _FakeRedisClient) -> None:
    # [E2E] real override endpoint.
    response = await session_override_endpoint(
        session_id="g-bulk",
        request=OverrideRequest(
            overrides=[
                OverrideItem(field_name="speed_rpm", value=3000),
                OverrideItem(field_name="temperature_c", value=90, unit="°C"),
                OverrideItem(field_name="medium", value="Öl"),
            ],
            client_event_id="g-bulk-1",
        ),
        current_user=_user(),
    )
    assert set(response.applied_fields) == {"speed_rpm", "temperature_c", "medium"}


# === Golden K — smalltalk (no case) =========================================


@pytest.mark.asyncio
async def test_golden_smalltalk_no_case() -> None:
    # [E2E] real dispatch — greeting routes to the fast path, no governed case.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Hallo", session_id="g-smalltalk"),
        current_user=_user(),
    )
    assert dispatch.pre_gate_classification == "GREETING"
    assert dispatch.runtime_mode == "CONVERSATION"
    assert dispatch.gate_applied is False


# === Golden L — final approval request (bounded) ============================


def test_golden_final_approval_is_bounded() -> None:
    # [ISOLATED] the governed boundary wording is produced deep in the runtime;
    # the blocked_boundary template is the contract for the bounded reply.
    reply = render_chat_reply(
        "blocked_boundary",
        {
            "boundary_statement": "Das kann ich nicht seriös als Garantie freigeben.",
            "constructive_alternative": "Ich kann den Fall für eine Herstellerbewertung vorbereiten.",
            "offer_question": "Soll ich daraus einen Technical RFQ Brief erstellen?",
        },
    )
    assert reply.disclaimer_mode == "explicit_boundary_required"
    # No affirmative suitability/release claim slipped in.
    assert detect_no_go_phrases(reply.markdown, (), include_final_release=True) == []


# === Golden M/N — RFQ with open points / RFQ DRAFT ==========================


@pytest.mark.asyncio
async def test_golden_rfq_draft_insufficient_core_names_minimum() -> None:
    # [E2E] real /rwdr/brief endpoint — too thin → DRAFT, names minimum input.
    from app.api.v1.endpoints.rfq import RwdrBriefRequest, generate_rwdr_brief

    result = await generate_rwdr_brief(
        body=RwdrBriefRequest(raw_inquiry="Dichtung undicht.", fields=[]),
        user=_user(),
    )
    readiness = result["rfq_readiness"]
    assert readiness["status"] == RFQ_READINESS_DRAFT
    assert readiness["can_generate_brief"] is False
    assert readiness["minimum_needed"]  # explicitly names what is missing


def test_golden_rfq_with_open_points_when_core_present() -> None:
    # [ISOLATED] request_goal is supplied by the RFQ intent, not raw-text
    # extraction; the readiness contract is asserted directly.
    readiness = evaluate_rfq_readiness(
        [
            "sealing_function",
            "shaft_diameter_d1_mm",
            "housing_bore_D_mm",
            "seal_width_b_mm",
            "application",
            "inside_medium",
            "request_goal",
        ],
        missing_fields=["shaft_condition_known", "temperature_max_c"],
    )
    assert readiness.status == RFQ_READINESS_WITH_OPEN_POINTS
    assert readiness.can_generate_brief is True
    assert "shaft_condition_known" in readiness.open_points_critical


# === Golden O — complex_review_required / out-of-scope (high risk) ==========


@pytest.mark.asyncio
async def test_golden_out_of_scope_high_risk_blocked() -> None:
    # [E2E] real /rwdr/brief endpoint — ATEX is out of the RWDR-MVP scope.
    from app.api.v1.endpoints.rfq import RwdrBriefRequest, generate_rwdr_brief

    result = await generate_rwdr_brief(
        body=RwdrBriefRequest(
            raw_inquiry="RWDR im ATEX-Bereich, explosionsgeschützt, finale Designfreigabe gewünscht",
            fields=[],
        ),
        user=_user(),
    )
    assert result["status"] == "OUT_OF_SCOPE"
    assert result["no_final_technical_release"] is True


# === Patch 2 — P0 RWDR killer-flow live-path baseline ======================
#
# Killer input (Blueprint P0 §26): the single message that must "just work".
# These tests pin what the CURRENT live backend paths actually do with it, so
# later patches can change behavior deliberately instead of breaking a contract
# by accident. They assert CURRENT behavior, not the V1.6 target. Each test
# names the live path it exercises:
#   [LIVE-DISPATCH]  _resolve_runtime_dispatch — the real pre-gate router that
#                    every chat turn enters first.
#   [LIVE-RFQ-API]   generate_rwdr_brief — the real POST /api/v1/rfq/rwdr/brief
#                    handler (same path Golden A uses).
#   [LIVE-DECISION]  _resolve_v8_turn_decision — the turn/slot decision seam the
#                    dispatch path calls for DOMAIN_INQUIRY turns. Used here
#                    because a full pending-slot dispatch round-trip needs a
#                    Redis-persisted pending question; the decision seam is the
#                    offline-deterministic live equivalent.
# No isolated builder is asserted here unless a live path has no equivalent.

_P0_KILLER_INPUT = "RWDR 45x62x8, Getriebe, Öl, 1500 rpm, staubig, undicht."


def _dispatch_emitted_text(dispatch) -> str:
    """Concatenate every outward-facing text a dispatch resolution can carry."""

    parts = [
        dispatch.direct_reply,
        dispatch.rfq_response,
        getattr(dispatch.fast_response, "content", None),
        getattr(dispatch.knowledge_response, "content", None),
        getattr(dispatch.knowledge_response, "answer_markdown", None),
    ]
    return " ".join(str(part) for part in parts if part)


@pytest.mark.asyncio
async def test_p0_killer_flow_routed_to_governed_case_not_smalltalk() -> None:
    # [LIVE-DISPATCH] The killer message is a concrete RWDR application, so the
    # router must treat it as case-building (GOVERNED), never as smalltalk.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message=_P0_KILLER_INPUT, session_id=None),
        current_user=_user(),
    )
    # (1) technical RWDR / case-building intent, not smalltalk/knowledge/RFQ.
    assert dispatch.pre_gate_classification == "DOMAIN_INQUIRY"
    assert dispatch.gate_route == "GOVERNED"
    assert dispatch.runtime_mode == "GOVERNED"
    assert dispatch.pre_gate_classification != "GREETING"
    action_mode = getattr(dispatch.runtime_action, "answer_mode", None)
    assert getattr(action_mode, "value", action_mode) == "governed_intake"
    assert getattr(dispatch.runtime_action, "graph_allowed", None) is True
    # (2) The router itself emits no outward text, so it cannot leak a final
    # suitability / guarantee / release claim — the governed graph + final guard
    # own all wording downstream. Lock that the router stays silent here.
    assert _dispatch_emitted_text(dispatch) == ""
    assert detect_no_go_phrases("", include_final_release=True) == []
    # No case is created or mutated by the router for this turn (session_id=None
    # → no governed state is loaded or persisted at the dispatch layer).
    assert dispatch.governed_state is None
    # CURRENT GAP (documented, intentionally not asserted as a feature): the
    # router does not itself extract 45x62x8, compute circumferential speed, or
    # surface the shaft/counterface review flag. Those are produced downstream
    # (governed graph) and in the RFQ brief path — see the next two tests.


@pytest.mark.asyncio
async def test_p0_killer_flow_brief_preserves_core_facts_and_boundary() -> None:
    # [LIVE-RFQ-API] real POST /rwdr/brief handler with raw inquiry only.
    from app.api.v1.endpoints.rfq import RwdrBriefRequest, generate_rwdr_brief

    result = await generate_rwdr_brief(
        body=RwdrBriefRequest(raw_inquiry=_P0_KILLER_INPUT, fields=[]),
        user=_user(),
    )
    blob = str(result)
    flags = result["engineering_review_flags"]

    # (1) Recognized as an RWDR case needing clarification (not smalltalk, not
    # out-of-scope, not COMPLETE on raw unconfirmed text).
    assert result["status"] == "NEEDS_CLARIFICATION"

    # (2) No final suitability / guarantee / compliance / release claim.
    assert result["no_final_technical_release"] is True
    assert "keine finale" in result["disclaimer"].lower()
    assert "final engineering release" in result["claim_boundary"]["forbidden"]
    assert "compliance claim" in result["claim_boundary"]["forbidden"]

    # (3) Core extracted facts the live path supports are preserved/surfaced:
    #   - RWDR / radial-shaft-seal candidate recognized
    assert "radial_shaft_seal" in blob
    assert "rwdr_generic_term_normalized" in flags
    #   - 45x62x8 dimensions surfaced
    assert "45" in blob and "62" in blob
    #   - leakage ("undicht") signal recognized
    assert "leakage" in blob
    assert "leakage_failure_intent" in flags
    #   - dusty environment supported as a review topic
    assert "dust" in blob
    assert "dust_lip_or_excluder_review_required" in flags
    # NOTE on current behavior: at this unconfirmed stage the brief normalizes
    # rather than echoes — "Getriebe", verbatim "1500 rpm", and the literal word
    # "undicht" are not echoed in the brief payload; only review-relevant signals
    # surface. Documented, not asserted as a target.

    # (5) Expert shaft / counterface review topic IS exposed by the RFQ brief
    # path (it is the chat/dispatch layer that does not surface it — see test 1).
    assert "shaft_surface_review_required" in flags

    # (4) CURRENT GAP — circumferential speed is NOT computed from raw text.
    # The extracted rpm/d1 are unconfirmed candidates, so the
    # EvidenceConfirmationIntelligence gate keeps them out of the calculation:
    # v = pi * d1 * rpm / 60000 is skipped and rpm stays a critical open point.
    computed = result["evaluation"]["computed_values"]
    speed_class = next(
        (c["value"] for c in computed if c.get("field") == "speed_class"), None
    )
    assert speed_class == "unknown"
    assert not any(c.get("field") == "circumferential_speed_mps" for c in computed)
    assert "critical_missing_max_speed_rpm" in flags
    # V1.6 may surface a screening speed from unconfirmed candidates; that is the
    # behavior a later patch can add. The next test proves the calc seam itself
    # is live and correct once the facts are confirmed.


@pytest.mark.asyncio
async def test_p0_circumferential_speed_computed_once_facts_confirmed() -> None:
    # [LIVE-RFQ-API] same handler, but d1 and rpm arrive as confirmed fields —
    # the realistic state after the user confirms the extracted values. The only
    # required MVP calculation (circumference speed) must then be exact.
    from app.api.v1.endpoints.rfq import RwdrBriefRequest, generate_rwdr_brief

    def _confirmed(field: str, value: float, unit: str) -> dict:
        return {
            "field": field,
            "value": value,
            "unit": unit,
            "confirmation_status": "confirmed",
            "status": "confirmed",
            "validation_status": "confirmed",
            "source_type": "user_text",
        }

    result = await generate_rwdr_brief(
        body=RwdrBriefRequest(
            raw_inquiry=_P0_KILLER_INPUT,
            fields=[
                _confirmed("shaft_diameter_d1_mm", 45, "mm"),
                _confirmed("max_speed_rpm", 1500, "rpm"),
            ],
        ),
        user=_user(),
    )
    computed = result["evaluation"]["computed_values"]
    circ = next(
        (c for c in computed if c.get("field") == "circumferential_speed_mps"), None
    )
    assert circ is not None
    # v = pi * 45 * 1500 / 60000 = 3.53 m/s
    assert circ["value"] == 3.53
    assert circ["formula"] == "v = pi * d1_mm * rpm / 60000"
    assert circ["not_for_final_technical_release"] is True


@pytest.mark.asyncio
async def test_p0_guarantee_question_routes_governed_without_guarantee_claim() -> None:
    # [LIVE-DISPATCH] "Which seal fits guaranteed?" — a guarantee-seeking turn.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="Welche Dichtung passt garantiert?", session_id=None),
        current_user=_user(),
    )
    # No guarantee / final-release claim is produced: the router emits no outward
    # text and defers to governed handling. It must NOT be answered as smalltalk
    # or a knowledge response (which could leak an unguarded answer).
    assert _dispatch_emitted_text(dispatch) == ""
    assert (
        detect_no_go_phrases(
            _dispatch_emitted_text(dispatch), include_final_release=True
        )
        == []
    )
    assert dispatch.fast_response is None
    assert dispatch.knowledge_response is None
    # CURRENT behavior: the ambiguous guarantee question is fail-safe routed to
    # the governed graph (the manufacturer-review / boundary wording is produced
    # downstream — see test_golden_final_approval_is_bounded). The router does
    # not itself emit the manufacturer-review redirect text.
    assert dispatch.runtime_mode == "GOVERNED"
    assert "ambiguous_fail_safe_domain_inquiry" in dispatch.gate_reason
    # No state mutation at the dispatch layer (session_id=None).
    assert dispatch.governed_state is None


@pytest.mark.asyncio
async def test_p0_pending_speed_slot_answer_recognized_live() -> None:
    # [LIVE-DECISION] After the assistant asked for rpm/speed, "jo ca 3000" is a
    # tolerant approximate slot answer. The decision seam the dispatch path uses
    # must treat it as a pending-slot answer — not a new case, not smalltalk.
    state = GovernedSessionState()
    state.pending_question = PendingQuestion(
        target_field="speed_rpm",
        expected_answer_type="rotational_speed_value",
        status="open",
    )
    pre_gate = PreGateClassifier().classify("jo ca 3000")
    turn_decision = await _resolve_v8_turn_decision(
        request=ChatRequest(message="jo ca 3000", session_id=None),
        pre_gate=pre_gate,
        governed_state=state,
    )
    answer_mode = getattr(turn_decision, "answer_mode", None)
    assert getattr(answer_mode, "value", answer_mode) == "pending_slot_answer"
    # The normalized approximate value (3000.0, approximate=True) is locked by the
    # deterministic binder in test_golden_pending_slot_tolerant_parse; this test
    # only proves the live decision seam routes the answer to the slot, not a new
    # case. CURRENT GAP: the full dispatch round-trip needs a Redis-persisted
    # pending question, so the offline live assertion stops at the decision seam.


# === Patch 3 — P0 RWDR leakage guidance in the live chat path ==============
#
# The killer input now surfaces one deterministic senior-engineer review hint
# (shaft / counterface / Wellenlauffläche) plus exactly one next question in the
# live chat reply, instead of a generic intake invite. The live JSON chat path
# for a governed-intake domain turn is:
#   chat_endpoint -> _run_conversation_first_with_engine_sidecar
#                 -> direct_reply = _rwdr_p0_leakage_guidance_reply(...) or invite
#                 -> _run_light_chat_response(mode="EXPLORATION", direct_reply=...)
#                 -> run_conversation(..., direct_reply=...)   # verbatim, no LLM
# These tests assert on that real downstream surface (the chat seam + the
# conversation renderer), not on the router, which still emits no text.


@pytest.mark.asyncio
async def test_p0_killer_flow_live_reply_surfaces_shaft_counterface_guidance() -> None:
    # [LIVE-CHAT] real dispatch -> chat guidance seam -> conversation renderer.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message=_P0_KILLER_INPUT, session_id=None),
        current_user=_user(),
    )
    direct_reply = _rwdr_p0_leakage_guidance_reply(
        pre_gate_classification=dispatch.pre_gate_classification,
        runtime_action=dispatch.runtime_action,
        message=_P0_KILLER_INPUT,
    )
    # The governed-intake domain turn selects the deterministic guidance, not the
    # generic open invite.
    assert direct_reply is not None

    # Render through the exact visible-reply path the live light/exploration
    # runtime uses (direct_reply short-circuits the LLM -> deterministic).
    result = await run_conversation(
        _P0_KILLER_INPUT,
        history=[],
        case_summary=None,
        mode="EXPLORATION",
        direct_reply=direct_reply,
    )
    reply = result.reply_text

    # (2) The shaft / running-surface review hint is present.
    assert "Wellenlauffläche" in reply
    assert "Rille" in reply and "Korrosion" in reply
    assert "eingelaufene Spur" in reply
    # (3) Exactly one primary question is asked.
    assert reply.count("?") == 1
    assert "Dichtlippenstelle" in reply  # the shaft/counterface question
    # The full case is not repeated (no dimension/rpm dump in the hint reply).
    assert "45x62x8" not in reply and "1500" not in reply
    # (4) No final suitability / guarantee / compliance / release wording.
    assert detect_no_go_phrases(reply, include_final_release=True) == []
    for forbidden in ("garantiert", "freigegeben", "geeignet", "zugelassen"):
        assert forbidden not in reply.casefold()


@pytest.mark.asyncio
async def test_p0_leakage_guidance_does_not_affect_smalltalk_or_ui_help() -> None:
    # [LIVE-CHAT] (5) Smalltalk and generic UI help must be untouched: the seam
    # only fires on a governed-intake domain turn carrying an RWDR leakage signal.
    greeting = await _resolve_runtime_dispatch(
        ChatRequest(message="Hallo", session_id=None),
        current_user=_user(),
    )
    assert greeting.pre_gate_classification == "GREETING"
    assert (
        _rwdr_p0_leakage_guidance_reply(
            pre_gate_classification=greeting.pre_gate_classification,
            runtime_action=greeting.runtime_action,
            message="Hallo",
        )
        is None
    )
    # Even on a domain turn, a non-RWDR / UI-help message does not trigger it.
    domain_action = (
        await _resolve_runtime_dispatch(
            ChatRequest(message=_P0_KILLER_INPUT, session_id=None),
            current_user=_user(),
        )
    ).runtime_action
    assert (
        _rwdr_p0_leakage_guidance_reply(
            pre_gate_classification="DOMAIN_INQUIRY",
            runtime_action=domain_action,
            message="Wie kann ich die Tabelle im Dashboard exportieren?",
        )
        is None
    )


def test_rwdr_p0_leakage_guidance_builder_is_deterministic() -> None:
    # [LIVE-RWDR-SERVICE] the deterministic guidance source the chat seam reuses.
    guidance = build_rwdr_p0_leakage_guidance(_P0_KILLER_INPUT)
    assert guidance is not None
    # One hint + exactly one question.
    assert "Wellenlauffläche" in guidance.review_hint
    assert guidance.reply_markdown().count("?") == 1
    # Canonical review flags (no parallel vocabulary); dusty env only adds a flag.
    assert "shaft_surface_review_required" in guidance.review_flags
    assert "leakage_failure_intent" in guidance.review_flags
    assert "dust_lip_or_excluder_review_required" in guidance.review_flags

    # Boundaries: needs an RWDR seal signal AND a leakage/replacement intent.
    assert build_rwdr_p0_leakage_guidance("Was ist FFKM?") is None
    assert build_rwdr_p0_leakage_guidance("RWDR 45x62x8, Getriebe, Öl") is None
    assert build_rwdr_p0_leakage_guidance("RWDR Austausch gesucht") is not None
    # Dust without a second question: a dusty leakage turn still asks exactly one.
    dusty = build_rwdr_p0_leakage_guidance("Wellendichtring undicht, sehr staubig")
    assert dusty is not None and dusty.reply_markdown().count("?") == 1


# === Patch 8 — Mobile triage action-chip answers resolve through chat ======
#
# After Patch 7 the frontend sends chip clicks as plain chat text ("Ja" / "Nein"
# / "Weiß ich nicht"). The backend must interpret those as answers to the active
# mobile triage question ("Dreht sich die Welle im Betrieb?") via the EXISTING
# pending-slot machinery — never as smalltalk, a new case, or invented truth.
# Seams (deterministic, offline):
#   [RWDR-SERVICE]  mobile_triage_pending_question — the pending-slot context.
#   [SLOT-BINDER]   resolve_slot_answer_binding — binds yes/no/unknown.
#   [LIVE-DECISION] _resolve_v8_turn_decision — the decision the dispatch uses
#                   for these DOMAIN_INQUIRY turns.
#
# NOTE on the live wire: "Ja"/"Nein"/"Weiß ich nicht" already classify as
# DOMAIN_INQUIRY (not smalltalk), so they reach _resolve_v8_turn_decision today.
# Persisting the pending question into the no-case mobile fast turn is the only
# remaining wire (kept out of this patch to avoid I/O on the instant fast path).


def _mobile_triage_state() -> GovernedSessionState:
    state = GovernedSessionState()
    state.pending_question = mobile_triage_pending_question()
    return state


def test_mobile_triage_exposes_pending_question_context() -> None:
    # (1) The triage turn exposes an active/pending question for shaft rotation.
    pending = mobile_triage_pending_question()
    assert pending.target_field == "shaft_rotates"
    assert pending.expected_answer_type == "yes_no_unknown"
    assert pending.status == "open"
    assert pending.question_text == "Dreht sich die Welle im Betrieb?"

    envelope = build_mobile_leakage_triage(has_attachment=True).model_dump(mode="json")
    assert envelope["pending_question"]["field"] == "shaft_rotates"
    answer_chips = [
        c for c in envelope["action_chips"] if c.get("field") == "shaft_rotates"
    ]
    assert {c["value"] for c in answer_chips} == {"yes", "no", "unknown"}


def test_mobile_triage_yes_no_unknown_bind_to_shaft_rotates() -> None:
    # (2)/(3)/(4) The existing slot binder resolves the chip-text answers.
    pending = mobile_triage_pending_question()
    cases = {"Ja": "yes", "Nein": "no", "Weiß ich nicht": "unknown"}
    for message, expected in cases.items():
        binding = resolve_slot_answer_binding(
            pending_question=pending, message=message, turn_index=1
        )
        assert binding is not None, message
        assert binding.target_field == "shaft_rotates"
        assert binding.normalized_value == expected
        assert binding.source == "pending_question"  # State Gate still owns persistence


@pytest.mark.asyncio
async def test_mobile_triage_answer_routed_as_pending_slot_answer_not_smalltalk() -> (
    None
):
    # [LIVE-DECISION] (2)/(3)/(4) With the triage context, the runtime decision
    # the dispatch uses routes each answer as a pending-slot answer — not
    # smalltalk and not a new case.
    for message in ("Ja", "Nein", "Weiß ich nicht"):
        pre_gate = PreGateClassifier().classify(message)
        # The text is treated as a domain turn, never a greeting/smalltalk.
        assert pre_gate.classification.value == "DOMAIN_INQUIRY", message
        decision = await _resolve_v8_turn_decision(
            request=ChatRequest(message=message, session_id=None),
            pre_gate=pre_gate,
            governed_state=_mobile_triage_state(),
        )
        answer_mode = getattr(decision, "answer_mode", None)
        assert (
            getattr(answer_mode, "value", answer_mode) == "pending_slot_answer"
        ), message


@pytest.mark.asyncio
async def test_bare_yes_without_triage_context_creates_no_truth() -> None:
    # (5) Without a pending triage question, bare "Ja" must not bind a slot or
    # invent a fact — it stays generic governed intake.
    assert (
        resolve_slot_answer_binding(pending_question=None, message="Ja", turn_index=1)
        is None
    )
    decision = await _resolve_v8_turn_decision(
        request=ChatRequest(message="Ja", session_id=None),
        pre_gate=PreGateClassifier().classify("Ja"),
        governed_state=GovernedSessionState(),
    )
    answer_mode = getattr(decision, "answer_mode", None)
    assert getattr(answer_mode, "value", answer_mode) != "pending_slot_answer"
    assert getattr(decision, "slot_answer_binding", None) is None


def test_mobile_triage_output_makes_no_release_claim() -> None:
    # (6) The immediate triage output carries no final suitability / guarantee /
    # compliance / release wording.
    envelope = build_mobile_leakage_triage(has_attachment=True)
    reply = envelope.chat_reply.markdown
    assert detect_no_go_phrases(reply, include_final_release=True) == []


def test_existing_speed_slot_answer_still_binds_after_yes_no_unknown_adapter() -> None:
    # (7) The "jo ca 3000" tolerant numeric binding is unaffected by the new
    # yes/no/unknown adapter.
    binding = resolve_slot_answer_binding(
        pending_question=PendingQuestion(
            target_field="speed_rpm",
            expected_answer_type="rotational_speed_value",
            status="open",
        ),
        message="jo ca 3000",
        turn_index=1,
    )
    assert (
        binding is not None
        and binding.normalized_value == 3000.0
        and binding.approximate is True
    )


# === Patch 9 — Mobile triage pending question bridged across the live turn ==
#
# Closes the Patch 8 chain end-to-end: the no-case mobile triage fast turn now
# persists its pending question (Redis-only, tenant/session-scoped, no DB case
# snapshot — the triage turn stays no-case) so the NEXT live turn loads it and
# the slot binder resolves "Ja"/"Nein"/"Weiß ich nicht". The bridge runs after
# the instant reply is sent and is fail-safe. No parallel state system, no State
# Gate bypass — it reuses the existing governed-state load/save helpers.


def _mobile_triage_fast_response() -> _MobileTriageFastResponse:
    envelope = build_mobile_leakage_triage(has_attachment=True)
    return _MobileTriageFastResponse(
        content=envelope.chat_reply.markdown,
        mobile_triage_envelope=envelope.model_dump(mode="json"),
    )


def _answer_mode_value(decision) -> str | None:
    mode = getattr(decision, "answer_mode", None)
    return str(getattr(mode, "value", mode)) if mode is not None else None


@pytest.mark.asyncio
async def test_mobile_triage_pending_question_bridges_to_next_turn(
    _override_env: _FakeRedisClient,
) -> None:
    # (1)/(2)/(3) End-to-end-ish: the triage turn persists the pending question;
    # the next turn loads it and resolves Ja/Nein/Weiß ich nicht via the existing
    # slot binder + runtime decision.
    persisted = await persist_mobile_triage_pending_question(
        current_user=_user(),
        session_id="m-bridge",
        fast_response=_mobile_triage_fast_response(),
    )
    assert persisted is True

    state = await _load_live_governed_state(
        current_user=_user(), session_id="m-bridge", create_if_missing=False
    )
    assert state is not None and state.pending_question is not None
    assert state.pending_question.target_field == "shaft_rotates"
    assert state.pending_question.expected_answer_type == "yes_no_unknown"

    cases = {"Ja": "yes", "Nein": "no", "Weiß ich nicht": "unknown"}
    for message, expected in cases.items():
        binding = resolve_slot_answer_binding(
            pending_question=state.pending_question, message=message, turn_index=1
        )
        assert binding is not None and binding.normalized_value == expected, message
        decision = await _resolve_v8_turn_decision(
            request=ChatRequest(message=message, session_id="m-bridge"),
            pre_gate=PreGateClassifier().classify(message),
            governed_state=state,
        )
        assert _answer_mode_value(decision) == "pending_slot_answer", message


@pytest.mark.asyncio
async def test_mobile_triage_bridge_is_tenant_and_session_scoped(
    _override_env: _FakeRedisClient,
) -> None:
    # (6) The bridged context is keyed by tenant + session — no cross-session or
    # cross-tenant leakage, so a bare "Ja" elsewhere has no pending context.
    await persist_mobile_triage_pending_question(
        current_user=_user(),
        session_id="m-scope-a",
        fast_response=_mobile_triage_fast_response(),
    )

    other_session = await _load_live_governed_state(
        current_user=_user(), session_id="m-scope-b", create_if_missing=False
    )
    assert other_session is None  # different session → no pending context

    other_tenant_user = RequestUser(
        user_id="user-2",
        username="t2",
        sub="user-2",
        roles=[],
        scopes=[],
        tenant_id="tenant-2",
    )
    other_tenant = await _load_live_governed_state(
        current_user=other_tenant_user, session_id="m-scope-a", create_if_missing=False
    )
    assert other_tenant is None  # different tenant → no pending context


@pytest.mark.asyncio
async def test_mobile_triage_bridge_is_fail_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The bridge never raises and only fires for a mobile triage fast response.
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert (
        await persist_mobile_triage_pending_question(
            current_user=_user(),
            session_id="m-nofx",
            fast_response=_mobile_triage_fast_response(),
        )
        is False  # no Redis → no-op, never raises
    )
    from types import SimpleNamespace

    monkeypatch.setenv("REDIS_URL", "redis://fake")
    assert (
        await persist_mobile_triage_pending_question(
            current_user=_user(),
            session_id="m-nonmobile",
            fast_response=SimpleNamespace(
                content="Hallo"
            ),  # not a mobile triage response
        )
        is False  # non-mobile fast response → no-op
    )


# === Patch 10 — Mobile P0 triage chain regression contract (backend) ========
#
# One end-to-end-ish backend test that walks the full mobile P0 chain across the
# real seams built in Patches 5/8/9, instead of repeating every unit detail:
#   dispatch mobile triage  →  SSE state_update carries the V1.6 envelope fields
#   →  pending question persisted (tenant/session-scoped)  →  next "Ja" resolves
#   as a pending_slot_answer  →  fresh/cross-session "Ja" creates no truth.
# The frontend half of the chain is covered by the route.spec.ts chain test.


def _sse_state_update_payload(frames: list[str]) -> dict:
    for frame in frames:
        if frame.startswith("data: {"):
            return json.loads(frame.removeprefix("data: ").strip())
    raise AssertionError("no state_update frame emitted")


@pytest.mark.asyncio
async def test_mobile_p0_triage_chain_backend_contract(
    _override_env: _FakeRedisClient,
) -> None:
    # 1) photo + "sifft" → dispatch returns the mobile triage fast response.
    dispatch = await _resolve_runtime_dispatch(
        ChatRequest(message="sifft", session_id="m-chain", has_attachment=True),
        current_user=_user(),
    )
    assert isinstance(dispatch.fast_response, _MobileTriageFastResponse)

    # 2) SSE state_update carries assistant_turn_envelope + pocket_cockpit_patch
    #    + action_chips additively (Patch 5), and still terminates with [DONE].
    frames = [
        frame
        async for frame in _stream_fast_response(
            request=SimpleNamespace(session_id="m-chain", message="sifft"),
            fast_response=dispatch.fast_response,
            event_builder=SSEEventBuilder(turn_id="t-chain"),
        )
    ]
    assert frames[-1] == "data: [DONE]\n\n"
    data = _sse_state_update_payload(frames)["data"]
    assert "assistant_turn_envelope" in data
    assert data["pocket_cockpit_patch"]
    assert {
        c["value"] for c in data["action_chips"] if c.get("field") == "shaft_rotates"
    } == {
        "yes",
        "no",
        "unknown",
    }

    # 3) The triage turn persists its pending question, tenant/session-scoped
    #    (Patch 9), with no cross-session leakage.
    assert (
        await persist_mobile_triage_pending_question(
            current_user=_user(),
            session_id="m-chain",
            fast_response=dispatch.fast_response,
        )
        is True
    )
    state = await _load_live_governed_state(
        current_user=_user(), session_id="m-chain", create_if_missing=False
    )
    assert state is not None and state.pending_question is not None
    assert state.pending_question.target_field == "shaft_rotates"

    # 4) The next chat turn "Ja" resolves as a pending_slot_answer for
    #    shaft_rotates=yes through the existing slot machinery (Patch 8).
    decision = await _resolve_v8_turn_decision(
        request=ChatRequest(message="Ja", session_id="m-chain"),
        pre_gate=PreGateClassifier().classify("Ja"),
        governed_state=state,
    )
    assert _answer_mode_value(decision) == "pending_slot_answer"
    binding = resolve_slot_answer_binding(
        pending_question=state.pending_question, message="Ja", turn_index=1
    )
    assert binding is not None and binding.normalized_value == "yes"

    # 5) A fresh / cross-session "Ja" has no pending context and creates no truth.
    assert (
        await _load_live_governed_state(
            current_user=_user(), session_id="m-chain-other", create_if_missing=False
        )
        is None
    )
    assert (
        resolve_slot_answer_binding(pending_question=None, message="Ja", turn_index=1)
        is None
    )


# === Patch 11 — Backend-owned Pocket Cockpit for the governed RWDR P0 text ===
#
# The governed RWDR P0 text case now emits a deterministic backend-owned
# pocket_cockpit_patch (a projection of candidate facts + the shaft/counterface
# review, never confirmed truth). This test pins the projection content; the SSE
# serialization is pinned in test_sse_event_contract.py.


def test_rwdr_p0_pocket_cockpit_patch_projection() -> None:
    result = build_rwdr_p0_pocket_cockpit_patch(_P0_KILLER_INPUT)
    assert result is not None
    patch, chips = result
    data = patch.model_dump(mode="json")

    # (2) recognized: RWDR leakage case + candidate facts (never confirmed).
    recognized = {item["label"]: item for item in data["recognized"]}
    assert "RWDR-Leckage" in recognized["Fall"]["value"]
    assert recognized["Maße"]["value"] == "45x62x8"
    assert recognized["Anwendung"]["value"] == "Getriebe"
    assert recognized["Medium"]["value"] == "Öl"
    assert all(item["status"] == "candidate" for item in data["recognized"])

    # (2) critical: shaft running surface review + dust/excluder review.
    critical_labels = {item["label"] for item in data["critical"]}
    assert any("Wellenlauffläche" in label for label in critical_labels)
    assert any("Staub" in label for label in critical_labels)

    # (2) next_step: the Rille / Korrosion / eingelaufene Spur question.
    assert "Rille" in data["next_step"]["question"]
    assert "Korrosion" in data["next_step"]["question"]
    assert "eingelaufene Spur" in data["next_step"]["question"]

    # Neutral draft status, display-only chips (no backend click provenance here).
    assert data["rfq_status"] == "DRAFT"
    assert [c.label for c in chips][:3] == ["glatt", "Rille sichtbar", "Korrosion"]

    # (6) No final suitability / guarantee / compliance / release wording.
    blob = json.dumps(data, ensure_ascii=False) + " ".join(c.label for c in chips)
    assert detect_no_go_phrases(blob, include_final_release=True) == []

    # (5) Non-RWDR text yields no projection.
    assert build_rwdr_p0_pocket_cockpit_patch("Was ist FFKM?") is None
    assert (
        build_rwdr_p0_pocket_cockpit_patch("RWDR 45x62x8, Getriebe") is None
    )  # no leakage intent
