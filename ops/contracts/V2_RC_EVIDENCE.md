# V2 production-RC evidence contract

Production authorization uses two non-circular artifacts: a canonical pre-eval
RC descriptor recorded in `results.json`, then a canonical post-adjudication
promotion manifest that embeds the descriptor and the exact `results_sha256`.
Gate 10 approves the promotion-manifest bytes. Either payload self-hash is only
an integrity check; it is never an approval or signature.

## Lane boundary

The current `ops/run_eval.sh` / staging Compose lane is intentionally
`RC_STUB_NON_ELIGIBLE`. It uses stub model IDs and a locally built Docker `.Id`,
and it does not set a canonical `SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH`. That lane
may produce runtime/safety diagnostics only. It cannot create a
promotion-authorizing manifest because `release_candidate_evidence` remains
`null`; if a binding is supplied anyway, the eval CLI rejects the lane class.

A production-eligible lane must set
`SEALAI_EVAL_EVIDENCE_CLASS=PRODUCTION_RC_ELIGIBLE` and evaluate the immutable
registry candidate approved by Gate 10. `candidate_image_digest` means exactly
Gate 10's `release_hashes.backend_image_digest` (the OCI registry manifest
digest), never a local Docker image/config ID.

The sanctioned runner must pull the Gate-10 digest-pinned registry reference,
verify that digest in `RepoDigests`, derive its local image-config digest, start
the container from that exact reference, and verify the container's `.Image`
equals the derived config digest. Only then may it export both measured values
to the eval. An environment label alone is not this proof.

## Canonical descriptor schema

`ops/v2_rc_evidence.py create` writes schema v1 as ASCII JSON with sorted keys,
no insignificant whitespace, and exactly one trailing newline. It refuses to
overwrite an existing path. The schema binds:

- Gate-10 OCI backend image manifest digest;
- local OCI image-config digest derived from that digest-pinned manifest;
- full Gate-10-approved source Git SHA;
- canonical served-tree SHA-256;
- Gate-10 database/Alembic migration digest;
- canonical `sha256:...` Authority Epoch;
- the complete secret-free runtime profile and its recomputed SHA-256;
- `retriever.backend=qdrant`, `fallback_allowed=false`, and
  `ground_enabled=true` in the runtime profile;
- an isolated Postgres database name and snapshot SHA-256;
- an isolated Qdrant RC collection name and snapshot SHA-256.
- scoped API-key authentication for the isolated Qdrant service (the key value
  is required at runtime but never enters either evidence file).

Unknown/missing keys, duplicate JSON keys, zero/noncanonical hashes, symlinks,
oversized files, noncanonical byte serialization, profile drift, in-process
retrieval, and Authority-Epoch/collection drift are rejected.

Creation contract (all values must already have been independently measured):

```sh
/usr/bin/python3 -I ops/v2_rc_evidence.py create \
  --output "$RC_DESCRIPTOR_FILE" \
  --candidate-image-digest "$GATE10_BACKEND_IMAGE_DIGEST" \
  --candidate-image-config-digest "$CANDIDATE_IMAGE_CONFIG_DIGEST" \
  --served-tree-sha256 "$GATE10_SERVED_TREE_SHA256" \
  --database-migration-sha256 "$GATE10_DATABASE_MIGRATION_SHA256" \
  --authority-epoch "$AUTHORITY_EPOCH" \
  --postgres-database "$RC_POSTGRES_DATABASE" \
  --postgres-snapshot-sha256 "$RC_POSTGRES_SNAPSHOT_SHA256" \
  --qdrant-collection "$RC_QDRANT_COLLECTION" \
  --qdrant-snapshot-sha256 "$RC_QDRANT_SNAPSHOT_SHA256" \
  --runtime-profile-file "$RC_RUNTIME_PROFILE_JSON" \
  --source-git-sha "$GATE10_SOURCE_GIT_SHA"
```

Generate the eval-side binding from the exact descriptor:

```sh
/usr/bin/python3 -I ops/v2_rc_evidence.py verify \
  "$RC_DESCRIPTOR_FILE" \
  > "$RC_BINDING_FILE"
```

The eligible eval process receives the binding file plus these exact values:

```text
SEALAI_EVAL_EVIDENCE_CLASS=PRODUCTION_RC_ELIGIBLE
SEALAI_EVAL_RC_BINDING_FILE=<read-only canonical binding file>
SEALAI_EVAL_RC_DESCRIPTOR_SHA256=<exact pre-eval descriptor SHA-256>
SEALAI_EVAL_IMAGE_DIGEST=<Gate-10 backend_image_digest, registry manifest>
SEALAI_EVAL_IMAGE_CONFIG_DIGEST=<config digest verified on the started container>
SEALAI_EVAL_SERVED_TREE_SHA256=<Gate-10 served_tree_sha256>
SEALAI_EVAL_DATABASE_MIGRATION_SHA256=<Gate-10 database_migration_sha256>
SEALAI_RC_POSTGRES_SNAPSHOT_SHA256=<attested isolated snapshot SHA-256>
SEALAI_RC_QDRANT_SNAPSHOT_SHA256=<attested isolated snapshot SHA-256>
SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH=<same canonical Authority Epoch>
SEALAI_EVAL_GIT_SHA=<full Gate-10-approved source Git SHA>
```

The executing Settings must use exactly
`postgresql+psycopg2://sealai_rc_eval:<secret>@rc-postgres:5432/<bound-db>`
without query/fragment and exactly `http://rc-qdrant:6333`. Qdrant grounding,
the bound collection, a non-empty scoped printable RC API key, and the embedded
runtime-profile hash are mandatory. Key/credential values never enter evidence.
The source must be clean (`dirty=false`). The harness records the descriptor at
`manifest.release_candidate_evidence`.

After complete replay and final adjudication, create the non-circular promotion
manifest:

```sh
/usr/bin/python3 -I ops/v2_rc_evidence.py finalize \
  --output "$RC_PROMOTION_EVIDENCE_FILE" \
  --rc-descriptor "$RC_DESCRIPTOR_FILE" \
  --run-label "$RUN_LABEL" \
  --results-file "$RUNS_DIR/$RUN_LABEL/results.json"
```

`finalize` refuses a results file that does not carry the exact descriptor
binding. Gate 10 must set `release_hashes.evidence_manifest_sha256` to the SHA-256
of this final promotion manifest, not the pre-eval descriptor.

## Production gate CLI

The production caller must supply all arguments; four legacy arguments alone
always fail:

```sh
/usr/bin/python3 -I ops/v2_deploy_gate.py \
  "$RUNS_DIR" "$TREE_HASH" "$SERVED_L1" "$RUNTIME_PROFILE_SHA256" \
  --rc-evidence "$RC_PROMOTION_EVIDENCE_FILE" \
  --rc-evidence-sha256 "$GATE10_EVIDENCE_MANIFEST_SHA256" \
  --candidate-image-digest "$GATE10_BACKEND_IMAGE_DIGEST" \
  --candidate-image-config-digest "$CANDIDATE_IMAGE_CONFIG_DIGEST" \
  --served-tree-sha256 "$GATE10_SERVED_TREE_SHA256" \
  --database-migration-sha256 "$GATE10_DATABASE_MIGRATION_SHA256" \
  --authority-epoch "$AUTHORITY_EPOCH" \
  --source-git-sha "$GATE10_SOURCE_GIT_SHA"
```

The gate loads and canonicalizes the file, checks the external Gate-10 byte
hash, compares every current candidate input, opens only the exact run named by
the promotion manifest, verifies its raw `results_sha256`, requires the exact
descriptor, clean source, and then applies complete/full/final clean-replay
adjudication. It never falls back to globbing another run. Old artifacts,
`release_candidate_evidence=null`, targeted or
chained remediation, provisional adjudication, and owner waivers cannot
authorize promotion.

## Deliberately external prerequisites

This pure-stdlib contract does not start containers, call providers, inspect a
registry, create snapshots, compute the Authority Epoch, or decide human
adjudication. The eligible runner/release integration must independently prove:

- the digest-pinned pull/RepoDigests/config-ID/container-ID chain described above;
- that the canonical served-tree digest describes that image;
- the canonical Alembic/migration digest algorithm and its Gate-10 value;
- non-empty, sanitized, isolated Postgres/Qdrant snapshots and their attestations;
- the Authority Epoch of the exact approved knowledge state;
- real-provider/full-suite execution and final human adjudication.

Changing any approved input requires a new evidence file, new Gate-10 file
hash, and new complete final replay.
