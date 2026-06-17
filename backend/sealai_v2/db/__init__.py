"""db — V2 durable persistence (build-spec §3: Postgres = durable system-of-record).

Green-field, self-contained: own SQLAlchemy engine + declarative ``Base`` + sync adapters that
implement the SAME memory Protocols as the in-process store (``core.contracts.ConversationMemory``
/ ``CrossSessionMemory``) — a config-gated drop-in (M3 lazy-adapter pattern), zero contract change.

Closes "gap #1: production persistence": memory layers 1-3 (working window / structured case-state
/ history) survive a process restart, and the layer-4 cross-session seam is wired to a durable store
instead of hard-returning nothing. Postgres (psycopg2) is the production driver; sqlite backs the
offline parity tests. NEVER imports ``app.*`` (green-field boundary — keystone test).

Tenant scope (P0) is mandatory at every read/write — a durable cross-tenant leak is the worst case
(build-spec §7), so it is enforced in every adapter method via ``security.tenant.require_tenant``.
"""
