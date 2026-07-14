\set ON_ERROR_STOP on

-- MUTATING GATE-07 TEMPLATE. This is intentionally unreachable without both an approval token and
-- evidence that the transaction-scoped runtime role/GUC adapter has passed the ephemeral PG tests.
\if :{?gate07_approved}
\else
  \echo 'gate07_approved is required; refusing RLS cutover'
  \quit 3
\endif
\if :gate07_approved
\else
  \echo 'gate07_approved must be true; refusing RLS cutover'
  \quit 3
\endif
\if :{?runtime_scope_adapter_verified}
\else
  \echo 'runtime_scope_adapter_verified is required; refusing RLS cutover'
  \quit 3
\endif
\if :runtime_scope_adapter_verified
\else
  \echo 'runtime scope adapter is not verified; refusing RLS cutover'
  \quit 3
\endif
\if :{?target_database}
\else
  \echo 'target_database is required; refusing RLS cutover'
  \quit 3
\endif

SELECT current_database() = :'target_database' AS target_database_matches \gset
\if :target_database_matches
\else
  \echo 'connected database does not match target_database; refusing RLS cutover'
  \quit 3
\endif

SELECT count(*) = 9 AND bool_and(convalidated) AS shadow_constraints_ready
  FROM pg_constraint
 WHERE conname IN (
     'ck_v2_sessions_boundary_shadow',
     'ck_v2_durable_facts_owner_shadow',
     'ck_v2_memory_items_owner_shadow',
     'ck_v2_leads_case_owner_shadow',
     'fk_v2_messages_session_shadow',
     'fk_v2_facts_session_shadow',
     'fk_v2_derived_session_shadow',
     'fk_v2_interview_state_session_shadow',
     'fk_v2_leads_case_shadow'
 ) \gset
\if :shadow_constraints_ready
\else
  \echo 'all nine shadow constraints must be validated in an earlier approved stage'
  \quit 3
\endif

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '60s';

DO $roles$
DECLARE role_name text;
BEGIN
  FOREACH role_name IN ARRAY ARRAY[
    'sealai_migration_owner', 'sealai_api', 'sealai_worker',
    'sealai_tenant_admin', 'sealai_platform_owner', 'sealai_system_operator'
  ] LOOP
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
      EXECUTE format(
        'CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
        role_name
      );
    END IF;
    EXECUTE format(
      'ALTER ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS',
      role_name
    );
  END LOOP;
END
$roles$;

ALTER TABLE v2_sessions OWNER TO sealai_migration_owner;
ALTER TABLE v2_messages OWNER TO sealai_migration_owner;
ALTER TABLE v2_facts OWNER TO sealai_migration_owner;
ALTER TABLE v2_derived OWNER TO sealai_migration_owner;
ALTER TABLE v2_interview_state OWNER TO sealai_migration_owner;
ALTER TABLE v2_durable_facts OWNER TO sealai_migration_owner;
ALTER TABLE v2_memory_items OWNER TO sealai_migration_owner;
ALTER TABLE v2_leads OWNER TO sealai_migration_owner;

GRANT SELECT, INSERT, UPDATE, DELETE ON
  v2_sessions, v2_messages, v2_facts, v2_derived, v2_interview_state,
  v2_durable_facts, v2_memory_items, v2_leads
TO sealai_api;
GRANT SELECT, INSERT, UPDATE, DELETE ON
  v2_sessions, v2_messages, v2_facts, v2_derived, v2_interview_state,
  v2_durable_facts, v2_memory_items, v2_leads
TO sealai_tenant_admin;
GRANT SELECT ON v2_leads TO sealai_platform_owner;

ALTER TABLE v2_sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_derived ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_interview_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_durable_facts ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_memory_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE v2_leads ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS api_owner ON v2_sessions;
CREATE POLICY api_owner ON v2_sessions TO sealai_api
  USING (
    tenant_id = current_setting('app.tenant_id', true)
    AND owner_subject = current_setting('app.subject_id', true)
    AND ownership_state = 'owned'
  )
  WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
    AND owner_subject = current_setting('app.subject_id', true)
    AND ownership_state = 'owned'
  );

DROP POLICY IF EXISTS tenant_admin_scope ON v2_sessions;
CREATE POLICY tenant_admin_scope ON v2_sessions TO sealai_tenant_admin
  USING (tenant_id = current_setting('app.tenant_id', true))
  WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DO $children$
DECLARE item record;
BEGIN
  FOR item IN
    SELECT * FROM (VALUES
      ('v2_messages'), ('v2_facts'), ('v2_derived'), ('v2_interview_state')
    ) AS child(table_name)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS api_owner ON %I', item.table_name);
    EXECUTE format(
      'CREATE POLICY api_owner ON %I TO sealai_api USING ('
      'EXISTS (SELECT 1 FROM v2_sessions s WHERE s.tenant_id = %I.tenant_id '
      'AND s.session_id = %I.session_id AND s.tenant_id = current_setting(''app.tenant_id'', true) '
      'AND s.owner_subject = current_setting(''app.subject_id'', true) '
      'AND s.ownership_state = ''owned'')) WITH CHECK ('
      'EXISTS (SELECT 1 FROM v2_sessions s WHERE s.tenant_id = %I.tenant_id '
      'AND s.session_id = %I.session_id AND s.tenant_id = current_setting(''app.tenant_id'', true) '
      'AND s.owner_subject = current_setting(''app.subject_id'', true) '
      'AND s.ownership_state = ''owned''))',
      item.table_name, item.table_name, item.table_name, item.table_name, item.table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS tenant_admin_scope ON %I', item.table_name);
    EXECUTE format(
      'CREATE POLICY tenant_admin_scope ON %I TO sealai_tenant_admin '
      'USING (tenant_id = current_setting(''app.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
      item.table_name
    );
  END LOOP;
END
$children$;

DO $direct_owner_tables$
DECLARE item record;
BEGIN
  FOR item IN
    SELECT * FROM (VALUES
      ('v2_durable_facts'), ('v2_memory_items')
    ) AS direct_table(table_name)
  LOOP
    EXECUTE format('DROP POLICY IF EXISTS api_owner ON %I', item.table_name);
    EXECUTE format(
      'CREATE POLICY api_owner ON %I TO sealai_api '
      'USING (tenant_id = current_setting(''app.tenant_id'', true) '
      'AND owner_subject = current_setting(''app.subject_id'', true) '
      'AND ownership_state = ''owned'') '
      'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true) '
      'AND owner_subject = current_setting(''app.subject_id'', true) '
      'AND ownership_state = ''owned'')', item.table_name
    );
    EXECUTE format('DROP POLICY IF EXISTS tenant_admin_scope ON %I', item.table_name);
    EXECUTE format(
      'CREATE POLICY tenant_admin_scope ON %I TO sealai_tenant_admin '
      'USING (tenant_id = current_setting(''app.tenant_id'', true)) '
      'WITH CHECK (tenant_id = current_setting(''app.tenant_id'', true))',
      item.table_name
    );
  END LOOP;
END
$direct_owner_tables$;

DROP POLICY IF EXISTS api_owner ON v2_leads;
CREATE POLICY api_owner ON v2_leads TO sealai_api
  USING (
    tenant_id = current_setting('app.tenant_id', true)
    AND owner_subject = current_setting('app.subject_id', true)
    AND ownership_state = 'owned'
  )
  WITH CHECK (
    tenant_id = current_setting('app.tenant_id', true)
    AND owner_subject = current_setting('app.subject_id', true)
    AND ownership_state = 'owned'
  );
DROP POLICY IF EXISTS tenant_admin_scope ON v2_leads;
CREATE POLICY tenant_admin_scope ON v2_leads TO sealai_tenant_admin
  USING (tenant_id = current_setting('app.tenant_id', true));
DROP POLICY IF EXISTS platform_owner_read ON v2_leads;
CREATE POLICY platform_owner_read ON v2_leads FOR SELECT TO sealai_platform_owner
  USING (true);

ALTER TABLE v2_sessions FORCE ROW LEVEL SECURITY;
ALTER TABLE v2_messages FORCE ROW LEVEL SECURITY;
ALTER TABLE v2_facts FORCE ROW LEVEL SECURITY;
ALTER TABLE v2_derived FORCE ROW LEVEL SECURITY;
ALTER TABLE v2_interview_state FORCE ROW LEVEL SECURITY;
ALTER TABLE v2_durable_facts FORCE ROW LEVEL SECURITY;
ALTER TABLE v2_memory_items FORCE ROW LEVEL SECURITY;
ALTER TABLE v2_leads FORCE ROW LEVEL SECURITY;

SELECT count(*) = 8 AND bool_and(c.relrowsecurity AND c.relforcerowsecurity)
       AS rls_contract_installed
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = current_schema()
   AND c.relname IN (
     'v2_sessions', 'v2_messages', 'v2_facts', 'v2_derived',
     'v2_interview_state', 'v2_durable_facts', 'v2_memory_items', 'v2_leads'
   ) \gset
\if :rls_contract_installed
\else
  \echo 'RLS verification failed; rolling back'
  ROLLBACK;
  \quit 4
\endif

COMMIT;
