#!/usr/bin/env python3
"""Atomic PTFE FactCard ingestion into Qdrant `technical_docs` collection."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from qdrant_client import QdrantClient, models


def _load_factcards(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    cards = list(data.get("factcards") or [])
    if len(cards) != 119:
        raise ValueError(f"Expected 119 factcards, got {len(cards)}")
    return cards


def _searchable_text(card: Dict[str, Any]) -> str:
    parts = [
        f"FactCard {card.get('id')}",
        f"Topic: {card.get('topic')}",
        f"Property: {card.get('property')}",
        f"Value: {card.get('value')}",
        f"Units: {card.get('units')}",
        f"Source rank: {card.get('source_rank')}",
        f"Conditions: {card.get('conditions')}",
        f"Method: {card.get('test_method')}",
    ]
    do_not_infer = str(card.get("do_not_infer") or "").strip()
    if do_not_infer:
        parts.append(f"DO_NOT_INFER: {do_not_infer}")
    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest PTFE factcards as atomic vectors.")
    parser.add_argument(
        "--kb-path",
        default=str(
            Path(__file__).resolve().parents[2]
            / "upload"
            / "PTFE"
            / "SEALAI_KB_PTFE_factcards_gates_v1_3.json"
        ),
    )
    parser.add_argument("--collection", default=os.getenv("QDRANT_TECHNICAL_COLLECTION", "technical_docs"))
    parser.add_argument("--qdrant-url", default=os.getenv("QDRANT_URL", "http://localhost:6333"))
    parser.add_argument("--qdrant-api-key", default=os.getenv("QDRANT_API_KEY"))
    args = parser.parse_args()

    kb_path = Path(args.kb_path).expanduser().resolve()
    cards = _load_factcards(kb_path)

    # Reuse app embedding setup so retrieval stays consistent.
    from app.services.rag import rag_orchestrator  # pylint: disable=import-outside-toplevel

    texts = [_searchable_text(card) for card in cards]
    vectors = rag_orchestrator._embed(texts)  # type: ignore[attr-defined]
    if not vectors:
        raise RuntimeError("No embeddings generated.")
    vector_dim = len(vectors[0])

    client = QdrantClient(url=args.qdrant_url, api_key=(args.qdrant_api_key or None))
    try:
        client.get_collection(args.collection)
    except Exception:
        client.recreate_collection(
            collection_name=args.collection,
            vectors_config=models.VectorParams(size=vector_dim, distance=models.Distance.COSINE),
        )

    points: List[models.PointStruct] = []
    for idx, (card, vec, text) in enumerate(zip(cards, vectors, texts), start=1):
        payload = {
            "id": card.get("id"),
            "topic": card.get("topic"),
            "property": card.get("property"),
            "value": card.get("value"),
            "units": card.get("units"),
            "source_rank": card.get("source_rank"),
            "source": card.get("source"),
            "text": text,
            "doc_type": "ptfe_factcard",
        }
        points.append(models.PointStruct(id=idx, vector=vec, payload=payload))

    client.upsert(collection_name=args.collection, points=points, wait=True)
    print(
        f"Ingested {len(points)} PTFE factcards into '{args.collection}' "
        f"at {args.qdrant_url} (vector_dim={vector_dim})."
    )


if __name__ == "__main__":
    main()
