# GATE-03 storage cleanup

Status: **not authorized**. This runbook prepares one object-specific Docker
image cleanup. It neither grants GATE-03 nor performs a production mutation.

## Fail-closed boundary

`ops/docker_image_cleanup.py` can remove only exact image IDs from
`ghcr.io/jungt72/sealai-backend-v2`. It has no container, volume, file, backup,
build-cache, wildcard, or prune deletion path. Every candidate must still:

- be absent from all running and stopped containers;
- exactly match its approved ID, RepoTags, RepoDigests, and canonical
  string-label digest;
- have every immutable recovery digest reachable in the registry;
- remain outside the complete approved protection set; and
- be classified `active_dependency=false`, `safe_to_remove=true`,
  `backup_required=false`, with registry-digest recovery.

The `execute` path holds `/run/lock/sealai-storage-mutation.lock` for the whole
batch. Under that lock it checks, before the first removal, immediately before
every individual removal, and immediately after every removal:

- the approved hostname and SHA-256 of the normalized machine ID;
- the fixed `/home/thorsten/sealai` checkout, `main`, exact commit, exact tree,
  clean tracked and untracked status, and canonical repository fingerprint;
- Docker's reported root path, the approved backing device identity, target
  filesystem, and at least 3 GiB free;
- all eight fixed core containers and their approved exact image IDs
  (`backend-v2`, `backend-v2-worker`, `sealai-frontend-1`, `nginx`, `keycloak`,
  `postgres`, `redis`, `qdrant`) as both running and healthy;
- approval TTL, backup/rollback evidence validity, the production Compose
  desired image set, rollback anchors, staging/V1/foreign attestations, and all
  running or stopped container references.

Any unavailable, malformed, missing, expired, mismatched, unhealthy, or drifted
input denies the next removal. A failure after one or more successful removals
emits a structured `partial` event before returning a denied exit. The tool
emits `indeterminate` and stops if a removal subprocess returns nonzero, is
interrupted, or times out and its mutation outcome cannot be proven; operators
must resolve that exact ID read-only before preparing any later gate. It stops
without consuming the remaining approved IDs as soon as exact byte accounting
shows the target filesystem at or below 80% used and the approved minimum
reclaim was observed; the final event is `target_reached`. An already-safe
filesystem requires no reclaim. Exhausting the approved list above 80% emits
`insufficient_reclaim` and exits nonzero. Reaching 80% after a deletion without
observing the manifest's minimum reclaim emits `minimum_reclaim_not_observed`
and also exits nonzero. Either result requires a fresh inventory, manifest, and
approval for any later batch.

Do not use `docker system prune`, `docker image prune`, `docker builder prune`,
`docker volume prune`, wildcard deletion, or tag-only deletion in this gate.
The subprocess environment fixes PATH and forces the local
`unix:///var/run/docker.sock`; inherited Docker hosts, contexts, and TLS flags
cannot redirect the approved command to another daemon.
All inherited `GIT_*` variables are removed. Git runs without system/global
configuration, optional index writes, hooks, or fsmonitor helpers; Docker
authentication variables and `HOME` remain available for registry recovery
checks.

## Manifest contract (schema version 2)

Store the manifest outside Git with mode 0600. It contains no secret value.
The following abbreviated example shows every exact root and binding field;
placeholders are not executable:

```json
{
  "schema_version": 2,
  "gate_id": "GATE-03",
  "purpose": "approved production headroom recovery",
  "minimum_reclaim_bytes": 11811160064,
  "operation": {
    "operation_id": "operator-selected-id",
    "host": {
      "hostname": "approved-hostname",
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
    "docker_storage": {
      "docker_root_dir": "/mnt/sealai-volume/docker-data",
      "target_filesystem": "/mnt/sealai-volume",
      "device_major_minor": "approved-major:minor",
      "minimum_free_bytes": 3221225472,
      "target_max_used_percent": 80
    },
    "core_containers": {
      "backend-v2": {"image_id": "sha256:..."},
      "backend-v2-worker": {"image_id": "sha256:..."},
      "sealai-frontend-1": {"image_id": "sha256:..."},
      "nginx": {"image_id": "sha256:..."},
      "keycloak": {"image_id": "sha256:..."},
      "postgres": {"image_id": "sha256:..."},
      "redis": {"image_id": "sha256:..."},
      "qdrant": {"image_id": "sha256:..."}
    },
    "production_fingerprint_sha256": "canonical-stable-runtime-fingerprint",
    "command": {
      "argv_prefix": ["/usr/bin/docker", "image", "rm", "--no-prune"],
      "ordered_image_ids": ["sha256:exact-id-in-objects"],
      "commands_sha256": "canonical-command-list-sha256"
    }
  },
  "recovery_evidence": {
    "backup": {
      "kind": "encrypted_offsite_restore_verified",
      "status": "VERIFIED",
      "evidence_id": "sanitized-offsite-backup-receipt-id",
      "evidence_sha256": "sanitized-receipt-sha256",
      "verified_at": "short-lived-UTC-Z-timestamp",
      "valid_until": "UTC-Z-no-more-than-24-hours-later"
    },
    "rollback": {
      "kind": "registry_digest_pull_verified",
      "status": "EXECUTABLE_VERIFIED",
      "evidence_id": "sanitized-registry-rollback-receipt-id",
      "evidence_sha256": "sanitized-receipt-sha256",
      "verified_at": "short-lived-UTC-Z-timestamp",
      "valid_until": "UTC-Z-no-more-than-24-hours-later"
    }
  },
  "protection": {
    "role_attestations": {
      "production_desired": {"status": "PRESENT", "image_ids": ["sha256:..."]},
      "staging": {"status": "PRESENT", "image_ids": ["sha256:..."]},
      "rollback_primary": {"status": "PRESENT", "image_ids": ["sha256:..."]},
      "rollback_secondary": {"status": "PRESENT", "image_ids": ["sha256:..."]},
      "legacy_v1": {"status": "NONE_APPROVED", "image_ids": []},
      "foreign_workloads": {"status": "PRESENT", "image_ids": ["sha256:..."]}
    }
  },
  "objects": []
}
```

The empty `objects` array is documentation only and intentionally invalid. A
real manifest contains one to ten unique candidates. Every object has exactly:

```text
type = docker_image
id = exact sha256 image ID
expected_repo_digests = non-empty immutable registry references
expected_repo_tags = exact current tag list, including [] when empty
expected_labels_sha256 = canonical SHA-256 of the exact current string label map
estimated_reclaim_bytes = positive integer
active_dependency = false
safe_to_remove = true
backup_required = false
recovery.kind = registry_digest
recovery.reference = one of expected_repo_digests
```

`command.ordered_image_ids` must equal object order. `commands_sha256` is the
SHA-256 of compact, key-sorted JSON for the ordered list of exact argv arrays,
one `/usr/bin/docker image rm --no-prune sha256:...` array per object. The repository
fingerprint uses the same canonical JSON encoding over exactly `hostname`,
`machine_id_sha256`, `checkout_path`, `branch`, `commit`, `tree`, and `clean`.
The machine-ID field is a SHA-256 of the normalized machine ID, never its raw
value. Device identity is the major/minor identity shared by the approved
Docker root and target filesystem.

The candidate label binding stores only canonical SHA-256, never raw Docker
label values. The tool hashes the complete live string-label map in memory and
does not emit it. This preserves exact drift detection without copying a
potentially sensitive label value into the manifest or logs.

The production fingerprint is canonical JSON over the approved host identity,
repository fingerprint, stable Docker storage path/device identity, the exact
eight-name core-container image-ID map, and the protection-set SHA-256. Mutable
capacity and health values are intentionally checked live at every checkpoint
rather than hashed into the stable fingerprint.

`protection_sha256` is canonical compact, key-sorted JSON of the exact six-role
map (`role -> {status, image_ids}`), with each image-ID list sorted. This hash
does not replace live protection validation; it binds the human approval to the
attested baseline that every checkpoint must still satisfy.

All six protection roles are mandatory. Production and exactly two distinct
rollback roles must be `PRESENT`; rollback images must still have a
`rollback-pre`, `rollback-hold`, or `rollback-reconstructed` tag. A genuinely
absent optional role is explicitly `NONE_APPROVED` with an empty list. The
runtime production Compose set must exactly equal `production_desired`.

Backup evidence must represent a verified offsite recovery source for critical
data. Rollback evidence must represent a tested, executable exact-digest image
recovery path. The files behind the evidence digests stay private; committed or
displayed gate material contains only sanitized IDs, status, timestamps, and
SHA-256 values. Both evidence windows are at most 24 hours and are rechecked at
every checkpoint.

## Approval receipt

Only after the user explicitly approves GATE-03 for those exact bytes, store a
mode-0600 receipt outside Git:

```json
{
  "schema_version": 2,
  "gate_id": "GATE-03",
  "decision": "APPROVED",
  "approval_id": "operator-supplied-approval-id",
  "approved_by": "operator-identity",
  "approved_at": "short-lived-UTC-Z-timestamp",
  "expires_at": "UTC-Z-at-most-four-hours-later",
  "manifest_sha256": "sha256-of-exact-manifest-bytes",
  "operation_id": "exact-manifest-operation-id",
  "approved_hostname": "exact-manifest-hostname",
  "approved_machine_id_sha256": "exact-manifest-machine-id-sha256",
  "repository_fingerprint_sha256": "exact-manifest-fingerprint",
  "production_fingerprint_sha256": "exact-manifest-stable-runtime-fingerprint",
  "commands_sha256": "exact-manifest-command-binding",
  "protection_sha256": "canonical-protection-binding",
  "backup_evidence_sha256": "exact-manifest-backup-evidence-sha256",
  "rollback_evidence_sha256": "exact-manifest-rollback-evidence-sha256"
}
```

Every field is exact-schema validated. The receipt is rejected if any explicit
binding disagrees even when another field is valid. `approvals.yaml` remains
`PENDING` until the explicit decision. Never invent, extend, or reuse a receipt,
and never use it for another host, checkout, protection set, command list, or
evidence set.

## Execution sequence

These production commands are examples for review. Do not run them during
local preparation or without the matching GATE-03 approval.

1. Capture a fresh sanitized inventory and exact schema-v2 manifest. Verify the
   offsite backup and executable registry rollback receipts.
2. Validate without mutation on the approved production host and checkout:

   ```bash
   /usr/bin/python3 -I ops/docker_image_cleanup.py plan /secure/path/gate-03-plan.json
   ```

3. Reconfirm the single-gate approval and execute one bounded batch:

   ```bash
   /usr/bin/python3 -I ops/docker_image_cleanup.py execute /secure/path/gate-03-plan.json \
     --approval /secure/path/gate-03-approval.json
   ```

4. Preserve the structured result and immediately run the separately approved
   non-mutating service, storage, Postgres, Redis, Qdrant, Keycloak, backend,
   worker, frontend, and Nginx verification. `partial` never authorizes a
   continuation; any later object needs a fresh manifest and receipt.

## Stop and recovery conditions

Zero objects may be removed when free space is below 3 GiB, a fixed core
container is not running and healthy, host/checkout/device identity drifts,
backup or rollback evidence is invalid, registry recovery is unavailable, a
candidate becomes referenced, protection changes, or approval expires. A drift
immediately after one removal stops the second removal and records the partial
result.

Recover an image only by its exact approved registry digest and only after the
disk guard permits the pull under the global storage lease. Never restore a
mutable tag. An unexpected health change requires read-only diagnosis and a
separate recovery/deployment gate; this cleanup receipt grants neither restart
nor deployment authority.

## Current evidence and target

The sanitized inventory is
`.ai-remediation/runs/REM-2026-07-14/storage-inventory.yaml`. Raw object metadata
remains local and ignored. At the last read-only check, the data filesystem was
95% used with 5,330,395,136 bytes available. The planning target is at least
11 GiB reclaimed including margin; 16 GiB is preferred. No cleanup or evidence
approval has occurred, and current offsite recovery remains a separate
prerequisite rather than an implied fact.
