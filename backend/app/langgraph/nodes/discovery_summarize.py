"""Summarisation node that refines discovery intake data."""
from __future__ import annotations

from typing import Dict

from app.langgraph.io.validation import ensure_discovery
from .base import IOValidatedNode


class DiscoverySummarizeNode(IOValidatedNode):
    """Polishes discovery metadata while keeping the schema contract intact."""

    _in_validator = ensure_discovery
    _out_validator = ensure_discovery

    def _run(self, payload: Dict[str, str]) -> Dict[str, str]:
        ziel = payload.get("ziel", "")
        summary = payload.get("zusammenfassung", "")

        if summary and ziel and ziel not in summary:
            summary = f"{ziel}: {summary}"
        summary = summary[:400]

        missing = list(payload.get("fehlende_parameter", []))
        if len(missing) > 3:
            missing = missing[:3]

        ready = payload.get("ready_to_route", False)
        if missing and ready:
            ready = False

        return {
            "schema_version": payload.get("schema_version", "1.0.0"),
            "ziel": ziel,
            "zusammenfassung": summary or ziel,
            "fehlende_parameter": missing,
            "ready_to_route": ready,
        }


__all__ = ["DiscoverySummarizeNode"]
