# Immutable dashboard releases

This contract replaces the mutable `frontend-v2/dist` production target. It prepares verifiable
artifacts locally; it does not authorize or perform a deployment.

## State and trust boundary

```text
clean source commit
  -> two clean, deterministic candidate builds
  -> canonical file inspection (sorted paths, size, SHA-256)
  -> immutable artifacts/<commit>-<artifact-sha256>/
  -> GATE-08 verifies the exact release and atomically replaces current
  -> rollback atomically restores the previously verified target
```

Production Nginx bind-mounts the fixed root-owned
`/var/lib/sealai/dashboard-releases` directory itself at
`/usr/share/nginx/dashboard-releases:ro`. It does not bind-mount `current` as the mount source; this
is important because replacing a host-side symlink source would not retarget an existing bind mount.
Nginx serves only `/usr/share/nginx/dashboard-releases/current/`.

The generated layout is:

```text
dashboard-releases/
  artifacts/
    <40-or-64-hex-commit>-<64-hex-artifact-digest>/
      index.html
      assets/...
      release.json
  current  -> artifacts/<verified-release-id>   # GATE-08 only
  rollback -> artifacts/<previous-release-id>   # GATE-08 only
```

Payload files and `release.json` are mode `0444`; all release directories are `0555`. The root and
`artifacts` directory remain owner-writable only so a controlled publisher can add a new,
content-addressed directory. Existing releases are never updated.

## Reproducible preparation

Prerequisites are a clean committed `frontend-v2` tree, the exact Node/npm versions in
`.node-version` and `.npm-version`, Python 3, and a local build host that is not
`/home/thorsten/sealai`. Run:

```bash
cd frontend-v2
npm run release:prepare
```

The wrapper:

1. refuses arguments, a dirty frontend tree, any Vite `.env*` file, the production repository path,
   or a Node/npm version drift (the clean build environment contains no `VITE_*` secrets);
2. records the exact Git commit and its commit timestamp as `SOURCE_DATE_EPOCH`;
3. hashes `package-lock.json` and performs `npm ci --ignore-scripts`;
4. builds twice into `.build/dashboard-candidate` with UTC/C locale and an otherwise minimal
   environment;
5. compares canonical inspections of both builds byte-for-byte;
6. rechecks source cleanliness and the lockfile digest; and
7. creates the immutable release without touching `current` or `rollback`.

The artifact digest is SHA-256 over canonical JSON containing the schema version, source commit,
source epoch, lockfile SHA-256, exact Node/npm versions, and the sorted payload records
`{path,size,sha256}`. `release.json` is generated after this calculation to avoid a self-referential
hash; all identity fields it contains are recomputed during verification.

## Verification and read-only plans

These commands are local/read-only except `prepare`, which can add one inert release directory:

```bash
python3 -I frontend-v2/scripts/dashboard_release.py verify \
  --release "$PWD/frontend-v2/dashboard-releases/artifacts/<release-id>"

python3 -I frontend-v2/scripts/dashboard_release.py plan-activate \
  --release-root "$PWD/frontend-v2/dashboard-releases" \
  --release-id '<release-id>'

python3 -I frontend-v2/scripts/dashboard_release.py plan-rollback \
  --release-root "$PWD/frontend-v2/dashboard-releases"
```

There is intentionally no `activate`, `apply`, or `rollback --apply` CLI. Plans report
`mutation_performed:false` and `gate_required:GATE-08`. The tested atomic link primitive is reserved
for the separately installed production-deployment executor after it has validated the exact gate
approval, release ID, commit, digest, host, release-root identity, global release/storage locks, and
freeze state.

## GATE-08 activation and rollback contract

The installed production executor fails closed and performs this ordered transaction while holding
its deployment lock:

1. verify the requested immutable directory and canonical manifest;
2. verify and snapshot the existing relative `current` and `rollback` targets;
3. atomically set `rollback` to the verified old `current` when one exists;
4. atomically replace `current` with a newly created relative symlink to the requested release;
5. fsync the release-root directory and re-verify the now-current manifest; and
6. record the before/after release IDs, commits, and artifact digests in gate evidence.

Rollback snapshots both targets before mutation, atomically moves `rollback` to the old current,
atomically moves `current` to the snapshotted rollback target, fsyncs, then verifies. If execution
stops between link replacements, the previously live release remains live; a partially populated
candidate is never referenced.

Removing old releases is not part of preparation, activation, or rollback. Retention cleanup needs
its own evidence and must never remove either link target.

## Safety checks and expected failures

The preparer/verifier rejects non-absolute or overlapping roots, symlinked roots or intermediate
paths, hard-linked or group/world-writable payload files, changed inodes/size/mtime during reads,
unexpected files or directories, mutable releases, noncanonical/duplicate manifest paths, unsafe
link targets, oversized trees, and publication collisions. Errors use stable reason codes and never
print candidate paths or file content.

Local verification:

```bash
npm --prefix frontend-v2 run verify
python3 -m pytest -q backend/tests/test_dashboard_immutable_release.py
bash -n frontend-v2/scripts/prepare-dashboard-release.sh
docker compose -f docker-compose.deploy.yml config --no-interpolate >/dev/null
docker compose -f ops/staging/docker-compose.staging.yml config --no-interpolate >/dev/null
```
