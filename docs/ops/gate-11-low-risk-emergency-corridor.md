# GATE-11: scoped low-risk emergency corridor

Status: **additive to the GATE-10 freeze, not a replacement**. Owner decision, 2026-07-18
(GATE-10 consolidation plan). `P0_SECRETS_CONTAINED` / `P0_STORAGE_STABLE` / `P0_REDIS_STABLE` /
`RELEASE_GATE_FAIL_CLOSED` remain required, unchanged, for any full/final release. GATE-11 exists
only for a narrow class of deploys while those four conditions are still being worked on.

## Why this exists

The GATE-10 freeze correctly blocks every deploy — including a pure documentation fix (PR #312 in
the routing audit) — until the full exact-artifact-attestation contract (P1) is built. That
blanket behavior has already caused real friction unrelated to the actual P0 risks (leaked
secrets, disk capacity, Redis memory pressure): a legitimate, fully-tested, fully-reviewed change
had no path to production at all. GATE-11 is a narrow, fail-closed exception for exactly that
situation — never a general deploy path.

## What qualifies (all of the following, every time)

1. The diff between `base_git_sha` and `source_git_sha` does **not** touch any path matching
   `production_release_gate.py::GATE11_EXCLUDED_PATH_PREFIXES` (currently: `ops/`,
   `.github/workflows/`, `.claude/`, any `docker-compose*` file, `backend/sealai_v2/config/settings.py`,
   `backend/sealai_v2/security/`, `backend/sealai_v2/core/output_guard.py`,
   `backend/sealai_v2/db/migrations/`, any Dockerfile, `keycloak/`). **The gate checks this itself**
   via `git diff --name-only` — it never trusts the approval document's own claim about what
   changed.
2. The full backend + frontend test suite passes (literal, verbatim runner output — not a
   paraphrase), and its SHA-256 is bound into the approval.
3. **The owner has personally read the diff** — `owner_read_diff_confirmation` must be literally
   `true`. No agent ever sets this field to `true` on the owner's behalf.
4. A short-lived (≤ 4 hours), root-owned approval receipt exists at
   `/etc/sealai/approvals/gate-11-low-risk-emergency.json`, mode `0600`, matching
   `ops/schemas/gate11-low-risk-emergency.schema.json`.

## What never qualifies, regardless of the diff

Anything under the excluded-path list above — most importantly the release-gate code itself
(`ops/production_release_gate.py`, `ops/production-release-gate-check.sh`), so this corridor can
never be used to widen or disable itself.

## Creating the approval (owner-run, never agent-run)

```bash
# 1. Confirm you are on the exact commit you intend to deploy, and that it is clean.
cd /home/thorsten/sealai
git status --porcelain   # must be empty
SOURCE_SHA="$(git rev-parse HEAD)"

# 2. Pick the base commit the diff is measured against -- typically what origin/main's
#    tip was before this change landed.
BASE_SHA="<commit sha before this change>"
git merge-base --is-ancestor "$BASE_SHA" "$SOURCE_SHA" && echo "base is a real ancestor"

# 3. Review the diff yourself. Do not skip this.
git diff --stat "$BASE_SHA" "$SOURCE_SHA"

# 4. Run the full test suite yourself (or paste CI's literal output) and hash it.
#    Example (adjust to whichever suite(s) the diff actually touches):
python3 -m pytest backend/sealai_v2/tests > /tmp/gate11-test-evidence.txt 2>&1
cat /tmp/gate11-test-evidence.txt   # read it -- must show 0 failures
TEST_SHA="$(sha256sum /tmp/gate11-test-evidence.txt | cut -d' ' -f1)"

# 5. Write the approval (root-owned, 0600, mode matches every other GATE receipt).
sudo mkdir -p /etc/sealai/approvals
sudo tee /etc/sealai/approvals/gate-11-low-risk-emergency.json > /dev/null <<JSON
{
  "schema_version": 1,
  "gate_id": "GATE-11",
  "decision": "APPROVED",
  "scope": "low-risk-emergency-deploy",
  "approval_id": "gate11-$(date -u +%Y%m%d-%H%M%S)",
  "approved_by": "thorsten",
  "approved_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "expires_at": "$(date -u -d '+2 hours' +%Y-%m-%dT%H:%M:%SZ)",
  "base_git_sha": "${BASE_SHA}",
  "source_git_sha": "${SOURCE_SHA}",
  "owner_read_diff_confirmation": true,
  "test_evidence_sha256": "${TEST_SHA}"
}
JSON
sudo chown root:root /etc/sealai/approvals/gate-11-low-risk-emergency.json
sudo chmod 0600 /etc/sealai/approvals/gate-11-low-risk-emergency.json

# 6. Verify the gate actually accepts it (read-only check, no deploy yet):
/usr/bin/env -i HOME=/nonexistent PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C LC_ALL=C \
  /usr/bin/python3 -I ops/production_release_gate.py check low-risk-emergency-deploy
```

## Rollback

Delete the receipt: `sudo rm -f /etc/sealai/approvals/gate-11-low-risk-emergency.json`. No
schema migration, no service restart, no other state to unwind — the gate falls back to denying
`low-risk-emergency-deploy` exactly like every other mutating operation under GATE-10.

## Deliberately not built in this pass

Wiring `low-risk-emergency-deploy` into `ops/release-backend-v2.sh` as a `--low-risk-emergency`
release stage is a follow-up, not part of this change. That script's full image-build, SBOM,
smoke-test, and rollback-ledger machinery deserves its own careful read before being extended;
this pass only adds the gate-check primitive and proves it independently (`ops/production_release_gate.py`
+ `ops/production-release-gate-check.sh` + tests).
