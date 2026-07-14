# Isolated RC evaluation and staging contract

Status: **BLOCKED_EXTERNAL**. The repository-side isolation and fail-closed
contracts exist, but no run is eligible until an independent process supplies
and attests sanitized snapshots, immutable stub images, and local TLS fixtures.
The deterministic stub lane is intentionally **never production evidence**.

## Security boundary

`ops/run_eval.sh` and `ops/staging/up-staging-v2.sh` read only
`ops/staging/rc.env`. `ops/staging/rc-contract.sh` treats that file as literal
data rather than shell code, requires owner-only mode `0400` or `0600`, rejects
unknown/duplicate/empty keys, and rejects inherited serving, provider, Docker,
and Compose variables. In particular, neither entrypoint reads `.env.prod`, and
production provider/database credentials are not accepted as RC inputs.
Both entrypoints resolve the checkout through `pwd -P` and reject the known live
checkout `/home/thorsten/sealai` and every path beneath it before any Docker
access. The stub lane therefore cannot bypass the production freeze from the
production checkout.

Docker Compose receives a clean process environment plus the validated RC file.
It uses four `internal: true` networks:

- `rc_edge`: loopback-bound Nginx, the candidate backend, and non-production
  frontend/auth stubs;
- `rc_postgres`: only the candidate backend/evaluator and Postgres;
- `rc_qdrant`: only the candidate backend/evaluator and Qdrant;
- `rc_provider`: only the candidate backend/evaluator and deterministic LLM
  stub.

There is no external or production Docker network. Nginx cannot reach the data
services, data services publish no host ports, and the only published port is
`127.0.0.1:8443`. Production certificate, ACME, database, Qdrant, frontend, and
other host paths are not mounted.

## RC input file

Create the private file from the deliberately blocked example, replace every
placeholder with independently verified RC-only values, and lock its mode:

```bash
install -m 600 ops/staging/rc.env.example ops/staging/rc.env
${EDITOR:?set EDITOR} ops/staging/rc.env
./ops/staging/rc-contract.sh eval
```

The final command performs only local file/contract checks. `staging` mode also
requires non-production web-stub images and complete local TLS fixtures.
Secret values are never printed on failure.

## Snapshot contract

Compose declares both snapshot volumes as `external: true`; it therefore cannot
create a blank Postgres or Qdrant store. Their names are derived, not supplied:

```text
sealai-rc-postgres-<RC_POSTGRES_SNAPSHOT_SHA256>
sealai-rc-qdrant-<RC_QDRANT_SNAPSHOT_SHA256>
```

Before either sanctioned entrypoint can build or create a container, each
volume must exist and carry all three exact labels:

```text
io.sealai.rc.kind                 = postgres | qdrant
io.sealai.rc.snapshot-sha256      = <matching 64-hex hash>
io.sealai.rc.seed-status          = READY
```

The independent seeder must attest that it copied rather than mounted a
production data path, sanitized regulated/customer data as required, rotated
the database login to the RC-only credential, restored at least two Postgres
application tables, restored both configured Qdrant collections, and verified
at least one point in the knowledge collection. It must also supply the
canonical non-zero `RC_AUTHORITY_EPOCH=sha256:<64hex>` bound to those snapshots;
the RC scripts never derive it from a production environment file. Compose
passes that exact value as `SEALAI_V2_KNOWLEDGE_AUTHORITY_EPOCH`. Until that
seeder and its evidence exist, `RC_DATA_SEED_STATUS` remains `BLOCKED_EXTERNAL`.

## Stub-provider contract

The RC runtime has no provider egress. It points both OpenAI-compatible client
paths to `http://rc-llm-stub:8080/v1` on `rc_provider`, using a documented synthetic
non-secret. The immutable stub image must be local-only and expose a deterministic
OpenAI-compatible chat/embedding API plus `/health` and
`/usr/local/bin/rc-stub-healthcheck`.

Every role uses model ID `rc-stub-noneligible-v1`; embeddings use
`rc-stub-embedding-noneligible-v1`. The runtime also records evidence class
`RC_STUB_NON_ELIGIBLE`. Those deliberate runtime-profile mismatches prevent a
stub artifact from being substituted for the production-like provider evidence
required by the release gate. Until the reviewed stub images exist,
`RC_STUB_PROVIDER_STATUS` remains `BLOCKED_EXTERNAL`.

## Entrypoints and fail-closed behavior

- `./ops/run_eval.sh ...` validates the contract and volume attestations, builds
  a clean tree/Git-bound candidate, rechecks the tree after build, verifies its
  immutable image ID, resolves Compose to that ID rather than its mutable build
  tag, and starts only
  the evaluator with `--no-deps`. It never auto-creates or auto-starts missing
  data/provider dependencies. Inside the candidate image, a preflight requires
  non-empty Postgres, Qdrant mode, both Qdrant collections, a non-empty knowledge
  collection, and the local stub health endpoint before replay starts.
- `./ops/staging/up-staging-v2.sh` uses the same RC contract and additionally
  requires local non-production TLS/auth/frontend fixtures. It retains the
  release-freeze check and global storage lease, then starts only the explicitly
  profiled isolated RC services. Build and start are separate: a post-build tree
  mismatch blocks before any RC service starts; the start phase likewise uses
  the inspected immutable image ID rather than the build tag.

Any inherited production-style secret/config variable, remote Docker target,
unknown RC key, empty DB/Qdrant contract, mutable image tag, zero/missing hash,
missing/mislabeled snapshot volume, unavailable stub, or production-network
dependency blocks with exit status `78`. There is no permissive fallback to an
in-process retriever in the sanctioned RC entrypoint.

## Remaining eligibility gap

This change establishes a safe pre-eligibility lane; it does not claim the full
P1-A production release proof. Snapshot capture/seeding, immutable stub/TLS
artifacts, and a separate approved real-provider evidence lane are external
dependencies. They must be supplied and independently reviewed before the
release-control state may move beyond `BLOCKED_EXTERNAL`.
