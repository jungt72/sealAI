#!/bin/bash
# Decrypts the git-tracked ops/env-prod.sops into the live .env.prod.
# Requires the age private key at ~/.config/sops/age/keys.txt (never
# committed). Refuses to overwrite an existing .env.prod unless FORCE=1, and
# always backs up the previous file first regardless -- its sibling,
# ops/rotate_env_rollbacks.sh, already prunes these backups weekly.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"
SOPS_BIN="${SOPS_BIN:-sops}"
FORCE="${FORCE:-0}"
IN="ops/env-prod.sops"

[[ -f "${IN}" ]] || { echo "env_prod_sops_decrypt: ${IN} not found" >&2; exit 1; }
command -v "${SOPS_BIN}" >/dev/null 2>&1 || { echo "env_prod_sops_decrypt: '${SOPS_BIN}' not found (see docs/ops/env-prod-sops-encryption.md)" >&2; exit 1; }

if [[ -f .env.prod ]]; then
  if [[ "${FORCE}" != "1" ]]; then
    echo "env_prod_sops_decrypt: .env.prod already exists; refusing to overwrite. Set FORCE=1 to proceed (a timestamped backup is taken first either way)." >&2
    exit 1
  fi
  cp .env.prod ".env.prod.bak-pre-sops-decrypt-$(date -u +%Y%m%d-%H%M%S)"
fi

"${SOPS_BIN}" --input-type dotenv --output-type dotenv -d "${IN}" > .env.prod.tmp
mv .env.prod.tmp .env.prod
chmod 600 .env.prod
echo "env_prod_sops_decrypt: decrypted ${IN} -> .env.prod"
