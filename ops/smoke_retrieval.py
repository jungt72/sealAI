"""Smoke: does the product retriever now surface the newly-promoted PROVISIONAL Fachkarten?
Run inside backend-v2: docker exec -i backend-v2 python - < ops/smoke_retrieval.py"""
import asyncio
from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.qdrant_retrieval import QdrantFachkartenRetriever

s = Settings()
r = QdrantFachkartenRetriever(s)

QUERIES = [
    "Welcher Dichtungswerkstoff eignet sich fuer DOT 4 Bremsfluessigkeit?",  # MEDIUM-BREMSFLUESSIGKEIT (new, provisional)
    "HNBR Eignung fuer Hochdruckgas und RGD",                                # HNBR / HOCHDRUCKGAS-RGD (new)
    "FFKM Reinheit Halbleiterfertigung",                                     # FFKM (new)
]

for q in QUERIES:
    res = asyncio.run(r.retrieve(q, tenant_id="promote-smoke", k=5))
    print("\nQ:", q, "->", type(res).__name__)
    found = {}
    for attr in ("grounding_facts", "provisional", "facts", "hits", "reviewed", "draft"):
        v = getattr(res, attr, None)
        if isinstance(v, (list, tuple)):
            found[attr] = v
            print(f"  {attr}: {len(v)}")
    # show one sample provisional fact text if present
    sample = found.get("provisional") or found.get("draft") or found.get("facts") or found.get("hits")
    if sample:
        item = sample[0]
        txt = getattr(item, "text", None) or getattr(item, "claim", None) or str(item)
        print("  sample:", str(txt)[:140])
