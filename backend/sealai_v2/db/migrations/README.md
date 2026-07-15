# V2 database migrations

`20260710_0001` is the only metadata-driven revision. It adopts the former
`create_all` schema after validating all modeled tables and columns, or creates
that schema on a fresh database.

Every later revision must use explicit Alembic operations. Production runs only
`python -m sealai_v2.db.migrate upgrade`; destructive downgrades require an
explicit development-only flag and production rollback relies on a verified
database backup plus a forward repair migration.

`20260715_0014`/`0015` add the reviewer-governance foundation and PostgreSQL
shadow checks/foreign keys plus append-only triggers. They intentionally import
no affiliation, infer no relationship, quarantine no legacy row, validate no
constraint, and activate no feature. The staged GATE-06/07/08 procedure is
documented in `docs/ops/gate06-07-reviewer-governance-cutover.md`.
