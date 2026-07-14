\set ON_ERROR_STOP on

-- GATE-07 read-only profiler. Preconditions: migrations through 20260715_0012 are installed.
-- Every result is aggregate metadata; no tenant, subject, case, message, fact, or lead value is
-- selected. Run output must still be stored as restricted operational evidence.
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '60s';
SET LOCAL lock_timeout = '2s';

SELECT source_table, total_rows, missing_owner, null_ownership_state, quarantined_rows
FROM (
    SELECT 'v2_sessions'::text AS source_table,
           count(*)::bigint AS total_rows,
           count(*) FILTER (WHERE owner_subject IS NULL OR btrim(owner_subject) = '')::bigint AS missing_owner,
           count(*) FILTER (WHERE ownership_state IS NULL)::bigint AS null_ownership_state,
           count(*) FILTER (WHERE ownership_state = 'quarantined')::bigint AS quarantined_rows
      FROM v2_sessions
    UNION ALL
    SELECT 'v2_durable_facts', count(*),
           count(*) FILTER (WHERE owner_subject IS NULL OR btrim(owner_subject) = ''),
           count(*) FILTER (WHERE ownership_state IS NULL),
           count(*) FILTER (WHERE ownership_state = 'quarantined')
      FROM v2_durable_facts
    UNION ALL
    SELECT 'v2_memory_items', count(*),
           count(*) FILTER (WHERE owner_subject IS NULL OR btrim(owner_subject) = ''),
           count(*) FILTER (WHERE ownership_state IS NULL),
           count(*) FILTER (WHERE ownership_state = 'quarantined')
      FROM v2_memory_items
    UNION ALL
    SELECT 'v2_leads', count(*),
           count(*) FILTER (WHERE owner_subject IS NULL OR btrim(owner_subject) = ''),
           count(*) FILTER (WHERE ownership_state IS NULL),
           count(*) FILTER (WHERE ownership_state = 'quarantined')
      FROM v2_leads
) AS ownership_profile
ORDER BY source_table;

SELECT 'v2_leads'::text AS source_table,
       count(*) FILTER (
           WHERE (owner_subject IS NULL) <> (case_id IS NULL)
              OR (case_id IS NULL) <> (case_revision IS NULL)
       )::bigint AS partial_case_boundaries,
       count(*) FILTER (WHERE case_revision < 0)::bigint AS negative_revisions,
       count(*) FILTER (
           WHERE case_id IS NOT NULL AND NOT EXISTS (
               SELECT 1 FROM v2_sessions s
                WHERE s.tenant_id = v2_leads.tenant_id
                  AND s.session_id = v2_leads.case_id
           )
       )::bigint AS orphan_case_references
  FROM v2_leads;

SELECT child_table, orphan_rows
FROM (
    SELECT 'v2_messages'::text AS child_table, count(*)::bigint AS orphan_rows
      FROM v2_messages c
     WHERE NOT EXISTS (
         SELECT 1 FROM v2_sessions p
          WHERE p.tenant_id = c.tenant_id AND p.session_id = c.session_id
     )
    UNION ALL
    SELECT 'v2_facts', count(*) FROM v2_facts c
     WHERE NOT EXISTS (
         SELECT 1 FROM v2_sessions p
          WHERE p.tenant_id = c.tenant_id AND p.session_id = c.session_id
     )
    UNION ALL
    SELECT 'v2_derived', count(*) FROM v2_derived c
     WHERE NOT EXISTS (
         SELECT 1 FROM v2_sessions p
          WHERE p.tenant_id = c.tenant_id AND p.session_id = c.session_id
     )
    UNION ALL
    SELECT 'v2_interview_state', count(*) FROM v2_interview_state c
     WHERE NOT EXISTS (
         SELECT 1 FROM v2_sessions p
          WHERE p.tenant_id = c.tenant_id AND p.session_id = c.session_id
     )
) AS orphan_profile
ORDER BY child_table;

SELECT count(*)::bigint AS quarantine_records,
       count(*) FILTER (WHERE resolution_status = 'unresolved')::bigint AS unresolved_records,
       count(DISTINCT source_table)::bigint AS affected_source_tables
  FROM v2_ownership_quarantine;

SELECT count(*)::bigint AS expected_shadow_constraints,
       count(*) FILTER (WHERE convalidated)::bigint AS already_validated,
       count(*) FILTER (WHERE NOT convalidated)::bigint AS still_not_valid
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
 );

SELECT count(*)::bigint AS scoped_tables,
       count(*) FILTER (WHERE c.relrowsecurity)::bigint AS rls_enabled,
       count(*) FILTER (WHERE c.relforcerowsecurity)::bigint AS force_rls_enabled
  FROM pg_class c
  JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname = current_schema()
   AND c.relname IN (
       'v2_sessions', 'v2_messages', 'v2_facts', 'v2_derived',
       'v2_interview_state', 'v2_durable_facts', 'v2_memory_items', 'v2_leads'
   );

SELECT count(*)::bigint AS expected_roles_present,
       count(*) FILTER (WHERE NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole)::bigint AS least_privilege_core,
       count(*) FILTER (WHERE NOT rolbypassrls)::bigint AS non_bypass_roles
  FROM pg_roles
 WHERE rolname IN (
     'sealai_migration_owner', 'sealai_api', 'sealai_worker',
     'sealai_tenant_admin', 'sealai_platform_owner', 'sealai_system_operator'
 );

SELECT count(*)::bigint AS pgcrypto_available
  FROM pg_available_extensions
 WHERE name = 'pgcrypto';

ROLLBACK;
