"""Post-response MAT-GOV-03B capture boundary.

No canonical-ID provider exists before MED-NORM-01.  The production-facing
entry point therefore returns `ineligible_unresolved_input` without DB, cache,
pin, or outbox work.  Tests can inject already server-verified IDs into the
pure/service seams without creating a text-normalization backdoor.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from sealai_v2.core.contracts import PipelineResult, VerifiedIdentity
from sealai_v2.core.material_shadow import ShadowReadinessState


_LOG = logging.getLogger("sealai_v2.material_shadow.capture")


@dataclass(frozen=True, slots=True)
class ShadowCaptureOutcome:
    state: ShadowReadinessState
    stable_error_code: str = "none"


def capture_chat_shadow_after_response(
    *,
    settings,
    identity: VerifiedIdentity,
    session_id: str,
    result: PipelineResult,
) -> ShadowCaptureOutcome:
    """Never raises and never persists raw request/result content."""

    try:
        if not settings.material_ruleset_shadow_enabled:
            return ShadowCaptureOutcome(ShadowReadinessState.DISABLED)
        # MAT-GOV-03B deliberately has no text-to-canonical-ID adapter.  Until
        # MED-NORM-01 supplies server-verified IDs, even a structurally complete
        # PipelineResult is ineligible and no dependency is constructed.
        _ = (identity, session_id, result)
        return ShadowCaptureOutcome(
            ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT,
            "SHADOW_INPUT_INELIGIBLE",
        )
    except Exception:  # noqa: BLE001 - post-response failures never reach ASGI
        _LOG.warning("material shadow capture stopped with SHADOW_INTERNAL_ERROR")
        return ShadowCaptureOutcome(
            ShadowReadinessState.INELIGIBLE_UNRESOLVED_INPUT,
            "SHADOW_INTERNAL_ERROR",
        )
