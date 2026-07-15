# Read-only Legacy and Orphan Inventory

`ops/legacy_inventory.py` classifies explicit, sanitized local inventory data.
It has no discovery adapter and imports no Docker, SSH, PM2, Qdrant, HTTP,
network, or subprocess client. It therefore cannot inspect a daemon or VPS and
cannot delete, archive, stop, restart, reconfigure, or otherwise mutate an
object.

The input schema requires coverage for all of these object types:

- old containers and images
- stopped services
- old frontends
- dead feature flags
- unused prompt families
- old Qdrant collections
- orphaned volumes
- old PM2 processes
- foreign workloads in the sealingAI network
- duplicate configurations
- obsolete backups
- unused ports

The machine names are `container`, `image`, `service`, `frontend`,
`feature_flag`, `prompt_family`, `qdrant_collection`, `volume`, `pm2_process`,
`network_workload`, `configuration`, `backup`, and `port`.

Only these classifications are emitted:

- `ACTIVE`
- `REQUIRED_FOR_ROLLBACK`
- `LEGACY_BUT_IN_USE`
- `ORPHANED`
- `SAFE_TO_ARCHIVE`
- `SAFE_TO_DELETE_AFTER_APPROVAL`
- `UNKNOWN`

Classification is graph-based. Active roots and their dependencies are kept;
rollback roots and their dependencies are kept; unknown ownership, conflicting
evidence, or an unknown lifecycle stays `UNKNOWN`. An object is never classified
from age alone—the schema intentionally has no age field.

The report lists every object, forward dependencies, reverse dependents, the
classification reason, candidate action, and separate backup, dependency,
rollback, and approval gates. `SAFE_TO_ARCHIVE` requires all gates, including
approval, to be ready. `SAFE_TO_DELETE_AFTER_APPROVAL` means backup, dependency,
and rollback evidence are ready but an explicit approval is still required. It
does not authorize deletion: every output object has
`mutation_authorized: false` and `action_taken: false`.

Local fixture use:

```bash
python3 -I ops/legacy_inventory.py classify \
  --input backend/tests/fixtures/legacy_inventory_synthetic.json \
  --output .ai-remediation/legacy-inventory/synthetic-report.json
```

The output directory must already exist inside the repository. Inputs and
outputs are bounded, secret-scanned regular files; duplicate JSON keys, path
escapes, symlinks, file swaps, duplicate IDs, missing dependencies, inconsistent
gate states, and incomplete asset-type coverage fail closed.

The included fixture is synthetic and safe for deterministic tests. A real
production inventory remains `NOT_RUN` until a separate approval authorizes a
sanitized read-only collection. This package neither requests nor performs that
collection.
