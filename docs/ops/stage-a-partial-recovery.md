# Stage-A partial recovery

This runbook covers only the incident-bound continuation of the failed
`remediation-control-install` transaction from commit `c905780b`. It is not a
second fresh install and it is not a Stage-B entry point.

## Bound incident

- Production remains on `b5fea96e387772547722bdbcaecde1e125d9100b` with a
  clean checkout and the previously recorded container/image identities.
- The legacy timer is `loaded/inactive/disabled`; the legacy service is
  `loaded/failed/static` with zero PIDs.
- The exact legacy cron line still occurs once.
- The four files below the evidence ID
  `legacy-stage-a-c905780b-20260716T062603Z` are immutable inputs.
- Every new control target is absent and the production release freeze remains
  active with `GATE10_LIFT_IMPLEMENTED = False`.

Any mismatch is a stop. Never reactivate the legacy timer or cron to make a
precondition pass.

## Approval boundary

The only accepted approval path is:

```text
/etc/sealai/approvals/gate-08-remediation-resume.json
```

It must be root-owned mode `0600`, valid for no more than four hours, and bind
the exact source commit, artifact set, production state, target absence, and
legacy evidence hashes. Package material remains
`PENDING_OWNER_APPROVAL`; changing that value and placing the approval requires
a separate owner authorization after PR review and audit.

## Owner-authenticated hash-to-exec entry

The following is execution-plan material, not authorization to run it. The
candidate bootstrap and source repository must first be transferred into a
root-owned private handoff by an owner-authenticated root session. Never run
`sudo` directly on bootstrap bytes from a user-writable checkout.

The fixed loader opens the candidate with `O_NOFOLLOW`, validates the opened
descriptor, copies from that descriptor into a new root-private file, hashes
the copied bytes, and only then invokes the fixed system Python interpreter.
Replacing the candidate pathname after `open` cannot change the bytes that are
executed.

```bash
set -Eeuo pipefail
umask 077

readonly CANDIDATE_BOOTSTRAP=/var/lib/sealai-gate08-recovery-handoff/bootstrap_gate08_remediation_resume.py
readonly SOURCE_REPOSITORY=/var/lib/sealai-gate08-recovery-handoff/approved-source.git
readonly EXPECTED_BOOTSTRAP_SHA256=OWNER_MUST_INSERT_PACKAGE_MANIFEST_HASH

LOADER_STAGE=$(/usr/bin/mktemp -d /run/sealai-recovery-loader.XXXXXX)
cleanup_loader() {
  /usr/bin/rm -rf -- "${LOADER_STAGE}"
}
trap cleanup_loader EXIT
/usr/bin/chown root:root "${LOADER_STAGE}"
/usr/bin/chmod 0700 "${LOADER_STAGE}"
readonly STAGED_BOOTSTRAP="${LOADER_STAGE}/bootstrap.data"

/usr/bin/python3 -I - \
  "${CANDIDATE_BOOTSTRAP}" \
  "${STAGED_BOOTSTRAP}" \
  "${EXPECTED_BOOTSTRAP_SHA256}" <<'PY'
import hashlib
import hmac
import os
from pathlib import Path
import stat
import sys

candidate = Path(sys.argv[1])
destination = Path(sys.argv[2])
expected = sys.argv[3]
flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
source_fd = os.open(candidate, flags)
try:
    source_stat = os.fstat(source_fd)
    if (
        not stat.S_ISREG(source_stat.st_mode)
        or source_stat.st_uid != 0
        or source_stat.st_gid != 0
        or stat.S_IMODE(source_stat.st_mode) != 0o600
        or source_stat.st_size > 1024 * 1024
    ):
        raise SystemExit("unsafe recovery bootstrap candidate")
    destination_fd = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC,
        0o600,
    )
    digest = hashlib.sha256()
    try:
        while chunk := os.read(source_fd, 65536):
            digest.update(chunk)
            os.write(destination_fd, chunk)
        os.fsync(destination_fd)
    finally:
        os.close(destination_fd)
finally:
    os.close(source_fd)
if not hmac.compare_digest(digest.hexdigest(), expected):
    raise SystemExit("recovery bootstrap hash mismatch")
PY

/usr/bin/chmod 0700 "${STAGED_BOOTSTRAP}"
/usr/bin/python3 -I "${STAGED_BOOTSTRAP}" \
  --source-repository "${SOURCE_REPOSITORY}" --apply
```

The bootstrap accepts no runner or interpreter argument. It clones the fixed
approved commit into a new root-private checkout, disables hooks, alternates,
submodules, network protocols, and lazy fetches, verifies the complete artifact
set, runs `remediation-control-resume`, then invokes only
`ops/resume-disk-guard-install.sh`.

## Transaction phases

1. **R0** verifies approval, production, containers, freeze, evidence, legacy
   states/PIDs, exact cron count, process exclusion, and all absent targets.
2. **R1** creates a private synthetic root and validates the exact staged unit
   and payload bytes with the production `systemd-analyze`, plus shell, Python,
   JSON, Sudoers, tmpfiles, Docker-root, and free-space checks.
3. **R2** fsyncs a rollback manifest and cron-before evidence before creating a
   live target.
4. **R3** installs exact staged files atomically with fixed owners and modes;
   it does not enable a unit.
5. **R4** runs live systemd verification with all referenced executables
   present, without `daemon-reload`.
6. **R5** rechecks the byte-identical crontab and removes exactly the one bound
   legacy line. It is never restored automatically.
7. **R6** creates the lock object, reloads systemd, enables the new timer, runs
   one non-destructive observation, and rechecks the storage lease and release
   freeze.
8. **R7** fsyncs a redacted receipt and consumes the one-time approval.

The recovery runner contains no call to the legacy retirement helper and no
command that stops or disables the legacy timer again.

## Failure behavior

Before cron retirement, newly installed absent targets are removed using the
rollback manifest. The legacy timer and cron are never activated. Verdict:

```text
RECOVERY_FAILED_BEFORE_CRON_RETIREMENT
```

After cron retirement, safe controls remain for incident inspection. If the
new timer was touched, it is disabled; the legacy timer and cron remain
inactive/absent. Verdict:

```text
RECOVERY_PARTIAL_STOPPED_NO_DESTRUCTIVE_FALLBACK
```

No failure path starts `gate08_legacy_unit_retirement.py`, reenables the old
timer, or recreates the old cron line.
