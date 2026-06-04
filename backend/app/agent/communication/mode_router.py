from __future__ import annotations

import re

from app.agent.communication.models import ConversationMode


class ConversationModeRouter:
    """Deterministic conversation-mode router for the human communication layer."""

    _unsafe_re = re.compile(
        r"\b(ignore|ignoriere|vergiss)\b.*\b(rule|rules|regeln|system|developer|sicherheits)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _rfq_re = re.compile(r"\b(rfq|anfrage|angebot|anfragen|anfragevorschau|export)\b", re.IGNORECASE)
    _failure_re = re.compile(r"\b(leckage|undicht|ausfall|schaden|verschleiss|verschleiß|failure|root cause|ursache)\b", re.IGNORECASE)
    _field_update_re = re.compile(
        r"\b\d+(?:[.,]\d+)?\s*(?:mm|bar|barg|bara|°?\s*c|grad|rpm|u\.?/?min|1/min)\b"
        r"|\b(medium\s+ist|temperatur|druck|drehzahl|welle|wellendurchmesser)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _case_re = re.compile(
        r"\b(pumpe|ruehrwerk|rührwerk|getriebe|welle|dichtung|dichtstelle|material|werkstoff|"
        r"o-?ring|rwdr|wellendichtring|gleitringdichtung|flachdichtung|hydraulikdichtung|"
        r"welche\s+dichtung|was\s+soll\s+ich\s+nehmen|passt|geeignet|freigegeben)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _knowledge_re = re.compile(
        r"^\s*(was\s+ist|was\s+sind|was\s+bedeutet|wie\s+funktioniert|warum|weshalb|"
        r"erklaer|erklär|unterschied|vergleich|wann\s+nimmt\s+man)\b",
        re.IGNORECASE | re.UNICODE,
    )
    _explicit_case_context_re = re.compile(
        r"\b(mein(?:em|er|en)?\s+fall|dies(?:er|e|es)\s+anwendung|konkret|bei\s+mir|"
        r"fuer\s+meine|für\s+meine|passt|geeignet|soll\s+ich\s+nehmen|welche\s+dichtung)\b",
        re.IGNORECASE | re.UNICODE,
    )

    def route(self, message: str, *, has_case_state: bool = False) -> ConversationMode:
        text = str(message or "").strip()
        lowered = text.lower()
        if not text:
            return ConversationMode.GENERAL_KNOWLEDGE
        if self._unsafe_re.search(lowered):
            return ConversationMode.OUT_OF_SCOPE_OR_UNSAFE
        if self._rfq_re.search(lowered):
            return ConversationMode.RFQ_PREPARATION
        if self._failure_re.search(lowered):
            return ConversationMode.FAILURE_ANALYSIS
        if self._knowledge_re.search(lowered) and not self._explicit_case_context_re.search(lowered):
            return ConversationMode.GENERAL_KNOWLEDGE
        if self._field_update_re.search(lowered):
            return ConversationMode.FIELD_EXTRACTION
        if has_case_state or self._case_re.search(lowered):
            return ConversationMode.CASE_QUALIFICATION
        return ConversationMode.GENERAL_KNOWLEDGE
