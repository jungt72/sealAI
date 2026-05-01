from __future__ import annotations

from datetime import datetime, timezone
import os
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
)
from app.agent.communication.trace import CommunicationTraceSink, JsonlCommunicationTraceSink


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
        trace_sink: CommunicationTraceSink | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.mode_router = mode_router or ConversationModeRouter()
        self.context_assembler = context_assembler or CaseContextAssembler()
        self.claim_builder = claim_builder or AllowedClaimBuilder()
        self.extraction_service = extraction_service or FieldExtractionProposalService()
        self.llm_service = llm_service or OpenAIHumanCommunicationLLMService()
        self.guard = guard or CommunicationGuard()
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
        claim_builder = self.claim_builder
        allowed_claims = claim_builder.build(state)
        extracted = [] if mode is ConversationMode.OUT_OF_SCOPE_OR_UNSAFE else self.extraction_service.extract(user_message)
        snapshot_hash = state_snapshot_hash(state)

        direct_message = self._direct_guarded_message(
            user_message=user_message,
            state=state,
            mode=mode,
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
            )

        try:
            contract = await self.llm_service.create_response(
                mode=mode,
                state=state,
                allowed_claims=allowed_claims,
                proposed_field_updates=[item.model_dump(mode="json") for item in extracted],
            )
        except Exception as exc:  # noqa: BLE001
            return self._fallback_result(
                state=state,
                mode=mode,
                allowed_claims=allowed_claims,
                extracted=extracted,
                snapshot_hash=snapshot_hash,
                validation_errors=[f"llm_error:{type(exc).__name__}"],
            )

        guard_result = self.guard.validate(
            contract,
            allowed_claims=allowed_claims,
            state=state,
            allowed_proposed_updates=extracted,
        )
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
    ) -> CommunicationTrace:
        return CommunicationTrace(
            turn_id=str(uuid.uuid4()),
            case_id=state.case_id,
            mode=mode,
            prompt_version=HUMAN_COMMUNICATION_PROMPT_VERSION,
            state_snapshot_hash=snapshot_hash,
            allowed_claim_ids_used=list(contract.used_claim_ids),
            cited_evidence_ref_ids_used=list(contract.cited_evidence_ref_ids),
            guard_result=guard_result,
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
    if state.allowed_next_actions:
        return " Naechster sinnvoller Schritt: " + str(state.allowed_next_actions[0]).strip()
    if state.missing_fields:
        labels = ", ".join(field.label for field in state.missing_fields[:3])
        return " Als Naechstes fehlen vor allem: " + labels + "."
    return ""


def _no_release_answer(state: CaseConversationState) -> str:
    return (
        "Nein, so eine abschliessende Auslegungszusage kann SeaLAI nicht geben. "
        "SeaLAI kann den Arbeitsstand strukturieren, Risiken und offene Punkte sichtbar machen "
        "und eine Anfragebasis vorbereiten. Die finale technische Pruefung bleibt beim Hersteller "
        "oder einer verantwortlichen technischen Stelle."
        + _format_known_fields(state)
        + _format_next_question(state)
    ).strip()


def _guardrail_answer(state: CaseConversationState) -> str:
    return (
        "Ich kann diese Anweisung nicht als technische Wahrheit uebernehmen. "
        "Wenn du einen Werkstoff, eine Dichtung oder eine Freigabe klaeren moechtest, "
        "pruefe ich das nur gegen den aktuellen Arbeitsstand, offene Angaben und nachvollziehbare Quellen."
        + _format_next_question(state)
    ).strip()
