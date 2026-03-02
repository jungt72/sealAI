"""FactCardStore — loads and queries PTFE FactCard knowledge base.

Singleton pattern: use ``FactCardStore.get_instance()`` for shared access.
Falls back gracefully if KB files are absent (returns empty results, no crash).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("app.services.knowledge.factcard_store")

_DEFAULT_KB_PATH = Path(__file__).parent.parent.parent / "data" / "kb" / "SEALAI_KB_PTFE_factcards_gates_v1_3.json"

_instance: Optional[FactCardStore] = None
_PTFE_FACTCARD_ID_PATTERN = re.compile(r"^PTFE-F-\d{3}$", re.IGNORECASE)


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
        self._sources: Dict[str, Dict[str, Any]] = {}
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
            self._sources = data.get("sources") or {}
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
        """Return FactCard by legacy ``compound_id`` or direct ``id``."""
        for card in self._factcards:
            if card.get("compound_id") == compound_id:
                return card
        return self.get_by_id(compound_id)

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
        if property_name in props:
            return props.get(property_name)
        if card.get("property") == property_name:
            return card.get("value")
        return None

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
        q = (query_lower or "").strip()
        if not q:
            return []

        legacy_trigger_keywords = {
            "chemical_resistance_query": [
                "chemisch beständig", "chemical resistance", "beständigkeit", "verträglichkeit"
            ],
            "food_grade_query": ["food grade", "fda", "pharma", "lebensmittel"],
        }
        legacy_matches: set[str] = set()
        for trigger, kws in legacy_trigger_keywords.items():
            if any(kw in q for kw in kws):
                legacy_matches.add(trigger)

        query_tokens = {
            tok for tok in re.split(r"[^a-z0-9]+", q.lower())
            if len(tok) >= 3 and tok not in {"what", "with", "gegen", "eine", "oder"}
        }
        if medium:
            query_tokens.update(
                tok for tok in re.split(r"[^a-z0-9]+", medium.lower()) if len(tok) >= 3
            )
        if food_grade:
            query_tokens.update({"food", "grade", "fda", "pharma", "uhp"})

        is_detailed_parameter_query = self._is_detailed_parameter_query(q)
        scored: List[tuple[int, Dict[str, Any]]] = []
        query_number_tokens = set(re.findall(r"\d+(?:[.,]\d+)?", q))
        for card in self._factcards:
            card_triggers = set(card.get("deterministic_triggers") or [])
            if legacy_matches and card_triggers.intersection(legacy_matches):
                scored.append((3, card))
                continue
            searchable = " ".join(
                str(card.get(field) or "")
                for field in ("topic", "property", "conditions", "value", "units", "do_not_infer")
            ).lower()
            score = sum(1 for tok in query_tokens if tok in searchable)
            if score <= 0:
                continue
            if query_number_tokens:
                if any(token in str(card.get("conditions") or "") for token in query_number_tokens):
                    score += 2
            if "tfm1700" in q and "tfm1700" in searchable:
                score += 3
            if "permeability" in q and "permeability" in searchable:
                score += 2
            if "hcl" in q and "hcl" in searchable:
                score += 3
            scored.append((score, card))

        scored.sort(key=lambda item: item[0], reverse=True)
        ranked_cards = [card for _, card in scored]

        if not is_detailed_parameter_query:
            return ranked_cards[:5]

        if not ranked_cards:
            ranked_cards = list(self._factcards)

        if len(ranked_cards) <= 15:
            return ranked_cards[:15]

        summarized = self._summarize_technical_table_cards(ranked_cards, per_topic=3)
        log.info(
            "factcard_store.summarized_technical_table",
            extra={"original_count": len(ranked_cards), "returned_count": len(summarized)},
        )
        return summarized

    @staticmethod
    def _is_detailed_parameter_query(query: str) -> bool:
        q = (query or "").lower()
        keywords = (
            "detaillierte parameter",
            "detail parameter",
            "detailliert",
            "alle parameter",
            "vollständige parameter",
            "vollstaendige parameter",
            "parameter tabelle",
            "technical table",
            "technical parameters",
            "datenblatt",
        )
        return any(kw in q for kw in keywords)

    @staticmethod
    def _topic_bucket(card: Dict[str, Any]) -> Optional[str]:
        topic = str(card.get("topic") or "").strip().lower()
        tags = [str(t).strip().lower() for t in (card.get("topic_tags") or []) if str(t).strip()]
        haystack = " ".join([topic, *tags])

        if any(token in haystack for token in ("thermal", "temperature", "heat", "kryo", "cryogenic")):
            return "Thermal"
        if any(token in haystack for token in ("mechanical", "tribology", "friction", "wear", "strength", "modulus")):
            return "Mechanical"
        if any(token in haystack for token in ("chemical", "compatibility", "resistance", "permeability", "media", "safety")):
            return "Chemical"
        return None

    def _summarize_technical_table_cards(
        self,
        ranked_cards: List[Dict[str, Any]],
        per_topic: int = 3,
    ) -> List[Dict[str, Any]]:
        grouped: Dict[str, List[Dict[str, Any]]] = {"Thermal": [], "Mechanical": [], "Chemical": []}
        for card in ranked_cards:
            bucket = self._topic_bucket(card)
            if bucket is None:
                continue
            if len(grouped[bucket]) >= per_topic:
                continue
            grouped[bucket].append(card)
            if all(len(grouped[name]) >= per_topic for name in grouped):
                break

        flattened: List[Dict[str, Any]] = []
        for name in ("Thermal", "Mechanical", "Chemical"):
            flattened.extend(grouped[name])
        if flattened:
            return flattened

        return ranked_cards[: min(len(ranked_cards), 9)]

    def source_rank_for(self, source_id: Optional[str]) -> Optional[int]:
        if not source_id:
            return None
        entry = self._sources.get(source_id)
        if not isinstance(entry, dict):
            return None
        rank = entry.get("rank")
        return int(rank) if isinstance(rank, (int, float)) else None


def is_validated_ptfe_factcard_id(card_id: Any) -> bool:
    """Return True when *card_id* is part of validated PTFE master factcards."""
    candidate = str(card_id or "").strip()
    return bool(_PTFE_FACTCARD_ID_PATTERN.fullmatch(candidate))
