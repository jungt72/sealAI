"""Central v0.4 conflict detection service.

The service owns tolerance-aware and provenance-aware conflict decisions.
Reducers and state builders should call this instead of re-implementing
field comparison rules locally.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Mapping, Sequence


DEFAULT_PROVENANCE_PRIORITY: dict[str, int] = {
    "confirmed": 100,
    "user_override": 95,
    "documented": 80,
    "calculated": 70,
    "user_stated": 60,
    "service": 55,
    "llm": 45,
    "inferred": 35,
    "web_hint": 20,
    "missing": 0,
    "unknown": 0,
}

DEFAULT_FIELD_TOLERANCES: dict[str, dict[str, float]] = {
    "temperature_c": {"absolute": 0.5},
    "temperature_max": {"absolute": 0.5},
    "temperature_min": {"absolute": 0.5},
    "pressure_bar": {"absolute": 0.05, "relative": 0.02},
    "pressure_nominal": {"absolute": 0.05, "relative": 0.02},
    "pressure_peak": {"absolute": 0.05, "relative": 0.02},
    "shaft_diameter_mm": {"absolute": 0.05, "relative": 0.001},
    "housing_bore_mm": {"absolute": 0.05, "relative": 0.001},
    "installation_width_mm": {"absolute": 0.05, "relative": 0.001},
    "speed_rpm": {"absolute": 1.0, "relative": 0.01},
    "rpm": {"absolute": 1.0, "relative": 0.01},
}

_NUMERIC_ALIASES: dict[str, str] = {
    "temperature_max_c": "temperature_max",
    "temperature_c": "temperature_c",
    "pressure_max_bar": "pressure_bar",
    "pressure_bar": "pressure_bar",
    "shaft_diameter": "shaft_diameter_mm",
    "shaft_diameter_mm": "shaft_diameter_mm",
}


@dataclass(frozen=True, slots=True)
class ConflictCandidate:
    field_name: str
    value: Any
    provenance: str = "unknown"
    confidence: str | None = None
    source_turn_index: int | None = None
    source_ref: str | None = None


@dataclass(frozen=True, slots=True)
class DetectedConflict:
    field_name: str
    current_value: Any
    candidate_value: Any
    severity: str
    description: str
    current_provenance: str = "unknown"
    candidate_provenance: str = "unknown"
    suggested_resolution_question: str = ""


@dataclass(frozen=True, slots=True)
class ConflictDetectionResult:
    conflicts: tuple[DetectedConflict, ...] = ()
    conflict_severity: str = "none"
    suggested_resolution_question: str | None = None

    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)


class ConflictDetectionService:
    """Detect conflicts using field tolerances and provenance priority."""

    def __init__(
        self,
        *,
        field_tolerances: Mapping[str, Mapping[str, float]] | None = None,
        provenance_priority: Mapping[str, int] | None = None,
    ) -> None:
        self.field_tolerances = dict(field_tolerances or DEFAULT_FIELD_TOLERANCES)
        self.provenance_priority = dict(provenance_priority or DEFAULT_PROVENANCE_PRIORITY)

    def detect(
        self,
        current_case_state: Mapping[str, Any] | None,
        accepted_delta_candidate: Mapping[str, Any] | Sequence[ConflictCandidate],
        *,
        field_tolerances: Mapping[str, Mapping[str, float]] | None = None,
        provenance_priority: Mapping[str, int] | None = None,
    ) -> ConflictDetectionResult:
        tolerances = dict(field_tolerances or self.field_tolerances)
        priority = dict(provenance_priority or self.provenance_priority)
        current = current_case_state or {}
        candidates = self._coerce_candidates(accepted_delta_candidate)
        conflicts: list[DetectedConflict] = []

        for candidate in candidates:
            field_name = candidate.field_name
            found, current_value, current_provenance = self._find_current_value(current, field_name)
            if not found or self._values_equivalent(field_name, current_value, candidate.value, tolerances):
                continue
            severity = self._severity(current_provenance, candidate.provenance, priority)
            question = self._resolution_question(field_name, current_value, candidate.value)
            conflicts.append(
                DetectedConflict(
                    field_name=field_name,
                    current_value=current_value,
                    candidate_value=candidate.value,
                    severity=severity,
                    description=(
                        f"Conflict for '{field_name}': current value {current_value!r} "
                        f"differs from candidate {candidate.value!r}."
                    ),
                    current_provenance=current_provenance,
                    candidate_provenance=candidate.provenance,
                    suggested_resolution_question=question,
                )
            )
        return self._result(conflicts)

    def detect_observed_candidates(
        self,
        field_name: str,
        candidates: Sequence[ConflictCandidate],
        *,
        field_tolerances: Mapping[str, Mapping[str, float]] | None = None,
    ) -> ConflictDetectionResult:
        if len(candidates) < 2:
            return ConflictDetectionResult()
        tolerances = dict(field_tolerances or self.field_tolerances)
        conflicts: list[DetectedConflict] = []
        sorted_candidates = sorted(
            candidates,
            key=lambda item: (self._priority(item.provenance), item.source_turn_index or 0),
            reverse=True,
        )
        winner = sorted_candidates[0]
        for candidate in sorted_candidates[1:]:
            if self._values_equivalent(field_name, winner.value, candidate.value, tolerances):
                continue
            question = self._resolution_question(field_name, winner.value, candidate.value)
            conflicts.append(
                DetectedConflict(
                    field_name=field_name,
                    current_value=winner.value,
                    candidate_value=candidate.value,
                    severity="warning",
                    description=(
                        f"Conflicting extractions for '{field_name}': "
                        f"{winner.value!r} vs {candidate.value!r}."
                    ),
                    current_provenance=winner.provenance,
                    candidate_provenance=candidate.provenance,
                    suggested_resolution_question=question,
                )
            )
        return self._result(conflicts)

    def _result(self, conflicts: list[DetectedConflict]) -> ConflictDetectionResult:
        if not conflicts:
            return ConflictDetectionResult()
        severity = "blocking" if any(conflict.severity == "blocking" for conflict in conflicts) else "warning"
        return ConflictDetectionResult(
            conflicts=tuple(conflicts),
            conflict_severity=severity,
            suggested_resolution_question=conflicts[0].suggested_resolution_question,
        )

    def _coerce_candidates(
        self,
        payload: Mapping[str, Any] | Sequence[ConflictCandidate],
    ) -> list[ConflictCandidate]:
        if isinstance(payload, Mapping):
            return [
                ConflictCandidate(field_name=str(key), value=value, provenance="user_stated")
                for key, value in payload.items()
            ]
        return list(payload)

    def _find_current_value(self, current: Mapping[str, Any], field_name: str) -> tuple[bool, Any, str]:
        direct = current.get(field_name)
        if direct is not None:
            return True, self._unwrap_value(direct), self._extract_provenance(direct)
        for bucket_name in ("parameters", "assertions", "case_data", "state", "facts"):
            bucket = current.get(bucket_name)
            if isinstance(bucket, Mapping) and field_name in bucket:
                value = bucket[field_name]
                return True, self._unwrap_value(value), self._extract_provenance(value)
        return False, None, "unknown"

    def _unwrap_value(self, value: Any) -> Any:
        if isinstance(value, Mapping):
            for key in ("value", "asserted_value", "proposed_value", "raw_value"):
                if key in value:
                    return value[key]
        return value

    def _extract_provenance(self, value: Any) -> str:
        if isinstance(value, Mapping):
            for key in ("provenance", "source", "status"):
                raw = value.get(key)
                if raw:
                    return str(raw)
        return "unknown"

    def _values_equivalent(
        self,
        field_name: str,
        left: Any,
        right: Any,
        tolerances: Mapping[str, Mapping[str, float]],
    ) -> bool:
        left_num = _to_float(left)
        right_num = _to_float(right)
        normalized_field = _NUMERIC_ALIASES.get(field_name, field_name)
        if left_num is not None and right_num is not None:
            tolerance = tolerances.get(normalized_field) or tolerances.get(field_name) or {}
            absolute = float(tolerance.get("absolute", 0.0))
            relative = float(tolerance.get("relative", 0.0)) * max(abs(left_num), abs(right_num), 1.0)
            return abs(left_num - right_num) <= max(absolute, relative)
        return _canonical(left) == _canonical(right)

    def _severity(self, current_provenance: str, candidate_provenance: str, priority: Mapping[str, int]) -> str:
        current_priority = int(priority.get(current_provenance, priority.get("unknown", 0)))
        candidate_priority = int(priority.get(candidate_provenance, priority.get("unknown", 0)))
        return "blocking" if current_priority >= candidate_priority else "warning"

    def _priority(self, provenance: str) -> int:
        return int(self.provenance_priority.get(provenance, self.provenance_priority.get("unknown", 0)))

    def _resolution_question(self, field_name: str, current_value: Any, candidate_value: Any) -> str:
        return (
            f"Ich sehe zwei unterschiedliche Angaben fuer {field_name}: "
            f"{current_value!r} und {candidate_value!r}. Welche Angabe soll fuer den Fall gelten?"
        )


def _canonical(value: Any) -> str:
    if value is None:
        return "none"
    return " ".join(str(value).strip().casefold().split())


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        number = float(value)
        return number if isfinite(number) else None
    text = str(value).strip().replace(",", ".")
    token = text.split()[0] if text else ""
    try:
        number = float(token)
    except ValueError:
        return None
    return number if isfinite(number) else None
