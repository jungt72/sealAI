import logging
import os
import dataclasses
from typing import Any, Literal, Optional, List

from app.agent.state.models import GovernedSessionState
from app.services.auth.dependencies import RequestUser
from app.agent.api.deps import (
    _canonical_scope,
    _runtime_mode_for_pre_gate,
    _is_light_runtime_mode,
)
from app.agent.api.loaders import (
    _load_live_governed_state,
)
from app.agent.api.utils import (
    _build_light_case_summary,
    _collect_light_missing_fields,
    _collect_tentative_domain_signals,
)

_log = logging.getLogger(__name__)

# Feature flags
_ENABLE_BINARY_GATE: bool = (
    os.environ.get("SEALAI_ENABLE_BINARY_GATE", "true").lower() == "true"
)
_ENABLE_CONVERSATION_RUNTIME: bool = (
    os.environ.get("SEALAI_ENABLE_CONVERSATION_RUNTIME", "true").lower() == "true"
)

@dataclasses.dataclass(frozen=True)
class RuntimeDispatchResolution:
    gate_route: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"]
    gate_reason: str
    runtime_mode: Literal["CONVERSATION", "EXPLORATION", "GOVERNED"]
    gate_applied: bool
    pre_gate_classification: str | None = None
    pre_gate_reason: str | None = None
    session_zone: str | None = None
    direct_reply: str | None = None
    fast_response: Any | None = None
    governed_state: GovernedSessionState | None = None

async def _resolve_runtime_dispatch(
    request: Any, # ChatRequest
    *,
    current_user: RequestUser | None,
) -> RuntimeDispatchResolution:
    if current_user is None:
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason="missing_current_user",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )

    if not _ENABLE_BINARY_GATE:
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason="binary_gate_disabled",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )

    try:
        from app.domain.pre_gate_classification import PreGateClassification  # noqa: PLC0415
        from app.services.fast_responder_service import FastResponderService  # noqa: PLC0415
        from app.services.pre_gate_classifier import PreGateClassifier  # noqa: PLC0415

        pre_gate = PreGateClassifier().classify(request.message)
        if pre_gate.classification in FastResponderService.allowed_classifications:
            fast_response = FastResponderService().respond(
                request.message,
                pre_gate.classification,
            )
            return RuntimeDispatchResolution(
                gate_route="CONVERSATION",
                gate_reason=f"pre_gate:{pre_gate.reasoning}",
                runtime_mode="CONVERSATION",
                gate_applied=False,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
                fast_response=fast_response,
            )

        if pre_gate.classification is not PreGateClassification.DOMAIN_INQUIRY:
            runtime_mode = (
                _runtime_mode_for_pre_gate(pre_gate.classification.value)
                if _ENABLE_CONVERSATION_RUNTIME
                else "GOVERNED"
            )
            return RuntimeDispatchResolution(
                gate_route=runtime_mode,
                gate_reason=f"pre_gate:{pre_gate.reasoning}",
                runtime_mode=runtime_mode,
                gate_applied=False,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
            )

        from redis.asyncio import Redis as AsyncRedis  # noqa: PLC0415
        from app.agent.runtime.gate import decide_route_async  # noqa: PLC0415
        from app.agent.runtime.session_manager import (  # noqa: PLC0415
            apply_gate_decision_and_persist_async,
            get_or_create_session_async,
        )

        redis_url = os.getenv("REDIS_URL", "")
        tenant_id, owner_id, _ = _canonical_scope(current_user, case_id=request.session_id)
        governed_state = None
        if request.session_id:
            governed_state = await _load_live_governed_state(
                current_user=current_user,
                session_id=request.session_id,
                create_if_missing=True,
            )
        short_state_summary = _build_light_case_summary(governed_state) if governed_state is not None else None
        missing_critical_fields = _collect_light_missing_fields(governed_state) if governed_state is not None else []
        tentative_signals = _collect_tentative_domain_signals(governed_state) if governed_state is not None else []

        async with AsyncRedis.from_url(redis_url) as redis:
            session = await get_or_create_session_async(
                redis,
                tenant_id=tenant_id,
                owner_id=owner_id,
                session_id=request.session_id,
            )
            decision = await decide_route_async(
                request.message,
                session,
                short_state_summary=short_state_summary,
                missing_critical_fields=missing_critical_fields,
                tentative_signals=tentative_signals,
            )
            await apply_gate_decision_and_persist_async(redis, session, decision)

            return RuntimeDispatchResolution(
                gate_route=decision.route,
                gate_reason=decision.reason,
                runtime_mode=decision.runtime_mode,
                gate_applied=True,
                pre_gate_classification=pre_gate.classification.value,
                pre_gate_reason=pre_gate.reasoning,
                governed_state=governed_state,
            )

    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "[runtime_dispatch] gate/session resolution failed (%s: %s) — fail-open to governed",
            type(exc).__name__,
            exc,
        )
        return RuntimeDispatchResolution(
            gate_route="GOVERNED",
            gate_reason=f"gate_session_fail_open:{type(exc).__name__}",
            runtime_mode="GOVERNED",
            gate_applied=False,
        )

