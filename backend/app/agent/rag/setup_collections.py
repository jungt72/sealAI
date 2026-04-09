"""Qdrant-Collection-Setup fuer sealai_technical_docs.

Erstellt die Ziel-Collection mit:
  - Dense Vector: 384-dim, Cosine (paraphrase-multilingual-MiniLM-L12-v2)
  - Sparse Vector: BM25
  - Payload-Indizes: sts_mat_codes, sts_type_codes, doc_type, language

Kann idempotent aufgerufen werden — existierende Collection wird nicht
geloescht, nur fehlende Indizes werden nachgezogen.

Verwendung:
  python -m app.agent.rag.setup_collections [--qdrant-url http://qdrant:6333]
"""

from __future__ import annotations

import argparse
import logging
import sys

from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    SparseIndexParams,
    SparseVectorParams,
    VectorParams,
)

logger = logging.getLogger(__name__)

COLLECTION_NAME = "sealai_technical_docs"
DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "bm25"
DENSE_DIM = 384
DENSE_DISTANCE = Distance.COSINE

PAYLOAD_INDICES: dict[str, PayloadSchemaType] = {
    "sts_mat_codes": PayloadSchemaType.KEYWORD,
    "sts_type_codes": PayloadSchemaType.KEYWORD,
    "doc_type": PayloadSchemaType.KEYWORD,
    "language": PayloadSchemaType.KEYWORD,
}


def collection_exists(client: QdrantClient, name: str) -> bool:
    """Pruefe ob eine Collection existiert."""
    try:
        client.get_collection(name)
        return True
    except (UnexpectedResponse, Exception):
        return False


def create_collection(client: QdrantClient) -> bool:
    """Erstelle sealai_technical_docs. Gibt True zurueck wenn neu erstellt."""
    if collection_exists(client, COLLECTION_NAME):
        logger.info("Collection '%s' existiert bereits.", COLLECTION_NAME)
        return False

    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            DENSE_VECTOR_NAME: VectorParams(
                size=DENSE_DIM,
                distance=DENSE_DISTANCE,
            ),
        },
        sparse_vectors_config={
            SPARSE_VECTOR_NAME: SparseVectorParams(
                index=SparseIndexParams(),
            ),
        },
        on_disk_payload=True,
    )
    logger.info("Collection '%s' erstellt (384-dim, Cosine, BM25).", COLLECTION_NAME)
    return True


def ensure_payload_indices(client: QdrantClient) -> list[str]:
    """Stelle sicher, dass alle Payload-Indizes vorhanden sind.

    Gibt Liste der neu erstellten Index-Namen zurueck.
    """
    info = client.get_collection(COLLECTION_NAME)
    existing = set(info.payload_schema.keys()) if info.payload_schema else set()
    created: list[str] = []

    for field_name, schema_type in PAYLOAD_INDICES.items():
        if field_name not in existing:
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field_name,
                field_schema=schema_type,
            )
            logger.info("Payload-Index '%s' (%s) erstellt.", field_name, schema_type)
            created.append(field_name)
        else:
            logger.info("Payload-Index '%s' existiert bereits.", field_name)

    return created


def setup(qdrant_url: str = "http://qdrant:6333") -> dict:
    """Hauptfunktion: Collection anlegen + Indizes sicherstellen.

    Returns:
        dict mit Ergebnis-Details.
    """
    client = QdrantClient(url=qdrant_url, timeout=30)

    was_created = create_collection(client)
    new_indices = ensure_payload_indices(client)

    # Verifizierung
    info = client.get_collection(COLLECTION_NAME)
    vectors_config = info.config.params.vectors
    dense_cfg = vectors_config.get(DENSE_VECTOR_NAME) if isinstance(vectors_config, dict) else None

    result = {
        "collection": COLLECTION_NAME,
        "created": was_created,
        "new_indices": new_indices,
        "dense_size": dense_cfg.size if dense_cfg else None,
        "dense_distance": str(dense_cfg.distance) if dense_cfg else None,
        "sparse_vectors": list(info.config.params.sparse_vectors.keys())
        if info.config.params.sparse_vectors
        else [],
        "payload_indices": list(info.payload_schema.keys())
        if info.payload_schema
        else [],
        "points_count": info.points_count,
    }
    return result


def main() -> None:
    """CLI-Einstiegspunkt."""
    parser = argparse.ArgumentParser(description="Qdrant Collection Setup fuer SealAI")
    parser.add_argument(
        "--qdrant-url",
        default="http://qdrant:6333",
        help="Qdrant HTTP URL (default: http://qdrant:6333)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    result = setup(args.qdrant_url)

    print("\n=== Qdrant Collection Setup ===")
    print(f"Collection:      {result['collection']}")
    print(f"Neu erstellt:    {result['created']}")
    print(f"Dense Dim:       {result['dense_size']}")
    print(f"Dense Distance:  {result['dense_distance']}")
    print(f"Sparse Vectors:  {result['sparse_vectors']}")
    print(f"Payload-Indizes: {result['payload_indices']}")
    print(f"Neue Indizes:    {result['new_indices']}")
    print(f"Points:          {result['points_count']}")


if __name__ == "__main__":
    main()
