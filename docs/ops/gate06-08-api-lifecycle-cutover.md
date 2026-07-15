# API-001 — Gate-06/07/08 cutover contract

Status: **IMPLEMENTED_NOT_DEPLOYED / BLOCKED_EXTERNAL**. This document is a preparation and
verification contract. It does not approve a production mutation, choose legal terms, set a
retention period, create a secret, or authorize a deployment.

## Authority boundary

The service may validate exact version identifiers supplied by an external authority; it may not
author legal text or infer a retention period. Before activation, accountable humans must approve
and record all of the following:

- the exact policy authority reference, purpose version, and consent version shown by the UI and
  accepted by the API;
- the rights/license declaration choices and the manufacturer-handoff wording;
- whether a retention-review duration is authorized and, if so, its exact integer day value;
- receipt-HMAC generation, custody, access, backup, rotation, and historical verification policy;
- actor/tenant rate, daily, storage, concurrency, and lease limits against an approved abuse and
  capacity model;
- privacy authority for platform-owner review access and manufacturer visibility of active leads.

An empty `SEALAI_V2_API_LIFECYCLE_RETENTION_DAYS` is intentional. It means no automated duration
has been authorized. Withdrawal, cancellation, and a later approved retention review can move
records into quarantine; this package has no hard-delete path. The upload schema is only a future
metadata contract and does not activate an upload endpoint or object storage.

## Gate-06 — AUTH_FLOW_CHANGE and governance authority

```yaml
gate_id: GATE-06 AUTH_FLOW_CHANGE
objective: >-
  Bind the contribution and manufacturer-handoff UI/API to human-approved, versioned governance
  authority without embedding invented legal text or silently accepting stale versions.
current_state: >-
  Strict schemas, exact-version comparison, explicit UI confirmations, PII classification,
  untrusted-content labeling, and default-off flags are implemented locally. No authority
  references, retention duration, receipt key, role census, or wording approval has been supplied.
exact_actions:
  - legal/privacy owner approves exact version references and user-facing wording
  - security owner approves receipt-key lifecycle without disclosing key material in evidence
  - product/data owners approve bounded quota values and quarantine/review responsibilities
  - identity owner confirms tenant, contributor, platform-owner, and manufacturer role mappings
exact_commands_sanitized:
  - "record approved non-secret references in the release configuration manifest"
  - "store the receipt key only through the approved runtime-secret mechanism"
affected_services: [dashboard-v2, sealai-v2-api, keycloak-role-mapping, runtime-secret-provider]
expected_downtime: "none for approval; deployment remains a separate Gate-08 action"
data_risk: high
security_risk: high
preconditions:
  - accountable approvers and change ticket are named
  - exact wording and version identifiers are immutable release inputs
  - no personal data or secret value is copied into approval/evidence files
backup_status: "not applicable to approval; Gate-07/08 still require restore evidence"
verification:
  - stale or cross-tenant governance versions fail closed
  - UI text states capture/quarantine accurately and never claims automatic use or delivery
  - empty retention authority schedules no automatic deletion or expiry
  - every accepted contribution is untrusted and quarantined
rollback:
  - keep SEALAI_V2_API_LIFECYCLE_ENABLED=false
  - preserve hard limits and quarantine semantics
  - supersede references only through a new reviewed version; never rewrite historical receipts
stop_conditions:
  - any required human authority is missing or ambiguous
  - wording or versions differ between the approved record, UI, API, and release manifest
  - receipt-key custody or historical verification is undefined
  - role assignment or platform-owner privacy purpose is unproven
```

Gate-06 remains **BLOCKED_EXTERNAL**. Repository defaults leave the feature disabled and the
authority references, receipt secret, and retention duration empty.

## Gate-07 — DATABASE_MIGRATION, profiling, constraints, and RLS

```yaml
gate_id: GATE-07 DATABASE_MIGRATION
objective: >-
  Install the additive API lifecycle schema, prove legacy-row handling, validate shadow
  constraints, and enforce actor/tenant isolation with non-bypassing PostgreSQL roles and FORCE RLS.
current_state: >-
  Alembic 0014/0015, transaction-scoped actor/tenant refs, RLS policy template, atomic shared
  admission, immutable transition receipts, and opt-in PostgreSQL race tests are implemented
  locally. No real PostgreSQL test DSN, production profile, restore proof, validation, role grant,
  policy activation, backfill, or production mutation was available.
exact_actions:
  - run 0014/0015 on an empty ephemeral database and an isolated restore copy
  - profile legacy contribution/lead nullability and lifecycle states using aggregate counts only
  - prepare a human-reviewed disposition; ambiguous rows remain legacy-unresolved/quarantined
  - validate all fifteen Gate-07 shadow constraints separately after zero-violation evidence
  - provision separate non-owner, non-BYPASSRLS roles and verify transaction-local GUC reset
  - apply and verify the reviewed RLS/FORCE transaction for thirteen protected tables
  - run actor/tenant quota races, IDOR, pool-reuse, pagination, receipt, and quarantine tests
exact_commands_sanitized:
  - "SEALAI_TEST_POSTGRES_DSN='<EMPTY_EPHEMERAL_TEST_DSN>' SEALAI_TEST_POSTGRES_CONFIRM=EPHEMERAL_ONLY pytest -q backend/sealai_v2/tests/test_postgres_runtime_scope_integration.py"
  - "SEALAI_V2_DATABASE_URL='<RESTORE_COPY_DSN>' python -m sealai_v2.db.migrate upgrade"
  - "psql '<RESTORE_COPY_DSN>' -v ON_ERROR_STOP=1 -c 'ALTER TABLE <REVIEWED_TABLE> VALIDATE CONSTRAINT <REVIEWED_CONSTRAINT>'"
  - "psql '<RESTORE_COPY_DSN>' -v gate07_approved=true -v runtime_scope_adapter_verified=true -v target_database='<EXPECTED_TEST_DB>' -f ops/postgres/gate07-rls-cutover.sql"
affected_services: [sealai-v2-api, postgres, dashboard-v2, keycloak-role-mapping]
expected_downtime: "production duration must be derived from restore-copy lock measurements"
data_risk: high
security_risk: high
preconditions:
  - Gate-06 approval is complete and exact
  - immutable production backup has passed an isolated restore
  - production fingerprint and migration head are re-confirmed read-only
  - aggregate profile has zero unexplained violations for each next step
  - API login role is neither table owner nor BYPASSRLS
  - explicit ephemeral PostgreSQL tests pass; SQLite and mocks do not count
backup_status: "NOT PROVEN; no production migration is authorized"
verification:
  - alembic_version equals 20260715_0015
  - six API lifecycle constraints and nine prior Gate-07 constraints are validated
  - RLS and FORCE RLS are true for all thirteen protected tables
  - runtime roles have no DELETE privilege on leads/contributions/lifecycle tables and receipts/events permit only SELECT/INSERT to the API role
  - app.tenant_ref and app.actor_ref are derived only from verified request identity and reset on reuse
  - exactly one contender wins each actor/tenant concurrency boundary
  - stale lease completion cannot finalize a recovered admission
  - cross-tenant/cross-actor reads, withdrawals, cancellations, receipts, and events are denied
  - legacy unresolved rows never enter partner or ordinary-user visibility
rollback:
  - before commit, rollback the transaction and leave the deployed artifact unchanged
  - after additive migration, roll the app back while retaining nullable columns/tables and quarantine
  - disable RLS/FORCE only through the separately approved Gate-07 rollback transaction
  - never delete, auto-assign, backfill heuristically, or remove quarantine during rollback
stop_conditions:
  - restore evidence, exact approval, or explicit test-DSN guard is absent
  - any raw personal data or secret appears in evidence output
  - any constraint violation, unexpected row count, lock timeout, or role/GUC leak appears
  - runtime role owns a table, has BYPASSRLS, or can escape actor/tenant scope
  - migration, policy, or production fingerprint differs from the reviewed artifact
```

Gate-07 remains **BLOCKED_EXTERNAL**. Migration `20260715_0014` is additive and nullable;
`20260715_0015` adds PostgreSQL `NOT VALID` checks only. Neither migration validates legacy data,
enables RLS, changes roles, backfills, quarantines, or deletes rows.

## Gate-08 — PRODUCTION_DEPLOYMENT and activation

```yaml
gate_id: GATE-08 PRODUCTION_DEPLOYMENT
objective: >-
  Promote one attested backend/dashboard/Nginx/Compose artifact, keep lifecycle writes off during
  schema verification, then activate the approved contract with reversible monitoring.
current_state: >-
  Backend, frontend, Nginx and Compose changes pass local tests and builds. No image was built,
  pushed, pulled, deployed, or exercised against production; production is unchanged.
exact_actions:
  - bind exact source tree, OCI digests, dashboard artifact, migrations, Nginx, Compose, and rollback
  - deploy schema-compatible code with SEALAI_V2_API_LIFECYCLE_ENABLED=false
  - complete Gate-07 checks and coordinated backend/frontend smoke tests
  - inject approved references and receipt secret through the runtime secret/config authority
  - activate only in the approved window, then observe denials, latency, quarantine, and receipts
exact_commands_sanitized:
  - "deploy '<ATTESTED_RELEASE_DIGEST>' using the approved release procedure"
  - "render and compare the exact production Compose runtime profile before activation"
  - "run authenticated same-tenant and negative cross-tenant smoke tests without recording payloads"
affected_services: [nginx, dashboard-v2, sealai-v2-api, postgres, runtime-secret-provider]
expected_downtime: "must be declared from the Gate-07 rehearsal and deployment plan"
data_risk: high
security_risk: high
preconditions:
  - Gates 06 and 07 are separately approved and fully evidenced
  - release freeze permits this exact deployment scope
  - prior artifact and configuration are immediately re-promotable
  - backup/restore and rollback rehearsals passed for the exact release
  - alert ownership and observation window are staffed
backup_status: "NOT PROVEN; Gate-08 is not authorized"
verification:
  - edge and app reject body, total envelope, header, query, path, case-byte, and case-fact overages
  - disabled mode returns fail-closed without creating data
  - exact governance versions are returned and stale versions rejected
  - contribution starts untrusted/quarantined and is absent from automatic answer authority
  - PII-unknown/present or injection-signaled lead remains unavailable to manufacturers
  - pagination remains bounded and tenant/owner scoped
  - withdrawal/cancellation returns a stable receipt and leaves the record quarantined, not deleted
  - shared actor/tenant limits remain atomic across at least two API workers
  - logs, metrics, and evidence contain neither payloads, personal data, idempotency keys, nor secrets
rollback:
  - set the feature back to disabled through the approved configuration rollback
  - re-promote the previous attested backend/dashboard/Nginx artifact together
  - retain additive schema, receipts, audit events, limits, and all quarantine markers
  - never hard-delete records or invalidate a historical receipt as a rollback shortcut
stop_conditions:
  - exact artifact/configuration mismatch or parallel deployment
  - authentication, tenant isolation, receipt, quota, migration, or negative smoke failure
  - unexpected row-count change, data visibility, log disclosure, or error-rate increase
  - missing rollback operator, observation owner, or immutable restore evidence
```

Gate-08 remains **BLOCKED_EXTERNAL**. The only valid local status is
`IMPLEMENTED_NOT_DEPLOYED`; production must never be described as verified from this package.

## Local evidence boundary

The local suite covers strict schemas, request/case bounds, keyset cursors, actor/tenant quotas,
concurrency races, non-refundable storage admission, idempotent replay and payload conflict,
recovered-lease fencing, PII/injection quarantine, owner/tenant IDOR denial, stable withdrawal and
cancellation receipts, retention quarantine without deletion, additive migrations, and default-off
activation. The real PostgreSQL RLS/race test is intentionally opt-in and remains an evidence gap
until an explicitly empty non-production DSN is provided.
