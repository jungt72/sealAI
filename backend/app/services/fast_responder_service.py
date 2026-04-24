from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.domain.pre_gate_classification import PreGateClassification


@dataclass(frozen=True, slots=True)
class RegistrationPrompt:
    reason: str
    message: str


@dataclass(frozen=True, slots=True)
class SessionContext:
    language_hint: str | None = None


@dataclass(frozen=True, slots=True)
class FastResponse:
    content: str
    source_classification: PreGateClassification
    output_class: str = "conversational_answer"
    registration_prompt: RegistrationPrompt | None = None
    no_case_created: bool = True


class BoundedFastResponderLLM(Protocol):
    def complete(
        self,
        *,
        system_prompt: str,
        user_input: str,
        classification: PreGateClassification,
        timeout_seconds: float,
    ) -> str:
        ...


@dataclass(slots=True)
class FastResponderMetrics:
    invocations_total: dict[str, int] = field(default_factory=dict)
    latency_seconds: list[float] = field(default_factory=list)
    escalated_to_graph_total: int = 0

    def record_invocation(self, classification: PreGateClassification, latency_seconds: float) -> None:
        key = classification.value
        self.invocations_total[key] = self.invocations_total.get(key, 0) + 1
        self.latency_seconds.append(latency_seconds)


class UnsupportedFastResponderClassification(ValueError):
    pass


class FastResponderService:
    """Pre-graph responder for non-case-creating pre-gate classifications."""

    allowed_classifications: frozenset[PreGateClassification] = frozenset(
        {
            PreGateClassification.GREETING,
            PreGateClassification.META_QUESTION,
            PreGateClassification.BLOCKED,
        }
    )

    def __init__(
        self,
        *,
        llm: BoundedFastResponderLLM | None = None,
        metrics: FastResponderMetrics | None = None,
        prompt_dir: Path | None = None,
        timeout_seconds: float = 1.5,
    ) -> None:
        self._llm = llm
        self.metrics = metrics or FastResponderMetrics()
        self._prompt_dir = prompt_dir or _DEFAULT_PROMPT_DIR
        self._timeout_seconds = timeout_seconds

    def respond(
        self,
        user_input: str,
        classification: PreGateClassification,
        session_context: SessionContext | None = None,
    ) -> FastResponse:
        start = time.perf_counter()
        if classification not in self.allowed_classifications:
            self.metrics.escalated_to_graph_total += 1
            raise UnsupportedFastResponderClassification(
                f"FastResponderService cannot handle {classification.value}"
            )

        prompt = self._load_prompt(classification)
        content = self._complete_or_fallback(
            user_input=user_input,
            classification=classification,
            session_context=session_context,
            system_prompt=prompt,
        )
        response = FastResponse(
            content=content,
            source_classification=classification,
            registration_prompt=_registration_prompt_for(classification),
        )
        self.metrics.record_invocation(classification, time.perf_counter() - start)
        return response

    def _load_prompt(self, classification: PreGateClassification) -> str:
        path = self._prompt_dir / _PROMPT_FILENAMES[classification]
        return path.read_text(encoding="utf-8")

    def _complete_or_fallback(
        self,
        *,
        user_input: str,
        classification: PreGateClassification,
        session_context: SessionContext | None,
        system_prompt: str,
    ) -> str:
        if self._llm is not None:
            result = self._llm.complete(
                system_prompt=system_prompt,
                user_input=user_input,
                classification=classification,
                timeout_seconds=self._timeout_seconds,
            )
            result = result.strip()
            if result:
                return result
        language = _detect_language(user_input, session_context)
        return _fallback_response(classification, language=language)


_DEFAULT_PROMPT_DIR = Path(__file__).resolve().parents[1] / "prompts" / "fast_responder"

_PROMPT_FILENAMES: dict[PreGateClassification, str] = {
    PreGateClassification.GREETING: "greeting.txt",
    PreGateClassification.META_QUESTION: "meta_question.txt",
    PreGateClassification.BLOCKED: "blocked.txt",
}


def _registration_prompt_for(
    classification: PreGateClassification,
) -> RegistrationPrompt | None:
    if classification is not PreGateClassification.META_QUESTION:
        return None
    return RegistrationPrompt(
        reason="case_creation_requires_registration",
        message=(
            "Wenn aus deiner Frage ein konkreter technischer Fall wird, "
            "legen wir erst nach deiner Registrierung einen Fall an."
        ),
    )


def _detect_language(user_input: str, session_context: SessionContext | None) -> str:
    hint = (session_context.language_hint if session_context else None) or ""
    if hint.lower().startswith("en"):
        return "en"
    text = (user_input or "").lower()
    english_markers = ("hello", "hi", "thanks", "thank you", "what can", "how does")
    if any(marker in text for marker in english_markers):
        return "en"
    return "de"


def _fallback_response(classification: PreGateClassification, *, language: str) -> str:
    english = language == "en"
    if classification is PreGateClassification.GREETING:
        return (
            "Hello. I can help you clarify a sealing technology question."
            if english
            else "Hallo. Ich kann dir helfen, eine dichtungstechnische Frage zu klaeren."
        )
    if classification is PreGateClassification.META_QUESTION:
        return (
            "SeaLAI is a neutral technical translation platform for sealing technology. "
            "It helps clarify sealing problems and prepares technically structured inquiries; "
            "it does not sell seals itself."
            if english
            else "SeaLAI ist eine neutrale technische Uebersetzungsplattform fuer Dichtungstechnik. "
            "Es hilft, Dichtungsprobleme zu klaeren und technisch strukturierte Anfragen vorzubereiten; "
            "SeaLAI verkauft selbst keine Dichtungen."
        )
    return (
        "I cannot help with that request. I can help with sealing technology questions instead."
        if english
        else "Dabei kann ich nicht helfen. Ich kann stattdessen bei Fragen zur Dichtungstechnik unterstuetzen."
    )
