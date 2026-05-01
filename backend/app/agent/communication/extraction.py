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
        ("housing_bore_mm", re.compile(r"(?:\bBohrung\b|\bGehäusebohrung\b|\bGehaeusebohrung\b)\s*(?P<value>\d+(?:[.,]\d+)?)\s*mm\b", re.IGNORECASE), "mm"),
        ("installation_width_mm", re.compile(r"(?:\bEinbaubreite\b|\bBaubreite\b)\s*(?P<value>\d+(?:[.,]\d+)?)\s*mm\b", re.IGNORECASE), "mm"),
        ("pressure_bar", re.compile(r"\b(?P<value>\d+(?:[.,]\d+)?)\s*bar(?:g|a)?\b", re.IGNORECASE), "bar"),
        ("temperature_c", re.compile(r"\b(?P<value>\d+(?:[.,]\d+)?)\s*(?:°\s*c|grad|celsius)\b", re.IGNORECASE), "degC"),
        ("surface_roughness_ra_um", re.compile(r"\bRa\s*(?P<value>\d+(?:[.,]\d+)?)\s*(?:µm|um|mikrometer)?\b", re.IGNORECASE), "um"),
        ("hardness_shore_a", re.compile(r"\b(?P<value>\d+(?:[.,]\d+)?)\s*(?:Shore\s*A|ShA|SH\s*A)\b", re.IGNORECASE), "Shore A"),
    )
    _medium_pattern = re.compile(r"\bmedium\s+(?:ist|=)\s+(?P<value>[A-Za-zÄÖÜäöüß0-9 +/.-]{2,60})", re.IGNORECASE)
    _seal_type_patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("rwdr", re.compile(r"\b(?:rwdr|radialwellendichtring|wellendichtring)\b", re.IGNORECASE)),
        ("mechanical_seal", re.compile(r"\b(?:gleitringdichtung|glrd|mechanical seal)\b", re.IGNORECASE)),
        ("o_ring", re.compile(r"\b(?:o-ring|oring|o ring)\b", re.IGNORECASE)),
        ("flat_gasket", re.compile(r"\b(?:flachdichtung|flanschdichtung)\b", re.IGNORECASE)),
        ("hydraulic_seal", re.compile(r"\b(?:hydraulikdichtung|kolbendichtung|stangendichtung)\b", re.IGNORECASE)),
    )
    _failure_patterns: tuple[tuple[str, re.Pattern[str]], ...] = (
        ("leakage", re.compile(r"\b(?:leckt|leckage|undicht|ölverlust|oelverlust)\b", re.IGNORECASE)),
        ("wear", re.compile(r"\b(?:verschleiß|verschleiss|riefen|abgerieben)\b", re.IGNORECASE)),
        ("swelling", re.compile(r"\b(?:quellung|aufgequollen|quillt)\b", re.IGNORECASE)),
        ("extrusion", re.compile(r"\b(?:extrusion|spaltextrusion|ausgequetscht)\b", re.IGNORECASE)),
        ("crack", re.compile(r"\b(?:riss|gerissen|bruch|gebrochen)\b", re.IGNORECASE)),
    )

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
        for value, pattern in self._seal_type_patterns:
            if pattern.search(text):
                result.append(
                    ProposedFieldUpdate(
                        key="seal_type",
                        value=value,
                        confidence="medium",
                        requires_user_confirmation=True,
                    )
                )
                break
        for value, pattern in self._failure_patterns:
            if pattern.search(text):
                result.append(
                    ProposedFieldUpdate(
                        key="damage_pattern",
                        value=value,
                        confidence="medium",
                        requires_user_confirmation=True,
                    )
                )
                break
        return result

    @staticmethod
    def _coerce_number(value: Any) -> float | int | str:
        raw = str(value or "").replace(",", ".").strip()
        try:
            parsed = float(raw)
        except ValueError:
            return str(value)
        return int(parsed) if parsed == int(parsed) else parsed
