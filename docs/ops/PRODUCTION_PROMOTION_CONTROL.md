# Root-trusted production promotion control

This is the prepared implementation contract for GATE-08 plus GATE-10. The
checked-in freeze is still active and `GATE10_LIFT_IMPLEMENTED` is still false;
therefore these controls cannot currently mutate production.

## Non-circular release sequence

1. Manually dispatch `.github/workflows/build-and-push.yml` for one full source
   SHA at that workflow run's exact `main` HEAD. The runner has no production
   environment, SSH credential, production secret or production network path.
   It builds the immutable RC before Gate 10 and publishes signed provenance
   plus SPDX SBOM for the exact registry digest.
2. Run the isolated, real-provider production-RC replay against that digest and
   finalize `promotion-evidence.json`. Stubs are never eligible. Place the
   canonical promotion file, its exact external `runs/` result and the reviewed
   rollback plan in the fixed root-owned evidence bundle:

   ```text
   /var/lib/sealai/release-evidence/promotion-evidence.json
   /var/lib/sealai/release-evidence/rollback-plan.json
   /var/lib/sealai/release-evidence/runs/<run-label>/results.json
   ```

   Every component of these paths, including the named run directory and
   `results.json`, is a real root-owned non-group/other-writable object; symlink
   indirection is denied. The result bytes must match the hash embedded in the
   Gate-10-bound promotion evidence.

3. Create the Gate-10 control commit as the single child of the source commit.
   It may change only the three fixed Gate-10 JSON documents. The manifest
   binds source, served tree, backend and frontend registry digests, database
   migration program, dashboard artifact, rollback plan and final promotion
   evidence bytes.
4. Obtain a separate, short-lived GATE-08 receipt for this one deployment. No
   receipt is generated or committed by the repository.
5. Under that approved GATE-08 command set, install the root controls and stage
   the control checkout from an already-present local repository. Staging has
   no network path and executes no candidate file. Candidate Git objects are
   exported only after dropping to `thorsten`, then imported as a root-owned
   data pack into a fresh repository; source-side Git hooks/configured upload
   commands therefore never run as root:

   ```bash
   sudo /usr/local/libexec/sealai/production_release_control.py stage \
     --source-repository /home/thorsten/sealai \
     --control-sha '<40-hex-control>' \
     --source-sha '<40-hex-source>' \
     --backend-image 'ghcr.io/jungt72/sealai-backend-v2:<tag>@sha256:<64-hex>' \
     --apply
   ```

6. Only then may the manual deploy workflow call the installed remote
   entrypoint. It performs no fetch or checkout. It validates the root-staged
   tree, Gate 10, fixed evidence, exact image and GATE-08 receipt, acquires the
   global storage lease, consumes the receipt once and drops to `thorsten`
   before Docker/Compose release code runs. The workflow's unprivileged SSH
   account crosses this boundary only through the installed narrow sudoers
   command; the root entrypoint itself accepts exactly the three validated
   release coordinates and no caller environment.

## Exact GATE-08 deployment receipt

Fixed path: `/etc/sealai/approvals/gate-08-production-deployment.json`, regular
root-owned mode `0600`; every ancestor must be root-owned, real and
non-group/other-writable. Timestamps are UTC seconds. Expiry must be after the
current time and no later than one hour after approval.

```json
{
  "schema_version": 1,
  "gate_id": "GATE-08",
  "decision": "APPROVED",
  "scope": "production-deployment",
  "approval_id": "<unique-id>",
  "approved_by": "<human>",
  "approved_at": "YYYY-MM-DDTHH:MM:SSZ",
  "expires_at": "YYYY-MM-DDTHH:MM:SSZ",
  "deployment_target": "sealingai-production",
  "operation": "backend-v2-promote",
  "single_use": true,
  "control_git_sha": "<40-hex>",
  "source_git_sha": "<40-hex>",
  "release_manifest_sha256": "<64-hex>",
  "promotion_evidence_sha256": "<64-hex>",
  "backend_image_digest": "sha256:<64-hex>"
}
```

The receipt does not lift Gate 10. Its exclusive consumed record is created
under `/var/lib/sealai/deployment-receipts/consumed/` while the storage lease is
held. An inherited root-open file descriptor is the unforgeable capability for
the unprivileged backend release child; direct execution of the staged release
script has no such descriptor and is denied.

## Release and exposure verification

Before database backup, migration or activation, the backend release verifies:

- requested backend digest equals Gate 10, the pulled image has that exact
  `RepoDigest`, its config ID is recorded, labels match source and served tree,
  and signed provenance/SBOM match the RC build workflow;
- canonical runtime profile and Authority Epoch equal the promotion evidence;
- the canonical migration-program digest equals Gate 10;
- the fixed promotion evidence names one exact external result whose raw hash,
  source, config ID, runtime, full-suite status and final adjudication validate;
- Compose and both future backend containers use the approved backend image;
- Compose and the already exposed `frontend` container use Gate 10's frontend
  registry digest and exact local config ID; and
- the fixed rollback-plan bytes equal Gate 10.

After backend/worker smoke succeeds, the still-root entrypoint revalidates the
consumed receipt and Gate 10, verifies the immutable root-owned dashboard
release `<source>-<dashboard_artifact_sha256>`, then atomically replaces only
`/var/lib/sealai/dashboard-releases/current`. The previous verified `current`
becomes `rollback`. A failed activation restores the former current link before
returning RED. Nginx mounts this fixed release root read-only.

## Stop and rollback

Stop immediately on gate/evidence drift, a consumed receipt, missing immutable
image metadata, frontend exposure mismatch, noncanonical Authority Epoch,
migration digest drift, unverified backup, storage guard failure, unhealthy
backend/worker, or dashboard verification failure. Do not substitute a direct
Compose, Docker, Git or symlink command.

The backend script prints the exact daemon-derived rollback image and verified
pre-migration backup on RED. Dashboard rollback is the tested
`rollback_dashboard_release` installed-control primitive: it verifies the
immutable rollback artifact, atomically changes `current`, fsyncs, verifies the
new exposure and only then swaps the rollback pointer. Executing a later
rollback is a new production mutation and requires its own GATE-08 command set;
this repository deliberately does not synthesize that approval or run it.

## Current external blockers

- installation/update of the root controls: GATE-08;
- real RC snapshots, Authority Epoch, provider replay and adjudication;
- Gate-10 control documents and freeze lift;
- placement/preparation of evidence, rollback plan and immutable dashboard;
- staging and execution of one production deployment: a separate GATE-08.

All are `BLOCKED_EXTERNAL`; none was performed by this remediation branch.
