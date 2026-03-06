from __future__ import annotations

import json

from app.services.knowledge.factcard_store import FactCardStore, is_validated_ptfe_factcard_id


def test_detailed_parameter_query_is_summarized_by_topic(tmp_path) -> None:
    cards = []
    for idx in range(8):
        cards.append(
            {
                "id": f"T-{idx}",
                "topic": "thermal",
                "property": f"ptfe_thermal_{idx}",
                "conditions": "ptfe",
                "value": idx,
                "units": "u",
            }
        )
    for idx in range(8):
        cards.append(
            {
                "id": f"M-{idx}",
                "topic": "mechanical",
                "property": f"ptfe_mechanical_{idx}",
                "conditions": "ptfe",
                "value": idx,
                "units": "u",
            }
        )
    for idx in range(8):
        cards.append(
            {
                "id": f"C-{idx}",
                "topic": "chemical",
                "property": f"ptfe_chemical_{idx}",
                "conditions": "ptfe",
                "value": idx,
                "units": "u",
            }
        )

    kb_path = tmp_path / "kb.json"
    kb_path.write_text(json.dumps({"factcards": cards, "gates": []}), encoding="utf-8")
    store = FactCardStore(kb_path=kb_path)

    result = store.match_query_to_cards("detaillierte parameter ptfe")
    assert len(result) == 9

    topics = [str(card.get("topic") or "").lower() for card in result]
    assert topics.count("thermal") == 3
    assert topics.count("mechanical") == 3
    assert topics.count("chemical") == 3


def test_is_validated_ptfe_factcard_id() -> None:
    assert is_validated_ptfe_factcard_id("PTFE-F-001") is True
    assert is_validated_ptfe_factcard_id("ptfe-f-119") is True
    assert is_validated_ptfe_factcard_id("PTFE-F-12") is False
    assert is_validated_ptfe_factcard_id("doc-ptfe") is False
