"""One-off Qdrant-interim ingest: embed the current seed (9 reviewed + 38 provisional cards) into
prod Qdrant. Run INSIDE the backend-v2 container so it uses the prod env (Qdrant URL on the docker
network, OpenAI key, embed provider) — the new seed is docker-cp'd in first.

    docker cp .../fachkarten_seed.json backend-v2:/app/sealai_v2/knowledge/fachkarten_seed.json
    docker exec -i backend-v2 python - < ops/ingest_prod_qdrant.py

Idempotent: uuid5 point ids → the 28 reviewed points re-upsert identically, the 522 provisional add.
"""
from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.fachkarten import load_fachkarten
from sealai_v2.knowledge.qdrant_retrieval import ingest_fachkarten, _make_client

s = Settings()
c = _make_client(s)
print("collection      :", s.qdrant_collection)
print("embed provider  :", getattr(s, "embed_provider", "?"))
print("baseline points :", c.count(s.qdrant_collection).count)

cat = load_fachkarten()
claims = sum(len(x.claims) for x in cat.cards)
print(
    "seed loaded     :",
    len(cat.cards),
    "cards |",
    len(cat.reviewed()),
    "reviewed |",
    claims,
    "claims",
)

n = ingest_fachkarten(s)
print("upserted points :", n)
print("after points    :", c.count(s.qdrant_collection).count)
