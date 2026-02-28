"""GateChecker — evaluates safety and compliance gates from the KB.

Singleton pattern: use ``GateChecker.get_instance()`` for shared access.
Falls back gracefully if KB files are absent.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

log = logging.getLogger("app.services.knowledge.gate_checker")


class GateResult:
    """Result of evaluating a single gate."""

    def __init__(
        self,
        gate_id: str,
        triggered: bool,
        action: str,
        severity: str,
        message: str,
        applies_to_compounds: Optional[List[str]] = None,
        required_fields_schema: Optional[List[Dict[str, Any]]] = None,
        missing_required_fields: Optional[List[Dict[str, Any]]] = None,
        matched_patterns: Optional[List[str]] = None,
    ) -> None:
        self.gate_id = gate_id
        self.triggered = triggered
        self.action = action
        self.severity = severity
        self.message = message
        self.applies_to_compounds = applies_to_compounds or []
        self.required_fields_schema = required_fields_schema or []
        self.missing_required_fields = missing_required_fields or []
        self.matched_patterns = matched_patterns or []

    def is_hard_block(self) -> bool:
        return self.triggered and self.action == "hard_block"

    def is_warning(self) -> bool:
        return self.triggered and self.action in ("soft_warn", "warning")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "triggered": self.triggered,
            "action": self.action,
            "severity": self.severity,
            "message": self.message,
            "applies_to_compounds": self.applies_to_compounds,
            "required_fields_schema": self.required_fields_schema,
            "missing_required_fields": self.missing_required_fields,
            "matched_patterns": self.matched_patterns,
        }


class GateChecker:
    """Evaluates safety/compliance gates against user context.

    Parameters
    ----------
    gates:
        List of gate dicts (loaded from the KB JSON).  If None, loads from
        ``FactCardStore.get_instance()``.
    """

    _instance: Optional["GateChecker"] = None

    def __init__(self, gates: Optional[List[Dict[str, Any]]] = None) -> None:
        if gates is not None:
            self._gates = gates
        else:
            try:
                from app.services.knowledge.factcard_store import FactCardStore
                self._gates = FactCardStore.get_instance().all_gates()
            except Exception as exc:
                log.warning("gate_checker.load_failed", extra={"error": str(exc)})
                self._gates = []

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "GateChecker":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_all(self, user_context: Dict[str, Any]) -> List[GateResult]:
        """Evaluate all gates against *user_context*.

        Parameters
        ----------
        user_context:
            Dict with keys matching gate ``condition_field`` values, e.g.::

                {
                    "temperature_max_c": 280,
                    "temperature_min_c": -50,
                    "medium_id": "hf_acid",
                    "food_grade_required": True,
                    "application_type": "dynamic",
                }

        Returns
        -------
        list of GateResult
            All triggered gates.
        """
        triggered: List[GateResult] = []
        for gate in self._gates:
            result = self._evaluate_gate(gate, user_context)
            if result.triggered:
                triggered.append(result)
        return triggered

    def check_trigger_patterns(self, query_text: str, user_context: Dict[str, Any]) -> List[GateResult]:
        """Evaluate gate trigger_patterns directly from user query text."""
        query = (query_text or "").strip().lower()
        if not query:
            return []

        triggered: List[GateResult] = []
        for gate in self._gates:
            patterns = [str(p or "").strip() for p in (gate.get("trigger_patterns") or []) if str(p or "").strip()]
            matched = [p for p in patterns if p.lower() in query]
            if not matched:
                continue

            required_schema = list(gate.get("required_fields_schema") or [])
            missing = []
            for item in required_schema:
                field_name = str((item or {}).get("field") or "").strip()
                if not field_name:
                    continue
                if not self._has_context_value(field_name, user_context):
                    missing.append(item)

            missing_fields_text = ", ".join(str(i.get("field")) for i in missing if i.get("field"))
            base_message = str(gate.get("if_missing_fields") or gate.get("name") or "Gate triggered").strip()
            if missing_fields_text:
                message = f"{base_message} Missing required fields: {missing_fields_text}."
            else:
                message = base_message

            triggered.append(
                GateResult(
                    gate_id=str(gate.get("id") or "unknown"),
                    triggered=True,
                    action="hard_block",
                    severity="high",
                    message=message,
                    applies_to_compounds=[],
                    required_fields_schema=required_schema,
                    missing_required_fields=missing,
                    matched_patterns=matched,
                )
            )
        return triggered

    def check_gate(self, gate_id: str, user_context: Dict[str, Any]) -> Optional[GateResult]:
        """Evaluate a specific gate by ID.  Returns None if gate not found."""
        for gate in self._gates:
            if gate.get("id") == gate_id:
                return self._evaluate_gate(gate, user_context)
        return None

    def has_hard_blockers(self, user_context: Dict[str, Any]) -> bool:
        """Return True if any gate triggers a hard_block."""
        return any(r.is_hard_block() for r in self.check_all(user_context))

    def get_excluded_compounds(self, user_context: Dict[str, Any]) -> List[str]:
        """Return list of compound IDs excluded by hard-block gates."""
        excluded: List[str] = []
        for result in self.check_all(user_context):
            if result.is_hard_block() and result.applies_to_compounds:
                excluded.extend(result.applies_to_compounds)
        return list(set(excluded))

    def get_allowed_compounds(self, user_context: Dict[str, Any]) -> List[str]:
        """Return explicitly allowed compounds (from 'filter' action gates)."""
        for gate in self._gates:
            result = self._evaluate_gate(gate, user_context)
            if result.triggered and gate.get("action") == "filter":
                return gate.get("allowed_compounds") or []
        return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evaluate_gate(self, gate: Dict[str, Any], ctx: Dict[str, Any]) -> GateResult:
        gate_id = gate.get("id", "unknown")
        action = gate.get("action", "soft_warn")
        severity = gate.get("severity", "info")
        message = gate.get("message", "")
        applies_to = gate.get("applies_to_compounds") or []

        triggered = self._matches_condition(gate, ctx)

        return GateResult(
            gate_id=gate_id,
            triggered=triggered,
            action=action,
            severity=severity,
            message=message,
            applies_to_compounds=applies_to,
        )

    @staticmethod
    def _matches_condition(gate: Dict[str, Any], ctx: Dict[str, Any]) -> bool:
        """Return True if the gate's condition is satisfied by the context."""
        field = gate.get("condition_field")
        op = gate.get("condition_op")
        threshold = gate.get("condition_value")

        if not field or not op:
            return False

        value = ctx.get(field)
        if value is None:
            return False

        if op == "gt":
            return float(value) > float(threshold)
        elif op == "lt":
            return float(value) < float(threshold)
        elif op == "gte":
            return float(value) >= float(threshold)
        elif op == "lte":
            return float(value) <= float(threshold)
        elif op == "eq":
            return value == threshold
        elif op == "in":
            if isinstance(threshold, list):
                return str(value).lower() in [str(t).lower() for t in threshold]
        elif op == "not_in":
            if isinstance(threshold, list):
                return str(value).lower() not in [str(t).lower() for t in threshold]

        return False

    @staticmethod
    def _normalize_field_name(field_name: str) -> str:
        normalized = re.sub(r"[^a-z0-9]+", "_", (field_name or "").strip().lower())
        return re.sub(r"_+", "_", normalized).strip("_")

    @classmethod
    def _has_context_value(cls, field_name: str, ctx: Dict[str, Any]) -> bool:
        normalized = cls._normalize_field_name(field_name)
        candidates = {
            normalized,
            normalized.replace("_if_gas", ""),
            normalized.replace("_or_", "_"),
            normalized.replace("temperature_c", "temperature_max_c"),
            normalized.replace("temperature_c", "temperature_min_c"),
            normalized.replace("medium_name", "medium_id"),
        }
        for key in candidates:
            if not key:
                continue
            value = ctx.get(key)
            if value is not None and str(value).strip() != "":
                return True
        return False
