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
            self._matrix = data.get("matrix") or []
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

            results.append(entry)

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
        """Check numeric and categorical screening conditions."""
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
        """Return True if any hard exclusion matches."""
        hard_excl = entry.get("hard_exclusions") or {}
        excl_medium_ids: List[str] = hard_excl.get("medium_ids") or []
        if not excl_medium_ids:
            return False

        user_medium_id: Optional[str] = conditions.get("medium_id")
        if user_medium_id and user_medium_id.lower() in [m.lower() for m in excl_medium_ids]:
            return True

        return False
