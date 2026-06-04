from __future__ import annotations

from datetime import datetime, timezone
import os
import time
import uuid
from typing import Any

from app.agent.communication.claims import AllowedClaimBuilder
from app.agent.communication.context import CaseContextAssembler, state_snapshot_hash
from app.agent.communication.extraction import FieldExtractionProposalService
from app.agent.communication.guard import CommunicationGuard
from app.agent.communication.llm_service import (
    HUMAN_COMMUNICATION_PROMPT_VERSION,
    HumanCommunicationLLM,
    OpenAIHumanCommunicationLLMService,
)
from app.agent.communication.mode_router import ConversationModeRouter
from app.agent.communication.models import (
    CaseConversationState,
    CommunicationTrace,
    ConversationMode,
    HumanCommunicationResult,
    LLMResponseContract,
    StateTransitionDecision,
)
from app.agent.communication.speech_act import SpeechActClassifier
from app.agent.communication.state_transition import StateTransitionGuard
from app.agent.communication.trace import CommunicationTraceSink, JsonlCommunicationTraceSink


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)


class ConversationOrchestrator:
    """Coordinates state-aware, guarded human communication.

    The orchestrator is read-only with respect to engineering state. Field
    extraction returns proposals only; existing reducers/governors remain the
    only authority for confirmed case state.
    """

    def __init__(
        self,
        *,
        mode_router: ConversationModeRouter | None = None,
        context_assembler: CaseContextAssembler | None = None,
        claim_builder: AllowedClaimBuilder | None = None,
        extraction_service: FieldExtractionProposalService | None = None,
        llm_service: HumanCommunicationLLM | None = None,
        guard: CommunicationGuard | None = None,
        speech_act_classifier: SpeechActClassifier | None = None,
        state_transition_guard: StateTransitionGuard | None = None,
        trace_sink: CommunicationTraceSink | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.mode_router = mode_router or ConversationModeRouter()
        self.context_assembler = context_assembler or CaseContextAssembler()
        self.claim_builder = claim_builder or AllowedClaimBuilder()
        self.extraction_service = extraction_service or FieldExtractionProposalService()
        self.llm_service = llm_service or OpenAIHumanCommunicationLLMService()
        self.guard = guard or CommunicationGuard()
        self.speech_act_classifier = speech_act_classifier or SpeechActClassifier()
        self.state_transition_guard = state_transition_guard or StateTransitionGuard()
        self.trace_sink = trace_sink or JsonlCommunicationTraceSink.from_env()
        self.enabled = (
            enabled
            if enabled is not None
            else os.environ.get("HUMAN_COMMUNICATION_LAYER_ENABLED", "true").lower() != "false"
        )

    async def handle(
        self,
        *,
        user_message: str,
        case_state: Any | None = None,
        case_id: str = "default",
        current_user_id: str | None = None,
        case_owner_id: str | None = None,
        tenant_id: str | None = None,
        conversation_summary: str | None = None,
    ) -> HumanCommunicationResult:
        state = self.context_assembler.assemble(
            case_state,
            latest_user_message=user_message,
            case_id=case_id,
            current_user_id=current_user_id,
            case_owner_id=case_owner_id,
            tenant_id=tenant_id,
            conversation_summary=conversation_summary,
        )
        mode = self.mode_router.route(user_message, has_case_state=case_state is not None)
        return await self._handle_preassembled_state(
            state=state,
            mode=mode,
            user_message=user_message,
        )

    async def handle_governed_reply(
        self,
        *,
        response_class: str,
        turn_context: Any | None,
        fallback_text: str,
        case_id: str = "default",
        latest_user_message: str | None = None,
    ) -> HumanCommunicationResult:
        user_text = str(latest_user_message or fallback_text or "").strip()
        state = self.context_assembler.assemble_from_turn_context(
            turn_context=turn_context,
            latest_user_message=user_text,
            case_id=case_id,
            deterministic_reply=fallback_text,
        )
        mode = self.mode_router.route(user_text, has_case_state=turn_context is not None)
        if response_class == "inquiry_ready" and mode is not ConversationMode.OUT_OF_SCOPE_OR_UNSAFE:
            mode = ConversationMode.RFQ_PREPARATION
        return await self._handle_preassembled_state(
            state=state,
            mode=mode,
            user_message=user_text,
        )

    async def _handle_preassembled_state(
        self,
        *,
        state: CaseConversationState,
        mode: ConversationMode,
        user_message: str,
    ) -> HumanCommunicationResult:
        stage_started = time.perf_counter()
        latency_ms_by_stage: dict[str, float] = {}
        claim_builder = self.claim_builder
        allowed_claims = claim_builder.build(state)
        latency_ms_by_stage["claims"] = _elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        raw_extracted = [] if mode is ConversationMode.OUT_OF_SCOPE_OR_UNSAFE else self.extraction_service.extract(user_message)
        latency_ms_by_stage["field_extraction"] = _elapsed_ms(stage_started)

        stage_started = time.perf_counter()
        speech_acts, language = self.speech_act_classifier.classify(user_message)
        transition = self.state_transition_guard.evaluate(
            state=state,
            mode=mode,
            speech_acts=speech_acts,
            proposed_updates=raw_extracted,
            language=language,
        )
        extracted = transition.allowed_proposed_updates
        latency_ms_by_stage["state_transition"] = _elapsed_ms(stage_started)

        snapshot_hash = state_snapshot_hash(state)

        direct_message = self._direct_guarded_message(
            user_message=user_message,
            state=state,
            mode=mode,
            transition=transition,
        )
        if direct_message:
            contract = LLMResponseContract(
                mode=mode,
                assistant_message=direct_message,
                used_claim_ids=self._fallback_claim_ids(allowed_claims),
                asks_for_fields=[field.key for field in state.missing_fields[:3]],
                proposed_field_updates=[],
                contains_solution_recommendation=False,
                contains_final_approval=False,
                requires_human_review=True,
                safety_flags=["deterministic_guarded_response"],
                next_action=state.allowed_next_actions[0] if state.allowed_next_actions else None,
            )
            result = HumanCommunicationResult(
                assistant_message=direct_message,
                response_contract=contract,
                allowed_claims=allowed_claims,
                proposed_field_updates=[],
                trace=self._trace(
                    state=state,
                    mode=mode,
                    snapshot_hash=snapshot_hash,
                    contract=contract,
                    guard_result="deterministic",
                    validation_errors=[],
                    transition=transition,
                    latency_ms_by_stage=latency_ms_by_stage,
                ),
                used_fallback=False,
            )
            self._emit_trace(result.trace)
            return result

        if not self.enabled:
            return self._fallback_result(
                state=state,
                mode=mode,
                allowed_claims=allowed_claims,
                extracted=extracted,
                snapshot_hash=snapshot_hash,
                validation_errors=["human_communication_layer_disabled"],
                transition=transition,
                latency_ms_by_stage=latency_ms_by_stage,
            )

        try:
            llm_started = time.perf_counter()
            contract = await self.llm_service.create_response(
                mode=mode,
                state=state,
                allowed_claims=allowed_claims,
                proposed_field_updates=[item.model_dump(mode="json") for item in extracted],
            )
            latency_ms_by_stage["llm"] = _elapsed_ms(llm_started)
        except Exception as exc:  # noqa: BLE001
            return self._fallback_result(
                state=state,
                mode=mode,
                allowed_claims=allowed_claims,
                extracted=extracted,
                snapshot_hash=snapshot_hash,
                validation_errors=[f"llm_error:{type(exc).__name__}"],
                transition=transition,
                latency_ms_by_stage=latency_ms_by_stage,
            )

        guard_started = time.perf_counter()
        guard_result = self.guard.validate(
            contract,
            allowed_claims=allowed_claims,
            state=state,
            allowed_proposed_updates=extracted,
            state_transition=transition,
        )
        latency_ms_by_stage["guard"] = _elapsed_ms(guard_started)
        if not guard_result.ok:
            fallback = guard_result.fallback_message or self.guard.fallback(state)
            fallback_contract = LLMResponseContract(
                mode=mode,
                assistant_message=fallback,
                used_claim_ids=self._fallback_claim_ids(allowed_claims),
                asks_for_fields=[field.key for field in state.missing_fields[:3]],
                proposed_field_updates=extracted,
                contains_solution_recommendation=False,
                contains_final_approval=False,
                requires_human_review=True,
                safety_flags=guard_result.errors,
                next_action=state.allowed_next_actions[0] if state.allowed_next_actions else None,
            )
            result = HumanCommunicationResult(
                assistant_message=fallback,
                response_contract=fallback_contract,
                allowed_claims=allowed_claims,
                proposed_field_updates=extracted,
                trace=self._trace(
                    state=state,
                    mode=mode,
                    snapshot_hash=snapshot_hash,
                    contract=fallback_contract,
                    guard_result="fallback",
                    validation_errors=guard_result.errors,
                    transition=transition,
                    latency_ms_by_stage=latency_ms_by_stage,
                ),
                used_fallback=True,
            )
            self._emit_trace(result.trace)
            return result

        result = HumanCommunicationResult(
            assistant_message=contract.assistant_message,
            response_contract=contract,
            allowed_claims=allowed_claims,
            proposed_field_updates=list(extracted),
            trace=self._trace(
                state=state,
                mode=mode,
                snapshot_hash=snapshot_hash,
                contract=contract,
                guard_result="pass",
                validation_errors=[],
                transition=transition,
                latency_ms_by_stage=latency_ms_by_stage,
            ),
            used_fallback=False,
        )
        self._emit_trace(result.trace)
        return result

    def _fallback_result(
        self,
        *,
        state: CaseConversationState,
        mode: ConversationMode,
        allowed_claims: list,
        extracted: list,
        snapshot_hash: str,
        validation_errors: list[str],
        transition: StateTransitionDecision | None = None,
        latency_ms_by_stage: dict[str, float] | None = None,
    ) -> HumanCommunicationResult:
        message = self.guard.fallback(state)
        contract = LLMResponseContract(
            mode=mode,
            assistant_message=message,
            used_claim_ids=self._fallback_claim_ids(allowed_claims),
            asks_for_fields=[field.key for field in state.missing_fields[:3]],
            proposed_field_updates=extracted,
            contains_solution_recommendation=False,
            contains_final_approval=False,
            requires_human_review=True,
            safety_flags=validation_errors,
            next_action=state.allowed_next_actions[0] if state.allowed_next_actions else None,
        )
        result = HumanCommunicationResult(
            assistant_message=message,
            response_contract=contract,
            allowed_claims=allowed_claims,
            proposed_field_updates=extracted,
            trace=self._trace(
                state=state,
                mode=mode,
                snapshot_hash=snapshot_hash,
                contract=contract,
                guard_result="fallback",
                validation_errors=validation_errors,
                transition=transition,
                latency_ms_by_stage=latency_ms_by_stage or {},
            ),
            used_fallback=True,
        )
        self._emit_trace(result.trace)
        return result

    def _trace(
        self,
        *,
        state: CaseConversationState,
        mode: ConversationMode,
        snapshot_hash: str,
        contract: LLMResponseContract,
        guard_result: str,
        validation_errors: list[str],
        transition: StateTransitionDecision | None = None,
        latency_ms_by_stage: dict[str, float] | None = None,
    ) -> CommunicationTrace:
        return CommunicationTrace(
            turn_id=str(uuid.uuid4()),
            case_id=state.case_id,
            session_id=state.case_id,
            mode=mode,
            route=mode.value if hasattr(mode, "value") else str(mode),
            prompt_version=HUMAN_COMMUNICATION_PROMPT_VERSION,
            state_snapshot_hash=snapshot_hash,
            allowed_claim_ids_used=list(contract.used_claim_ids),
            cited_evidence_ref_ids_used=list(contract.cited_evidence_ref_ids),
            guard_result=guard_result,
            guard_decision=transition.decision if transition else None,
            state_patch_size=transition.state_patch_size if transition else len(contract.proposed_field_updates),
            fallback_level=transition.fallback_level if transition else 0,
            language=transition.language if transition else None,
            latency_ms_by_stage=latency_ms_by_stage or {},
            human_handoff=transition.human_handoff if transition else False,
            speech_acts=transition.speech_acts if transition else [],
            commands=transition.commands if transition else [],
            validation_errors=list(validation_errors),
            model_provider=getattr(self.llm_service, "provider_name", None),
            model_name=getattr(self.llm_service, "model_name", None),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _emit_trace(self, trace: CommunicationTrace) -> None:
        try:
            self.trace_sink.emit(trace)
        except Exception:
            # Trace emission must never break user communication.
            return None

    @staticmethod
    def _fallback_claim_ids(allowed_claims: list) -> list[str]:
        ids = [
            claim.id
            for claim in allowed_claims
            if getattr(claim, "type", None) in {"missing_field", "allowed_action", "limitation"}
        ]
        return ids[:6]

    @staticmethod
    def _direct_guarded_message(
        *,
        user_message: str,
        state: CaseConversationState,
        mode: ConversationMode,
        transition: StateTransitionDecision,
    ) -> str | None:
        lowered = str(user_message or "").casefold()
        asks_for_release = any(
            token in lowered
            for token in (
                "freigegeben",
                "garantiert",
                "garantie",
                "final geeignet",
                "sicher passend",
                "garantiert dicht",
            )
        )
        if mode is ConversationMode.OUT_OF_SCOPE_OR_UNSAFE:
            return _guardrail_answer(state)
        if asks_for_release:
            return _no_release_answer(state)
        if transition.decision == "block_progress":
            reasons = set(transition.reasons)
            if "cancel_requested" in reasons:
                return _cancel_answer(state)
            if "unknown_is_not_progress" in reasons:
                return _unknown_answer(state)
            if "confirmation_without_pending_action" in reasons:
                return _unmatched_confirmation_answer(state)
            if "social_only_utterance" in reasons:
                return _social_no_progress_answer(state)
            if "intent_to_start_case" in reasons:
                return _intent_to_start_answer(state)
        return None


def _format_known_fields(state: CaseConversationState) -> str:
    values = [
        f"{field.label or field.key}: {field.value}"
        + (f" {field.unit}" if field.unit else "")
        for field in state.confirmed_fields[:6]
        if field.value not in (None, "")
    ]
    if not values:
        return ""
    return " Aktuell bekannt: " + "; ".join(values) + "."


def _format_next_question(state: CaseConversationState) -> str:
    question = _best_next_question(state)
    if question:
        return " " + question
    return ""


def _best_next_question(state: CaseConversationState) -> str:
    active_question = str(state.active_question or "").strip()
    if active_question and active_question.endswith("?"):
        return active_question

    missing_keys = {str(field.key).strip().lower() for field in state.missing_fields}
    missing_labels = {str(field.label).strip().lower() for field in state.missing_fields}
    combined = missing_keys | missing_labels

    if {"asset_type", "pump or aggregate type", "anlage", "anlage/baugruppe"}.intersection(combined):
        return "In welcher Anlage oder Baugruppe sitzt die Dichtung, zum Beispiel Pumpe, Rührwerk, Getriebe, Flansch oder Hydraulik?"
    if {"seal_type", "dichtungstyp", "dichtungsprinzip"}.intersection(combined):
        return "Um welches Dichtprinzip geht es ungefähr: O-Ring, Wellendichtring, Flachdichtung, Hydraulikdichtung oder Gleitringdichtung?"
    if {"seal_location", "dichtstelle"}.intersection(combined):
        return "Wo sitzt die Dichtung genau: an einer Welle, an einem Flansch, in einem Zylinder oder an einer anderen Stelle?"
    if {"motion_type", "statisch oder dynamisch", "static or dynamic"}.intersection(combined):
        return "Ist die Dichtstelle statisch, rotierend oder linear bewegt?"
    if {"medium", "medium_name"}.intersection(combined):
        return "Welches Medium liegt direkt an der Dichtstelle an?"
    if {"pressure_bar", "pressure_nominal", "druck", "betriebsdruck"}.intersection(combined):
        return "Welcher Druck liegt an der Dichtstelle an, und ist das Dauer- oder Spitzendruck?"
    if {"temperature_c", "temperature_max_c", "temperatur", "temperature"}.intersection(combined):
        return "Welche Temperatur sieht die Dichtung im normalen Betrieb und als Maximum?"
    if {"speed_rpm", "drehzahl"}.intersection(combined):
        return "Welche Drehzahl liegt an der Welle an?"
    if {"shaft_diameter_mm", "wellendurchmesser"}.intersection(combined):
        return "Welchen Wellendurchmesser hat die Dichtstelle?"

    if state.allowed_next_actions:
        next_action = str(state.allowed_next_actions[0]).strip()
        if next_action.endswith("?"):
            return next_action
        return f"Was kannst du mir dazu als Nächstes sagen: {next_action}?"
    if state.missing_fields:
        return f"Was kannst du mir als Nächstes zu {state.missing_fields[0].label} sagen?"
    return ""


def _no_release_answer(state: CaseConversationState) -> str:
    return (
        "Nein, so eine abschliessende Auslegungszusage kann SeaLAI nicht geben. "
        "SeaLAI kann den Fall strukturieren, Risiken und offene Punkte sichtbar machen "
        "und eine Anfragebasis vorbereiten. Die finale technische Pruefung bleibt beim Hersteller "
        "oder einer verantwortlichen technischen Stelle."
        + _format_next_question(state)
    ).strip()


def _guardrail_answer(state: CaseConversationState) -> str:
    return (
        "Ich kann diese Anweisung nicht als technische Wahrheit uebernehmen. "
        "Wenn du einen Werkstoff, eine Dichtung oder eine Freigabe klaeren moechtest, "
        "pruefe ich das nur gegen den aktuellen Arbeitsstand, offene Angaben und nachvollziehbare Quellen."
        + _format_next_question(state)
    ).strip()


def _social_no_progress_answer(state: CaseConversationState) -> str:
    next_step = _format_next_question(state)
    if next_step:
        return ("Gern. Dann machen wir genau dort weiter." + next_step).strip()
    return (
        "Gern. Beschreibe kurz die Anwendung oder das Problem an der Dichtstelle, "
        "dann gehen wir es Schritt fuer Schritt durch."
    )


def _intent_to_start_answer(state: CaseConversationState) -> str:
    next_question = _best_next_question(state)
    if next_question:
        return (
            "Sehr gut, dann gehen wir das Schritt für Schritt durch. "
            "Ich stelle dir immer nur die nächste sinnvolle Frage. "
            f"{next_question}"
        ).strip()
    return (
        "Sehr gut, dann gehen wir das Schritt für Schritt durch. "
        "Beschreibe mir kurz, wo die Dichtung sitzt und welches Problem oder Ziel du hast."
    )


def _unmatched_confirmation_answer(state: CaseConversationState) -> str:
    next_step = _format_next_question(state)
    if next_step:
        return ("Damit ich nichts falsch uebernehme: Worauf bezieht sich dein Ja genau?" + next_step).strip()
    return "Damit ich nichts falsch uebernehme: Worauf bezieht sich dein Ja genau?"


def _unknown_answer(state: CaseConversationState) -> str:
    next_step = _format_next_question(state)
    if next_step:
        return ("Alles gut, dann markieren wir das nicht als geklaert." + next_step).strip()
    return "Alles gut, dann markieren wir das nicht als geklaert. Was ist der naechste Punkt, den du sicher weisst?"


def _cancel_answer(state: CaseConversationState) -> str:
    next_step = _format_next_question(state)
    if next_step:
        return ("Alles klar, ich halte den aktuellen Schritt an." + next_step).strip()
    return "Alles klar, ich halte den aktuellen Schritt an. Sag mir einfach, womit wir weitermachen sollen."
