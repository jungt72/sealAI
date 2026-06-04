"""
Seed 3 pilot datasheet chunks into Qdrant collection 'sealai_technical_docs'.

Run inside the backend container:
  python -m app.agent.rag.seed_pilot_chunks

Or directly:
  docker exec backend python /app/app/agent/rag/seed_pilot_chunks.py

Idempotent: uses deterministic IDs derived from sts_mat code.
Collection: sealai_technical_docs  (384-dim COSINE, named vector 'dense')
Embedding:  sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
"""

from __future__ import annotations

import os
import hashlib
import logging

log = logging.getLogger(__name__)

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "sealai_technical_docs")
EMBED_MODEL = os.getenv(
    "FASTEMBED_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
CACHE_PATH = os.getenv("FASTEMBED_CACHE_PATH", "/tmp/fastembed_cache")

# ---------------------------------------------------------------------------
# Pilot datasheets (one chunk per material for Phase-F smoke tests)
# ---------------------------------------------------------------------------
PILOT_CHUNKS = [
    {
        "sts_mat": "STS-MAT-SIC-A1",
        "sts_type": "STS-TYPE-GS-CART",
        "doc_type": "datasheet",
        "lang": "de",
        "source": "pilot",
        "title": "SiC Datenblatt v2",
        "text": (
            "Siliciumcarbid (SiC) Werkstoff STS-MAT-SIC-A1. "
            "Einsatzbereich: Gleitringdichtungen in aggressiven Medien. "
            "Temperaturbereich: -200°C bis +450°C. "
            "Druckbereich: bis 40 bar. "
            "Geeignet für: Salzwasser, Säuren, Laugen, Kohlenwasserstoffe. "
            "Härte: 2400 HV. Thermische Leitfähigkeit: 120 W/mK. "
            "Gleitreibungskoeffizient: 0,05 (trocken). "
            "Normbezug: DIN EN 12756, ISO 21049."
        ),
    },
    {
        "sts_mat": "STS-MAT-FKM-A1",
        "sts_type": "STS-TYPE-OR-A",
        "doc_type": "datasheet",
        "lang": "de",
        "source": "pilot",
        "title": "FKM Datenblatt v1",
        "text": (
            "FKM (Viton) Werkstoff STS-MAT-FKM-A1. "
            "Temperaturbereich -20°C bis +200°C (kurzzeitig +220°C). "
            "Druckbereich: bis 20 bar. "
            "Medienbeständigkeit: Mineralöle, Kraftstoffe, aromatische KW, "
            "verdünnte Säuren. Nicht geeignet für: Ketone, Ester, Amine. "
            "Härte: 70–80 Shore A. Zugfestigkeit: 10 MPa. "
            "Normbezug: ISO 1629 (FKM), ASTM D1418."
        ),
    },
    {
        "sts_mat": "STS-MAT-PTFE-A1",
        "sts_type": "STS-TYPE-RWDR-A",
        "doc_type": "datasheet",
        "lang": "de",
        "source": "pilot",
        "title": "PTFE Datenblatt v1",
        "text": (
            "PTFE Werkstoff STS-MAT-PTFE-A1. Universell chemikalienbeständig. "
            "Temperaturbereich: -200°C bis +260°C. "
            "Druckbereich: statisch bis 25 bar. "
            "Geeignet für: nahezu alle Chemikalien inkl. Säuren, Laugen, "
            "Lösemittel, Wasser, Lebensmittel (FDA-konform). "
            "Nicht geeignet für: Alkalimetalle, Fluor. "
            "Reibungskoeffizient: 0,04 (sehr niedrig). "
            "Normbezug: DIN 28090, FDA 21 CFR 177.1550."
        ),
    },
]


def _chunk_id(sts_mat: str) -> int:
    """Deterministic integer ID from sts_mat code (fits Qdrant uint64)."""
    digest = hashlib.md5(f"pilot:{sts_mat}".encode()).hexdigest()
    return int(digest[:16], 16)


def seed(verbose: bool = True) -> None:
    from fastembed import TextEmbedding
    from qdrant_client import QdrantClient
    from qdrant_client.models import PointStruct

    model = TextEmbedding(EMBED_MODEL, cache_dir=CACHE_PATH)
    client = QdrantClient(url=QDRANT_URL)

    texts = [c["text"] for c in PILOT_CHUNKS]
    embeddings = list(model.embed(texts))

    points = [
        PointStruct(
            id=_chunk_id(chunk["sts_mat"]),
            vector={"dense": emb.tolist()},
            payload=chunk,
        )
        for chunk, emb in zip(PILOT_CHUNKS, embeddings)
    ]

    client.upsert(collection_name=COLLECTION, points=points)

    info = client.get_collection(COLLECTION)
    if verbose:
        print(
            f"[seed_pilot_chunks] Upserted {len(points)} points "
            f"→ {COLLECTION} (total: {info.points_count})"
        )
        for p in points:
            print(f"  id={p.id}  sts_mat={p.payload['sts_mat']}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    seed()
