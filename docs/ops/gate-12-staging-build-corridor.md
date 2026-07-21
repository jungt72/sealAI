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
2. A short-lived (≤ 4 hours), root-owned approval receipt exists at
   `/etc/sealai/approvals/gate-12-staging-build.json`, mode `0600`, matching
   `ops/schemas/gate12-staging-build.schema.json`.
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

## What never qualifies, regardless of the diff

Anything under the excluded-path list above — most importantly the release-gate code itself
(`ops/production_release_gate.py`, `ops/production-release-gate-check.sh`) and, since that list
excludes `ops/` wholesale, `ops/staging/*` too — so this corridor can never be used to widen or
disable itself, or to quietly change how it builds. Testing a change to the staging harness itself
is a manual, ungated action the owner takes directly, outside this corridor, exactly like GATE-11's
own treatment of anything on its excluded list.

## Prerequisites this gate does not solve

GATE-12 only removes the release-freeze blocker. Two other things independently block a working
`./ops/staging/up-staging-v2.sh` run today, found while designing this gate:

- `/usr/local/libexec/sealai/production-storage-lease.sh` does not exist on the VPS yet — only
  `docker_disk_guard.py` has been installed under `/usr/local/libexec/sealai/`. Installing it is
  `ops/install-disk-guard.sh`, itself a separate GATE-08 root-run, non-live-checkout bootstrap
  (see `docs/ops/production-release-freeze.md`'s GATE-08 section) — owner-run, not covered here.
- The checked-in `ops/staging/conf/` output predates recent `nginx/default.conf` changes.
  Re-run `ops/staging/gen-staging-conf.sh` before relying on it.

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

# 4. Write the approval (root-owned, 0600, mode matches every other GATE receipt).
sudo mkdir -p /etc/sealai/approvals
sudo tee /etc/sealai/approvals/gate-12-staging-build.json > /dev/null <<JSON
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
sudo chown root:root /etc/sealai/approvals/gate-12-staging-build.json
sudo chmod 0600 /etc/sealai/approvals/gate-12-staging-build.json

# 5. Verify the gate actually accepts it (read-only check, no build yet):
/usr/bin/env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C LC_ALL=C \
  /usr/bin/python3 -I ops/production_release_gate.py check staging-build

# 6. Run the staging build.
./ops/staging/up-staging-v2.sh
```

## Rollback

Delete the receipt: `sudo rm -f /etc/sealai/approvals/gate-12-staging-build.json`. No schema
migration, no service restart, no other state to unwind — the gate falls back to denying
`staging-build` exactly like every other mutating operation under GATE-10.

## Deliberately not built in this pass

No bridge from this VPS-local, root-owned approval into GitHub-hosted CI — that would be a real
cross-system trust design question, and the owner explicitly chose not to build one now
(2026-07-19, "vorerst gar nicht"). GATE-12 stays purely local to the VPS, same trust boundary the
receipt already lives in.
