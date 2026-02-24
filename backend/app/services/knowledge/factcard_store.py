"""FactCardStore — loads and queries PTFE FactCard knowledge base.

Singleton pattern: use ``FactCardStore.get_instance()`` for shared access.
Falls back gracefully if KB files are absent (returns empty results, no crash).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("app.services.knowledge.factcard_store")

_DEFAULT_KB_PATH = Path(__file__).parent.parent.parent / "data" / "kb" / "SEALAI_KB_PTFE_factcards_gates_v1_3.json"

_instance: Optional[FactCardStore] = None


class FactCardStore:
    """Provides deterministic lookup of PTFE material factcards.

    Parameters
    ----------
    kb_path:
        Path to the FactCards + Gates JSON file.  Defaults to the bundled KB.
    """

    def __init__(self, kb_path: Optional[Path] = None) -> None:
        self._path = kb_path or _DEFAULT_KB_PATH
        self._factcards: List[Dict[str, Any]] = []
        self._gates: List[Dict[str, Any]] = []
        self._loaded = False
        self._load()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(cls) -> "FactCardStore":
        global _instance
        if _instance is None:
            _instance = cls()
        return _instance

    @classmethod
    def reset_instance(cls) -> None:
        """For testing — force reload on next get_instance()."""
        global _instance
        _instance = None

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load(self) -> None:
        if not self._path.exists():
            log.warning("factcard_store.kb_file_missing", extra={"path": str(self._path)})
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._factcards = data.get("factcards") or []
            self._gates = data.get("gates") or []
            self._loaded = True
            log.info(
                "factcard_store.loaded",
                extra={"cards": len(self._factcards), "gates": len(self._gates)},
            )
        except Exception as exc:
            log.error("factcard_store.load_failed", extra={"error": str(exc)})

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_by_id(self, card_id: str) -> Optional[Dict[str, Any]]:
        """Return a single FactCard by its ``id`` field, or None."""
        for card in self._factcards:
            if card.get("id") == card_id:
                return card
        return None

    def get_by_compound_id(self, compound_id: str) -> Optional[Dict[str, Any]]:
        """Return a FactCard matching ``compound_id``, or None."""
        for card in self._factcards:
            if card.get("compound_id") == compound_id:
                return card
        return None

    def search_by_topic(self, topic: str) -> List[Dict[str, Any]]:
        """Return all FactCards whose ``topic_tags`` contain *topic* (case-insensitive)."""
        topic_lower = topic.lower()
        return [
            card for card in self._factcards
            if any(t.lower() == topic_lower for t in (card.get("topic_tags") or []))
        ]

    def search_by_trigger(self, trigger: str) -> List[Dict[str, Any]]:
        """Return all FactCards whose ``deterministic_triggers`` include *trigger*."""
        trigger_lower = trigger.lower()
        return [
            card for card in self._factcards
            if any(t.lower() == trigger_lower for t in (card.get("deterministic_triggers") or []))
        ]

    def lookup_property(self, compound_id: str, property_name: str) -> Any:
        """Return a specific property value for a compound, or None."""
        card = self.get_by_compound_id(compound_id)
        if card is None:
            return None
        props: Dict[str, Any] = card.get("properties") or {}
        return props.get(property_name)

    def all_cards(self) -> List[Dict[str, Any]]:
        """Return all loaded FactCards."""
        return list(self._factcards)

    def all_gates(self) -> List[Dict[str, Any]]:
        """Return all loaded Gates."""
        return list(self._gates)

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    def match_query_to_cards(
        self,
        query_lower: str,
        medium: Optional[str] = None,
        food_grade: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Heuristic: return cards relevant to the query and optional filters.

        Used by ``node_factcard_lookup`` to detect deterministic questions.
        """
        results: List[Dict[str, Any]] = []

        trigger_keywords = {
            "chemical_resistance_query": [
                "chemisch beständig", "chemical resistance", "beständigkeit",
                "verträglichkeit", "säure", "lauge", "lösungsmittel"
            ],
            "temperature_range_query": [
                "temperatur", "temperature", "einsatztemperatur",
                "temperaturbereich", "°c", "celsius"
            ],
            "food_grade_query": [
                "lebensmittel", "food grade", "food-grade", "fda", "trinkwasser",
                "pharma", "nahrungsmittel"
            ],
            "antistatic_query": [
                "antistatisch", "antistatic", "elektrisch leitfähig",
                "elektrostatisch", "ableitfähig"
            ],
            "high_pressure_static_query": [
                "hochdruck", "high pressure", "350 bar", "400 bar", "500 bar",
                "hochdruckdichtung"
            ],
            "dry_running_query": [
                "trockenlauf", "dry running", "ohne schmierung", "trocken"
            ],
            "guide_ring_query": [
                "führungsring", "guide ring", "gleitlager", "führungselement"
            ],
            "cold_flow_reduction_query": [
                "kaltfluss", "cold flow", "kriechfestigkeit", "kriech"
            ],
        }

        matched_triggers: set[str] = set()
        for trigger, keywords in trigger_keywords.items():
            if any(kw in query_lower for kw in keywords):
                matched_triggers.add(trigger)

        if medium:
            medium_lower = medium.lower()
            if any(kw in medium_lower for kw in ["säure", "acid", "lauge", "alkali"]):
                matched_triggers.add("chemical_resistance_query")
            if any(kw in medium_lower for kw in ["lebensmittel", "food", "pharma"]):
                matched_triggers.add("food_grade_query")

        for card in self._factcards:
            # food-grade filter
            if food_grade is True and not card.get("food_grade", False):
                continue
            # trigger match
            card_triggers = set(card.get("deterministic_triggers") or [])
            if matched_triggers & card_triggers:
                results.append(card)

        return results
