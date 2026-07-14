# GATE-04: Legacy-Redis-Remediation

Status: **GATE-04 closed; consistent read-only observation implemented**.

`ops/redis_legacy_cleanup.py` cannot mutate Redis, the production filesystem,
or a local filesystem. It does not create reports, receipts, approvals, lock
files, temporary files, or caches. It emits one redacted JSON observation to
standard output. `--execute` is a negative control that always exits denied
before any host, Docker, or Redis runtime probe.

The only successful status is:

```text
CONSISTENT_READ_ONLY_OBSERVATION
```

This status is explicitly not a point-in-time snapshot, proof, approval,
cleanup authorization, or satisfied production gate. Every successful event
contains `is_snapshot=false`, `is_proof=false`, `is_approval=false`,
`execution_authorized=false`, and `gate04_closed=true`.

## Why execution remains closed

Production discovery established two unresolved limits:

1. RedisJSON `MEMORY USAGE` values are not additive allocator shares. Their
   sum can exceed Redis INFO `used_memory`. Per-category sums are diagnostics
   only and cannot bind a manifest, predict reclaim, or decide the 70% target.
2. Hashing a potentially attacker-controlled key does not provide a
   collision-proof exact-key authorization. Returning raw key names would
   violate the no-raw-key evidence boundary. The current observer therefore
   cannot prove a safe exact deletion set.

The observer uses opaque double-SHA-1 tokens only in process memory to
deduplicate possible SCAN duplicates. It never prints or persists raw keys,
raw values, or tokens and never treats a token as key identity proof.

## Read-only boundary

Redis access is restricted in source to this fixed allowlist:

- `INFO all`
- `CONFIG GET` for the fixed persistence and memory fields
- `LASTSAVE`
- `DBSIZE`
- the fixed inventory script through server-enforced `EVAL_RO`

The Lua script calls only SCAN, TYPE, PTTL, and MEMORY USAGE. The controller has
no Redis write command, generic command pass-through, local write-open mode,
file-creation option, report option, or approval option.

Every `docker exec` addresses the exact 64-hex container ID bound in the
manifest, never the mutable container name. Before, between, and after the two
cursor passes, Docker inspection resolves both the fixed name `redis` and the
exact ID and requires them to identify the same running, healthy container with
the bound image. Removal, replacement, rename, or name-to-ID drift fails
closed.

The manifest is read with no-follow semantics and must be an operator-owned
regular file with exact mode 0600. Duplicate JSON object keys are rejected at
every nesting level. JSON booleans are rejected for every integer field,
including schema version, database, counters, persistence epoch, DB size,
memory target, cursor size, category counts, and type counts. Duplicate CONFIG
GET names are also rejected.

## Observation protocol

One run performs the following read-only sequence:

1. Validate the private manifest and current recovery-evidence timestamps.
2. Bind hostname, hashed machine identity, exact clean checkout, commit, tree,
   and repository fingerprint.
3. Resolve and validate Redis name-to-container-ID and image binding.
4. Read the first Redis health and allocator observation through that ID.
5. Walk one bounded SCAN cursor pass through `EVAL_RO`.
6. Re-inspect name and ID, then read health again.
7. Walk a second independent bounded SCAN cursor pass.
8. Read health a third time, re-inspect name and ID, and revalidate checkout.
9. Require all three health observations and both inventory bindings to be
   identical and equal to the manifest's expected categorical binding.

Each cursor pass must cover the full cursor cycle, but Redis SCAN does not
provide snapshot isolation. Even two matching passes can miss a precisely
timed change; this is why the result is only a consistent observation and not a
snapshot or proof.

Any unknown or unstable key, namespace overlap, cursor cycle, duplicate or
invalid response field, category count/type/TTL drift, DB-size drift, allocator
drift, write-error or eviction-counter drift, non-quiescent recovery, AOF/RDB
uncertainty, evidence expiry, checkout drift, container drift, or probe failure
denies the observation.

Queue, session, lock, authority, and cache categories cannot be proposed as
legacy cleanup categories. A proposed category must be
`legacy_rebuildable`, persistent-only, non-empty, and supported by explicit
`VERIFIED_REBUILDABLE` evidence. This classification is observed only; it does
not authorize deletion.

## Memory semantics

Only Redis INFO allocator values are authoritative for capacity:

```text
used_memory * 100 <= maxmemory * 70
```

The event reports the allocator ratio and labels memory semantics
`NONADDITIVE_DIAGNOSTIC_ONLY`. Per-key MEMORY USAGE sums are intentionally
excluded from the manifest and event. Adding an aggregate-memory field to a
category binding is a schema error.

Do not change `maxmemory`, `maxmemory-policy`, TTLs, AOF, RDB, or persistence
settings through this runbook. Those are separate GATE-04 production
mutations.

## Manifest contract

The manifest is an operator-prepared, private read-only input. It contains no
secret or raw key. The following shape is synthetic and deliberately contains
placeholder digests rather than usable production values:

```json
{
  "schema_version": 1,
  "gate_id": "GATE-04",
  "purpose": "synthetic read-only consistency observation",
  "operation": {
    "operation_id": "synthetic:gate04-observation",
    "kind": "UNLINK_EXACT_REBUILDABLE_KEYS",
    "host": {
      "hostname": "synthetic.example",
      "machine_id_sha256": "64-lowercase-hex"
    },
    "checkout": {
      "path": "/home/thorsten/sealai",
      "branch": "main",
      "commit": "40-lowercase-hex",
      "tree": "40-lowercase-hex",
      "clean": true,
      "fingerprint_sha256": "64-lowercase-hex"
    },
    "redis": {
      "container_name": "redis",
      "container_id": "64-lowercase-hex",
      "image_id": "sha256:64-lowercase-hex",
      "database": 0,
      "run_id": "40-lowercase-hex",
      "version": "7.4.0",
      "role": "master",
      "maxmemory_bytes": 1073741824,
      "maxmemory_policy": "noeviction",
      "evicted_keys": 0,
      "write_error_total": 0,
      "instance_fingerprint_sha256": "64-lowercase-hex",
      "persistence": {
        "appendonly": "yes",
        "save": "900 1 300 10 60 10000",
        "dir": "/data",
        "dbfilename": "dump.rdb",
        "appenddirname": "appendonlydir",
        "lastsave_epoch": 1700000000,
        "fingerprint_sha256": "64-lowercase-hex"
      }
    },
    "expected_dbsize": 3,
    "inventory_binding_sha256": "64-lowercase-hex",
    "production_fingerprint_sha256": "64-lowercase-hex",
    "target_max_memory_percent": 70,
    "scan_count": 1000
  },
  "categories": [
    {
      "category_id": "synthetic-legacy-checkpoints",
      "namespace_prefix": "synthetic_checkpoint:",
      "owner": "synthetic-paperless",
      "safety_class": "legacy_rebuildable",
      "rebuildability": {
        "status": "VERIFIED_REBUILDABLE",
        "evidence_sha256": "64-lowercase-hex"
      },
      "ttl_policy": "persistent_only",
      "allowed_types": ["ReJSON-RL"],
      "expected": {
        "count": 2,
        "persistent_count": 2,
        "expiring_count": 0,
        "type_counts": {"ReJSON-RL": 2}
      }
    },
    {
      "category_id": "synthetic-protected-queue",
      "namespace_prefix": "synthetic_queue:",
      "owner": "synthetic-paperless",
      "safety_class": "queue",
      "rebuildability": {
        "status": "PROTECTED",
        "evidence_sha256": "64-lowercase-hex"
      },
      "ttl_policy": "persistent_only",
      "allowed_types": ["set"],
      "expected": {
        "count": 1,
        "persistent_count": 1,
        "expiring_count": 0,
        "type_counts": {"set": 1}
      }
    }
  ],
  "cleanup_categories": ["synthetic-legacy-checkpoints"],
  "recovery_evidence": {
    "persistence": {
      "evidence_id": "synthetic-aof-rdb-evidence",
      "kind": "redis_aof_rdb_live_verified",
      "status": "VERIFIED",
      "evidence_sha256": "64-lowercase-hex",
      "verified_at": "short-lived-UTC-Z-timestamp",
      "valid_until": "UTC-Z-at-most-24-hours-later"
    },
    "restore": {
      "evidence_id": "synthetic-restore-drill-evidence",
      "kind": "redis_backup_restore_drill_verified",
      "status": "RESTORE_VERIFIED",
      "evidence_sha256": "64-lowercase-hex",
      "verified_at": "short-lived-UTC-Z-timestamp",
      "valid_until": "UTC-Z-at-most-24-hours-later"
    }
  }
}
```

The namespace catalog must be pairwise non-overlapping and account for every
observed key in DB 0. `expected_dbsize` must equal the sum of category counts.
The catalog includes protected categories so an unknown queue, session, lock,
authority, cache, or application namespace denies the observation.

## Invocation boundary

No command in this runbook creates a file on the VPS. If an operator separately
authorizes a read-only production observation, invoke the observer with an
already-existing private manifest and inspect standard output directly:

```bash
/usr/bin/python3 -I ops/redis_legacy_cleanup.py /secure/existing-gate-04-manifest.json
```

Do not redirect output to a file on the VPS as part of this runbook. There is no
`--report` or `--approval` option. The following negative control always fails
before runtime probes:

```bash
/usr/bin/python3 -I ops/redis_legacy_cleanup.py \
  /secure/existing-gate-04-manifest.json --execute
```

## Requirements before any future executable cleanup

Do not enable execution by changing the constant alone. A separate security
design, implementation, review, and explicit production GATE-04 approval must
first establish:

- collision-independent exact server-side key selection without raw-key
  output;
- exact category and batch binding at mutation time;
- fixed-order, inode-verified global storage and Redis mutation locks;
- health, write-error, allocator, persistence, and recovery rechecks around
  every bounded batch;
- redacted, no-clobber receipts created only under the separately approved
  mutation procedure;
- success based only on allocator `used_memory <= 70% of maxmemory`; and
- rollback only through the bound verified restore procedure, never blind key
  reinsertion.

Bulk database clearing, wildcard deletion, an uncontrolled cursor-to-delete
pipeline, and persistence or memory-policy changes remain prohibited.
