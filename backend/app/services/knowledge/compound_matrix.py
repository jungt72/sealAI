"""CompoundDecisionMatrix — pre-screens PTFE compound candidates.

Singleton pattern: use ``CompoundDecisionMatrix.get_instance()`` for shared access.
Falls back gracefully if KB files are absent.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("app.services.knowledge.compound_matrix")

_DEFAULT_MATRIX_PATH = (
    Path(__file__).parent.parent.parent
    / "data"
    / "kb"
    / "SEALAI_KB_PTFE_compound_matrix_v1_3.json"
)

_instance: Optional[CompoundDecisionMatrix] = None


class CompoundDecisionMatrix:
    """Screens PTFE compound candidates against operating conditions.

    Parameters
    ----------
    matrix_path:
        Path to the Compound Decision Matrix JSON file.
    """

    def __init__(self, matrix_path: Optional[Path] = None) -> None:
        self._path = matrix_path or _DEFAULT_MATRIX_PATH
        self._matrix: List[Dict[str, Any]] = []
        self._loaded = False
        self._load()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "CompoundDecisionMatrix":
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    @classmethod
    def reset_instance(cls) -> None:
        global _instance
        _instance = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            log.warning("compound_matrix.kb_file_missing", extra={"path": str(self._path)})
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._matrix = data.get("compound_decision_matrix") or data.get("matrix") or []
            self._loaded = True
            log.info("compound_matrix.loaded", extra={"entries": len(self._matrix)})
        except Exception as exc:
            log.error("compound_matrix.load_failed", extra={"error": str(exc)})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def screen(
        self,
        conditions: Dict[str, Any],
        filler_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Return compound entries that pass all screening conditions.

        Parameters
        ----------
        conditions:
            Dict of operating parameters, e.g.::

                {
                    "temp_max_c": 150,
                    "temp_min_c": -40,
                    "pressure_max_bar": 100,
                    "medium_id": "ethanol",
                    "application_type": "static",
                    "food_grade_required": False,
                }

        filler_id:
            If given, only screen the entry with this ``filler_id``.

        Returns
        -------
        list
            Matching compound entries (each is a dict from the matrix JSON).
        """
        results: List[Dict[str, Any]] = []

        for entry in self._matrix:
            if filler_id and entry.get("filler_id") != filler_id:
                continue

            if not self._passes_conditions(entry, conditions):
                continue

            if self._is_hard_excluded(entry, conditions):
                continue

            reason_notes = list(entry.get("forbidden_conditions") or [])
            custom_blocks = ((entry.get("forbidden_conditions_structured") or {}).get("custom_blocks") or [])
            enriched = dict(entry)
            enriched["rationale"] = " | ".join(str(x) for x in [*reason_notes, *custom_blocks] if str(x).strip())
            enriched["recommended_for"] = [entry.get("recommended_use")] if entry.get("recommended_use") else []
            enriched["compound_name"] = entry.get("filler_type")
            enriched["food_grade"] = "FDA" not in str(entry.get("forbidden_conditions_structured", {}).get("forbidden_purity_classes", []))
            if "score" not in enriched:
                enriched["score"] = self._default_score(entry)
            results.append(enriched)

        # Sort by score descending
        results.sort(key=lambda e: e.get("score", 0), reverse=True)
        return results

    def get_by_filler_id(self, filler_id: str) -> Optional[Dict[str, Any]]:
        for entry in self._matrix:
            if entry.get("filler_id") == filler_id:
                return entry
        return None

    def all_entries(self) -> List[Dict[str, Any]]:
        return list(self._matrix)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _passes_conditions(entry: Dict[str, Any], conditions: Dict[str, Any]) -> bool:
        """Check optional legacy screening rules if present."""
        screening = entry.get("screening_conditions") or {}

        for field, rule in screening.items():
            user_val = conditions.get(field)
            if user_val is None:
                continue  # unknown — allow (conservative)

            if not isinstance(rule, dict):
                continue

            for op, threshold in rule.items():
                if op == "lte" and user_val > threshold:
                    return False
                elif op == "gte" and user_val < threshold:
                    return False
                elif op == "lt" and user_val >= threshold:
                    return False
                elif op == "gt" and user_val <= threshold:
                    return False
                elif op == "in":
                    if isinstance(threshold, list) and user_val not in threshold:
                        return False
                elif op == "not_in":
                    if isinstance(threshold, list) and user_val in threshold:
                        return False
                elif op == "eq" and user_val != threshold:
                    return False

        return True

    @staticmethod
    def _is_hard_excluded(entry: Dict[str, Any], conditions: Dict[str, Any]) -> bool:
        """Return True if any deterministic forbidden_conditions_structured rule matches."""
        # Legacy schema compatibility
        hard_excl = entry.get("hard_exclusions") or {}
        legacy_medium_ids: List[str] = hard_excl.get("medium_ids") or []
        if legacy_medium_ids:
            user_medium_id: Optional[str] = conditions.get("medium_id")
            if user_medium_id and user_medium_id.lower() in [m.lower() for m in legacy_medium_ids]:
                return True

        rules = entry.get("forbidden_conditions_structured") or {}

        min_hrc = rules.get("min_counterface_hardness_hrc")
        user_hrc = conditions.get("counterface_hardness_hrc")
        if min_hrc is not None:
            if user_hrc is not None and float(user_hrc) < float(min_hrc):
                return True
            counterface_material = str(conditions.get("counterface_material") or "").lower()
            if any(tok in counterface_material for tok in ("aluminum", "aluminium", "bronze", "messing", "brass", "soft")):
                return True

        max_pv = rules.get("max_pv_limit_MPa_m_s")
        if max_pv is not None:
            pv = conditions.get("pv_mpa_m_s")
            if pv is not None and float(pv) > float(max_pv):
                return True

        media_tags = {str(x).strip().lower() for x in (conditions.get("media_tags") or []) if str(x).strip()}
        forbidden_media = {str(x).strip().lower() for x in (rules.get("forbidden_media_tags") or []) if str(x).strip()}
        if media_tags and forbidden_media and media_tags.intersection(forbidden_media):
            return True

        purity_class = str(conditions.get("purity_class") or "").strip()
        forbidden_purity = {str(x).strip() for x in (rules.get("forbidden_purity_classes") or []) if str(x).strip()}
        if purity_class and forbidden_purity and purity_class in forbidden_purity:
            return True

        needs_insulation = bool(conditions.get("requires_electrical_insulation"))
        if needs_insulation and bool(rules.get("requires_electrical_insulation")):
            return True

        return False

    @staticmethod
    def _default_score(entry: Dict[str, Any]) -> int:
        wear = str(entry.get("wear_resistance") or "").lower()
        if "excellent" in wear:
            return 90
        if "good" in wear:
            return 75
        if "poor" in wear:
            return 45
        return 60
