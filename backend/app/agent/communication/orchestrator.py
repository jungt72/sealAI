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
        enabled: bool | None = None,
    ) -> None:
        self.mode_router = mode_router or ConversationModeRouter()
        self.context_assembler = context_assembler or CaseContextAssembler()
        self.claim_builder = claim_builder or AllowedClaimBuilder()
        self.extraction_service = extraction_service or FieldExtractionProposalService()
        self.llm_service = llm_service or OpenAIHumanCommunicationLLMService()
        self.guard = guard or CommunicationGuard()
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
    ) -> HumanCommunicationResult:
        state = self.context_assembler.assemble_from_turn_context(
            turn_context=turn_context,
            latest_user_message=fallback_text,
            case_id=case_id,
            deterministic_reply=fallback_text,
        )
        mode = (
            ConversationMode.RFQ_PREPARATION
            if response_class == "inquiry_ready"
            else ConversationMode.CASE_QUALIFICATION
        )
        return await self._handle_preassembled_state(
            state=state,
            mode=mode,
            user_message=fallback_text,
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
        extracted = self.extraction_service.extract(user_message)
        snapshot_hash = state_snapshot_hash(state)

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

        guard_result = self.guard.validate(contract, allowed_claims=allowed_claims, state=state)
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
            return HumanCommunicationResult(
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

        merged_proposals = list(extracted)
        for proposal in contract.proposed_field_updates:
            if not any(item.key == proposal.key and item.value == proposal.value for item in merged_proposals):
                merged_proposals.append(proposal)
        return HumanCommunicationResult(
            assistant_message=contract.assistant_message,
            response_contract=contract,
            allowed_claims=allowed_claims,
            proposed_field_updates=merged_proposals,
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
        return HumanCommunicationResult(
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
            guard_result=guard_result,
            validation_errors=list(validation_errors),
            model_provider=getattr(self.llm_service, "provider_name", None),
            model_name=getattr(self.llm_service, "model_name", None),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @staticmethod
    def _fallback_claim_ids(allowed_claims: list) -> list[str]:
        ids = [
            claim.id
            for claim in allowed_claims
            if getattr(claim, "type", None) in {"missing_field", "allowed_action", "limitation"}
        ]
        return ids[:6]
