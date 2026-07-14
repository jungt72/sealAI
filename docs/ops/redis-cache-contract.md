# Redis and exact-answer cache contract

## Current production contract

The sealingAI V2 API and its Postgres outbox worker do not depend on Redis,
Celery, or Kombu. Redis remains a shared Paperless dependency and a legacy V1
data store; it is not a V2 cache or queue. V2 must continue to start and process
its durable Postgres outbox when Redis is unavailable.

The V2 exact-answer cache is process-local, disabled by default, and currently
hard-disabled by `Settings` even if an operator supplies a well-formed digest.
A config-provided static digest cannot observe mutable ledger transitions.
Activation remains unavailable until the ledger advances and exposes its epoch
atomically on every cache read and write, with real lifecycle integration tests.
The eventual activation contract additionally requires all of the following:

- the deterministic execution policy is enabled;
- `SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH` is a canonical `sha256:<64 hex>` digest
  of the complete active authority set;
- the epoch changes before any approval, quarantine, revocation, expiry, or
  authority-relevant replacement can be served;
- a finite TTL of at most 24 hours is configured;
- both global and per-tenant entry ceilings are valid.

Cache keys bind the tenant, whitespace-normalized but case-preserving question,
versioned cache contract,
knowledge version, execution policy, answer contract, model identity, structured
answer mode, and authority epoch. The stored key is an irreversible digest.
Entries expose aggregate counts, hit/miss rate, expiry, capacity eviction, and
invalidation counts only. They never expose tenant IDs, questions, answers, or
key material through metrics.

Changing the authority epoch makes every older key unreachable. Explicit
tenant or global invalidation is also available. Production activation remains
blocked until the authority epoch is advanced atomically by every mutable
ledger lifecycle path and bound into exact release evidence; a manually chosen
or static placeholder epoch is not valid evidence.

## Future Redis adapters

A future Redis-backed V2 cache must preserve the same contract and additionally
use a versioned, allowlisted cache namespace with mandatory TTL on every entry.
It must enforce tenant cardinality independently of total cardinality. Unknown
namespaces fail closed.

Cache, locks, rate limits, queues, sessions, and non-rebuildable workflow state
are separate data classes. They must not share an eviction domain or deletion
procedure merely because they use Redis. Queue/session/lock state is never
classified as rebuildable cache.

Do not change `noeviction` on the shared production instance. A policy change is
eligible only after rebuildable cache has its own bounded instance or equivalent
isolation, non-rebuildable state has verified recovery, the effects and rollback
are tested, and GATE-04 plus the applicable deployment gate are approved.

## Required monitoring

The target state records and alerts on:

- used memory and configured maxmemory, with warning before 80% and a stable
  target at or below 70%;
- total and per-category key counts and growth;
- TTL coverage for rebuildable cache categories;
- evictions and rejected writes;
- queue depth for explicitly classified queue categories;
- cache hits, misses, and hit rate;
- unknown categories or owner drift.

Raw Redis keys, values, payloads, tenant names, user identifiers, and personal
data are forbidden in events, metrics, manifests, approvals, and receipts.
