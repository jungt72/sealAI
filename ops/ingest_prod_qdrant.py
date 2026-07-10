"""Compatibility entrypoint for a full knowledge publication.

The historical script wrote the seed directly to Qdrant. That bypass is closed:
publication now idempotently imports the reviewed artifact into Postgres and
drains the transactional derived-index outbox.
"""

from sealai_v2.config.settings import Settings
from sealai_v2.knowledge.bootstrap import bootstrap_seed
from sealai_v2.knowledge.ledger import build_knowledge_ledger
from sealai_v2.knowledge.outbox_worker import main as outbox_main

settings = Settings()
print("collection      :", settings.qdrant_collection)
print("ledger import   :", bootstrap_seed(build_knowledge_ledger(settings)))
raise SystemExit(outbox_main(["drain-all", "--batch-size", "100"]))
