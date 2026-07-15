# sealingAI disaster recovery target state

This runbook describes repository-side preparation. Nothing in this document authorizes a
production backup, deployment, offsite transfer, retention deletion, restore, permission change, or
network change. No production or external system was touched while implementing this package.

## Current status

The repository now defines a fail-closed recovery-set manifest, encrypted provider-neutral offsite
transport through Restic, a dedicated isolated restore runner, non-authoritative local evidence,
monthly systemd scheduling, stable monitoring metrics, a verification-only threshold-signed DSSE
receipt importer, and a candidate-only canonical Postgres-to-Qdrant rebuild. It cannot sign a
receipt, perform independent attestation, call a real embedding provider from the repository CLI,
or mutate a production collection. The following items remain `BLOCKED_EXTERNAL`:

- a dedicated encrypted recovery runner and its Docker daemon;
- an approved versioned/immutable Restic repository, verified TLS, least-privilege access, and the
  Restic binary at the fixed path `/usr/bin/restic`;
- offline escrow for the repository password/key version and actual secret-recovery authorities;
- sanitized real Postgres/Qdrant/upload/document recovery material;
- immutable digest-pinned Postgres, Qdrant, and verifier images preloaded on the recovery runner;
- a Gate-08-approved cryptographic receipt trust root, independently held attestor/approver signing
  keys, and actual external receipt production;
- two successful isolated full restores and import of their receipts;
- installation/activation under an exact `GATE-08` approval; and
- an approved real embedding adapter/model identity, live tenant-count inventory, and a separately
  reviewed cutover mechanism. The implemented rebuild creates and verifies isolated run-specific
  candidates only; it contains no alias, rename, delete, or production cutover operation.

## Recovery authority and asset inventory

Postgres is canonical application truth. Qdrant is a derived index. Redis remains non-authoritative
for V2; its persistence and restore decision stays in the separate Gate-04 contract and must not be
silently promoted to a DR system of record.

| Component | Recovery source | Target RPO | Target RTO | Required proof |
| --- | --- | ---: | ---: | --- |
| Postgres, including V2 ledger and Keycloak/Strapi DBs on that instance | verified `pg_dumpall` plus P0 SHA-256 sidecar | 24 h | 4 h | isolated restore, non-empty V2 schema, `pg_amcheck` |
| Qdrant knowledge and memory collections | verified snapshots or candidate-only canonical rebuild from Postgres | 24 h | 8 h | source fingerprint, authority epoch, exact IDs/payloads/vector dimensions, tenant-count digest, no production mutation |
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
oversized sets, forbidden configuration-secret filenames, invalid P0 sidecars, stale payload
mtimes, Qdrant snapshot/hash drift, and authority-epoch drift. Manifest version 2 binds each file's
actual `mtime_ns` together with path, size, mode, and content hash. A freshly written
`recovery-point.json` is not freshness proof: the newest real file in each component must agree
with `captured_at` within the bounded clock skew, and every component file must still be inside its
RPO when the manifest or local observation is created. Its manifest never records source host paths
or secret values. After creation, rename the directory to the emitted
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
evidence. The repository writer can record only `LOCAL_EVIDENCE_ONLY` with
`authoritative=false` and provenance `LOCAL_UNATTESTED`. That record binds the manifest, set,
snapshot, actual payload mtimes, and exact Gate-08 receipt/approval hashes, but it cannot be renamed,
edited, or revalidated into an authoritative receipt. The two `dr_recovery.py` verifier commands
terminate with `external_receipt_required` unless a separate imported record and active policy are
supplied; local evidence is deliberately never a trust root.

`ops/dr_receipts.py` is the separate external trust boundary. It has no signer and accepts only
canonical DSSE envelopes meeting an active, unexpired Ed25519 policy with at least two distinct
role keys. Import is exclusive into a private store and every later consumption re-verifies the
embedded signatures under the current policy. The repository implementation was exercised only
with ephemeral test keys; no production trust root, signer, envelope, or import exists.

A real `OFFSITE_VERIFIED` decision still requires an independent external attestor that observed
`restic check --read-data`, full restore, authenticated decryption, and byte-for-byte manifest
verification. The file-level `offsite_backup` receipt currently consumed by P0 retention binds an
exact backup filename/plaintext digest, complete downloaded-ciphertext digest, object/version hash,
and encryption-key-version hash. The DR-set `dr_offsite_set` subject additionally binds the exact
manifest, set, Restic snapshot, Gate-08 approval, repository/key identifiers, and SHA-256 of the
local evidence file. Upload responses, object existence, ETags, partial reads, local JSON, and
provider dashboards are insufficient.

### Authoritative receipt import and consumption

Provision one reviewed public-key policy at `/etc/sealai/dr/receipt-trust-policy.json` and a private
mode-`0700` import store. Private signer keys must not exist on the VPS or recovery runner. After the
external attestors return a canonical envelope through the approved channel, import it exactly
once:

```bash
/usr/bin/python3 -I /usr/local/libexec/sealai/dr_receipts.py import \
  --envelope /secure/incoming/<offsite-envelope>.dsse.json \
  --policy /etc/sealai/dr/receipt-trust-policy.json \
  --kind dr_offsite_set --store /var/lib/sealai-dr/imported-receipts

/usr/bin/python3 -I /usr/local/libexec/sealai/dr_receipts.py import \
  --envelope /secure/incoming/<restore-envelope>.dsse.json \
  --policy /etc/sealai/dr/receipt-trust-policy.json \
  --kind restore_drill --store /var/lib/sealai-dr/imported-receipts
```

Import does not itself mark a drill successful. Consume the imported record through the wrapper
that first revalidates the local evidence and Gate-08 provenance, then re-verifies the DSSE and
requires exact subject equality:

Retain the exact root-private Gate-08 receipt referenced by each local evidence record in immutable
drill evidence storage. Recreating or overwriting `/run/sealai-gates/gate-08-dr.json` cannot satisfy
the later wrapper because its approval digest must still match byte-for-byte.

```bash
/usr/bin/python3 -I /usr/local/libexec/sealai/dr_recovery.py verify-offsite-receipt \
  --root /var/lib/sealai-dr/drills/<drill>/var/lib/sealai-dr/sets/<set-id> \
  --receipt /var/lib/sealai-dr/receipts/<set-id>/<offsite-local-evidence>.json \
  --gate-receipt /run/sealai-gates/gate-08-dr.json \
  --imported-receipt /var/lib/sealai-dr/imported-receipts/<receipt-id>.dsse.json \
  --trust-policy /etc/sealai/dr/receipt-trust-policy.json

/usr/bin/python3 -I /usr/local/libexec/sealai/dr_recovery.py verify-drill-receipt \
  --root /var/lib/sealai-dr/drills/<drill>/var/lib/sealai-dr/sets/<set-id> \
  --receipt /var/lib/sealai-dr/receipts/<set-id>/<restore-local-evidence>.json \
  --gate-receipt /run/sealai-gates/gate-08-dr.json \
  --imported-receipt /var/lib/sealai-dr/imported-receipts/<receipt-id>.dsse.json \
  --trust-policy /etc/sealai/dr/receipt-trust-policy.json
```

Omitting either imported record or policy blocks. A local-evidence file passed as the imported
record, a receipt for the other kind/run, a stale/revoked policy or key, insufficient signatures,
or any manifest/set/snapshot/Gate/evidence-digest mismatch blocks. Only the final wrapper `ok`
result may feed authoritative receipt status; `write-*-receipt` output never may.

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

1. fresh `GATE-08` verification bound to the exact set ID and SHA-256 of the selected Restic
   snapshot ID, before any full-data read or restore begins;
2. complete Restic repository read-data verification;
3. exact snapshot download followed by a second manifest- and snapshot-bound `GATE-08` check;
4. full `pg_dumpall` restore, V2 schema assertion, and `pg_amcheck`;
5. Qdrant snapshot recovery with checksum, exact point count, duplicate-ID detection, and exact
   tenant-count digest;
6. a second whole-set verification; and
7. Gate-08-bound `LOCAL_EVIDENCE_ONLY` records, followed by a fail-closed
   `external_attestation_required` result.

The short-lived `dr_restore_drill` gate receipt must contain `snapshot_id_sha256`, the SHA-256 of
the 64-hex Restic snapshot ID. This value is an identifier binding, not backup content. A receipt
for another set or snapshot is rejected before `restic check --read-data` can read payload bytes.

Run an explicitly selected set/snapshot with:

```bash
/usr/local/libexec/sealai/dr_restore_drill.sh <set-id> <restic-snapshot-id>
```

The monthly timer selects the newest snapshot having exactly one `set-<set-id>` tag and delegates to
that command. It still fails closed without a fresh matching Gate-08 receipt and, even after all
local checks, exits blocked because the independent signer has not produced a threshold-signed
envelope. A `restore_drill` envelope can be verified/imported by `dr_receipts.py`, but importing test
or locally generated evidence is forbidden and no repository command can sign it.
Installation and timer activation are external and gated; repository presence and local evidence
are not proof that a verified drill ran. Restored plaintext under `/var/lib/sealai-dr/drills/` must
be retained only until an external evidence workflow is reviewed, then deleted as the exact drill
directory under a separately reviewed runner-local retention job. Never run the drill on the VPS.

For `mode=postgres_rebuild`, use only the candidate workflow below. Do not use ad-hoc ingestion, a
guessed collection name, direct production writes, or an in-process fallback. The restore drill
still cannot claim `qdrant_recovered=true`: its current container path verifies snapshots, while a
real-embedding rebuild and any later cutover require separate Gate-08 evidence.

## Canonical Postgres-to-Qdrant candidate rebuild

`backend/sealai_v2/knowledge/qdrant_rebuild.py` reads Postgres in one `REPEATABLE READ`, `READ ONLY`,
`DEFERRABLE` transaction. It reuses the exact live knowledge and memory projection builders, binds
the authority sequence, source rows, tenant counts, payloads, IDs, database identity, embedder model
digest, vector size, production collection-name digest, and run-specific candidate names. Snapshot,
plan, imported approval, and journal files are private canonical JSON. A run ID is single-use.
The plan explicitly binds both collections to the named dense-vector-only schema used by current
defaults. If the approved runtime has hybrid/sparse knowledge enabled, stop: this implementation
rejects that schema and must be extended/reviewed before the run rather than silently dropping the
sparse projection.

The module intentionally contains no alias, collection rename, delete, or cutover function. It
creates only absent `sealai-dr-<run-id>-knowledge` and `sealai-dr-<run-id>-memory` collections and
refuses to adopt an existing collection. Partial candidates are retained for investigation; retry
with a newly approved run ID rather than deleting or reusing them.

The offline example path is restricted to a loopback Qdrant endpoint, requires
`--ephemeral-only`, uses the fixed deterministic fake-model digest
`sha256("sealai-local-fake-embedder-v1")`, and is never production evidence. A plan for a real run
uses `embedder_kind=runtime_external`; execution must inject an approved adapter exposing the exact
`model_id_sha256` from the plan and `dr_rebuild_admission_verified=true` only after the reviewed
budget/rate/concurrency admission wrapper is active. Passing the ordinary runtime embedder directly
fails before provider access. The repository CLI deliberately cannot construct that paid/external
adapter, so provider selection, cost approval, and the real run remain external Gate-08 work.

Prepare a private working and journal directory, capture the canonical plan from the restored
Postgres, and submit the emitted plan hash plus candidate-name hash for the independent
`qdrant_rebuild_approval` DSSE envelope:

The digest-pinned verifier container must receive the reviewed root-owned `dr_receipts.py` read-only
at `/opt/dr/dr_receipts.py`; the rebuild loader rejects symlinks, writable files, hardlinks, and
untrusted ownership. The database URL, private artifacts, and journal need separately scoped
read/write mounts. These mounts are part of the Gate-08 command manifest, not inherited ad hoc.

```bash
install -d -m 0700 /var/lib/sealai-dr/rebuild /var/lib/sealai-dr/rebuild-journal
# Run inside the digest-pinned backend verifier image, whose WORKDIR is /app.
/usr/local/bin/python -m sealai_v2.knowledge.qdrant_rebuild capture-plan \
  --snapshot /var/lib/sealai-dr/rebuild/<run-id>.snapshot.json \
  --plan /var/lib/sealai-dr/rebuild/<run-id>.plan.json \
  --run-id <run-id> --created-at <UTC-RFC3339> \
  --embedder-kind runtime_external --model-id-sha256 <approved-model-digest> \
  --vector-size <exact-dimension> --passage-prefix 'passage: ' \
  --production-collection sealai_v2_knowledge_v1 \
  --production-collection sealai_v2_memory
```

`capture-plan` reads the database URL only from the named environment variable and never prints it.
The approval subject is exactly `gate_id=GATE-08`, the plan SHA-256, snapshot SHA-256, and candidate
collection-name SHA-256. Import it with `dr_receipts.py --kind qdrant_rebuild_approval`; an unsigned,
locally edited, expired, replayed, wrong-plan, or wrong-role approval fails before Qdrant access.

After candidate construction, capture a second read-only snapshot to a new file:

```bash
/usr/local/bin/python -m sealai_v2.knowledge.qdrant_rebuild capture-snapshot \
  --snapshot /var/lib/sealai-dr/rebuild/<run-id>.current.json \
  --captured-at <later-UTC-RFC3339>
```

Verification rejects the original snapshot reused as “current,” a different database identity,
authority/row drift, missing or extra IDs, payload drift, tenant-count drift, missing/non-finite or
wrong-size dense vectors, and any candidate name that is a production collection. A passing result
is only `CANDIDATES_VERIFIED_NO_CUTOVER`. Separately test tenant-filtered retrieval and compare
semantic samples under a new Gate-08 request. No command in this package authorizes an alias switch
or deletion of either old or candidate collections.

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
component, so partial exporter state cannot look healthy. `LOCAL_EVIDENCE_ONLY` must leave
`sealai_backup_receipt_valid` at `0`. The import/consumption code exists, but production trust-root
provisioning, external signing, import execution, status publication after wrapper success, and
external alert delivery remain `BLOCKED_EXTERNAL`.

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
