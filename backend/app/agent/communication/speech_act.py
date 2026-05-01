from __future__ import annotations

import re

from app.agent.communication.models import SpeechAct


_GERMAN_MARKERS = re.compile(
    r"\b(hallo|danke|bitte|ich|wir|dichtung|welle|druck|temperatur|medium|weiss|weiß)\b",
    re.IGNORECASE | re.UNICODE,
)
_ENGLISH_MARKERS = re.compile(
    r"\b(hello|thanks|thank you|seal|pressure|temperature|medium|shaft|not sure)\b",
    re.IGNORECASE,
)


class SpeechActClassifier:
    """Small deterministic speech-act layer for safety-critical chat turns.

    The labels are intentionally multi-label. A turn like "ja danke" can be
    both a confirmation and a social act; the state-transition guard decides
    whether the confirmation is allowed to affect workflow state.
    """

    _greeting_re = re.compile(
        r"^\s*(hallo|hi|hey|moin|servus|guten\s+(morgen|tag|abend)|hello)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _thanks_re = re.compile(
        r"\b(danke|vielen\s+dank|dankeschoen|dankeschön|merci|thanks|thank\s+you)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _yes_re = re.compile(r"^\s*(ja|jep|genau|ok(?:ay)?|yes|yep|correct)\b", re.IGNORECASE | re.UNICODE)
    _no_re = re.compile(r"^\s*(nein|nee|no|nope)\b", re.IGNORECASE | re.UNICODE)
    _unknown_re = re.compile(
        r"\b(weiss\s+ich\s+nicht|weiß\s+ich\s+nicht|keine\s+ahnung|nicht\s+sicher|unklar|not\s+sure|unknown)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _correction_re = re.compile(
        r"\b(korrigier\w*|korrektur|das\s+stimmt\s+nicht|nicht\b.+\bsondern|stattdessen|gemeint\s+war|ich\s+meinte)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _ask_explain_re = re.compile(
        r"\b(warum|wieso|weshalb|was\s+brauchst\s+du|was\s+fehlt|erklaer|erklär|explain|why)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _intent_to_start_re = re.compile(
        r"\b("
        r"(?:ich|wir)\s+(?:moechte|möchte|moechten|möchten|will|wollen)\b.*\b"
        r"(?:dichtung(?:sloesung|slösung|ssituation|sfall)?|loesung|lösung|fall|problem|anfrage)\b|"
        r"(?:dichtung(?:sloesung|slösung|ssituation|sfall)?|loesung|lösung|fall|problem)\s+"
        r"(?:besprechen|klaeren|klären|erarbeiten|ausarbeiten|anschauen)|"
        r"(?:lass|lassen)\s+(?:uns|sie\s+uns)\b.*\b(?:starten|anfangen|klaeren|klären)"
        r")\b",
        re.IGNORECASE | re.UNICODE,
    )
    _cancel_re = re.compile(r"\b(stopp|stop|abbrechen|cancel|spaeter|später)\b", re.IGNORECASE | re.UNICODE)
    _oos_re = re.compile(r"\b(wetter|weather|witz|joke|fussball|fußball|aktienkurs)\b", re.IGNORECASE | re.UNICODE)
    _technical_answer_re = re.compile(
        r"\b(mm|bar|barg|bara|mpa|rpm|u\.?/?min|grad|celsius|°\s*c|"
        r"o-?ring|rwdr|wellendichtring|gleitringdichtung|flachdichtung|"
        r"pumpe|welle|medium|druck|temperatur|salzwasser|ethanol|hydraulik)\b|\d",
        re.IGNORECASE | re.UNICODE,
    )

    def classify(self, message: str) -> tuple[list[SpeechAct], str]:
        text = str(message or "").strip()
        lowered = text.casefold()
        language = self._detect_language(text)
        acts: list[SpeechAct] = []

        def add(label: str, confidence: float) -> None:
            if label not in {act.label for act in acts}:
                acts.append(SpeechAct(label=label, confidence=confidence))

        if not text:
            add("task.empty", 1.0)
            return acts, language
        if self._greeting_re.search(text):
            add("social.greeting", 0.96)
        if self._thanks_re.search(text):
            add("social.thanks", 0.98)
        if self._yes_re.search(text):
            add("confirm.yes", 0.92)
        if self._no_re.search(text):
            add("confirm.no", 0.92)
        if self._unknown_re.search(text):
            add("task.unknown", 0.95)
        if self._correction_re.search(text):
            add("task.correction", 0.94)
        if self._ask_explain_re.search(text):
            add("meta.ask_explain", 0.82)
        if self._intent_to_start_re.search(text):
            add("task.intent_to_start", 0.9)
        if self._cancel_re.search(text):
            add("meta.cancel", 0.9)
        if self._oos_re.search(text):
            add("out_of_scope", 0.85)
        if self._technical_answer_re.search(text):
            add("task.answer", 0.86)

        # If the user asks a domain question without values, keep it as a meta
        # request instead of an empty task answer.
        if "?" in lowered and not any(act.label.startswith("task.") for act in acts):
            add("meta.ask_explain", 0.76)

        if not acts:
            add("task.free_text", 0.55)
        return acts, language

    @staticmethod
    def _detect_language(text: str) -> str:
        if _GERMAN_MARKERS.search(text):
            return "de"
        if _ENGLISH_MARKERS.search(text):
            return "en"
        return "de"


def has_act(acts: list[SpeechAct], label: str) -> bool:
    return any(act.label == label for act in acts)


def has_any_act(acts: list[SpeechAct], prefixes: tuple[str, ...]) -> bool:
    return any(any(act.label.startswith(prefix) for prefix in prefixes) for act in acts)
