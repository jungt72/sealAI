# Backup storage safety

This runbook describes the repository implementation only. Installing or executing changed
scripts on the production VPS remains a gated production change; this document does not authorize
deployment, deletion, permission changes, or offsite-storage configuration.

## Capacity preflight

Every backup script first acquires the global storage lease, then calls the canonical Docker disk
guard and `ops/backup_safety.py preflight` against the nearest existing target parent. Only after
that succeeds may the helper create/open the target and lifecycle lock; a second `preflight-bound`
then measures that exact open target descriptor before temporary output, a database dump, or a
Qdrant server-side snapshot. The Docker guard protects the separate filesystem that backs the source
containers and Qdrant's server-side snapshot. Its wrapper and config use fixed,
non-environment-overridable canonical paths; missing, stale, blocked, or failed guard state fails
the backup closed:

```bash
DOCKER_DISK_GUARD_WRAPPER=/usr/local/libexec/sealai/docker-disk-guard.sh
DOCKER_DISK_GUARD_CONFIG=/etc/sealai/disk-guard.json
```

The backup user does not read the root-private guard config/state directly. The installed lease
library invokes exactly that preflight through the gated, non-interactive root mediation installed
for this one command. Backup scripts contain no second direct guard call; a missing or broadened
mediation rule remains a deployment blocker.

The first target helper finds the nearest existing parent of `TARGET_DIR`; the bound helper uses
`fstatvfs` on the subsequently opened target descriptor. It does not assume that backups live on
`/`, `/data`, or any particular device. Both checks are required because the target can be created
after the first check and because backup and Docker data can be different mounts. `TARGET_DIR` must
already be absolute and normalized. Literal `~`, relative paths, `.`/`..` components, duplicate
separators, and a trailing separator are rejected instead of being expanded or silently rewritten.
The helper walks and creates missing directory components with no-follow directory descriptors,
binds the resulting inode, and the shell writes through `/proc/self/fd/<target-fd>`. Qdrant also
applies the configured estimate and reserve to fixed `/mnt/sealai-data` before the snapshot POST;
current 85/80 state alone is not enough. After Qdrant reports the server snapshot's exact byte size,
the script runs another `preflight-bound` against the still-open target inode immediately before
`docker cp`. If both copies share one filesystem, current usage already includes the server snapshot,
so their coexisting peak is covered.

Before either preflight, each entrypoint sources the fixed, non-symlink installed library
`/usr/local/libexec/sealai/production-storage-lease.sh` and acquires the global production storage
lease. Its descriptor remains open for the entire script, including Qdrant POST, copy, verification,
DELETE, and retention. This serializes backups with builds, pulls, releases, and approved cleanup.
Missing library, unsafe lock, contention, or failed acquire blocks the backup. The path has no
environment override. The library validates and reuses an inherited descriptor for the sanctioned
backend release → pre-migration-backup call chain, so nested backup acquisition cannot self-deadlock;
an inherited descriptor for any other inode fails closed.

The writers never source `.env.prod`. They invoke `ops/backup_safety.py` with a fixed
`/usr/bin/python3 -I` under an empty, allowlisted environment and parse the fixed
`/home/thorsten/sealai/.env.prod` as inert data. That file must be a non-symlink, single-link regular
file owned by the backup user with exact mode `0600`. Only the profile's required keys are returned;
duplicates, malformed requested values, and shell constructions such as `$()`, `${...}`, or
backticks in a requested value fail closed without evaluation. Compose interpolation in an
unrequested key remains inert and is ignored. `ENV_FILE`, `PATH`, `PYTHONPATH`, and exported Bash
functions cannot select code, a parser, or a credential source. Every backup shell starts with
`/bin/bash -p`, a fixed system `PATH`, and `umask 077`. Numeric capacity/retention settings, fixed
container tokens, state path, and Qdrant deletion policy/receipt are explicitly allowlisted and
validated across both the orchestrator and lifecycle re-exec boundaries. In particular,
`verified-offsite` can never silently reset to the weaker local-only policy.

Rollout must install the versioned library at that exact path and pre-create
`/run/lock/sealai-storage-mutation.lock` as a regular `0660 root:thorsten` file. This is part of
the gated production installer, not something a backup script creates or repairs. Activating the
new backups before both artifacts verify will intentionally make every run fail closed.

The preflight is fail-closed when any of these conditions applies:

- actual utilization is at least 85%;
- a previous actual-critical state has not recovered to 80% or lower;
- the estimated backup plus the configured minimum free reserve does not fit; or
- the estimated backup would take the target filesystem to at least 85%.

The backup-specific estimate and minimum remaining reserve are bytes:

| Setting | Default |
| --- | ---: |
| `BACKUP_MIN_FREE_BYTES` | 3 GiB; lower overrides are rejected fail-closed |
| `POSTGRES_BACKUP_ESTIMATED_BYTES` | 1 GiB |
| `QDRANT_BACKUP_ESTIMATED_BYTES` | 1 GiB |
| `V2_DATABASE_BACKUP_ESTIMATED_BYTES` | 1 GiB |

Set estimates from measured high-water marks with explicit growth headroom. Do not lower the
reserve merely to make a blocked run pass. The small hysteresis state contains only a hashed target
identifier and status; by default it is stored under
`/home/thorsten/.local/state/sealai-backup` with directory mode `0700` and file mode `0600`.
`BACKUP_SAFETY_STATE_DIR` can move it to an approved absolute persistent state location and is
validated and preserved across re-exec.
The state directory must be an absolute, non-symlink directory owned by the invoking user with
exact mode `0700`; an existing state file must be a non-symlink regular file owned by that user with
exact mode `0600`. Unsafe state storage blocks rather than being silently repaired or ignored.

## Local verification and temporary files

Postgres output must be non-trivial, gzip-valid, and contain the dump marker. A V2 custom dump must
pass `pg_restore --list`. A Qdrant create response must report `status=ok` plus a valid name, byte
size, and SHA-256 checksum; the fully copied local file must match both reported size and checksum
before it can replace the partial file or authorize the remote DELETE. Only then is the unique
`.partial` file atomically renamed and a mode-`0600` SHA-256 sidecar written. The helper re-reads the
final file and verifies that sidecar before the run can succeed. Exit and signal traps remove partial
files; they never remove a finalized backup. Final names include a random `mktemp` token, and a
hard-link publish creates the final name only if it does not already exist. A same-second run cannot
overwrite an earlier good backup. State/receipt/checksum atomic replacements fsync both the file and
parent directory. Before publishing the checksum, the helper hashes and `fsync`s the opened final
backup inode, then revalidates its device, inode, size, ownership, link count, and timestamps against
the unchanged path. The final parent-directory `fsync` then durably flushes the backup and sidecar
directory entries. Any file-sync or revalidation failure blocks before Qdrant remote deletion.
The Qdrant writer keeps the target lifecycle lock and an exclusive lock on an open descriptor for
the published local snapshot through the confirmed remote DELETE response. The remote-delete gate
re-hashes that inherited descriptor immediately before DELETE and requires the pathname to retain
the same device, inode, owner, mode, single-link count, size, timestamps, and server-provided
SHA-256. For the offsite policy, the receipt's backup name and digest must match this same bound
inode. The descriptor and both locks are released only after Qdrant confirms deletion; retention
runs afterward under a newly acquired lifecycle lock.

Target creation and lifecycle locking are descriptor-based. The helper walks directory components
with no-follow opens, requires the opened target to remain the exact path inode, and requires exact
owner/mode plus a same-filesystem, single-link, non-symlink regular lock file. Existing lock content
is never truncated. The writer uses `/proc/self/fd/<target-fd>` for temporary and final names and
re-runs capacity projection against the opened filesystem after acquiring the lock, immediately
before any dump, Qdrant POST, or local temporary file. The orchestrator applies the same rules to
its fixed log and run lock and appends through the pinned log descriptor rather than reopening a
pathname.

Events are one-line JSON with fixed reason tokens and numeric/boolean metrics. They intentionally
omit environment values, API responses, target paths, snapshot names, checksums, and credentials.
The pre-migration script still prints the resulting local filename on stdout because the release
wrapper binds that artifact; all of its JSON events go to stderr.

## Offsite receipt contract

Age alone never authorizes deletion. Writers and retention share an exclusive, non-blocking fcntl
lock in `TARGET_DIR/.backup-lifecycle.lock`. Before every individual unlink, retention opens and
checksum-pins every remaining local candidate with no-follow descriptors, re-hashes those open
descriptors, re-verifies the selected receipt, and uses a directory descriptor plus inode checks for
unlink. This closes races between cooperating repository entrypoints. The target directory is
non-symlink, owned by the backup user, and exactly mode `0700`; root or a deliberately
non-cooperating process running as that same owner remains outside the cooperative-lock guarantee.
Only files with link count one qualify, so multiple hardlink names for one inode can never inflate
the minimum-independent-copy count.
A local file is retention-eligible only if all of the following are true:

1. the local backup and its `.sha256` sidecar verify;
2. the file is older than `RETENTION_DAYS`;
3. an adjacent `<backup>.offsite-receipt.json` is a regular file and strictly validates; and
4. deleting it leaves at least `BACKUP_MIN_LOCAL_COPIES` verified local backups (default: two).

The repository receipt writer accepts distinct ciphertext-download and post-decryption files. It
hashes the complete local backup and both supplied files, rejects hard links and digest mismatches,
then writes the receipt atomically with mode `0600`:

```bash
/usr/bin/env -i HOME=/home/thorsten PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C LC_ALL=C \
  /usr/bin/python3 -I /home/thorsten/sealai/ops/backup_safety.py write-receipt \
  --component backup_postgres \
  --backup /approved/backup/postgres-all-YYYY-MM-DD_HH-MM-SS.sql.gz \
  --downloaded-ciphertext /secure/temp/full-downloaded-ciphertext \
  --decrypted-plaintext-copy /secure/temp/decrypted-plaintext \
  --offsite-object-id-sha256 '<sha256-of-canonical-provider-bucket-object-id>' \
  --encryption-key-id-sha256 '<sha256-of-versioned-kms-or-client-key-id>'
```

The caller must create both supplied files as fresh, distinct, single-link regular files owned by
the backup user with mode `0600`. The writer hashes the complete downloaded ciphertext, requires it
to differ from the local plaintext, then hashes the complete post-decryption plaintext and requires
that digest to equal the local backup and sidecar. Passing the local backup, a hard link, plaintext
masquerading as ciphertext, or output from a failed decrypt is rejected. The writer cannot by itself
prove that the ciphertext originated off-host; that provenance must come from the approved external
download workflow. An upload response, multipart ETag, object existence check, or unverified copy
command is not sufficient.

Offsite storage provisioning, network transport, endpoint selection, credentials, and the download
job are currently **`BLOCKED_EXTERNAL`**. No such secret or transport configuration is committed by
this remediation. Therefore content verification is implemented locally, but automatic production
retention, offsite DR, and origin provenance remain externally blocked until an approved storage
target produces the download and an isolated restore test succeeds.

Approval of that external workflow requires all of the following, none of which is implied by this
repository change:

- TLS with certificate verification for every upload/download and no public bucket or anonymous
  access;
- a private storage identity with least-privilege IAM limited to the exact backup prefix, separate
  read/write roles where supported, and no broad account administration permission;
- encrypted objects using a customer-controlled KMS key or reviewed client-side authenticated
  encryption before upload (provider-default transport encryption alone is insufficient);
- documented key creation, rotation, revocation, escrow/recovery, retention, and destruction
  lifecycle, with versioned key identifiers but no key material in receipts or logs; and
- a periodic isolated restore-key test that downloads ciphertext, retrieves the exact historical
  key version, authenticates/decrypts the object, verifies the plaintext digest, and restores into
  disposable Postgres/Qdrant services. Losing the historical key is treated exactly like losing the
  backup.

The strict schema is:

```json
{
  "schema_version": 2,
  "backup_name": "postgres-all-YYYY-MM-DD_HH-MM-SS-RANDOM.sql.gz",
  "local_plaintext_sha256": "<64 lowercase hex characters>",
  "downloaded_ciphertext_sha256": "<SHA-256 of the complete encrypted object>",
  "decrypted_plaintext_sha256": "<same digest as local_plaintext_sha256>",
  "offsite_verified": true,
  "offsite_ciphertext_object_id_sha256": "<SHA-256 of provider/bucket/object/version>",
  "encryption_key_id_sha256": "<SHA-256 of the versioned KMS or client key identifier>",
  "verified_at": "YYYY-MM-DDTHH:MM:SSZ",
  "verification_method": "full-download-decrypt-sha256"
}
```

The object identifier is hashed so the log and receipt need not expose an internal bucket or
endpoint while still binding the proof to one canonical ciphertext object/version. The hashed key
identifier binds the evidence to the exact decryption-key version without exposing key material.
The helper accepts only `full-download-decrypt-sha256` and rejects extra fields, a future timestamp,
filename mismatch, non-private file modes, malformed digests, plaintext presented as ciphertext, or
any disagreement between local, sidecar, and post-decryption plaintext checksums.
Existing backups without sidecars or receipts are retained, not grandfathered. Receipts remain as
audit evidence after a local payload ages out. A receipt is deletion-authoritative for at most 24
hours. Before an old local backup may be removed, the external workflow must perform a new complete
download and atomically refresh the receipt; stale proof fails closed.

## Qdrant remote snapshot deletion

`QDRANT_REMOTE_DELETE_POLICY` has exactly two values:

- `verified-local` (default): delete the server-side snapshot only after the finalized local file
  and its checksum sidecar verify.
- `verified-offsite`: additionally require a valid receipt supplied in
  `QDRANT_OFFSITE_RECEIPT`; otherwise retain the server-side snapshot and fail the run so monitoring
  cannot mistake incomplete cleanup for success.

The default deliberately favors service capacity: Qdrant's server-side snapshot is on the live
data filesystem, so keeping a new duplicate after every nightly run can itself cause an outage.
The finalized, checksum-verified backup on the configured target filesystem is required before
deletion. This default is not an off-host disaster-recovery guarantee; the offsite policy becomes
appropriate only when a synchronous, verified offsite receipt is available.

If extraction, checksum creation, local verification, the remote-delete gate, or the DELETE request
fails, the script does not issue any fallback deletion. An operator must inspect capacity and the
redacted failure reason before retrying. Never clean up with an unscoped `find -delete`, Docker
prune, or Qdrant snapshot-directory removal.

## Operational verification before rollout

Before seeking the relevant production approval:

1. run `python -m pytest backend/tests/test_backup_safety.py`;
2. run `bash -n` over all four `ops/backup_*.sh` scripts;
3. configure realistic estimates and a persistent state directory;
4. configure and independently test offsite receipt production in an isolated environment;
5. restore one Postgres and one Qdrant backup into isolated disposable services; and
6. verify alerting consumes `status=blocked` and `status=error` JSON events.

Do not enable age-based reclamation until real offsite receipts have passed the isolated restore
test. A capacity block is safer than silently deleting the only recoverable copy.

## Backup log retention

`ops/logrotate/sealai-backups` is the versioned production logrotate policy for the structured
backup log: weekly or at 10 MiB, 14 compressed rotations, delayed compression, mode `0600`, and the
non-root backup owner. Installing it under `/etc/logrotate.d/` is a production deployment and file
permission change; the repository file alone does not authorize that gate. Validate the installed
copy with logrotate's debug mode before activation, without forcing a live rotation.

`backup_run.sh` also holds a non-blocking orchestration lock for the complete Postgres-plus-Qdrant
cycle. Log directory/file setup and start/final event writes are checked under `set -e`; a full disk,
unsafe symlink, missing `flock`, concurrent run, or failed JSON event makes the orchestrator fail
instead of silently reporting success.
