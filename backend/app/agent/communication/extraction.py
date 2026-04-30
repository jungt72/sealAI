from __future__ import annotations

import re
from typing import Any

from app.agent.communication.models import ProposedFieldUpdate


class FieldExtractionProposalService:
    """Extracts lightweight field candidates from user text.

    This service never confirms values. It only creates proposals that can be
    passed into the existing governed reducer / validation path.
    """

    _patterns: tuple[tuple[str, re.Pattern[str], str | None], ...] = (
        ("speed_rpm", re.compile(r"\b(?P<value>\d+(?:[.,]\d+)?)\s*(?:u\.?/?min|rpm|1/min)\b", re.IGNORECASE), "rpm"),
        ("shaft_diameter_mm", re.compile(r"(?:\bWelle\b|\bWellendurchmesser\b|[Øø])\s*(?P<value>\d+(?:[.,]\d+)?)\s*mm\b", re.IGNORECASE), "mm"),
        ("pressure_bar", re.compile(r"\b(?P<value>\d+(?:[.,]\d+)?)\s*bar(?:g|a)?\b", re.IGNORECASE), "bar"),
        ("temperature_c", re.compile(r"\b(?P<value>\d+(?:[.,]\d+)?)\s*(?:°\s*c|grad|celsius)\b", re.IGNORECASE), "degC"),
    )
    _medium_pattern = re.compile(r"\bmedium\s+(?:ist|=)\s+(?P<value>[A-Za-zÄÖÜäöüß0-9 +/.-]{2,60})", re.IGNORECASE)

    def extract(self, message: str) -> list[ProposedFieldUpdate]:
        text = str(message or "")
        result: list[ProposedFieldUpdate] = []
        for key, pattern, unit in self._patterns:
            match = pattern.search(text)
            if not match:
                continue
            result.append(
                ProposedFieldUpdate(
                    key=key,
                    value=self._coerce_number(match.group("value")),
                    unit=unit,
                    confidence="high",
                    requires_user_confirmation=True,
                )
            )
        medium = self._medium_pattern.search(text)
        if medium:
            result.append(
                ProposedFieldUpdate(
                    key="medium",
                    value=medium.group("value").strip(" .,!?:;"),
                    confidence="medium",
                    requires_user_confirmation=True,
                )
            )
        return result

    @staticmethod
    def _coerce_number(value: Any) -> float | int | str:
        raw = str(value or "").replace(",", ".").strip()
        try:
            parsed = float(raw)
        except ValueError:
            return str(value)
        return int(parsed) if parsed == int(parsed) else parsed
