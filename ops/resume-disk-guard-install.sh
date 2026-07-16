#!/bin/bash -p
# Resume only the evidence-bound Stage-A partial transaction under GATE-08.
set -Eeuo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

usage() {
  printf 'Usage: %s [--apply]\n' "$0"
}

APPLY=0
case "${1:-}" in
  "") ;;
  --apply) APPLY=1 ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 64 ;;
esac
[[ "$#" -le 1 ]] || { usage >&2; exit 64; }

SOURCE_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)"
REPO_ROOT="$(dirname "${SOURCE_DIR}")"
[[ "$(realpath "${REPO_ROOT}")" != /home/thorsten/sealai ]] || {
  printf 'recovery runner: live production checkout is forbidden\n' >&2
  exit 78
}
readonly APPROVAL=/etc/sealai/approvals/gate-08-remediation-resume.json
readonly LEGACY_CRON_USER=thorsten
readonly LEGACY_CRON_LINE='0 * * * * /home/thorsten/sealai/ops/disk_safeguard.sh'
readonly -a ARTIFACTS=(
  docs/ops/docker-disk-guard.md
  docs/ops/production-release-freeze.md
  docs/ops/stage-a-partial-recovery.md
  ops/bootstrap_gate08_remediation_resume.py
  ops/disk-guard.example.json
  ops/docker-disk-guard.sh
  ops/docker_disk_guard.py
  ops/gate08_partial_recovery.py
  ops/hash_verified_python_loader.py
  ops/production-deploy-remote-entrypoint.sh
  ops/production-release-gate-check.sh
  ops/production-release-state.json
  ops/production-storage-lease.sh
  ops/production_release_gate.py
  ops/resume-disk-guard-install.sh
  ops/schemas/gate08-remediation-resume.schema.json
  ops/sudoers/sealai-storage-preflight
  ops/systemd/sealai-disk-guard.service
  ops/systemd/sealai-disk-guard.timer
  ops/tmpfiles/sealai-storage-mutation.conf
)

for relative in "${ARTIFACTS[@]}"; do
  [[ -f "${REPO_ROOT}/${relative}" && ! -L "${REPO_ROOT}/${relative}" ]] || {
    printf 'recovery runner: required source is unavailable\n' >&2
    exit 66
  }
done

if [[ "${APPLY}" -eq 0 ]]; then
  printf '%s\n' \
    'Stage-A recovery dry-run: no files changed' \
    'accepts only the evidence-bound inactive/disabled partial state' \
    'does not repeat legacy unit retirement' \
    'does not reactivate the legacy timer or cron' \
    'requires a new short-lived GATE-08 recovery approval'
  exit 0
fi

[[ "${EUID}" -eq 0 ]] || {
  printf 'recovery runner: --apply requires root\n' >&2
  exit 77
}

/usr/bin/python3 -I - "${REPO_ROOT}" "${ARTIFACTS[@]}" <<'PY'
import os
from pathlib import Path
import stat
import sys


def fail():
    raise SystemExit("recovery runner: source checkout topology is unsafe")


repo = Path(sys.argv[1])
for path, directory in ((repo, True), (repo / ".git", True)):
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    for index, part in enumerate((absolute.anchor, *absolute.parts[1:])):
        if index:
            current /= part
        metadata = current.lstat()
        leaf = current == absolute
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or ((directory if leaf else True) and not stat.S_ISDIR(metadata.st_mode))
        ):
            fail()
for relative in sys.argv[2:]:
    item = Path(relative)
    if item.is_absolute() or ".." in item.parts:
        fail()
    path = repo / item
    metadata = path.lstat()
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) & 0o022
    ):
        fail()
PY

# The release gate is the only authority transition. It validates the exact
# recovery approval, commit, and complete artifact set before staging begins.
# shellcheck source=production-release-gate-check.sh
source "${SOURCE_DIR}/production-release-gate-check.sh"
production_release_gate_check \
  "${SOURCE_DIR}/production_release_gate.py" remediation-control-resume
GATE_DECISION="${PRODUCTION_RELEASE_GATE_DECISION}"

# R0: every production, evidence, unit, cron, process, target, and real
# filesystem precondition is read-only and precedes the first recovery write.
/usr/bin/python3 -I "${SOURCE_DIR}/gate08_partial_recovery.py" \
  preflight --approval "${APPROVAL}" >/dev/null
STORAGE_PREFLIGHT_JSON="$(
  /usr/bin/python3 -I "${SOURCE_DIR}/gate08_partial_recovery.py" \
    storage-preflight --approval "${APPROVAL}" --source-root "${REPO_ROOT}"
)"

exec 8>/run/lock/sealai-stage-a-recovery.lock
flock -n 8 || {
  printf 'recovery runner: another recovery process is active\n' >&2
  exit 79
}
# Close the interval between the read-only preflight and lock acquisition.
/usr/bin/python3 -I "${SOURCE_DIR}/gate08_partial_recovery.py" \
  preflight --approval "${APPROVAL}" >/dev/null

STAGE_DIR="$(mktemp -d /run/sealai-remediation-resume.XXXXXX)"
chmod 0700 "${STAGE_DIR}"
TRANSACTION_DIR=""
MUTATION_STARTED=0
CRON_RETIRED=0
NEW_TIMER_TOUCHED=0

write_failure_receipt() {
  local verdict="$1"
  [[ -n "${TRANSACTION_DIR}" && -d "${TRANSACTION_DIR}" ]] || return 0
  /usr/bin/python3 -I - "${TRANSACTION_DIR}" "${verdict}" <<'PY'
import json
import os
from pathlib import Path
import sys

directory = Path(sys.argv[1])
path = directory / "failure-receipt.json"
raw = (json.dumps({
    "operation": "remediation-control-resume",
    "verdict": sys.argv[2],
    "legacy_reactivated": False,
    "legacy_cron_reactivated": False,
}, sort_keys=True, indent=2) + "\n").encode()
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.write(fd, raw)
    os.fsync(fd)
finally:
    os.close(fd)
PY
}

rollback_before_cron() {
  /usr/bin/python3 -I - "${TRANSACTION_DIR}/rollback-manifest.json" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

manifest = json.loads(Path(sys.argv[1]).read_text())
if (
    manifest.get("operation") != "remediation-control-resume"
    or manifest.get("legacy_reactivation_allowed") is not False
    or manifest.get("cron_reactivation_allowed") is not False
):
    raise SystemExit("recovery rollback manifest is invalid")
preconditions = manifest.get("target_preconditions")
hashes = manifest.get("staged_target_sha256")
if not isinstance(preconditions, dict) or not isinstance(hashes, dict):
    raise SystemExit("recovery rollback manifest is incomplete")
for target, expected in reversed(sorted(hashes.items())):
    if preconditions.get(target) != "ABSENT":
        raise SystemExit("recovery rollback precondition is not ABSENT")
    path = Path(target)
    if not path.exists() and not path.is_symlink():
        continue
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise SystemExit("recovery rollback target topology drift")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise SystemExit("recovery rollback target hash drift")
    os.unlink(path)
PY
  rmdir /usr/local/libexec/sealai 2>/dev/null || true
  rmdir /usr/local/libexec 2>/dev/null || true
  rmdir /usr/local/share/doc/sealai 2>/dev/null || true
}

cleanup() {
  local rc=$?
  if [[ "${rc}" -ne 0 ]]; then
    if [[ "${MUTATION_STARTED}" -eq 1 && "${CRON_RETIRED}" -eq 0 ]]; then
      if ! rollback_before_cron; then
        printf 'recovery runner: rollback requires owner incident review\n' >&2
      fi
      rm -f -- "${APPROVAL}"
      write_failure_receipt RECOVERY_FAILED_BEFORE_CRON_RETIREMENT || true
      printf 'RECOVERY_FAILED_BEFORE_CRON_RETIREMENT\n' >&2
    elif [[ "${CRON_RETIRED}" -eq 1 ]]; then
      if [[ "${NEW_TIMER_TOUCHED}" -eq 1 ]]; then
        systemctl disable --now sealai-disk-guard.timer >/dev/null 2>&1 || true
      fi
      rm -f -- "${APPROVAL}"
      write_failure_receipt RECOVERY_PARTIAL_STOPPED_NO_DESTRUCTIVE_FALLBACK || true
      printf 'RECOVERY_PARTIAL_STOPPED_NO_DESTRUCTIVE_FALLBACK\n' >&2
    else
      printf 'RECOVERY_PREFLIGHT_FAILED\n' >&2
    fi
  fi
  rm -rf -- "${STAGE_DIR}"
  exit "${rc}"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

for relative in "${ARTIFACTS[@]}"; do
  install -D -m 0600 "${REPO_ROOT}/${relative}" "${STAGE_DIR}/${relative}"
done

/usr/bin/python3 -I - "${GATE_DECISION}" "${STAGE_DIR}" <<'PY'
import hashlib
import json
from pathlib import Path
import sys

decision = json.loads(sys.argv[1])
stage = Path(sys.argv[2])
expected_keys = {
    "allowed", "operation", "reason", "state_id", "required_gate",
    "source_git_sha", "approval_id", "artifact_sha256",
}
if (
    set(decision) != expected_keys
    or decision.get("allowed") is not True
    or decision.get("operation") != "remediation-control-resume"
    or decision.get("reason") != "gate08_hash_bound_remediation_control_resume"
    or decision.get("required_gate") != "GATE-08"
):
    raise SystemExit("recovery gate decision is invalid")
expected = decision.get("artifact_sha256")
actual_paths = {
    str(path.relative_to(stage)) for path in stage.rglob("*") if path.is_file()
}
if not isinstance(expected, dict) or actual_paths != set(expected):
    raise SystemExit("recovery staged artifact set mismatch")
for relative, digest in expected.items():
    if hashlib.sha256((stage / relative).read_bytes()).hexdigest() != digest:
        raise SystemExit("recovery staged artifact hash mismatch")
PY

STORAGE_PREFLIGHT_RESULT="${STAGE_DIR}/storage-preflight.json"
/usr/bin/python3 -I - "${STORAGE_PREFLIGHT_RESULT}" "${STORAGE_PREFLIGHT_JSON}" <<'PY'
import json
import os
from pathlib import Path
import sys

value = json.loads(sys.argv[2])
raw = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
fd = os.open(sys.argv[1], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.write(fd, raw)
    os.fsync(fd)
finally:
    os.close(fd)
PY

CRON_BEFORE="${STAGE_DIR}/crontab.before"
CRON_AFTER="${STAGE_DIR}/crontab.after"
crontab -u "${LEGACY_CRON_USER}" -l >"${CRON_BEFORE}" 2>/dev/null
[[ "$(awk -v exact="${LEGACY_CRON_LINE}" '$0==exact{n++}END{print n+0}' "${CRON_BEFORE}")" == 1 ]]
awk -v exact="${LEGACY_CRON_LINE}" '$0 != exact { print }' \
  "${CRON_BEFORE}" >"${CRON_AFTER}"

# R1: the exact staged unit and payload bytes pass all non-mutating checks.
ACTUAL_DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}')"
VALIDATION_RESULT="${STAGE_DIR}/validation-result.json"
/usr/bin/python3 -I "${STAGE_DIR}/ops/gate08_partial_recovery.py" \
  validate-stage \
  --stage-dir "${STAGE_DIR}" \
  --validation-root "${STAGE_DIR}/validation-root" \
  --actual-docker-root "${ACTUAL_DOCKER_ROOT}" >"${VALIDATION_RESULT}"
STAGED_HASHES="${STAGE_DIR}/staged-target-hashes.json"
/usr/bin/python3 -I - "${VALIDATION_RESULT}" "${STAGED_HASHES}" <<'PY'
import json
import os
from pathlib import Path
import sys

value = json.loads(Path(sys.argv[1]).read_text())
raw = (json.dumps(value["validated_targets"], sort_keys=True, indent=2) + "\n").encode()
fd = os.open(sys.argv[2], os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.write(fd, raw)
    os.fsync(fd)
finally:
    os.close(fd)
PY

# R2: durable rollback and incident evidence precede the first live target.
install -d -m 0700 -o root -g root /var/lib/sealai-disk-guard/recovery-evidence
TRANSACTION_JSON="$(/usr/bin/python3 -I "${STAGE_DIR}/ops/gate08_partial_recovery.py" \
  prepare-transaction \
  --approval "${APPROVAL}" \
  --evidence-root /var/lib/sealai-disk-guard/recovery-evidence \
  --staged-hashes "${STAGED_HASHES}")"
TRANSACTION_DIR="$(printf '%s' "${TRANSACTION_JSON}" | /usr/bin/python3 -I -c \
  'import json,sys; print(json.load(sys.stdin)["transaction_directory"])')"
install -m 0600 -o root -g root "${CRON_BEFORE}" "${TRANSACTION_DIR}/crontab.before"
install -m 0600 -o root -g root \
  "${STORAGE_PREFLIGHT_RESULT}" "${TRANSACTION_DIR}/storage-preflight.json"
/bin/sync -f "${TRANSACTION_DIR}/crontab.before"
/bin/sync -f "${TRANSACTION_DIR}/storage-preflight.json"
MUTATION_STARTED=1

install -d -m 0755 -o root -g root \
  /usr/local/libexec /usr/local/libexec/sealai \
  /usr/local/share/doc /usr/local/share/doc/sealai
test "$(stat -Lc '%F:%a:%U:%G' /etc/sealai)" = 'directory:700:root:root'

# R3: install only the exact staged bytes; no unit is enabled yet.
INSTALL_RESULT="${STAGE_DIR}/install-result.json"
/usr/bin/python3 -I "${STAGE_DIR}/ops/gate08_partial_recovery.py" \
  install-targets --stage-dir "${STAGE_DIR}" >"${INSTALL_RESULT}"
POSTINSTALL_TARGETS="${STAGE_DIR}/postinstall-targets.json"
/usr/bin/python3 -I "${STAGE_DIR}/ops/gate08_partial_recovery.py" \
  verify-targets --stage-dir "${STAGE_DIR}" >"${POSTINSTALL_TARGETS}"
cmp -s "${INSTALL_RESULT}" "${POSTINSTALL_TARGETS}" || {
  printf 'recovery runner: post-install target metadata drift\n' >&2
  exit 78
}

# R4: live verification occurs only after every referenced executable exists.
systemd-analyze verify \
  /etc/systemd/system/sealai-disk-guard.service \
  /etc/systemd/system/sealai-disk-guard.timer

# R5: the crontab must still be byte-identical to R0 before removing one line.
CRON_CURRENT="${STAGE_DIR}/crontab.current"
crontab -u "${LEGACY_CRON_USER}" -l >"${CRON_CURRENT}" 2>/dev/null
cmp -s "${CRON_BEFORE}" "${CRON_CURRENT}" || {
  printf 'recovery runner: legacy cron changed during transaction\n' >&2
  exit 79
}
crontab -u "${LEGACY_CRON_USER}" "${CRON_AFTER}"
CRON_INSTALLED="$(crontab -u "${LEGACY_CRON_USER}" -l)"
if grep -Fqx "${LEGACY_CRON_LINE}" <<<"${CRON_INSTALLED}"; then
  printf 'recovery runner: bound legacy cron remains installed\n' >&2
  exit 78
fi
install -m 0600 -o root -g root "${CRON_AFTER}" "${TRANSACTION_DIR}/crontab.after"
/bin/sync -f "${TRANSACTION_DIR}/crontab.after"
CRON_RETIRED=1

# R6: activate only the non-destructive replacement and observe it once.
systemd-tmpfiles --create /etc/tmpfiles.d/sealai-storage-mutation.conf
test "$(stat -Lc '%F:%a:%U:%G' /run/lock/sealai-storage-mutation.lock)" = \
  'regular file:660:root:thorsten'
systemctl daemon-reload
NEW_TIMER_TOUCHED=1
systemctl enable --now sealai-disk-guard.timer
systemctl start sealai-disk-guard.service
systemctl is-enabled --quiet sealai-disk-guard.timer
systemctl is-active --quiet sealai-disk-guard.timer
test "$(systemctl show sealai-docker-disk-guard.timer -p ActiveState --value)" = inactive
test "$(systemctl show sealai-docker-disk-guard.timer -p UnitFileState --value)" = disabled
test "$(systemctl show sealai-docker-disk-guard.service -p MainPID --value)" = 0
test "$(systemctl show sealai-docker-disk-guard.service -p ControlPID --value)" = 0
test -s /var/lib/sealai-disk-guard/state.json
test "$(stat -Lc '%F:%a:%U:%G' /var/lib/sealai-disk-guard/state.json)" = \
  'regular file:600:root:root'

set +e
/usr/bin/python3 -I "${STAGE_DIR}/ops/production_release_gate.py" check deploy \
  >"${STAGE_DIR}/freeze.stdout" 2>"${STAGE_DIR}/freeze.stderr"
FREEZE_RC=$?
set -e
[[ "${FREEZE_RC}" -eq 20 ]]
grep -Fq production_release_freeze_active "${STAGE_DIR}/freeze.stderr"

set +e
sudo -u thorsten /bin/bash -p -c \
  'source /usr/local/libexec/sealai/production-storage-lease.sh; acquire_production_storage_lease' \
  >/dev/null
LEASE_RC=$?
set -e
[[ "${LEASE_RC}" -eq 0 || "${LEASE_RC}" -eq 22 ]]

# R7: revalidate every target immediately before the complete one-time receipt.
RECEIPT_TARGETS="${STAGE_DIR}/receipt-targets.json"
/usr/bin/python3 -I "${STAGE_DIR}/ops/gate08_partial_recovery.py" \
  verify-targets --stage-dir "${STAGE_DIR}" >"${RECEIPT_TARGETS}"
cmp -s "${POSTINSTALL_TARGETS}" "${RECEIPT_TARGETS}" || {
  printf 'recovery runner: target metadata drift before receipt\n' >&2
  exit 78
}
/usr/bin/python3 -I - \
  "${APPROVAL}" "${TRANSACTION_DIR}" "${RECEIPT_TARGETS}" <<'PY'
import json
import os
from pathlib import Path
import sys

approval = json.loads(Path(sys.argv[1]).read_text())
transaction = Path(sys.argv[2])
target_value = json.loads(Path(sys.argv[3]).read_text())
targets = target_value.get("targets")
if not isinstance(targets, list) or any(
    not isinstance(item, dict)
    or set(item) != {"path", "sha256", "uid", "gid", "mode"}
    or item["uid"] != 0
    or item["gid"] != 0
    for item in targets
):
    raise SystemExit("recovery target receipt input is incomplete")
receipt = {
    "operation": "remediation-control-resume",
    "required_gate": "GATE-08",
    "source_git_sha": approval["source_git_sha"],
    "approval_id": approval["approval_id"],
    "incident_evidence_id": approval["legacy_evidence"]["evidence_id"],
    "recovery_transaction_id": transaction.name,
    "legacy_timer_remained_disabled": True,
    "legacy_cron_removed": True,
    "new_timer_active": True,
    "new_timer_enabled": True,
    "observation_completed": True,
    "release_freeze_active": True,
    "targets": targets,
}
raw = (json.dumps(receipt, sort_keys=True, indent=2) + "\n").encode()
path = transaction / "recovery-receipt.json"
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.write(fd, raw)
    os.fsync(fd)
finally:
    os.close(fd)
PY
rm -f -- "${APPROVAL}"
/bin/sync -f /etc/sealai/approvals
trap - EXIT INT TERM HUP
rm -rf -- "${STAGE_DIR}"
printf 'STAGE_A_RECOVERY_COMPLETED\n'
