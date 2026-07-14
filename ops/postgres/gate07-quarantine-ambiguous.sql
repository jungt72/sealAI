\set ON_ERROR_STOP on

-- MUTATING GATE-07 SCRIPT. It never assigns an owner and never deletes source data. It marks only
-- ambiguous legacy rows as quarantined and records keyed fingerprints. Do not run without the
-- separately recorded DATABASE_MIGRATION approval, immutable backup, and reviewed profile.
\if :{?gate07_approved}
\else
  \echo 'gate07_approved is required; refusing to run'
  \quit 3
\endif
\if :gate07_approved
\else
  \echo 'gate07_approved must be true; refusing to run'
  \quit 3
\endif
\if :{?target_database}
\else
  \echo 'target_database is required; refusing to run'
  \quit 3
\endif

SELECT current_database() = :'target_database' AS target_database_matches \gset
\if :target_database_matches
\else
  \echo 'connected database does not match target_database; refusing to run'
  \quit 3
\endif

SELECT EXISTS (
    SELECT 1 FROM pg_extension WHERE extname = 'pgcrypto'
) AS pgcrypto_installed \gset
\if :pgcrypto_installed
\else
  \echo 'pgcrypto is not installed; extension installation needs separate review'
  \quit 3
\endif

\prompt -s 'GATE-07 quarantine HMAC pepper (minimum 32 chars): ' quarantine_pepper
SELECT length(:'quarantine_pepper') >= 32 AS pepper_is_bounded \gset
\if :pepper_is_bounded
\else
  \echo 'quarantine pepper is too short; refusing to run'
  \quit 3
\endif

BEGIN;
SET LOCAL lock_timeout = '2s';
SET LOCAL statement_timeout = '60s';

WITH candidates AS (
    SELECT tenant_id, session_id
      FROM v2_sessions
     WHERE owner_subject IS NULL OR btrim(owner_subject) = ''
), inserted AS (
    INSERT INTO v2_ownership_quarantine (
        source_table, tenant_fingerprint, record_fingerprint, reason_code,
        detected_at, resolution_status, resolution_note
    )
    SELECT 'v2_sessions',
           encode(hmac(tenant_id, :'quarantine_pepper', 'sha256'), 'hex'),
           encode(hmac(tenant_id || E'\x1f' || session_id, :'quarantine_pepper', 'sha256'), 'hex'),
           'missing_owner',
           to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
           'unresolved', ''
      FROM candidates
    ON CONFLICT (source_table, record_fingerprint, reason_code) DO NOTHING
    RETURNING 1
), marked AS (
    UPDATE v2_sessions s
       SET ownership_state = 'quarantined'
      FROM candidates c
     WHERE s.tenant_id = c.tenant_id AND s.session_id = c.session_id
       AND s.ownership_state IS DISTINCT FROM 'quarantined'
    RETURNING 1
)
SELECT (SELECT count(*) FROM candidates)::bigint AS ambiguous_rows,
       (SELECT count(*) FROM inserted)::bigint AS quarantine_records_added,
       (SELECT count(*) FROM marked)::bigint AS rows_marked_quarantined;

WITH candidates AS (
    SELECT tenant_id, feld
      FROM v2_durable_facts
     WHERE owner_subject IS NULL OR btrim(owner_subject) = ''
), inserted AS (
    INSERT INTO v2_ownership_quarantine (
        source_table, tenant_fingerprint, record_fingerprint, reason_code,
        detected_at, resolution_status, resolution_note
    )
    SELECT 'v2_durable_facts',
           encode(hmac(tenant_id, :'quarantine_pepper', 'sha256'), 'hex'),
           encode(hmac(tenant_id || E'\x1f' || feld, :'quarantine_pepper', 'sha256'), 'hex'),
           'missing_owner',
           to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
           'unresolved', ''
      FROM candidates
    ON CONFLICT (source_table, record_fingerprint, reason_code) DO NOTHING
    RETURNING 1
), marked AS (
    UPDATE v2_durable_facts f
       SET ownership_state = 'quarantined'
      FROM candidates c
     WHERE f.tenant_id = c.tenant_id AND f.feld = c.feld
       AND f.ownership_state IS DISTINCT FROM 'quarantined'
    RETURNING 1
)
SELECT (SELECT count(*) FROM candidates)::bigint AS ambiguous_rows,
       (SELECT count(*) FROM inserted)::bigint AS quarantine_records_added,
       (SELECT count(*) FROM marked)::bigint AS rows_marked_quarantined;

WITH candidates AS (
    SELECT id, tenant_id
      FROM v2_memory_items
     WHERE owner_subject IS NULL OR btrim(owner_subject) = ''
), inserted AS (
    INSERT INTO v2_ownership_quarantine (
        source_table, tenant_fingerprint, record_fingerprint, reason_code,
        detected_at, resolution_status, resolution_note
    )
    SELECT 'v2_memory_items',
           encode(hmac(tenant_id, :'quarantine_pepper', 'sha256'), 'hex'),
           encode(hmac(tenant_id || E'\x1f' || id, :'quarantine_pepper', 'sha256'), 'hex'),
           'missing_owner',
           to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
           'unresolved', ''
      FROM candidates
    ON CONFLICT (source_table, record_fingerprint, reason_code) DO NOTHING
    RETURNING 1
), marked AS (
    UPDATE v2_memory_items m
       SET ownership_state = 'quarantined'
      FROM candidates c
     WHERE m.id = c.id AND m.ownership_state IS DISTINCT FROM 'quarantined'
    RETURNING 1
)
SELECT (SELECT count(*) FROM candidates)::bigint AS ambiguous_rows,
       (SELECT count(*) FROM inserted)::bigint AS quarantine_records_added,
       (SELECT count(*) FROM marked)::bigint AS rows_marked_quarantined;

WITH candidates AS (
    SELECT id, tenant_id
      FROM v2_leads
     WHERE owner_subject IS NULL OR btrim(owner_subject) = ''
        OR case_id IS NULL OR btrim(case_id) = '' OR case_revision IS NULL
), inserted AS (
    INSERT INTO v2_ownership_quarantine (
        source_table, tenant_fingerprint, record_fingerprint, reason_code,
        detected_at, resolution_status, resolution_note
    )
    SELECT 'v2_leads',
           encode(hmac(tenant_id, :'quarantine_pepper', 'sha256'), 'hex'),
           encode(hmac(tenant_id || E'\x1f' || id::text, :'quarantine_pepper', 'sha256'), 'hex'),
           'incomplete_case_boundary',
           to_char(clock_timestamp() AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
           'unresolved', ''
      FROM candidates
    ON CONFLICT (source_table, record_fingerprint, reason_code) DO NOTHING
    RETURNING 1
), marked AS (
    UPDATE v2_leads l
       SET ownership_state = 'quarantined'
      FROM candidates c
     WHERE l.id = c.id AND l.ownership_state IS DISTINCT FROM 'quarantined'
    RETURNING 1
)
SELECT (SELECT count(*) FROM candidates)::bigint AS ambiguous_rows,
       (SELECT count(*) FROM inserted)::bigint AS quarantine_records_added,
       (SELECT count(*) FROM marked)::bigint AS rows_marked_quarantined;

COMMIT;
