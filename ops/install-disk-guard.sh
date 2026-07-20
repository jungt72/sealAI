#!/bin/bash -p
# Install and activate the canonical storage controls as one GATE-08 transaction.
set -euo pipefail
umask 077
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

SCRIPT_INVOKED_PATH="$0"
if [[ "${SCRIPT_INVOKED_PATH}" != /* ]]; then
  SCRIPT_INVOKED_PATH="${PWD}/${SCRIPT_INVOKED_PATH}"
fi

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

SOURCE_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
REPO_ROOT="$(dirname "${SOURCE_DIR}")"
[[ "$(realpath "${REPO_ROOT}")" != /home/thorsten/sealai ]] || {
  printf 'disk-guard installer: live production checkout is forbidden\n' >&2
  exit 78
}
readonly LEGACY_CRON_USER=thorsten
readonly LEGACY_CRON_LINE='0 * * * * /home/thorsten/sealai/ops/disk_safeguard.sh'
readonly -a ARTIFACTS=(
  docs/ops/docker-disk-guard.md
  docs/ops/production-release-freeze.md
  ops/bootstrap_gate08_remediation_control.py
  ops/disk-guard.example.json
  ops/docker-disk-guard.sh
  ops/docker_disk_guard.py
  ops/gate08_legacy_unit_retirement.py
  ops/hash_verified_python_loader.py
  ops/install-disk-guard.sh
  ops/production-deploy-remote-entrypoint.sh
  ops/production-release-gate-check.sh
  ops/production-release-state.json
  ops/production-storage-lease.sh
  ops/production_release_gate.py
  ops/sudoers/sealai-storage-preflight
  ops/schemas/gate08-legacy-units.schema.json
  ops/systemd/sealai-disk-guard.service
  ops/systemd/sealai-disk-guard.timer
  ops/tmpfiles/sealai-storage-mutation.conf
)

for relative in "${ARTIFACTS[@]}"; do
  [[ -f "${REPO_ROOT}/${relative}" ]] || {
    printf 'disk-guard installer: required source missing\n' >&2
    exit 66
  }
done

if [[ "${APPLY}" -eq 0 ]]; then
  printf '%s\n' \
    'disk-guard installer dry-run: no files changed' \
    'requires the verified bootstrap root-clone and exact GATE-08 receipt' \
    'would stage and re-hash every approved artifact before installation' \
    'would fingerprint and retire exactly the two approved legacy systemd units' \
    'would retire exactly the destructive legacy cron line and preserve all others' \
    'would install the storage lease, lock policy, guard, and systemd timer' \
    'would enable the timer and verify one root-owned observation' \
    'external alert delivery remains BLOCKED_EXTERNAL'
  exit 0
fi

if [[ "${EUID}" -ne 0 ]]; then
  printf 'disk-guard installer: --apply requires root\n' >&2
  exit 77
fi

# Defense in depth: the root bootstrap already created and verified this clone.
# Recheck the lexical invocation path, every artifact ancestor, and .git before
# executing even the hash-bound release-gate program from the checkout.
/usr/bin/python3 -I - \
  "${SCRIPT_INVOKED_PATH}" "${REPO_ROOT}" "${ARTIFACTS[@]}" <<'PY'
import os
from pathlib import Path
import stat
import sys


def fail() -> None:
    raise SystemExit("disk-guard installer: source checkout topology is unsafe")


def verify(path: Path, *, leaf_directory: bool) -> None:
    absolute = Path(os.path.abspath(path))
    current = Path(absolute.anchor)
    parts = (absolute.anchor, *absolute.parts[1:])
    for index, part in enumerate(parts):
        if index:
            current /= part
        try:
            metadata = current.lstat()
        except OSError:
            fail()
        is_leaf = current == absolute
        expected_directory = leaf_directory if is_leaf else True
        if (
            stat.S_ISLNK(metadata.st_mode)
            or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) & 0o022
            or (expected_directory and not stat.S_ISDIR(metadata.st_mode))
            or (not expected_directory and not stat.S_ISREG(metadata.st_mode))
        ):
            fail()


invoked = Path(sys.argv[1])
repo = Path(sys.argv[2])
artifacts = tuple(sys.argv[3:])
if ".." in invoked.parts or ".." in repo.parts:
    fail()
verify(invoked, leaf_directory=False)
verify(repo, leaf_directory=True)
verify(repo / ".git", leaf_directory=True)
if invoked.resolve(strict=True) != (repo / "ops/install-disk-guard.sh").resolve(
    strict=True
):
    fail()
for relative in artifacts:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        fail()
    verify(repo / relative_path, leaf_directory=False)
PY

# The shared invocation boundary isolates system Python and validates the exact
# success document. The gate validates the exact commit and source artifacts;
# its JSON decision is then used to re-hash a root-private staged copy, closing
# the source TOCTOU gap.
# shellcheck source=production-release-gate-check.sh
source "${SOURCE_DIR}/production-release-gate-check.sh"
production_release_gate_check \
  "${SOURCE_DIR}/production_release_gate.py" remediation-control-install
GATE_DECISION="${PRODUCTION_RELEASE_GATE_DECISION}"
STAGE_DIR="$(mktemp -d /run/sealai-remediation-control.XXXXXX)"
chmod 700 "${STAGE_DIR}"
cleanup() {
  rm -r -- "${STAGE_DIR}" 2>/dev/null || true
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
import pathlib
import sys

decision = json.loads(sys.argv[1])
stage = pathlib.Path(sys.argv[2])
base = {"allowed", "operation", "reason", "state_id", "required_gate"}
if (
    set(decision)
    != base | {"source_git_sha", "approval_id", "artifact_sha256"}
    or decision.get("allowed") is not True
    or decision.get("operation") != "remediation-control-install"
    or decision.get("reason")
    != "gate08_hash_bound_remediation_control_install"
    or decision.get("required_gate") != "GATE-08"
):
    raise SystemExit("staged control authorization decision is invalid")
expected = decision.get("artifact_sha256")
if not isinstance(expected, dict) or not expected:
    raise SystemExit("staged control verification failed")
actual_paths = {
    str(path.relative_to(stage)) for path in stage.rglob("*") if path.is_file()
}
if actual_paths != set(expected):
    raise SystemExit("staged control artifact set mismatch")
for relative, claimed in expected.items():
    actual = hashlib.sha256((stage / relative).read_bytes()).hexdigest()
    if actual != claimed:
        raise SystemExit("staged control artifact hash mismatch")
PY

# The staged and hash-bound helper neutralizes only the two fixed legacy units.
# It intentionally has no rollback path that could reactivate destructive automation.
/usr/bin/python3 -I "${STAGE_DIR}/ops/gate08_legacy_unit_retirement.py" \
  apply \
  --manifest /etc/sealai/approvals/gate-08-legacy-units.json \
  --evidence-root /var/lib/sealai-disk-guard/legacy-unit-evidence
systemd-analyze verify \
  "${STAGE_DIR}/ops/systemd/sealai-disk-guard.service" \
  "${STAGE_DIR}/ops/systemd/sealai-disk-guard.timer"

# Capture and validate the exact destructive cron entry before any installed
# control changes. Absence/duplication is fingerprint drift and stops the gate.
CRON_BEFORE="${STAGE_DIR}/crontab.before"
CRON_AFTER="${STAGE_DIR}/crontab.after"
crontab -u "${LEGACY_CRON_USER}" -l >"${CRON_BEFORE}" 2>/dev/null || {
  printf 'disk-guard installer: legacy crontab unavailable\n' >&2
  exit 79
}
LEGACY_COUNT="$(awk -v exact="${LEGACY_CRON_LINE}" '$0 == exact { count++ } END { print count+0 }' "${CRON_BEFORE}")"
case "${LEGACY_COUNT}" in
  0|1) ;;
  *)
    printf 'disk-guard installer: legacy cron fingerprint drift\n' >&2
    exit 79
    ;;
esac
awk -v exact="${LEGACY_CRON_LINE}" '$0 != exact { print }' \
  "${CRON_BEFORE}" >"${CRON_AFTER}"

if [[ "${LEGACY_COUNT}" == 1 ]]; then
  # Neutralize the old automatic prune before installing the replacement. A
  # failed later step intentionally does not restore destructive automation.
  crontab -u "${LEGACY_CRON_USER}" "${CRON_AFTER}"
  if crontab -u "${LEGACY_CRON_USER}" -l | grep -Fqx "${LEGACY_CRON_LINE}"; then
    printf 'disk-guard installer: legacy cron retirement failed\n' >&2
    exit 79
  fi
else
  printf 'disk-guard installer: legacy cron entry already retired, skipping removal\n'
fi
if pgrep -f '[/]home/thorsten/sealai/ops/disk_safeguard[.]sh' >/dev/null; then
  printf 'disk-guard installer: legacy cleanup process still running\n' >&2
  exit 79
fi

install -d -m 0700 /var/lib/sealai-disk-guard
install -m 0600 -o root -g root "${CRON_BEFORE}" \
  /var/lib/sealai-disk-guard/legacy-crontab.before-gate08

install -d -m 0755 -o root -g root /usr/local/libexec /usr/local/libexec/sealai
install -m 0755 -o root -g root "${STAGE_DIR}/ops/docker_disk_guard.py" \
  /usr/local/libexec/sealai/docker_disk_guard.py
install -m 0755 -o root -g root "${STAGE_DIR}/ops/docker-disk-guard.sh" \
  /usr/local/libexec/sealai/docker-disk-guard.sh
install -m 0644 -o root -g root "${STAGE_DIR}/ops/production-storage-lease.sh" \
  /usr/local/libexec/sealai/production-storage-lease.sh
install -m 0755 -o root -g root \
  "${STAGE_DIR}/ops/production-release-gate-check.sh" \
  /usr/local/libexec/sealai/production-release-gate-check.sh
install -m 0755 -o root -g root \
  "${STAGE_DIR}/ops/production-deploy-remote-entrypoint.sh" \
  /usr/local/libexec/sealai/production-deploy-remote-entrypoint.sh
install -m 0755 -o root -g root \
  "${STAGE_DIR}/ops/hash_verified_python_loader.py" \
  /usr/local/libexec/sealai/hash-verified-python-loader.py

for trusted_path in /usr/local /usr/local/libexec /usr/local/libexec/sealai; do
  [[ "$(stat -Lc '%F:%a:%U:%G' "${trusted_path}")" == 'directory:755:root:root' ]] || {
    printf 'disk-guard installer: privileged helper ancestor is unsafe\n' >&2
    exit 78
  }
done
[[ "$(stat -Lc '%F:%a:%U:%G' /usr/local/libexec/sealai/docker-disk-guard.sh)" == \
  'regular file:755:root:root' ]] || exit 78
[[ "$(stat -Lc '%F:%a:%U:%G' /usr/local/libexec/sealai/docker_disk_guard.py)" == \
  'regular file:755:root:root' ]] || exit 78
[[ "$(stat -Lc '%F:%a:%U:%G' /usr/local/libexec/sealai/production-storage-lease.sh)" == \
  'regular file:644:root:root' ]] || exit 78
[[ "$(stat -Lc '%F:%a:%U:%G' /usr/local/libexec/sealai/production-release-gate-check.sh)" == \
  'regular file:755:root:root' ]] || exit 78
[[ "$(stat -Lc '%F:%a:%U:%G' /usr/local/libexec/sealai/production-deploy-remote-entrypoint.sh)" == \
  'regular file:755:root:root' ]] || exit 78
[[ ! -L /usr/local/libexec/sealai/hash-verified-python-loader.py ]] || exit 78
[[ "$(stat -Lc '%F:%a:%U:%G' /usr/local/libexec/sealai/hash-verified-python-loader.py)" == \
  'regular file:755:root:root' ]] || exit 78
[[ "$(sha256sum "${STAGE_DIR}/ops/hash_verified_python_loader.py" | awk '{print $1}')" == \
  "$(sha256sum /usr/local/libexec/sealai/hash-verified-python-loader.py | awk '{print $1}')" ]] || {
  printf 'disk-guard installer: trusted loader hash verification failed\n' >&2
  exit 78
}

install -d -m 0700 -o root -g root /etc/sealai
if [[ -L /etc/sealai/disk-guard.json ]]; then
  printf 'disk-guard installer: refusing symlinked configuration\n' >&2
  exit 78
fi
if [[ ! -e /etc/sealai/disk-guard.json ]]; then
  install -m 0600 -o root -g root \
    "${STAGE_DIR}/ops/disk-guard.example.json" /etc/sealai/disk-guard.json
fi

install -d -m 0755 /usr/local/share/doc/sealai
install -m 0644 "${STAGE_DIR}/docs/ops/docker-disk-guard.md" \
  /usr/local/share/doc/sealai/docker-disk-guard.md
install -m 0644 "${STAGE_DIR}/ops/systemd/sealai-disk-guard.service" \
  /etc/systemd/system/sealai-disk-guard.service
install -m 0644 "${STAGE_DIR}/ops/systemd/sealai-disk-guard.timer" \
  /etc/systemd/system/sealai-disk-guard.timer
install -m 0644 "${STAGE_DIR}/ops/tmpfiles/sealai-storage-mutation.conf" \
  /etc/tmpfiles.d/sealai-storage-mutation.conf
visudo -cf "${STAGE_DIR}/ops/sudoers/sealai-storage-preflight" >/dev/null
install -m 0440 -o root -g root \
  "${STAGE_DIR}/ops/sudoers/sealai-storage-preflight" \
  /etc/sudoers.d/sealai-storage-preflight

test -x /usr/local/libexec/sealai/docker-disk-guard.sh
test -r /usr/local/libexec/sealai/production-storage-lease.sh
test -x /usr/local/libexec/sealai/production-release-gate-check.sh
test -x /usr/local/libexec/sealai/production-deploy-remote-entrypoint.sh
test -x /usr/local/libexec/sealai/hash-verified-python-loader.py
/usr/bin/python3 -I /usr/local/libexec/sealai/docker_disk_guard.py --help >/dev/null
systemd-tmpfiles --create /etc/tmpfiles.d/sealai-storage-mutation.conf
test "$(stat -Lc '%F:%a:%U:%G' /run/lock/sealai-storage-mutation.lock)" = \
  'regular file:660:root:thorsten'

CONFIGURED_DOCKER_ROOT="$(/usr/bin/python3 -I - /etc/sealai/disk-guard.json <<'PY'
import json
import pathlib
import sys

value = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
root = value.get("docker_root_dir")
if not isinstance(root, str) or not root.startswith("/"):
    raise SystemExit(78)
print(root)
PY
)"
ACTUAL_DOCKER_ROOT="$(docker info --format '{{.DockerRootDir}}')"
[[ "${CONFIGURED_DOCKER_ROOT}" == "${ACTUAL_DOCKER_ROOT}" ]] || {
  printf 'disk-guard installer: Docker root/config mismatch\n' >&2
  exit 78
}

systemd-analyze verify \
  /etc/systemd/system/sealai-disk-guard.service \
  /etc/systemd/system/sealai-disk-guard.timer
systemctl daemon-reload
systemctl enable --now sealai-disk-guard.timer
systemctl start sealai-disk-guard.service
systemctl is-enabled --quiet sealai-disk-guard.timer
systemctl is-active --quiet sealai-disk-guard.timer
! systemctl is-active --quiet sealai-docker-disk-guard.timer
! systemctl is-enabled --quiet sealai-docker-disk-guard.timer
test -s /var/lib/sealai-disk-guard/state.json
test "$(stat -c '%a:%U:%G' /var/lib/sealai-disk-guard/state.json)" = \
  '600:root:root'
set +e
sudo -u thorsten /bin/bash -p -c \
  'source /usr/local/libexec/sealai/production-storage-lease.sh; acquire_production_storage_lease' \
  >/dev/null
PREFLIGHT_RC=$?
set -e
[[ "${PREFLIGHT_RC}" == 0 || "${PREFLIGHT_RC}" == 22 ]] || {
  printf 'disk-guard installer: delegated preflight verification failed\n' >&2
  exit 78
}

printf '%s\n' \
  'disk-guard GATE-08 install completed' \
  'legacy destructive cron line and exact legacy systemd timer retired' \
  'storage mutation lease installed and initial guard observation verified' \
  'normal application release freeze remains active' \
  'external alert delivery remains BLOCKED_EXTERNAL'
