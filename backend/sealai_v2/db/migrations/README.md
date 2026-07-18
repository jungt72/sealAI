# V2 database migrations

`20260710_0001` is the only metadata-driven revision. It adopts the former
`create_all` schema after validating all modeled tables and columns, or creates
that schema on a fresh database.

Every later revision must use explicit Alembic operations. Production runs only
`python -m sealai_v2.db.migrate upgrade`; destructive downgrades require an
explicit development-only flag and production rollback relies on a verified
database backup plus a forward repair migration.

`20260717_0011` is the inert MAT-GOV-03A exception to the legacy No-FK
convention. It creates four empty technical tables with internal
`ON DELETE RESTRICT` relationships and immutable-row triggers. It imports no
seed and creates no lifecycle or runtime-selection state. Its production
execution is not authorized by the implementation commit.
