# sealingAI disaster recovery target state

This runbook describes repository-side preparation. Nothing in this document authorizes a
production backup, deployment, offsite transfer, retention deletion, restore, permission change, or
network change. No production or external system was touched while implementing this package.

## Current status

The repository now defines a fail-closed recovery-set manifest, encrypted provider-neutral offsite
transport through Restic, a dedicated isolated restore runner, fresh offsite and restore receipts,
monthly systemd scheduling, and stable monitoring metrics. The following items remain
`BLOCKED_EXTERNAL`:

- a dedicated encrypted recovery runner and its Docker daemon;
- an approved versioned/immutable Restic repository, verified TLS, least-privilege access, and the
  Restic binary at the fixed path `/usr/bin/restic`;
- offline escrow for the repository password/key version and actual secret-recovery authorities;
- sanitized real Postgres/Qdrant/upload/document recovery material;
- immutable digest-pinned Postgres, Qdrant, and verifier images preloaded on the recovery runner;
- two successful isolated full restores and import of their receipts;
- installation/activation under an exact `GATE-08` approval; and
- the P1-D canonical Postgres-to-Qdrant rebuild command and tenant-count inventory. Until P1-D
  lands, the automated Qdrant leg supports only checksum-bound snapshots. It must not claim that a
  Postgres-only rebuild has been proven.

## Recovery authority and asset inventory

Postgres is canonical application truth. Qdrant is a derived index. Redis remains non-authoritative
for V2; its persistence and restore decision stays in the separate Gate-04 contract and must not be
silently promoted to a DR system of record.

| Component | Recovery source | Target RPO | Target RTO | Required proof |
| --- | --- | ---: | ---: | --- |
| Postgres, including V2 ledger and Keycloak/Strapi DBs on that instance | verified `pg_dumpall` plus P0 SHA-256 sidecar | 24 h | 4 h | isolated restore, non-empty V2 schema, `pg_amcheck` |
| Qdrant knowledge and memory collections | verified snapshots; canonical rebuild from Postgres after P1-D | 24 h | 8 h | checksum, exact point count, tenant-count digest, no duplicate IDs |
| Strapi uploads | read-only export of `sealai_strapi_uploads` | 24 h | 8 h | manifest byte/file verification |
| Paperless documents | read-only export of `data`, `media`, `export`, and `consume` | 24 h | 8 h | manifest byte/file verification |
| Runtime configuration | clean exact Git tree allowlist plus immutable image digests | one release | 2 h | source commit and file-manifest match |
| Secrets | identifiers and recovery procedure only; never values | n/a | 4 h | authority/key-version procedure, then rotate exposed/recovered runtime values |

Odoo's separate database and data volumes are not silently included: they are a distinct business
workload and need an owner classification before entering the sealingAI DR set. TLS private keys,
provider tokens, `.env.prod`, Restic passwords, SSH keys, and Keycloak client secrets are never put
in the configuration archive. Only their non-secret key-version hashes and recovery procedures are
recorded.

## Immutable recovery-set contract

An approved capture creates a private mode-`0700` directory under
`/var/lib/sealai-dr/sets/<set-id>` with mode-`0600` regular, single-link files:

```text
postgres/       one verified full-instance dump and its P0 .sha256 sidecar
qdrant/         zero or more verified snapshots and their P0 .sha256 sidecars
uploads/        Strapi upload export plus capture inventory
documents/      Paperless export plus capture inventory
configuration/  allowlisted clean-tree configuration plus inventory.json, never runtime secrets
recovery/       recovery-point.json, qdrant-rebuild.json, secret-recovery.json
dr-manifest.json
```

`ops/dr_recovery.py create-manifest` rejects relative/ambiguous roots, non-private directories,
symlinks, hardlinks, writable-by-group/other files, duplicate JSON keys, missing components,
oversized sets, forbidden configuration-secret filenames, invalid P0 sidecars, stale component
captures, Qdrant snapshot/hash drift, and authority-epoch drift. Its manifest never records source
host paths or secret values. After creation, rename the directory to the emitted
`set_id_sha256`; `ops/dr_offsite.sh` refuses any other basename. Never edit a completed set—capture
a new set.

The example contracts under `ops/dr/` contain placeholder hashes only. Generate the real recovery
point and counts from the same storage-lease-bound capture. In particular, the Qdrant
`tenant_counts_sha256` is the SHA-256 of canonical compact JSON containing exact tenant-to-point
counts; the isolated verifier recomputes it by scrolling every point.

`configuration/inventory.json` must bind the exact source commit and at least the base/deploy
Compose definitions, Nginx routing, identity configuration, monitoring configuration, and release
control state to their individual hashes. A generic archive or a single placeholder file does not
satisfy this contract.

`uploads/inventory.json` and `documents/inventory.json` bind the hashed source identity, exact file
count, and total bytes to the files in the set. A genuinely empty source requires the explicit
`empty_source_confirmed` flag; silently omitting a volume or Paperless directory fails closed.

Production capture is a data-bearing write and therefore needs `GATE-08`. It must reuse the P0
writers, storage lease, 85/80 hysteresis, 3-GiB reserve, lifecycle locks, no-clobber publication, and
checksums in `ops/backup_*.sh`; do not make a parallel weaker dump path. Export uploads/documents
read-only into a fresh private staging directory while the global storage lease is held. Export
configuration from the exact clean Git commit with an explicit allowlist. Run the repository secret
scanner before manifest creation. A missing component blocks the set; an empty component requires a
signed inventory stating zero files rather than omission.

## Provider-neutral encrypted offsite copy

Restic supplies client-side authenticated encryption, content checksums, deduplication, and backends
for multiple storage providers. The wrapper intentionally accepts no repository URL, password, or
credential from command-line arguments or inherited environment. It uses these fixed root-private
mode-`0600` files:

```text
/etc/sealai/dr/restic-repository
/etc/sealai/dr/restic-password
/etc/sealai/dr/restic-key-id.sha256
```

Provisioning the repository is external. Require verified TLS, a private write identity, object
versioning/immutability where the backend supports it, a separate read identity for the recovery
runner, and offline recovery of the exact historical encryption-key version. Provider-side
encryption is additional protection, not a substitute for Restic encryption.

With a fresh manifest-bound root-owned Gate-08 receipt at
`/run/sealai-gates/gate-08-dr.json`, the sanctioned upload is:

```bash
/usr/local/libexec/sealai/dr_offsite.sh backup \
  /var/lib/sealai-dr/sets/<64-hex-set-id>
```

Upload success is deliberately reported as `backup_uploaded_unverified`. It is not retention
evidence. A valid `OFFSITE_VERIFIED` receipt exists only after the dedicated runner executes
`restic check --read-data`, restores the exact snapshot completely, authenticates/decrypts it, and
re-verifies every manifest byte. Receipt creation also compares every component capture timestamp
with the current verification time and refuses a recovery point outside its declared RPO. Upload
responses, object existence, ETags, partial reads, and provider dashboards are insufficient.

The offsite policy is 14 daily, 8 weekly, 12 monthly, and 7 yearly snapshots, while preserving at
least two independently verified snapshots. `dr_offsite.sh retention-plan` is dry-run only. There
is intentionally no ungated `forget --prune` path. Applying a plan requires fresh offsite and
isolated-restore receipts for every deletion boundary plus a separate exact Gate-08 approval. Local
P0 backup deletion remains governed by `backup_safety.py`; this package does not weaken it.

## Isolated restore drill

The runner must be a dedicated host with encrypted local storage. It needs the exact sentinel
`SEALAI_DEDICATED_RECOVERY_RUNNER_V1` in
`/etc/sealai/dr/isolated-recovery-runner`. The drill refuses known production files, production
container names, and the production Docker network. It never mounts production paths or the Docker
socket into a container. The compose network is `internal: true`, has no published ports, and has IP
masquerading disabled.

Install digest-pinned, preloaded images in `/etc/sealai/dr/restore-images.env`:

```text
DR_POSTGRES_IMAGE=<registry>/<postgres>@sha256:<64-hex>
DR_QDRANT_IMAGE=<registry>/<qdrant>@sha256:<64-hex>
DR_VERIFIER_IMAGE=<registry>/<backend>@sha256:<64-hex>
```

`pull_policy: never` makes a missing image fail closed. The drill generates only ephemeral
non-production Postgres/Qdrant credentials and removes their private env file on exit. It performs:

1. complete Restic repository read-data verification;
2. exact snapshot download and recovery-set manifest verification;
3. fresh manifest-bound `GATE-08` verification before containers start;
4. full `pg_dumpall` restore, V2 schema assertion, and `pg_amcheck`;
5. Qdrant snapshot recovery with checksum, exact point count, duplicate-ID detection, and exact
   tenant-count digest;
6. a second whole-set verification; and
7. canonical offsite and restore receipts bound to the manifest and set ID.

Run an explicitly selected set/snapshot with:

```bash
/usr/local/libexec/sealai/dr_restore_drill.sh <set-id> <restic-snapshot-id>
```

The monthly timer selects the newest snapshot having exactly one `set-<set-id>` tag and delegates to
that command. It still fails closed without a fresh matching Gate-08 receipt. Installation and timer
activation are external and gated; repository presence is not proof that a drill ran. Restored
plaintext under `/var/lib/sealai-dr/drills/` must be retained only until receipts are exported, then
deleted as the exact drill directory under a separately reviewed runner-local retention job. Never
run the drill on the VPS.

For `mode=postgres_rebuild`, stop after Postgres verification until P1-D supplies the canonical
command registry. Do not replace it with ad-hoc ingestion, a guessed collection name, or an
in-process fallback. Once P1-D lands, the rebuild must start from empty target collections and prove
authority epoch, tenant counts, orphan absence, and idempotence before the receipt can say
`qdrant_recovered=true`.

## Secret recovery

`secret-recovery.json` allows only tokenized identifiers, purpose, custody class, a SHA-256 of the
versioned key identifier, test class, and post-restore rotation policy. Fields such as value, token,
password, private key, endpoint credential, or arbitrary prose are not accepted by schema. The
actual recovery channel is out of band.

At least twice yearly, custodians should recover a non-production key version on the isolated
runner. A real incident restores the exact historical Restic key first, then issues fresh runtime
credentials. Never restore a revoked/exposed credential from a backup. Losing the historical Restic
key is equivalent to losing the backup and must alert immediately.

## Monitoring contract

The textfile renderer emits only these stable metrics with the allowlisted `component` label; it
never labels by object, snapshot, path, tenant, repository, key, or secret:

```text
sealai_backup_last_success_timestamp_seconds{component}
sealai_backup_last_failure_timestamp_seconds{component}
sealai_offsite_backup_last_success_timestamp_seconds{component}
sealai_restore_drill_last_success_timestamp_seconds{component}
sealai_backup_receipt_valid{component}
```

Alert on a missed RPO, failed backup, invalid/stale receipt, no successful monthly drill within 35
days, or any timer failure. The renderer rejects a status document that omits any required recovery
component, so partial exporter state cannot look healthy. External alert delivery remains
`BLOCKED_EXTERNAL`.

## Gate-08 request

Submit one request per action; never approve capture, upload, drill installation, production restore,
and retention deletion as one broad gate.

```yaml
gate_id: GATE-08
objective: Install and execute the named DR action only
current_state: Repository implementation tested locally; production and offsite unchanged
exact_actions:
  - install reviewed immutable scripts/config on the named host
  - execute only the manifest-bound action in the short-lived receipt
exact_commands_sanitized:
  - /usr/local/libexec/sealai/dr_offsite.sh backup /var/lib/sealai-dr/sets/<set-id>
affected_services: [backup storage or dedicated recovery runner]
expected_downtime: none for capture/upload/drill; separately assessed for a real production restore
data_risk: encrypted data leaves the VPS; restored plaintext exists transiently on the dedicated runner
security_risk: key custody, offsite IAM, runner isolation, and secret rotation must verify
preconditions: [P0 storage lease green, exact manifest, clean source commit, fresh scoped approval]
backup_status: local copies retained; no retention deletion until two isolated restores
verification: [full download, authenticated decryption, manifest, Postgres, Qdrant, files, receipts]
rollback: disable timer/job and retain all pre-existing local/offsite copies; never roll back key rotation
stop_conditions:
  - free space below 3 GiB or P0 disk guard blocked
  - missing/invalid manifest, sidecar, receipt, image digest, key version, or approval
  - production marker/container/network appears on the recovery runner
  - database integrity, point count, tenant digest, or RPO/RTO differs
  - any secret appears in output or any external endpoint other than the approved Restic repository is contacted
```

## Rollback and real incident boundary

Repository rollback means disable the timer/service and revert only to another fail-closed backup
implementation. Keep all old verified copies while the new path is evaluated. Never delete an
offsite snapshot to roll back code, never restore revoked credentials, and never weaken P0 sidecar,
capacity, receipt, or minimum-copy requirements.

A real production restore is a separate incident action and separate Gate-08 request. Stop writers,
record the production fingerprint, select an exact fresh receipt, preserve the damaged state for
forensics, restore into an isolated candidate first, compare row/tenant counts, then use the
sanctioned release path. `ops/RESTORE.md` remains the component-level reference; no command in this
runbook authorizes replay directly into live Postgres or Qdrant.
