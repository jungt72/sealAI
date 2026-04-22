from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

pytest.skip("legacy router-facade tests expect pre-SSoT private APIs; migrate to app.agent.api.assembly/streaming contract tests", allow_module_level=True)

from app.agent.api.router import (
    _build_governed_stream_payload,
    _build_governed_allowed_surface_claims,
    _run_governed_chat_response,
    _stream_governed_graph,
    RuntimeDispatchResolution,
    chat_endpoint,
    event_generator,
)
from app.agent.graph import GraphState
from app.agent.runtime.reply_composition import build_governed_render_prompt, guard_governed_rendered_text
from app.agent.runtime.user_facing_reply import collect_governed_visible_reply
from app.agent.state.models import AssertedClaim, ConversationStrategyContract, GovernedSessionState, RequirementClass, TurnContextContract
from app.services.auth.dependencies import RequestUser


class _FakeProjection:
    def model_dump(self) -> dict:
        return {
            "rfq": {
                "status": "rfq_ready",
                "transport_channel": "internal_transport_envelope",
                "notes": [
                    "Governed output is releasable and handover-ready.",
                    "Internal transport envelope is ready for later sender/connector consumption.",
                ],
            },
            "export_profile": {
                "notes": [
                    "Runtime dispatch basis is ready for an internal trigger.",
                    "Governed output is releasable and handover-ready.",
                ]
            },
            "dispatch_contract": {
                "handover_notes": [
                    "Technical dispatch bridge is ready for later transport consumption.",
                    "Current mapping uses demo catalog data and remains category-level only.",
                ],
                "event_id": "evt-1",
                "event_key": "dispatch:evt-1",
                "partner_id": "partner-7",
            },
            "medium_context": {
                "medium_label": "Salzwasser",
                "status": "available",
                "scope": "orientierend",
                "summary": "Allgemeiner Medium-Kontext, nicht als Freigabe.",
                "properties": ["wasserbasiert", "salzhaltig"],
                "challenges": ["Korrosionsrisiko an Metallkomponenten beachten"],
                "followup_points": ["Salzkonzentration", "Temperatur"],
                "confidence": "medium",
                "source_type": "llm_general_knowledge",
                "not_for_release_decisions": True,
                "disclaimer": "Allgemeiner Medium-Kontext, nicht als Freigabe.",
            },
        }


def test_governed_stream_payload_scrubs_internal_transport_and_event_fields() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(output_reply="ok", output_response_class="inquiry_ready"),
            persisted_state=GovernedSessionState(),
        )

    dumped = str(payload["ui"]).lower()
    assert "transport_channel" not in dumped
    assert "event_id" not in dumped
    assert "event_key" not in dumped
    assert "partner_id" not in dumped
    assert payload["ui"]["rfq"]["notes"] == ["Governed output is releasable and handover-ready."]
    assert payload["ui"]["export_profile"]["notes"] == ["Governed output is releasable and handover-ready."]
    assert payload["ui"]["dispatch_contract"]["handover_notes"] == [
        "Current mapping uses demo catalog data and remains category-level only."
    ]


def test_governed_stream_payload_prefers_visible_reply_override_without_touching_contract_fields() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(output_reply="Bitte Medium angeben.", output_response_class="structured_clarification"),
            persisted_state=GovernedSessionState(),
            visible_reply="Erzaehlen Sie mir kurz, welches Medium abgedichtet werden soll.",
        )

    assert payload["reply"] == "Erzaehlen Sie mir kurz, welches Medium abgedichtet werden soll."
    assert payload["response_class"] == "structured_clarification"
    assert payload["structured_state"]["output_status"] == "clarification_needed"


def test_governed_stream_payload_carries_medium_context_only_as_ui_data() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(output_reply="Betriebsparameter wurden strukturiert erfasst.", output_response_class="governed_state_update"),
            persisted_state=GovernedSessionState(),
            visible_reply="Betriebsparameter wurden strukturiert erfasst.",
        )

    assert payload["reply"] == "Betriebsparameter wurden strukturiert erfasst."
    assert payload["ui"]["medium_context"]["medium_label"] == "Salzwasser"
    assert payload["ui"]["medium_context"]["scope"] == "orientierend"
    assert payload["ui"]["medium_context"]["not_for_release_decisions"] is True


def test_governed_stream_payload_does_not_duplicate_existing_user_signal_prefix() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(output_reply="Bitte Medium angeben.", output_response_class="structured_clarification"),
            persisted_state=GovernedSessionState(),
            visible_reply="Erzaehlen Sie mir kurz, welches Medium abgedichtet werden soll.",
        )

    assert payload["reply"] == "Erzaehlen Sie mir kurz, welches Medium abgedichtet werden soll."
    assert payload["response_class"] == "structured_clarification"


def test_governed_state_update_payload_uses_visible_reply_without_prefix_injection() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(
                output_reply="Betriebsparameter wurden strukturiert erfasst.",
                output_response_class="governed_state_update",
            ),
            persisted_state=GovernedSessionState(),
            visible_reply="Betriebsparameter wurden strukturiert erfasst.",
        )

    assert payload["reply"] == "Betriebsparameter wurden strukturiert erfasst."
    assert payload["response_class"] == "governed_state_update"


def test_technical_preselection_payload_uses_fallback_without_prefix_injection() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(
                output_reply="Technische Einengung auf Basis bestaetigter Parameter.",
                output_response_class="technical_preselection",
            ),
            persisted_state=GovernedSessionState(),
            visible_reply="",
        )

    # C1: output_reply is the content SSOT — reply equals the output_reply value
    assert payload["reply"] == "Technische Einengung auf Basis bestaetigter Parameter."
    assert payload["response_class"] == "technical_preselection"


def test_inquiry_ready_payload_uses_result_class_specific_facts_prefix() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        state = GraphState(
            output_reply="Die Anfragebasis ist jetzt strukturiert vorbereitet.",
            output_response_class="inquiry_ready",
        )
        state.asserted.assertions["medium"] = AssertedClaim(
            field_name="medium",
            asserted_value="Dampf",
            confidence="confirmed",
        )
        state.governance.requirement_class = RequirementClass(
            class_id="PTFE10",
            description="Steam class",
            seal_type="gasket",
        )
        payload = _build_governed_stream_payload(
            result_state=state,
            persisted_state=GovernedSessionState(),
            visible_reply="",
        )

    # C1: output_reply is the content SSOT — reply equals the output_reply value
    assert "Anfragebasis" in payload["reply"]
    assert payload["response_class"] == "inquiry_ready"
    assert "inquiry" in payload["ui"]
    assert payload["ui"]["inquiry"]["status"] == "rfq_ready"


def test_governed_stream_payload_uses_central_user_facing_reply_assembly() -> None:
    assembled = {
        "reply": "Assembled governed reply",
        "structured_state": {"output_status": "clarification_needed"},
        "policy_path": "governed",
        "run_meta": {"path": "governed_graph"},
        "response_class": "structured_clarification",
    }
    with (
        patch("app.agent.api.router.project_for_ui", return_value=_FakeProjection()),
        patch("app.agent.api.router.assemble_user_facing_reply", return_value=assembled) as mock_assemble,
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(
                output_reply="Bitte Medium angeben.",
                output_response_class="structured_clarification",
            ),
            persisted_state=GovernedSessionState(),
        )

    assert payload["reply"] == "Assembled governed reply"
    assert payload["response_class"] == "structured_clarification"
    assert payload["policy_path"] == "governed"
    assert payload["structured_state"]["output_status"] == "clarification_needed"
    mock_assemble.assert_called_once()
    assert mock_assemble.call_args.kwargs["response_class"] == "structured_clarification"
    assert "ui" in payload


def test_governed_stream_payload_keeps_structured_state_unchanged_for_clarification_wording() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(
                output_reply=(
                    "Welchen Betriebsdruck sehen Sie in bar? "
                    "Der Druck bestimmt, welche Belastung die Dichtung sicher aufnehmen muss."
                ),
                output_response_class="structured_clarification",
            ),
            persisted_state=GovernedSessionState(),
        )

    assert payload["response_class"] == "structured_clarification"
    assert payload["structured_state"]["case_status"] == "clarification_needed"
    assert payload["structured_state"]["output_status"] == "clarification_needed"
    assert payload["structured_state"]["next_step"] == "provide_missing_parameters"


def test_conversation_strategy_contract_has_stable_defaults() -> None:
    contract = ConversationStrategyContract()

    assert contract.conversation_phase == "exploration"
    assert contract.turn_goal == "continue_conversation"
    assert contract.user_signal_mirror == ""
    assert contract.primary_question is None
    assert contract.primary_question_reason == ""
    assert contract.supporting_reason is None
    assert contract.response_mode == "guided_explanation"


def test_allowed_surface_claims_are_structured_and_response_class_specific() -> None:
    claims = _build_governed_allowed_surface_claims("structured_clarification")

    assert claims["response_class"] == "structured_clarification"
    assert "allowed_claims" in claims
    assert "forbidden_claims" in claims
    assert "allowed_focus" in claims
    assert "forbidden_fragments" in claims
    assert "class_guard" in claims
    assert "fallback_text" in claims
    assert any("wichtigste Unsicherheit" in item for item in claims["allowed_focus"])
    assert "freigabe" in " ".join(claims["forbidden_fragments"]).lower()


def test_governed_render_prompt_avoids_redundant_focus_block_when_fachbasis_already_contains_it() -> None:
    prompt = build_governed_render_prompt(
        response_class="structured_clarification",
        turn_context=TurnContextContract(
            conversation_phase="narrowing",
            turn_goal="clarify_primary_open_point",
            primary_question="Welches Medium soll abgedichtet werden?",
            primary_question_reason="Das Medium bestimmt den Einsatzrahmen.",
            response_mode="single_question",
            open_points_summary=["Medium"],
        ),
        fallback_text=(
            "Welches Medium soll abgedichtet werden? "
            "Das Medium bestimmt den Einsatzrahmen."
        ),
        allowed_surface_claims=_build_governed_allowed_surface_claims("structured_clarification"),
    )

    assert "STATE-DRIVEN FOKUS:" in prompt
    assert "- Naechster Fokus: Medium" in prompt
    assert prompt.count("Welches Medium soll abgedichtet werden?") == 1


def test_governed_render_prompt_uses_engineering_explainer_mode_for_well_scoped_clarification() -> None:
    prompt = build_governed_render_prompt(
        response_class="structured_clarification",
        turn_context=TurnContextContract(
            conversation_phase="narrowing",
            turn_goal="clarify_primary_open_point",
            primary_question="Wie ist die Einbausituation bei Ihnen ausgeführt?",
            primary_question_reason="Die Einbausituation bestimmt, wie ich den bereits erkannten Anwendungsfall technisch einordne.",
            response_mode="single_question",
            confirmed_facts_summary=[
                "Medium: Salzwasser",
                "Wellendurchmesser: 40.0",
                "Drehzahl: 2000.0",
            ],
            open_points_summary=["Einbausituation"],
        ),
        fallback_text="Wie ist die Einbausituation bei Ihnen ausgeführt?",
        allowed_surface_claims=_build_governed_allowed_surface_claims("structured_clarification"),
    )

    assert "- Render-Modus: engineering_explainer_clarification" in prompt
    assert "kurzen Saetzen fachlicher Einordnung" in prompt
    assert "bekannten technischen Fakten knapp verbindet" in prompt
    assert "genau 1 natuerlichen, state-driven Rueckfrage" in prompt


def test_governed_render_prompt_stays_single_question_for_thin_context() -> None:
    prompt = build_governed_render_prompt(
        response_class="structured_clarification",
        turn_context=TurnContextContract(
            conversation_phase="narrowing",
            turn_goal="clarify_primary_open_point",
            primary_question="Um welches Medium geht es genau?",
            primary_question_reason="Das Medium entscheidet zuerst ueber Werkstoffwahl und Einsatzrahmen.",
            response_mode="single_question",
            confirmed_facts_summary=["Medium: Wasser"],
            open_points_summary=["Medium"],
        ),
        fallback_text="Um welches Medium geht es genau?",
        allowed_surface_claims=_build_governed_allowed_surface_claims("structured_clarification"),
    )

    assert "- Render-Modus: single_question" in prompt
    assert "engineering_explainer_clarification" not in prompt


def test_governed_render_prompt_includes_domain_knowledge_block() -> None:
    prompt = build_governed_render_prompt(
        response_class="technical_preselection",
        turn_context=TurnContextContract(
            conversation_phase="recommendation",
            turn_goal="present_preselection",
            primary_question_reason="Werkstoffe eingegrenzt.",
        ),
        fallback_text="FKM und PTFE als Kandidaten identifiziert.",
        applicable_norms=["DIN 3760", "ISO 6194"],
        requirement_class_id="RD30-2-1",
        evidence_summary_lines=["FKM: bestaendig gegen Mineraloel bis 120°C"],
        material_candidates=["FKM", "PTFE"],
    )
    assert "DOMAIN-WISSEN" in prompt
    assert "RD30-2-1" in prompt
    assert "FKM" in prompt
    assert "PTFE" in prompt
    assert "DIN 3760" in prompt
    assert "bestaendig gegen Mineraloel" in prompt


def test_governed_render_prompt_omits_domain_block_when_empty() -> None:
    prompt = build_governed_render_prompt(
        response_class="structured_clarification",
        turn_context=None,
        fallback_text="Welches Medium?",
    )
    assert "DOMAIN-WISSEN" not in prompt


def test_surface_claims_cover_all_outward_classes() -> None:
    for response_class in (
        "conversational_answer",
        "structured_clarification",
        "governed_state_update",
        "technical_preselection",
        "candidate_shortlist",
        "inquiry_ready",
    ):
        claims = _build_governed_allowed_surface_claims(response_class)
        assert claims["response_class"] == response_class
        assert claims["allowed_claims"]
        assert claims["forbidden_claims"]
        assert claims["fallback_text"]


def test_structured_clarification_blocks_recommendation_manufacturer_and_rfq_language() -> None:
    claims = _build_governed_allowed_surface_claims("structured_clarification")

    assert guard_governed_rendered_text(
        "Ich empfehle Parker. Die Anfragebasis ist RFQ-ready. Welches Medium liegt an?",
        fallback_text="Bitte Medium angeben.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_technical_preselection_allows_requirement_class_but_blocks_final_release() -> None:
    claims = _build_governed_allowed_surface_claims("technical_preselection")

    assert guard_governed_rendered_text(
        "Requirement Class: PTFE10. Scope of Validity: bis 180 C. Offene Pruefpunkte bleiben bestehen.",
        fallback_text="Technische Richtung eingegrenzt.",
        allowed_surface_claims=claims,
    ).startswith("Requirement Class: PTFE10")
    assert guard_governed_rendered_text(
        "Requirement Class: PTFE10. Die Loesung ist final freigegeben.",
        fallback_text="Technische Richtung eingegrenzt.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_candidate_shortlist_blocks_final_manufacturer_release() -> None:
    claims = _build_governed_allowed_surface_claims("candidate_shortlist")

    assert guard_governed_rendered_text(
        "Acme ist der technisch passende Kandidatenrahmen. Offene Herstellerpruefung bleibt bestehen.",
        fallback_text="Kandidatenrahmen liegt vor.",
        allowed_surface_claims=claims,
    ).startswith("Acme ist der technisch passende")
    assert guard_governed_rendered_text(
        "Acme ist der finale Hersteller und verbindlich ausgewaehlt.",
        fallback_text="Kandidatenrahmen liegt vor.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_inquiry_ready_blocks_order_or_send_execution_language() -> None:
    claims = _build_governed_allowed_surface_claims("inquiry_ready")

    assert guard_governed_rendered_text(
        "Die Anfragebasis ist versandfaehig vorbereitet. Offene Herstellerpruefpunkte bleiben sichtbar.",
        fallback_text="Anfragebasis ist vorbereitet.",
        allowed_surface_claims=claims,
    ).startswith("Die Anfragebasis ist versandfaehig vorbereitet.")
    assert guard_governed_rendered_text(
        "Die Anfragebasis ist bereit und bereits bestellt.",
        fallback_text="Anfragebasis ist vorbereitet.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_one_question_rule_blocks_multiple_questions_in_structured_clarification() -> None:
    claims = _build_governed_allowed_surface_claims("structured_clarification")

    assert guard_governed_rendered_text(
        "Welches Medium liegt an? Welcher Druck liegt an?",
        fallback_text="Bitte Medium angeben.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_no_final_certainty_rule_blocks_simulated_finality() -> None:
    claims = _build_governed_allowed_surface_claims("technical_preselection")

    assert guard_governed_rendered_text(
        "Die technische Richtung ist sicher geeignet.",
        fallback_text="Technische Richtung eingegrenzt.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_no_unauthorized_rfq_rule_blocks_rfq_language_outside_inquiry_ready() -> None:
    claims = _build_governed_allowed_surface_claims("governed_state_update")

    assert guard_governed_rendered_text(
        "Die Anfragebasis ist versandfaehig vorbereitet.",
        fallback_text="Status wurde aktualisiert.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_old_outward_aliases_normalize_to_new_surface_claims() -> None:
    assert _build_governed_allowed_surface_claims("governed_recommendation")["response_class"] == "technical_preselection"
    assert _build_governed_allowed_surface_claims("manufacturer_match_result")["response_class"] == "candidate_shortlist"
    assert _build_governed_allowed_surface_claims("rfq_ready")["response_class"] == "inquiry_ready"


def test_class_guard_blocks_semantic_breakout_for_structured_clarification() -> None:
    claims = _build_governed_allowed_surface_claims("structured_clarification")

    assert guard_governed_rendered_text(
        "Requirement Class: PTFE10. Welches Medium liegt an?",
        fallback_text="Bitte Medium angeben.",
        allowed_surface_claims=claims,
    ) == claims["fallback_text"]


def test_guard_uses_fallback_text_on_empty_render() -> None:
    claims = _build_governed_allowed_surface_claims("governed_state_update")

    assert guard_governed_rendered_text(
        "",
        fallback_text="Status wurde aktualisiert.",
        allowed_surface_claims=claims,
    ) == "Status wurde aktualisiert."


def test_governed_stream_payload_includes_additive_conversation_strategy() -> None:
    with patch(
        "app.agent.api.router.project_for_ui",
        return_value=_FakeProjection(),
    ):
        payload = _build_governed_stream_payload(
            result_state=GraphState(
                asserted={
                    "blocking_unknowns": ["medium"],
                },
                # C1: output_reply is user-visible content SSOT — question only, no reason text
                output_reply="Welches Medium soll abgedichtet werden?",
                output_response_class="structured_clarification",
            ),
            persisted_state=GovernedSessionState(),
        )

    strategy = payload["conversation_strategy"]
    assert strategy["conversation_phase"] == "narrowing"
    assert strategy["turn_goal"] == "clarify_primary_open_point"
    assert strategy["response_mode"] == "single_question"
    assert strategy["user_signal_mirror"] == (
        "Die technische Richtung ist schon enger, jetzt brauche ich noch genau einen belastbaren Hebel."
    )
    assert isinstance(strategy["primary_question"], (str, type(None)))
    assert payload["response_class"] == "structured_clarification"
    assert payload["structured_state"]["output_status"] == "clarification_needed"
    assert strategy["primary_question"] in payload["reply"]
    assert strategy["primary_question_reason"] not in payload["reply"]
    turn_context = payload["turn_context"]
    assert turn_context["conversation_phase"] == "narrowing"
    assert turn_context["turn_goal"] == "clarify_primary_open_point"
    assert isinstance(turn_context["confirmed_facts_summary"], list)
    assert isinstance(turn_context["open_points_summary"], list)
    assert "Medium" in "".join(turn_context["open_points_summary"])


async def _collect_sse_payloads(gen):
    payloads: list[dict] = []
    async for frame in gen:
        if not isinstance(frame, str) or not frame.startswith("data: "):
            continue
        raw = frame[6:].strip()
        if raw == "[DONE]":
            payloads.append({"type": "__DONE__"})
            continue
        payloads.append(json.loads(raw))
    return payloads


def _request_user() -> RequestUser:
    return RequestUser(
        user_id="user-1",
        username="user-1",
        sub="user-1",
        roles=["admin"],
        scopes=["openid"],
        tenant_id="tenant-1",
    )


@pytest.mark.asyncio
async def test_stream_governed_graph_state_update_reply_uses_controlled_turn_context_rendering() -> None:
    captured: dict[str, object] = {}

    async def _fake_collect(**kwargs):
        captured.update(kwargs)
        return "Gerne. Welches Medium soll abgedichtet werden?"

    async def _fake_astream(*_args, **_kwargs):
        yield ("custom", {"event_type": "evidence_retrieved", "sources_count": 2})
        yield ("values", {})
        yield ("values", GraphState(
            output_reply="Bitte Medium angeben.",
            output_response_class="structured_clarification",
        ).model_dump(mode="python"))

    with (
        patch.dict("os.environ", {"REDIS_URL": ""}),
        patch(
            "app.agent.api.router.GOVERNED_GRAPH",
            new=SimpleNamespace(
                astream=_fake_astream,
                ainvoke=AsyncMock(
                    return_value=GraphState(
                        output_reply="Bitte Medium angeben.",
                        output_response_class="structured_clarification",
                    )
                )
            ),
        ),
        patch("app.agent.api.router.project_for_ui", return_value=_FakeProjection()),
        patch("app.agent.api.router.collect_governed_visible_reply", side_effect=_fake_collect),
        patch("app.agent.api.router._persist_live_governed_state", AsyncMock()),
    ):
        payloads = await _collect_sse_payloads(
            _stream_governed_graph(
                SimpleNamespace(session_id="case-1", message="Ich moechte eine Dichtungsloesung erarbeiten."),
                current_user=_request_user(),
            )
        )

    progress = next(payload for payload in payloads if payload.get("type") == "progress")
    assert progress["event_type"] == "evidence_retrieved"
    assert progress["sources_count"] == 2
    state_update = next(payload for payload in payloads if payload.get("type") == "state_update")
    assert state_update["reply"] == "Gerne. Welches Medium soll abgedichtet werden?"
    assert state_update["response_class"] == "structured_clarification"
    token_chunks = [payload["text"] for payload in payloads if payload.get("type") == "text_chunk"]
    assert token_chunks == []
    assert captured["response_class"] == "structured_clarification"
    assert isinstance(captured["turn_context"], TurnContextContract)
    # C1: fallback_text is output_reply (not claims_spec default)
    assert captured["fallback_text"] == "Bitte Medium angeben."
    assert isinstance(captured["allowed_surface_claims"], dict)


@pytest.mark.asyncio
async def test_stream_governed_graph_state_update_reply_falls_back_to_deterministic_text_when_rendering_yields_nothing() -> None:
    async def _fake_astream(*_args, **_kwargs):
        yield ("values", {})
        yield ("values", GraphState(
            output_reply="Bitte Medium angeben.",
            output_response_class="structured_clarification",
        ).model_dump(mode="python"))

    with (
        patch.dict("os.environ", {"REDIS_URL": ""}),
        patch(
            "app.agent.api.router.GOVERNED_GRAPH",
            new=SimpleNamespace(
                astream=_fake_astream,
                ainvoke=AsyncMock(
                    return_value=GraphState(
                        output_reply="Bitte Medium angeben.",
                        output_response_class="structured_clarification",
                    )
                )
            ),
        ),
        patch("app.agent.api.router.project_for_ui", return_value=_FakeProjection()),
        patch("app.agent.api.router.collect_governed_visible_reply", AsyncMock(return_value="")),
    ):
        payloads = await _collect_sse_payloads(
            _stream_governed_graph(
                SimpleNamespace(session_id="case-2", message="Ich moechte eine Dichtungsloesung erarbeiten."),
                current_user=_request_user(),
            )
        )

    state_update = next(payload for payload in payloads if payload.get("type") == "state_update")
    # C1: fallback when rendering empty = output_reply (not claims_spec default)
    assert state_update["reply"] == "Bitte Medium angeben."
    assert state_update["response_class"] == "structured_clarification"


@pytest.mark.asyncio
async def test_render_governed_reply_falls_back_to_deterministic_text_on_llm_error() -> None:
    with patch(
        "app.agent.runtime.user_facing_reply.openai.AsyncOpenAI",
        side_effect=RuntimeError("llm unavailable"),
    ):
        reply = await collect_governed_visible_reply(
            response_class="structured_clarification",
            turn_context=TurnContextContract(
                conversation_phase="narrowing",
                turn_goal="clarify_primary_open_point",
                primary_question="Welches Medium soll abgedichtet werden?",
                primary_question_reason="Das Medium bestimmt den Einsatzrahmen.",
                response_mode="single_question",
                open_points_summary=["Medium"],
            ),
            fallback_text="Bitte Medium angeben.",
            allowed_surface_claims=["Nutze nur bestaetigte Fakten."],
        )

    assert reply == "Bitte Medium angeben."


@pytest.mark.asyncio
async def test_render_governed_reply_falls_back_when_rendered_text_violates_allowed_surface_claims() -> None:
    class _Chunk:
        def __init__(self, text: str):
            self.choices = [SimpleNamespace(delta=SimpleNamespace(content=text))]

    class _FakeStream:
        def __aiter__(self):
            async def _gen():
                yield _Chunk("Die Anwendung ist final freigegeben.")

            return _gen()

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=AsyncMock(return_value=_FakeStream()))
        )
    )

    with patch("app.agent.runtime.user_facing_reply.openai.AsyncOpenAI", return_value=fake_client):
        reply = await collect_governed_visible_reply(
            response_class="structured_clarification",
            turn_context=TurnContextContract(
                conversation_phase="narrowing",
                turn_goal="clarify_primary_open_point",
                primary_question="Welches Medium soll abgedichtet werden?",
                primary_question_reason="Das Medium bestimmt den Einsatzrahmen.",
                response_mode="single_question",
                open_points_summary=["Medium"],
            ),
            fallback_text="Bitte Medium angeben.",
            allowed_surface_claims=_build_governed_allowed_surface_claims("structured_clarification"),
        )

    assert reply == "Bitte Medium angeben."


@pytest.mark.asyncio
async def test_non_stream_governed_response_uses_turn_context_rendering() -> None:
    captured: dict[str, object] = {}

    async def _fake_collect(**kwargs):
        captured.update(kwargs)
        return "Gerne. Welches Medium soll abgedichtet werden?"

    with (
        patch(
            "app.agent.api.router._run_governed_graph_once",
            AsyncMock(
                return_value=(
                    GraphState(
                        output_reply="Bitte Medium angeben.",
                        output_response_class="structured_clarification",
                    ),
                    GovernedSessionState(),
                )
            ),
        ),
        patch("app.agent.api.router.project_for_ui", return_value=_FakeProjection()),
        patch("app.agent.api.router.collect_governed_visible_reply", side_effect=_fake_collect),
        patch("app.agent.api.router._persist_live_governed_state", AsyncMock()),
    ):
        response = await _run_governed_chat_response(
            SimpleNamespace(session_id="case-json-1", message="Ich moechte eine Dichtungsloesung erarbeiten."),
            current_user=_request_user(),
        )

        assert response.reply == "Gerne. Welches Medium soll abgedichtet werden?"
        assert response.response_class == "structured_clarification"
        assert response.structured_state["output_status"] == "clarification_needed"
        assert captured["response_class"] == "structured_clarification"
        assert isinstance(captured["turn_context"], TurnContextContract)
        # C1: fallback_text is output_reply (not claims_spec default)
        assert captured["fallback_text"] == "Bitte Medium angeben."


@pytest.mark.asyncio
async def test_non_stream_governed_response_falls_back_to_deterministic_reply_when_rendering_is_empty() -> None:
    with (
        patch(
            "app.agent.api.router._run_governed_graph_once",
            AsyncMock(
                return_value=(
                    GraphState(
                        output_reply="Bitte Medium angeben.",
                        output_response_class="structured_clarification",
                    ),
                    GovernedSessionState(),
                )
            ),
        ),
        patch("app.agent.api.router.project_for_ui", return_value=_FakeProjection()),
        patch("app.agent.api.router.collect_governed_visible_reply", AsyncMock(return_value="")),
    ):
        response = await _run_governed_chat_response(
            SimpleNamespace(session_id="case-json-2", message="Ich moechte eine Dichtungsloesung erarbeiten."),
            current_user=_request_user(),
        )

    # C1: fallback when rendering empty = output_reply (not claims_spec default)
    assert response.reply == "Bitte Medium angeben."
    assert response.response_class == "structured_clarification"
    assert response.structured_state["output_status"] == "clarification_needed"


@pytest.mark.asyncio
async def test_chat_endpoint_uses_governed_json_renderer_for_governed_dispatch() -> None:
    with (
        patch(
            "app.agent.api.router._resolve_runtime_dispatch",
            AsyncMock(
                return_value=RuntimeDispatchResolution(
                    gate_route="GOVERNED",
                    gate_reason="test",
                    runtime_mode="GOVERNED",
                    gate_applied=True,
                )
            ),
        ),
        patch(
            "app.agent.api.router._run_governed_chat_response",
            AsyncMock(
                return_value=SimpleNamespace(
                    session_id="case-json-3",
                    reply="Gerne. Welches Medium soll abgedichtet werden?",
                    response_class="structured_clarification",
                    structured_state={"output_status": "clarification_needed"},
                    policy_path="governed",
                    run_meta={"path": "governed_graph"},
                )
            ),
        ),
    ):
        response = await chat_endpoint(
            SimpleNamespace(session_id="case-json-3", message="Ich moechte eine Dichtungsloesung erarbeiten."),
            current_user=_request_user(),
        )

    assert response.reply == "Gerne. Welches Medium soll abgedichtet werden?"
    assert response.response_class == "structured_clarification"


@pytest.mark.asyncio
async def test_chat_endpoint_fails_closed_to_governed_on_unexpected_runtime_mode() -> None:
    legacy_resolution = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="unexpected_runtime_mode",
        runtime_mode="legacy_fallback",
        gate_applied=False,
    )

    with (
        patch(
            "app.agent.api.router._resolve_runtime_dispatch",
            AsyncMock(return_value=legacy_resolution),
        ),
        patch(
            "app.agent.api.router._run_governed_chat_response",
            AsyncMock(
                return_value=SimpleNamespace(
                    session_id="case-fallback-1",
                    reply="Welcher Druck liegt an?",
                    response_class="structured_clarification",
                    structured_state={"output_status": "clarification_needed"},
                    policy_path="governed",
                    run_meta={"path": "governed_graph"},
                )
            ),
        ) as mock_governed,
    ):
        response = await chat_endpoint(
            SimpleNamespace(session_id="case-fallback-1", message="ich muss salzwasser draussen halten"),
            current_user=_request_user(),
        )

    assert response.reply == "Welcher Druck liegt an?"
    mock_governed.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_endpoint_fails_closed_to_governed_instead_of_light_legacy_fallback() -> None:
    legacy_resolution = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="unexpected_runtime_mode",
        runtime_mode="legacy_fallback",
        gate_applied=False,
    )

    with (
        patch(
            "app.agent.api.router._resolve_runtime_dispatch",
            AsyncMock(return_value=legacy_resolution),
        ),
        patch(
            "app.agent.api.router._run_governed_chat_response",
            AsyncMock(
                return_value=SimpleNamespace(
                    session_id="case-fallback-light-1",
                    reply="Welcher Druck liegt an?",
                    response_class="structured_clarification",
                    structured_state={"output_status": "clarification_needed"},
                    policy_path="governed",
                    run_meta={"path": "governed_graph"},
                )
            ),
        ) as mock_governed,
        patch(
            "app.agent.api.router._run_light_chat_response",
            AsyncMock(
                return_value=SimpleNamespace(
                    session_id="case-fallback-light-1",
                    reply="Gerne, schildern Sie kurz die Anwendung.",
                    response_class="conversational_answer",
                    structured_state=None,
                    policy_path="fast",
                    run_meta=None,
                )
            ),
        ) as mock_light,
        patch("app.agent.api.router.execute_agent", new=AsyncMock()) as mock_execute,
        ):
        response = await chat_endpoint(
            SimpleNamespace(session_id="case-fallback-light-1", message="Hallo"),
            current_user=_request_user(),
        )

    assert response.reply == "Welcher Druck liegt an?"
    mock_governed.assert_awaited_once()
    mock_light.assert_not_awaited()
    mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_stream_event_generator_fails_closed_to_governed_on_unexpected_runtime_mode() -> None:
    legacy_resolution = RuntimeDispatchResolution(
        gate_route="GOVERNED",
        gate_reason="unexpected_runtime_mode",
        runtime_mode="legacy_fallback",
        gate_applied=False,
    )

    async def _fake_stream_governed_graph(*_args, **_kwargs):
        yield 'data: {"type":"state_update","reply":"Welcher Druck liegt an?"}\n\n'
        yield "data: [DONE]\n\n"

    with (
        patch(
            "app.agent.api.router._resolve_runtime_dispatch",
            AsyncMock(return_value=legacy_resolution),
        ),
        patch(
            "app.agent.api.router._stream_governed_graph",
            side_effect=_fake_stream_governed_graph,
        ) as mock_governed_stream,
    ):
        frames = []
        async for frame in event_generator(
            SimpleNamespace(session_id="case-fallback-2", message="ich muss salzwasser draussen halten"),
            current_user=_request_user(),
        ):
            frames.append(frame)

    assert frames == [
        'data: {"type":"state_update","reply":"Welcher Druck liegt an?"}\n\n',
        "data: [DONE]\n\n",
    ]
    assert mock_governed_stream.call_count == 1
