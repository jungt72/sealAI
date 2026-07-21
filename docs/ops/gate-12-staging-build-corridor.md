# GATE-12: scoped staging-build corridor

Status: **additive to the GATE-10 freeze, not a replacement**. Owner decision, 2026-07-20.
`P0_SECRETS_CONTAINED` / `P0_STORAGE_STABLE` / `P0_REDIS_STABLE` / `RELEASE_GATE_FAIL_CLOSED`
remain required, unchanged, for any full/final release. GATE-12 exists only to unblock rebuilding
the local, non-production **staging** stack while those four conditions are still being worked on.
It authorizes nothing production-facing: never `deploy`, `pull`, `migration`, or
`dashboard-publish`, only the single `staging-build` operation.

## Why this exists

The GATE-10 freeze also blocks `ops/staging/up-staging-v2.sh`, which calls the same gate with
`operation=build` — there was no exception for it, so the staging container (`backend-v2-staging`,
port 8443, `APP_ENV=staging`) had gone 12 days without a successful rebuild, identical to CI's
frozen `build-and-push` workflow. That leaves no way to see any code change running anywhere, not
even in a sandbox with no production exposure. GATE-11 (the existing low-risk-emergency corridor)
was considered first for this, but it only unlocks the `deploy` operation and its approval receipt
is root-owned on the VPS — a GitHub-hosted CI build could never reach it. The staging build runs
entirely on the VPS host, in the same trust context the receipt already lives in, so a narrow,
GATE-11-shaped exception for exactly this one local operation closes the gap without touching
production risk at all.

## What qualifies (all of the following, every time)

1. **The owner has personally read the diff** — `owner_read_diff_confirmation` must be literally
   `true`. No agent ever sets this field to `true` on the owner's behalf.
2. A short-lived (≤ 4 hours) approval receipt exists at
   `/etc/sealai/approvals/gate-12-staging-build.json`, mode `0600`, matching
   `ops/schemas/gate12-staging-build.schema.json`. **Owned by whichever host user runs
   `ops/staging/up-staging-v2.sh` (never root)** — see the 2026-07-21 correction below; this
   differs from GATE-08/10/11's own approval receipts, which really are root-owned because those
   corridors really do run as root.
3. `base_git_sha` is an ancestor of `source_git_sha`, `source_git_sha` equals the current
   checkout's `HEAD`, and the diff between them is non-empty. **The gate checks this itself** via
   `git diff`/`git merge-base` — it never trusts the approval document's own claim about what
   changed.

### Owner decision, 2026-07-21: no more path exclusion

Until 2026-07-21, requirement 1 above also required the diff to avoid
`production_release_gate.py::GATE11_EXCLUDED_PATH_PREFIXES` (`ops/`, `.github/workflows/`, etc.) —
the same list GATE-11 uses. In practice this meant almost no real rebuild could ever qualify:
`ops/`-touching work is most of this repo's release-engineering activity, and staging went stale
for well over a week as a direct result, with no way to see *any* accumulated work running
anywhere, not even in a sandbox.

GATE-11's exclusion exists because that corridor authorizes a real *production* deploy through a
narrow path — letting it also approve changes to the gate itself would let a narrow exception
silently widen its own authority. That risk does not apply here: GATE-12 authorizes nothing
production-facing at all, the code it rebuilds already passed the normal branch/PR/CI/merge review
to reach `main`, and staging (`backend-v2-staging`, `nginx-staging` on a separate port) carries
zero production traffic. The exclusion was inherited from GATE-11 for free, never re-derived for
GATE-12's actually much lower stakes. It has been removed from GATE-12's validation
(`_validate_staging_build_approval`); GATE-11's own copy of the list and its own validation
function are completely unaffected.

Unlike GATE-11, no `test_evidence_sha256` is required — this builds a non-production sandbox for
manual inspection, not a release.

### Owner-observed, 2026-07-21: the approval receipt is self-owned, not root-owned

This corridor's first real non-root end-to-end run (after the path-exclusion relax above)
surfaced two more gaps, both now fixed:

- `_validate_staging_build_approval` called `_assert_trusted_path(..., root_only=True)`, requiring
  the receipt be owned by uid 0. `up-staging-v2.sh` runs with no `sudo` anywhere in it, by design
  (see "Why this exists" above) — so its receipt is written and read by that same unprivileged host
  user, never root. That directly contradicted `_load_private_json`'s own check two lines later
  (which already only requires the file's owner match the calling process's uid) and could never
  both pass for a non-root caller. Fixed in `production_release_gate.py`
  (`fix/gate12-non-root-approval-ownership`, merged): the leaf receipt now only needs to be owned
  by uid 0 **or** the calling process's own uid; the directory chain above it is still required to
  be root-owned, unchanged.
- `backend/Dockerfile.v2` had, by then, grown a mandatory `GATE_TREE_HASH`/`SOURCE_GIT_SHA`
  build-arg requirement (GATE-10 P1 image attestation) that `up-staging-v2.sh` never learned to
  pass — fixed (`fix/staging-build-identity-args`, merged): the script now computes both via
  `ops/tree-hash.sh` + `git rev-parse HEAD`, matching `ops/release-backend-v2.sh`/`ops/run_eval.sh`.

Because the receipt is self-owned, the host user also needs plain traversal into
`/etc/sealai/approvals/` — see the updated "Creating the approval" section below for the one-time
setup this requires.

## What never qualifies, regardless of the diff

Anything under the excluded-path list above — most importantly the release-gate code itself
(`ops/production_release_gate.py`, `ops/production-release-gate-check.sh`) and, since that list
excludes `ops/` wholesale, `ops/staging/*` too — so this corridor can never be used to widen or
disable itself, or to quietly change how it builds. Testing a change to the staging harness itself
is a manual, ungated action the owner takes directly, outside this corridor, exactly like GATE-11's
own treatment of anything on its excluded list.

## Prerequisites this gate does not solve

GATE-12 only removes the release-freeze blocker. As of 2026-07-21, a real end-to-end
`./ops/staging/up-staging-v2.sh` run succeeded and produced two healthy containers
(`backend-v2-staging`, `nginx-staging`); everything below reflects what that run actually needed,
not just design-time guesses:

- **`/usr/local/libexec/sealai/production-storage-lease.sh` must be installed** (via
  `ops/install-disk-guard.sh`, a separate GATE-08 root-run bootstrap — owner-run, not covered here).
  Resolved on this VPS as of the GATE-08 disk-guard install; the 2026-07-21 run acquired the lease
  without incident.
- **The checked-in `ops/staging/conf/` output** was still consistent with `ops/staging/
  gen-staging-conf.sh`'s regeneration as of 2026-07-21 (`git status` showed no diff after
  regenerating) — the "predates recent nginx changes" concern from 2026-07-20 no longer applied by
  the time this corridor was actually exercised. Re-run the generator yourself if you've since
  touched `nginx/default.conf` and want to be sure.
- **One-time host setup for the self-owned receipt** (see the correction above): the invoking user
  needs plain traversal into the approval directory, since it is root-owned:
  ```bash
  sudo chgrp sealai /etc/sealai /etc/sealai/approvals
  sudo chmod 0710 /etc/sealai /etc/sealai/approvals   # execute-only for the group -- no listing
  ```
  This does not expose GATE-08's own two root-only (`0600`) receipts that live in the same
  directory — only traversal changed, not their individual file permissions. Already done on this
  VPS; a fresh host would need it once, before the first GATE-12 approval is ever written.
- **`backend/Dockerfile.v2`'s `docker-entrypoint-v2.sh` must be mode `755`** in the live checkout
  (git tracks it as `100755`, but this VPS's working-tree copy had drifted to `0700` at some point
  — invisible to `git status`/`git diff`, since git only tracks the owner-executable bit, not
  group/other permissions). A `0700` entrypoint gets baked into the image with `COPY` +
  `chmod +x` still leaving group/other execute without read (`-rwx--x--x`), which
  `appuser` (the image's non-root runtime user) cannot even open to interpret its shebang line --
  `backend-v2-staging` then crash-loops with `cannot open ... Permission denied`. Fix:
  `chmod 755 backend/docker-entrypoint-v2.sh`, then rebuild. Since this affects the shared
  Dockerfile, it would equally break a real production `backend-v2` rebuild off the same checkout,
  not just staging.

## Creating the approval (owner-run, never agent-run)

```bash
# 1. Confirm you are on the exact commit you intend to build, and that it is clean.
cd /home/thorsten/sealai
git status --porcelain   # must be empty
SOURCE_SHA="$(git rev-parse HEAD)"

# 2. Pick the base commit the diff is measured against -- typically what origin/main's
#    tip was before this change landed.
BASE_SHA="<commit sha before this change>"
git merge-base --is-ancestor "$BASE_SHA" "$SOURCE_SHA" && echo "base is a real ancestor"

# 3. Review the diff yourself. Do not skip this.
git diff --stat "$BASE_SHA" "$SOURCE_SHA"

# 4. Write the approval -- owned by YOU (the user who runs up-staging-v2.sh), never root.
#    First time on a fresh host: the one-time directory setup in "Prerequisites" above must
#    already be done, or this tee will fail to reach the directory at all.
tee /etc/sealai/approvals/gate-12-staging-build.json > /dev/null <<JSON
{
  "schema_version": 1,
  "gate_id": "GATE-12",
  "decision": "APPROVED",
  "scope": "staging-build",
  "approval_id": "gate12-$(date -u +%Y%m%d-%H%M%S)",
  "approved_by": "thorsten",
  "approved_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "expires_at": "$(date -u -d '+4 hours' +%Y-%m-%dT%H:%M:%SZ)",
  "base_git_sha": "${BASE_SHA}",
  "source_git_sha": "${SOURCE_SHA}",
  "owner_read_diff_confirmation": true
}
JSON
chmod 0600 /etc/sealai/approvals/gate-12-staging-build.json

# 5. Verify the gate actually accepts it (read-only check, no build yet):
/usr/bin/env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C LC_ALL=C \
  /usr/bin/python3 -I ops/production_release_gate.py check staging-build

# 6. Run the staging build.
./ops/staging/up-staging-v2.sh
```

Every subsequent approval refresh is exactly this recipe again with a fresh `SOURCE_SHA` (whatever
`HEAD` currently is) and a `BASE_SHA` of your choosing -- typically the previous approval's
`SOURCE_SHA`, so the diff you review is exactly what changed since the last approved build.

## Rollback

Delete the receipt: `rm -f /etc/sealai/approvals/gate-12-staging-build.json` (no `sudo` needed --
it's your own file). No schema migration, no service restart, no other state to unwind — the gate
falls back to denying `staging-build` exactly like every other mutating operation under GATE-10.

## Deliberately not built in this pass

No bridge from this VPS-local, root-owned approval into GitHub-hosted CI — that would be a real
cross-system trust design question, and the owner explicitly chose not to build one now
(2026-07-19, "vorerst gar nicht"). GATE-12 stays purely local to the VPS, same trust boundary the
receipt already lives in.
