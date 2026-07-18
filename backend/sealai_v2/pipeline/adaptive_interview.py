"""Cost-neutral orchestration for the adaptive-interview shadow path."""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from sealai_v2.core.case_state import CaseStateV2
from sealai_v2.core.contracts import DerivedFact
from sealai_v2.core.interview.contracts import (
    DomainPack,
    InterviewDecision,
    InterviewShadowRecord,
    NextQuestionPayload,
)
from sealai_v2.core.interview.policy import (
    apply_state_patches,
    classify_scope,
    completeness_metrics,
    decide_next_interview_step,
    next_question_payload,
    reconcile_runtime_facts,
    resolve_need_states,
)
from sealai_v2.obs.safe_trace import hmac_id

_HEADING_RE = re.compile(r"^\*\*(.+?)\*\*$")
_LEGACY_HEADINGS = {
    "noch erforderlich",
    "für auswahl oder freigabe noch erforderlich",
}


class AdaptiveInterviewUnavailable(RuntimeError):
    code = "adaptive_interview_unavailable"

    def __init__(self) -> None:
        super().__init__(self.code)


@dataclass(frozen=True)
class AdaptiveInterviewEvaluation:
    decision: InterviewDecision
    next_question: NextQuestionPayload | None
    divergence_type: str


def _legacy_question_block(answer_text: str) -> tuple[str, ...]:
    collecting = False
    items: list[str] = []
    for raw_line in (answer_text or "").splitlines():
        line = raw_line.strip()
        heading = _HEADING_RE.match(line)
        if heading:
            label = heading.group(1).strip().casefold()
            collecting = label in _LEGACY_HEADINGS
            continue
        if collecting and line.startswith("-"):
            item = line[1:].strip()
            if item:
                items.append(item)
        elif collecting and line:
            break
    return tuple(items)


def _legacy_need_id(items: tuple[str, ...], pack: DomainPack) -> str | None:
    text = " ".join(items).casefold()
    matched = {
        question.primary_need_id
        for question in pack.questions
        if any(alias.casefold() in text for alias in question.legacy_aliases)
    }
    return next(iter(matched)) if len(matched) == 1 else None


def _divergence(
    *,
    legacy_items: tuple[str, ...],
    legacy_need_id: str | None,
    decision: InterviewDecision,
) -> str:
    directive = decision.directives[0] if decision.directives else None
    if directive is not None and directive.type.value == "escalate":
        return "controller_escalates"
    controller_need = directive.primary_need_id if directive is not None else None
    if legacy_items and controller_need:
        if legacy_need_id is None:
            return "legacy_unstructured"
        return "same_need" if legacy_need_id == controller_need else "different_need"
    if legacy_items:
        return "legacy_question_only"
    if controller_need:
        return "controller_question_only"
    return "no_decision"


class AdaptiveInterviewService:
    """Runs one pure policy decision and persists state/logs atomically via a repository."""

    def __init__(self, *, pack: DomainPack, repository) -> None:
        self.pack = pack
        self.repository = repository

    def evaluate(
        self,
        *,
        tenant_id: str,
        session_id: str,
        case_state: CaseStateV2,
        derived_facts: tuple[DerivedFact, ...] = (),
        legacy_answer_text: str = "",
        persist_shadow: bool,
    ) -> AdaptiveInterviewEvaluation | None:
        scope = classify_scope(case_state, self.pack)
        if scope == "unknown":
            return None
        if scope == "unsupported":
            decision = decide_next_interview_step(case_state, self.pack)
            legacy_items = _legacy_question_block(legacy_answer_text)
            return AdaptiveInterviewEvaluation(
                decision=decision,
                next_question=None,
                divergence_type=_divergence(
                    legacy_items=legacy_items,
                    legacy_need_id=(
                        _legacy_need_id(legacy_items, self.pack)
                        if legacy_items
                        else None
                    ),
                    decision=decision,
                ),
            )
        started = time.perf_counter()
        runtime = self.repository.load(
            tenant_id=tenant_id,
            session_id=session_id,
            topic_id="rwdr.default",
        )
        runtime = reconcile_runtime_facts(case_state, self.pack, runtime)
        decision = decide_next_interview_step(
            case_state,
            self.pack,
            runtime_state=runtime,
            derived_facts=derived_facts,
        )
        now = datetime.now(timezone.utc).isoformat()
        next_state = apply_state_patches(runtime, decision, created_at=now)
        payload = next_question_payload(
            case_id=case_state.case_id,
            topic_id=next_state.topic_id,
            pack=self.pack,
            decision=decision,
        )
        legacy_items = _legacy_question_block(legacy_answer_text)
        legacy_need = _legacy_need_id(legacy_items, self.pack) if legacy_items else None
        divergence = _divergence(
            legacy_items=legacy_items,
            legacy_need_id=legacy_need,
            decision=decision,
        )
        shadow = None
        if persist_shadow:
            states = resolve_need_states(
                case_state,
                self.pack,
                next_state,
                derived_facts=derived_facts,
            )
            metrics = completeness_metrics(self.pack, states)
            directive = decision.directives[0] if decision.directives else None
            shadow = InterviewShadowRecord(
                record_id=uuid.uuid4().hex,
                tenant_id=tenant_id,
                case_reference=hmac_id(f"{tenant_id}:{session_id}"),
                state_revision=case_state.revision,
                pack_id=self.pack.pack_id,
                pack_version=self.pack.version,
                policy_version=self.pack.policy_version,
                legacy_question_present=bool(legacy_items),
                legacy_question_fingerprint=(
                    hmac_id("\n".join(legacy_items)) if legacy_items else None
                ),
                legacy_need_id=legacy_need,
                controller_directive=(directive.type.value if directive else "none"),
                controller_question_id=(directive.question_id if directive else None),
                rule_refs=decision.rule_refs,
                divergence_type=divergence,
                decision_duration_ms=round((time.perf_counter() - started) * 1000.0, 3),
                completeness={**asdict(metrics), "ratio": metrics.ratio},
                created_at=now,
            )
        self.repository.save_evaluation(
            tenant_id=tenant_id,
            session_id=session_id,
            state=next_state,
            updated_at=now,
            shadow=shadow,
        )
        return AdaptiveInterviewEvaluation(
            decision=decision,
            next_question=payload,
            divergence_type=divergence,
        )

    def clear(self, *, tenant_id: str, session_id: str) -> None:
        self.repository.clear(tenant_id=tenant_id, session_id=session_id)
