"""Confirmation gate deciding whether discovery is ready to route."""
from __future__ import annotations

from typing import Dict

from app.langgraph.io.validation import ensure_discovery
from .base import IOValidatedNode


class ConfirmGateNode(IOValidatedNode):
    """Turns discovery payloads into a final ready/not-ready decision."""

    _out_validator = ensure_discovery

    def _run(self, payload: Dict[str, object]) -> Dict[str, object]:
        base_payload = {k: v for k, v in payload.items() if k in {"schema_version", "ziel", "zusammenfassung", "fehlende_parameter", "ready_to_route"}}
        validated = ensure_discovery(base_payload or {})

        override = payload.get("force_ready")
        if isinstance(override, bool):
            ready = override
        else:
            ready = not validated.fehlende_parameter

        return {
            "schema_version": validated.schema_version,
            "ziel": validated.ziel,
            "zusammenfassung": validated.zusammenfassung,
            "fehlende_parameter": list(validated.fehlende_parameter)[:3],
            "ready_to_route": ready,
        }


__all__ = ["ConfirmGateNode"]
