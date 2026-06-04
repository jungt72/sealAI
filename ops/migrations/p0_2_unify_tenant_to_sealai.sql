-- ops/migrations/p0_2_unify_tenant_to_sealai.sql
--
-- P0-2 data migration — unify legacy, fallback-collapsed tenants to the single
-- real tenant 'sealai' so the strict request-tenant resolver (no "default" /
-- user_id fallback; see app.services.auth.dependencies.require_tenant_id) does
-- NOT orphan existing rows once the fallback removal is deployed.
--
-- Properties:
--   * IDEMPOTENT      — re-running is a no-op (no 'default'/realm-user tenants left).
--   * DRY-RUN DEFAULT — rolls back unless invoked with  -v apply=1  (then COMMITs).
--   * CONSERVATIVE    — only real data moves; per-table totals are conserved.
--
-- Run (against the prod postgres container):
--   DRY-RUN :  docker exec -i postgres psql -U sealai -d sealai -f /tmp/p0_2.sql
--   APPLY   :  docker exec -i postgres psql -U sealai -d sealai -v apply=1 -f /tmp/p0_2.sql
--
-- SCOPE — tables migrated: cases, mutation_events, outbox.
--   Source tenants moved to 'sealai':  'default'  OR  a real sealAI realm user_id
--   (the six uuids below — the only legitimately-migratable user_id tenants).
--
-- HARD EXCLUSIONS (never touched — by omission and/or WHERE clause):
--   * rag_documents            — shared-tenant 'sealai' RAG/Paperless pipeline (by design).
--   * tenant_id = 'sealai'      — already the shared/target tenant.
--   * audit_log                 — append-only audit trail (immutability: not rewritten).
--   * test/dev labels           — codex-*, calc-*, u1, dev-tenant, … (not real data; left orphaned).
--   * empty tables              — deterministic_din_norms, deterministic_material_limits,
--                                 inquiry_extracts, rca_early_access.

\set ON_ERROR_STOP on
\if :{?apply}
\else
  \set apply 0
\endif

BEGIN;

-- The only legitimately-migratable user_id tenants: real sealAI realm users.
CREATE TEMP TABLE _p0_2_realm_users(uid text) ON COMMIT DROP;
INSERT INTO _p0_2_realm_users(uid) VALUES
 ('1617f8ff-b5ac-43dd-a33c-6227d1b69a15'),  -- codex-live
 ('1b79c20d-771b-48cf-825e-90168d5b46df'),  -- codexscrollmay15
 ('16e67159-fd2e-425e-9c35-249cd4c78c37'),  -- fraoel
 ('7748ba15-bef4-43b4-b95a-cf80fcc476d8'),  -- jungt  (the only one with collapsed rows)
 ('305fd896-288e-4574-a394-d0ff426bb44b'),  -- wazwfqwgqavdntfcg
 ('2f816137-fb94-4af0-9243-8f1d490daaf4');  -- xbttckojhxxfwlguxiitdj

\echo '================== BEFORE =================='
SELECT tbl, sealai, def, realm_user, test_other, total FROM (
  SELECT 'cases' tbl,
    count(*) FILTER (WHERE tenant_id='sealai') sealai,
    count(*) FILTER (WHERE tenant_id='default') def,
    count(*) FILTER (WHERE tenant_id IN (SELECT uid FROM _p0_2_realm_users)) realm_user,
    count(*) FILTER (WHERE tenant_id NOT IN ('sealai','default')
                       AND tenant_id NOT IN (SELECT uid FROM _p0_2_realm_users)) test_other,
    count(*) total, 1 ord FROM cases
  UNION ALL SELECT 'mutation_events',
    count(*) FILTER (WHERE tenant_id='sealai'),count(*) FILTER (WHERE tenant_id='default'),
    count(*) FILTER (WHERE tenant_id IN (SELECT uid FROM _p0_2_realm_users)),
    count(*) FILTER (WHERE tenant_id NOT IN ('sealai','default') AND tenant_id NOT IN (SELECT uid FROM _p0_2_realm_users)),
    count(*),2 FROM mutation_events
  UNION ALL SELECT 'outbox',
    count(*) FILTER (WHERE tenant_id='sealai'),count(*) FILTER (WHERE tenant_id='default'),
    count(*) FILTER (WHERE tenant_id IN (SELECT uid FROM _p0_2_realm_users)),
    count(*) FILTER (WHERE tenant_id NOT IN ('sealai','default') AND tenant_id NOT IN (SELECT uid FROM _p0_2_realm_users)),
    count(*),3 FROM outbox
) q ORDER BY ord;

-- Migrate: default + real realm users -> 'sealai'.  Idempotent.
UPDATE cases           SET tenant_id='sealai'
  WHERE tenant_id='default' OR tenant_id IN (SELECT uid FROM _p0_2_realm_users);
UPDATE mutation_events SET tenant_id='sealai'
  WHERE tenant_id='default' OR tenant_id IN (SELECT uid FROM _p0_2_realm_users);
UPDATE outbox          SET tenant_id='sealai'
  WHERE tenant_id='default' OR tenant_id IN (SELECT uid FROM _p0_2_realm_users);

\echo '================== AFTER =================='
SELECT tbl, sealai, def, realm_user, test_other, total FROM (
  SELECT 'cases' tbl,
    count(*) FILTER (WHERE tenant_id='sealai') sealai,
    count(*) FILTER (WHERE tenant_id='default') def,
    count(*) FILTER (WHERE tenant_id IN (SELECT uid FROM _p0_2_realm_users)) realm_user,
    count(*) FILTER (WHERE tenant_id NOT IN ('sealai','default')
                       AND tenant_id NOT IN (SELECT uid FROM _p0_2_realm_users)) test_other,
    count(*) total, 1 ord FROM cases
  UNION ALL SELECT 'mutation_events',
    count(*) FILTER (WHERE tenant_id='sealai'),count(*) FILTER (WHERE tenant_id='default'),
    count(*) FILTER (WHERE tenant_id IN (SELECT uid FROM _p0_2_realm_users)),
    count(*) FILTER (WHERE tenant_id NOT IN ('sealai','default') AND tenant_id NOT IN (SELECT uid FROM _p0_2_realm_users)),
    count(*),2 FROM mutation_events
  UNION ALL SELECT 'outbox',
    count(*) FILTER (WHERE tenant_id='sealai'),count(*) FILTER (WHERE tenant_id='default'),
    count(*) FILTER (WHERE tenant_id IN (SELECT uid FROM _p0_2_realm_users)),
    count(*) FILTER (WHERE tenant_id NOT IN ('sealai','default') AND tenant_id NOT IN (SELECT uid FROM _p0_2_realm_users)),
    count(*),3 FROM outbox
) q ORDER BY ord;

\if :apply
  COMMIT;
  \echo '>>> APPLIED (committed).'
\else
  ROLLBACK;
  \echo '>>> DRY-RUN (rolled back). Re-run with  -v apply=1  to commit.'
\endif
