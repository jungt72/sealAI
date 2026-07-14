#!/bin/bash -p
set -euo pipefail
umask 077
readonly PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin
export PATH

readonly UV_VERSION="0.11.28"
readonly UV_RELEASE_URL="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}"
readonly PYTHON_VERSION="3.12"
readonly TARGET_PLATFORM="x86_64-manylinux_2_28"

case "$(uname -s):$(uname -m)" in
  Darwin:arm64)
    readonly UV_TARGET="aarch64-apple-darwin"
    readonly UV_ARCHIVE_SHA256="33540eb7c883ab857eff79bd5ac2aa31fe27b595abecb4a9c003a2c998447232"
    ;;
  Darwin:x86_64)
    readonly UV_TARGET="x86_64-apple-darwin"
    readonly UV_ARCHIVE_SHA256="2ad79983127ffca7d77b77ce6a24278d7e4f7b817a1acf72fea5f8124b4aac5e"
    ;;
  Linux:aarch64)
    readonly UV_TARGET="aarch64-unknown-linux-gnu"
    readonly UV_ARCHIVE_SHA256="03e9fe0a81b0718d0bc84625de3885df6cc3f89a8b6af6121d6b9f6113fb6533"
    ;;
  Linux:x86_64)
    readonly UV_TARGET="x86_64-unknown-linux-gnu"
    readonly UV_ARCHIVE_SHA256="e490a6464492183c5d4534a5527fb4440f7f2bb2f228162ad7e4afe076dc0224"
    ;;
  *)
    echo "unsupported lock-generator platform" >&2
    exit 2
    ;;
esac

ROOT="$(git rev-parse --show-toplevel)"
cd "${ROOT}"
TOOL_DIR="$(mktemp -d "${TMPDIR:-/tmp}/sealai-uv.XXXXXX")"
trap 'rm -rf "${TOOL_DIR}"' EXIT
UV_ARCHIVE="${TOOL_DIR}/uv-${UV_TARGET}.tar.gz"

curl --proto '=https' --tlsv1.2 --fail --location --silent --show-error \
  "${UV_RELEASE_URL}/uv-${UV_TARGET}.tar.gz" --output "${UV_ARCHIVE}"
python3 -I - "${UV_ARCHIVE}" "${UV_ARCHIVE_SHA256}" <<'PY'
import hashlib
import sys
from pathlib import Path

path = Path(sys.argv[1])
expected = sys.argv[2]
actual = hashlib.sha256(path.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"uv archive digest mismatch: {actual}")
PY
tar -xzf "${UV_ARCHIVE}" -C "${TOOL_DIR}"
readonly UV_BIN="${TOOL_DIR}/uv-${UV_TARGET}/uv"
[[ -x "${UV_BIN}" ]] || { echo "verified uv executable is missing" >&2; exit 2; }
[[ "$("${UV_BIN}" --version)" == "uv ${UV_VERSION}"* ]] || {
  echo "verified uv archive reports an unexpected version" >&2
  exit 2
}

compile() {
  local input="$1" output="$2" temporary
  temporary="$(mktemp "${TMPDIR:-/tmp}/sealai-lock.XXXXXX")"
  trap 'rm -f "${temporary}"' RETURN
  "${UV_BIN}" pip compile "${input}" \
    --output-file "${temporary}" \
    --python-version "${PYTHON_VERSION}" \
    --python-platform "${TARGET_PLATFORM}" \
    --only-binary :all: \
    --generate-hashes \
    --no-emit-package pip \
    --custom-compile-command 'ops/update-python-locks.sh' \
    --no-cache \
    --quiet
  chmod 0644 "${temporary}"
  mv "${temporary}" "${output}"
  trap - RETURN
}

compile backend/requirements-v2.txt backend/requirements-v2.lock
compile backend/requirements-ci.txt backend/requirements-ci.lock
compile security/tools/requirements.txt security/tools/requirements.lock

# Bind the reviewed inputs and newly generated locks in the machine-readable
# policy. The resulting policy diff is part of the dependency-update review.
python3 -I - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path.cwd()
path = root / "security" / "supply-chain-policy.json"
policy = json.loads(path.read_text(encoding="utf-8"))
for item in policy["python_locks"]:
    for path_key, digest_key in (("input", "input_sha256"), ("lock", "lock_sha256")):
        item[digest_key] = hashlib.sha256((root / item[path_key]).read_bytes()).hexdigest()
temporary = path.with_suffix(".json.tmp")
temporary.write_text(json.dumps(policy, indent=2) + "\n", encoding="utf-8")
temporary.replace(path)
PY

python3 -I ops/supply_chain_gate.py verify
echo "locks regenerated with verified uv ${UV_VERSION}; review every dependency diff" >&2
