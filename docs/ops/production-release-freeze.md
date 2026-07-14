# Production release freeze

The checked-in production release state is intentionally frozen. The gate has
no environment-variable override and no owner-waiver path. While the freeze is
active, `build`, `pull`, `deploy`, `migration`, and `dashboard-publish` release
operations are denied. Boot recovery is limited to starting containers which
already exist; it cannot pull, build, create, recreate, remove, or migrate an
artifact.

The GATE-10 lift is deliberately hard-disabled in this P0 package, even when
all current control documents are syntactically valid and committed in the
documented two-commit shape. P1 must first bind the approval to the exact
backend image digest, immutable dashboard bytes, runtime/retrieval profile,
dataset and authority epochs, migrations, SBOM, and production verification
path. Until that implementation is reviewed and tested,
`freeze_lift_implemented` remains `false` and no GATE-10 document set can
authorize a release.

## Fail-closed invocation and remote deployment boundary

Every production shell entrypoint invokes the gate through
`ops/production-release-gate-check.sh`. The helper accepts only a fixed
operation token, runs `/usr/bin/python3 -I` under an empty, explicitly rebuilt
environment and fixed `PATH`, and treats a zero exit status as insufficient.
It validates the complete JSON success object, including `allowed: true`, the
exact requested operation and reason, the expected gate, and the approved
source SHA for artifact-mutating operations. Unexpected fields, output, source
commits, or caller-controlled Python configuration fail closed.

Every production mutator and every shell child in its release, recovery, and
staging call chain starts in Bash privileged mode (`#!/bin/bash -p`). Parent
scripts cross shell boundaries only with `/bin/bash -p`, use the fixed system
command path, and invoke host Python as `/usr/bin/python3 -I`. This is required
at each boundary: privileged Bash ignores exported `BASH_FUNC_*` definitions
but leaves them in the environment, so a later ordinary Bash process could
otherwise import attacker-defined replacements for `source`, the gate or
storage-lease functions, `docker`, `git`, or `mkdir`.
The deploy and immutable-image build workflows use the same privileged runner,
and every tree-hash/evaluation-evidence caller preserves that mode when it
starts a child. Root systemd wrappers and documented privileged firewall
commands do likewise. The storage-lease library is installed non-executable at
mode `0644` and is sourced only by an already privileged caller.

Repository automation instructions and Claude Code permissions preserve the
same boundary: sanctioned release examples use direct execution of the
privileged shebang, and every configured governance hook is started with
`/bin/bash -p`. Ordinary `bash ops/release-*.sh` forms are neither documented
nor allow-listed because they would import exported functions before the script
shebang could select privileged mode. The legacy deploy-sentinel parser still
recognizes direct execution, ordinary Bash, and explicit `/bin/bash -p` forms
so an unsanctioned spelling cannot evade its deny decision.

The deployment workflow performs no `git fetch`, checkout, gate execution or
image resolution on the runner. It can call only the installed root-owned
remote entrypoint. The P1 boundary accepts only an exact root-staged two-commit
checkout, fixed root-owned evidence, a matching Gate-10 decision and a
single-use private GATE-08 deployment receipt. It acquires the global storage
lease and permanently drops privilege before the staged backend release runs;
no code from `/home/thorsten/sealai` executes as root. The checked-in active
freeze plus `GATE10_LIFT_IMPLEMENTED = False` still denies every release. See
`docs/ops/PRODUCTION_PROMOTION_CONTROL.md`.

Backend-v2 RC publication is deliberately non-circular: its manual workflow
builds and signs an immutable candidate before Gate 10, without a production
environment, production secrets, SSH credential or production network path.
Publication is not deployment and does not lift the freeze. Production pull,
migration and activation remain denied by the two production gates. Keycloak
publication remains separately gated.

## Narrow GATE-08 bootstrap exception

The only mutating operation accepted while the normal release freeze remains
active is `remediation-control-install`. It exists solely to install and start
the non-destructive disk guard without first pretending that
`P0_STORAGE_STABLE` is already true. It requires the fixed root-owned file
`/etc/sealai/approvals/gate-08-remediation-control.json` with mode `0600` and an
expiry no later than four hours after approval. Every receipt-path ancestor
must also be a root-owned, non-group/other-writable real directory; symlinks are
rejected.

The receipt has an exact schema:

```json
{
  "schema_version": 1,
  "gate_id": "GATE-08",
  "decision": "APPROVED",
  "scope": "p0-remediation-control-install",
  "approval_id": "operator-supplied-id",
  "approved_by": "operator-identity",
  "approved_at": "YYYY-MM-DDTHH:MM:SSZ",
  "expires_at": "YYYY-MM-DDTHH:MM:SSZ",
  "source_git_sha": "40-lowercase-hex",
  "artifact_sha256": {
    "fixed/repository/path": "64-lowercase-hex"
  }
}
```

`artifact_sha256` must contain exactly the fixed artifact set compiled into
`ops/production_release_gate.py`; missing and extra paths both fail. The gate
also requires the receipt owner to equal the executing root user, the checkout
to be clean, every artifact to be tracked and unchanged, the current HEAD to
equal `source_git_sha`, and every file hash to match. The checkout must be a
root-owned detached non-live source path; both gate and installer reject
`/home/thorsten/sealai`. The fixed set includes the bootstrap itself, the active
freeze state read by the gate, and every file consumed by the installer.

Never run `sudo` on the bootstrap, gate, or installer in a user-writable
checkout. The only supported trust transition is the inline, independently
reviewed system-tool loader below. It first copies the candidate bootstrap as a
non-executable mode-`0600` data file into a root-private `/run` directory. Its
trusted inline `/usr/bin/python3 -I` code opens both source and receipt without
following a final symlink, requires a root-owned mode-`0600` receipt, and checks
the copied bytes against the bootstrap hash in that receipt. Only after the
hash matches does the loader change the staged file to mode `0700` and execute
it with an empty environment.

Set the local candidate repository path, then paste the loader body from the
independently reviewed control-plane record—not by piping a file from the
candidate checkout into `sudo`:

```bash
CANDIDATE_REPOSITORY='/absolute/local/path/to/candidate-repository'
sudo /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin HOME=/root LANG=C LC_ALL=C \
  /bin/bash --noprofile --norc -s -- \
  "$CANDIDATE_REPOSITORY" \
  "$CANDIDATE_REPOSITORY/ops/bootstrap_gate08_remediation_control.py" <<'ROOT_LOADER'
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
readonly RECEIPT=/etc/sealai/approvals/gate-08-remediation-control.json
readonly SOURCE_REPOSITORY="$1"
readonly CANDIDATE_BOOTSTRAP="$2"
[[ "${SOURCE_REPOSITORY}" == /* && "${CANDIDATE_BOOTSTRAP}" == /* ]] || exit 64
LOADER_STAGE="$(/usr/bin/mktemp -d /run/sealai-gate08-loader.XXXXXX)"
/usr/bin/chown root:root "${LOADER_STAGE}"
/usr/bin/chmod 0700 "${LOADER_STAGE}"
readonly LOADER_STAGE
cleanup_loader() {
  [[ "${LOADER_STAGE}" == /run/sealai-gate08-loader.* ]] || return
  /usr/bin/rm -r -- "${LOADER_STAGE}" 2>/dev/null || true
}
trap cleanup_loader EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
readonly STAGED_BOOTSTRAP="${LOADER_STAGE}/bootstrap.data"
/usr/bin/python3 -I - \
  "${CANDIDATE_BOOTSTRAP}" "${STAGED_BOOTSTRAP}" "${RECEIPT}" <<'PY'
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import sys
from datetime import datetime, timedelta, timezone

def require_root_chain(value):
    path = Path(os.path.abspath(value))
    current = Path(path.anchor)
    for index, part in enumerate((path.anchor, *path.parts[1:])):
        if index:
            current /= part
        metadata = current.lstat()
        is_leaf = current == path
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (not is_leaf and not stat.S_ISDIR(metadata.st_mode))
            or (is_leaf and not stat.S_ISREG(metadata.st_mode))
        ):
            raise SystemExit("GATE-08 loader: receipt path is unsafe")

source, target, receipt_path = sys.argv[1:]
read_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
try:
    source_fd = os.open(source, read_flags)
except OSError as exc:
    raise SystemExit("GATE-08 loader: bootstrap source unavailable") from exc
target_fd = -1
digest = hashlib.sha256()
try:
    source_stat = os.fstat(source_fd)
    if not stat.S_ISREG(source_stat.st_mode) or source_stat.st_size > 256 * 1024:
        raise SystemExit("GATE-08 loader: bootstrap source is unsafe")
    target_fd = os.open(
        target,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    while True:
        chunk = os.read(source_fd, 64 * 1024)
        if not chunk:
            break
        digest.update(chunk)
        view = memoryview(chunk)
        while view:
            written = os.write(target_fd, view)
            if written <= 0:
                raise SystemExit("GATE-08 loader: bootstrap copy failed")
            view = view[written:]
    os.fsync(target_fd)
finally:
    os.close(source_fd)
    if target_fd >= 0:
        os.close(target_fd)
try:
    require_root_chain(receipt_path)
    receipt_fd = os.open(receipt_path, read_flags)
except OSError as exc:
    raise SystemExit("GATE-08 loader: private receipt unavailable") from exc
try:
    receipt_stat = os.fstat(receipt_fd)
    if (
        not stat.S_ISREG(receipt_stat.st_mode)
        or receipt_stat.st_uid != 0
        or stat.S_IMODE(receipt_stat.st_mode) != 0o600
        or receipt_stat.st_size > 64 * 1024
    ):
        raise SystemExit("GATE-08 loader: private receipt is unsafe")
    raw = os.read(receipt_fd, 64 * 1024 + 1)
finally:
    os.close(receipt_fd)
try:
    receipt = json.loads(raw)
    expected = receipt["artifact_sha256"][
        "ops/bootstrap_gate08_remediation_control.py"
    ]
except (KeyError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
    raise SystemExit("GATE-08 loader: bootstrap approval is invalid") from exc
if (
    not isinstance(receipt, dict)
    or set(receipt)
    != {
        "schema_version",
        "gate_id",
        "decision",
        "scope",
        "approval_id",
        "approved_by",
        "approved_at",
        "expires_at",
        "source_git_sha",
        "artifact_sha256",
    }
    or receipt.get("schema_version") != 1
    or receipt.get("gate_id") != "GATE-08"
    or receipt.get("decision") != "APPROVED"
    or receipt.get("scope") != "p0-remediation-control-install"
    or not isinstance(receipt.get("approval_id"), str)
    or not receipt["approval_id"].strip()
    or not isinstance(receipt.get("approved_by"), str)
    or not receipt["approved_by"].strip()
    or not isinstance(receipt.get("source_git_sha"), str)
    or not re.fullmatch(r"[0-9a-f]{40}", receipt["source_git_sha"])
    or not isinstance(expected, str)
    or not re.fullmatch(r"[0-9a-f]{64}", expected)
    or not hmac.compare_digest(digest.hexdigest(), expected)
):
    raise SystemExit("GATE-08 loader: bootstrap hash is not approved")
timestamp_pattern = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z"
approved_text = receipt.get("approved_at")
expires_text = receipt.get("expires_at")
if (
    not isinstance(approved_text, str)
    or not re.fullmatch(timestamp_pattern, approved_text)
    or not isinstance(expires_text, str)
    or not re.fullmatch(timestamp_pattern, expires_text)
):
    raise SystemExit("GATE-08 loader: approval timestamp is invalid")
try:
    approved_at = datetime.fromisoformat(approved_text[:-1] + "+00:00")
    expires_at = datetime.fromisoformat(expires_text[:-1] + "+00:00")
except ValueError as exc:
    raise SystemExit("GATE-08 loader: approval timestamp is invalid") from exc
now = datetime.now(timezone.utc)
if (
    approved_at > now + timedelta(minutes=5)
    or expires_at <= now
    or expires_at > approved_at + timedelta(hours=4)
):
    raise SystemExit("GATE-08 loader: approval is expired or over-broad")
PY
/usr/bin/chown root:root "${STAGED_BOOTSTRAP}"
/usr/bin/chmod 0700 "${STAGED_BOOTSTRAP}"
/usr/bin/env -i HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C LC_ALL=C \
  "${STAGED_BOOTSTRAP}" \
  --source-repository "${SOURCE_REPOSITORY}" --apply
ROOT_LOADER
```

The verified bootstrap uses only fixed system tools. It clones the local source
with `git clone --no-local --no-checkout` into a root-owned mode-`0700` temporary
directory. The candidate repository must advertise the approved commit as its
current `HEAD`; the clone is single-branch, depth one, and excludes tags so it
does not duplicate unrelated history under storage pressure. The bootstrap
disables hooks and recursive submodules, rejects any gitlink or object
alternate, disables lazy fetches and executable alternate-ref commands, and
checks out exactly `source_git_sha` detached. Before any checked-out code runs,
the already verified bootstrap checks clean HEAD, root ownership, non-writable
modes, every path component, the complete `.git` topology, and the receipt
hashes of the gate program and active freeze-state file without following
symlinks. It then runs that verified gate with isolated system Python. The gate
verifies the exact complete artifact set, Git state, and every artifact hash.
The installer repeats path/gate checks, copies all inputs to another
root-private stage, and re-hashes that exact copy before installation. It also
installs the fail-closed gate-invocation helper, root-staging control,
dashboard verifier and remote deployment boundary as root-owned executables.
Installing these inert controls does not authorize them to stage or release an
application artifact; every later deployment needs its own GATE-08 receipt.
An approved GATE-08 command set must include placement of the private receipt,
this trust transition, exact retirement of the one destructive legacy cron
line, and the verified installer transaction; the receipt never authorizes an
application build, image pull, migration, dashboard publish, or cleanup.

No GATE-08 receipt is committed or synthesized by this repository. The checked
in code remains denied until a human provides that exact, short-lived approval.

## Gate-10 two-commit model

The reserved future lift uses two commits so no document has to contain its own
Git hash. The exact-artifact P1 binding is implemented and tested, but the
checked-in lift constant remains false until the external evidence and human
Gate-10 decision exist:

1. The source commit contains the exact reviewed application and release code.
   Immutable images and all release-evidence hashes are produced for this
   commit.
2. Its direct child is a dedicated Gate-10 control commit. That commit may
   change exactly these three paths and no others:
   - `ops/production-release-state.json`
   - `ops/production-release-gate10-approval.json`
   - `ops/production-release-manifest.json`

The control commit must have exactly one parent. The manifest's
`source_git_sha` must equal that parent. The approval must be `GATE-10`, have the
fixed `production-release-freeze-lift` scope, and bind the manifest's exact file
bytes by SHA-256. The state, approval, and manifest must all be tracked,
committed, and unchanged in the checkout.

The manifest must contain exactly these readiness claims, all as the JSON
boolean `true`:

- `P0_SECRETS_CONTAINED`
- `P0_STORAGE_STABLE`
- `P0_REDIS_STABLE`
- `RELEASE_GATE_FAIL_CLOSED`

It must also carry the complete fixed hash set declared in the state file. An
extra or missing claim, hash, changed path, merge commit, dirty checkout,
manifest byte mismatch, or source-parent mismatch fails closed.

After P1 completes the currently disabled artifact binding, the deploy workflow
will be invoked with the Gate-10 control commit. It must execute the gate from
that checkout, resolve every approved immutable artifact from the approved
parent source commit, and verify the same parent and digests again on the VPS
before release.

No Gate-10 approval or release manifest is present while the freeze remains
active. Those documents are approval evidence, not placeholders or generated
defaults.
