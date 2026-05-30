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

import pytest

from app.agent.api.models import ChatRequest, OverrideItem, OverrideRequest
from app.agent.api.router import _resolve_runtime_dispatch, session_override_endpoint
from app.agent.communication.knowledge_modes import apply_knowledge_turn, resolve_knowledge_mode
from app.agent.communication.mobile_triage import (
    build_mobile_leakage_triage,
    build_visual_low_confidence_guidance,
)
from app.agent.communication.rfq_one_pager import (
    RFQ_READINESS_DRAFT,
    RFQ_READINESS_WITH_OPEN_POINTS,
    evaluate_rfq_readiness,
)
from app.agent.graph.slot_answer_binding import resolve_slot_answer_binding
from app.agent.state.models import GovernedSessionState, PendingQuestion
from app.agent.templates.no_go_guard import FORBIDDEN_NORMAL_TURN_PHRASES, detect_no_go_phrases
from app.agent.templates.registry import render_chat_reply
from app.agent.v92.dashboard_contract import extract_case_revision
from app.services.auth.dependencies import RequestUser


def _user() -> RequestUser:
    return RequestUser(
        user_id="user-1", username="tester", sub="user-1", roles=[], scopes=[], tenant_id="tenant-1"
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
            raw_inquiry="RWDR 45x62x8, Getriebe, Öl, 1500 rpm, staubig, undicht", fields=[]
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
    assert reply.disclaimer_mode == "suppress_normal_turn"  # no liability block in a normal turn


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
    assert envelope["trace"]["rag_used"] is False and envelope["trace"]["graph_used"] is False


def test_golden_mobile_triage_builder_offers_chips() -> None:
    # [ISOLATED] confirms the chip labels of the immediate triage envelope.
    envelope = build_mobile_leakage_triage(has_attachment=True)
    assert [c.label for c in envelope.action_chips][:3] == ["Ja", "Nein", "Weiß ich nicht"]


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
            target_field="speed_rpm", expected_answer_type="rotational_speed_value", status="open"
        ),
        message="jo ca 3000",
        turn_index=1,
    )
    assert binding is not None and binding.normalized_value == 3000.0 and binding.approximate is True


# === Golden C — why-question (no mutation) ==================================


def test_golden_why_question_no_mutation() -> None:
    # [ISOLATED] knowledge mode contract; case_revision must be unchanged.
    state = GovernedSessionState()
    mode = resolve_knowledge_mode("Warum fragst du nach der Welle?", has_active_case=True)
    result = apply_knowledge_turn(state, "Warum fragst du nach der Welle?", has_active_case=True)
    assert mode == "why_question_active_case"
    assert result is state and extract_case_revision(result) == extract_case_revision(state)


# === Golden D/E/F — knowledge modes =========================================


def test_golden_knowledge_general_no_mutation() -> None:
    # [ISOLATED]
    state = GovernedSessionState()
    assert resolve_knowledge_mode("Was ist FFKM?", has_active_case=False) == "knowledge_general"
    assert apply_knowledge_turn(state, "Was ist FFKM?", has_active_case=False) is state


def test_golden_knowledge_case_aware_no_mutation() -> None:
    # [ISOLATED]
    state = GovernedSessionState()
    assert (
        resolve_knowledge_mode("Was bedeutet FKM in meinem Fall?", has_active_case=True)
        == "knowledge_case_aware"
    )
    assert apply_knowledge_turn(state, "Was bedeutet FKM in meinem Fall?", has_active_case=True) is state


def test_golden_knowledge_case_mutating_applies_only_supplied_facts() -> None:
    # [ISOLATED] only the new facts flow through the State Gate.
    state = GovernedSessionState()
    result = apply_knowledge_turn(state, "Wir verwenden FKM, Öltemperatur 100 °C", has_active_case=True)
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
        ["sealing_function", "shaft_diameter_d1_mm", "housing_bore_D_mm", "seal_width_b_mm",
         "application", "inside_medium", "request_goal"],
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
