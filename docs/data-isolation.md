# Data Isolation: Tenant-Scoped vs. Global Knowledge

## The two scopes

- **Tenant-scoped**: everything a specific customer's session/case produces — `V2Session`,
  `V2Message`, `V2Fact`, `V2Derived`, `V2DurableFact`, `V2LegalAcceptance` (`db/models.py`). Every
  row is keyed `tenant_id`-first. Enforced at the API boundary by `security/tenant.py`'s
  `require_tenant()` (fail-closed — raises if tenant is missing/empty) and threaded through
  `pipeline.run()`'s `TenantContext` from day one (P0).
- **Global/public**: the curated Fachkarten knowledge base (sealing-technology domain knowledge,
  owner-reviewed) — stored in Qdrant under `tenant_id: GLOBAL_TENANT`
  (`knowledge/qdrant_retrieval.py`). Every tenant's retrieval query includes `GLOBAL_TENANT`
  alongside its own `tenant_id` (`MatchAny(any=[tenant_id, GLOBAL_TENANT])`) — this is how a
  customer session sees the shared knowledge base without customer data ever entering it.

## The current write path (audited 2026-07-08)

**There is no customer-upload ingestion endpoint anywhere in the codebase.** The only Qdrant WRITE
path is `ingest_fachkarten()` / `claim_points()` — owner-curated Fachkarten knowledge, called either
via the CLI (`ops/ingest_fachkarte.py`) or the Paperless webhook (`api/routes/rag_ingest.py`, a
static-shared-secret-authenticated endpoint, NOT the tenant-JWT flow). Both hardcode
`tenant_id: GLOBAL_TENANT` — there is structurally no way to write a tenant-scoped point today.
`test_tenant_isolation.py::test_ingest_fachkarten_only_writes_to_the_global_tenant_scope` locks this
in by asserting neither function even accepts a `tenant_id` parameter.

## Guardrail for a future upload feature

This absence of a write path is the reason Legal-by-Design Phase C is preventive, not remedial. If/
when a customer-upload feature is built, it MUST:

1. Require `tenant_id` + `case_id` on every write (mirrors the fail-closed pattern already used by
   `QdrantFachkartenRetriever.retrieve()`, which raises `ValueError` on an empty `tenant_id`).
2. Never write to `GLOBAL_TENANT` from a customer-triggered path — promotion draft→global stays a
   separate, deliberate, owner-authorized step (mirrors the existing Fachkarten `review_state`
   draft→reviewed discipline).
3. Reuse `tests/_tenant_assertions.py::assert_tenant_scoped_query()` in its own test suite — it
   asserts a Qdrant `Filter` restricts a query to exactly `{tenant_id, GLOBAL_TENANT}`, catching a
   missing-scope or leaked-extra-tenant regression immediately.

## Tests

`backend/sealai_v2/tests/test_tenant_isolation.py` — retrieval query scoping (dense + hybrid),
missing-tenant_id hard failure, no-tenant-parameter-on-any-write-path. `test_tenant_guard.py` —
`require_tenant()`'s own fail-closed behavior. `test_api_chat.py`'s cross-tenant tests — token-driven
isolation at the API layer (a spoofed tenant header is ignored; each tenant's token only sees its
own session history).
