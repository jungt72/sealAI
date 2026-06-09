"""memory — Gedächtnis, 4 Schichten (build-spec §7).

1. working window (recent verbatim turns), 2. structured case-state (distilled REMEMBERED-CLAIMS
→ case_context; the re-ask keystone), 3. history (persist/list/recall), 4. cross-session durable
facts (seam only).

M5 lands layers 1-3 as a pure in-process store (``store.InProcessConversationMemory``) + a light
LLM distiller (``distiller.Distiller``); layer 4 is a complete Protocol seam with a trivial
in-process impl (``store.InProcessCrossSessionMemory``) whose curation/relevance/retrieval logic is
DEFERRED to its own sub-gate. The Redis (working/live), Postgres (history/snapshot) and Qdrant
(cross-session retrieval) adapters swap in by config behind the same Protocols (build-spec §3) — no
new infra now. Tenant scope is mandatory at every read/write (P0); memory never gates or routes.
"""
