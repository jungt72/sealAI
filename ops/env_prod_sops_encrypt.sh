#!/bin/bash
# Encrypts the live .env.prod into the git-tracked ops/env-prod.sops
# (sops+age, per-key dotenv encryption -- keys stay readable, values don't).
# Run this after every edit to .env.prod, then commit ops/env-prod.sops.
# Never modifies .env.prod itself; requires no key material beyond the age
# public key already pinned in .sops.yaml.
#
# The output deliberately does not live at a .env*-shaped path:
# ops/check-secret-hygiene.py's filename.env rule rejects any committed file
# that looks like an env file by name alone, regardless of content.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"
SOPS_BIN="${SOPS_BIN:-sops}"
OUT="ops/env-prod.sops"

[[ -f .env.prod ]] || { echo "env_prod_sops_encrypt: .env.prod not found" >&2; exit 1; }
command -v "${SOPS_BIN}" >/dev/null 2>&1 || { echo "env_prod_sops_encrypt: '${SOPS_BIN}' not found (see docs/ops/env-prod-sops-encryption.md)" >&2; exit 1; }

mkdir -p secrets
"${SOPS_BIN}" --input-type dotenv --output-type dotenv -e .env.prod > "${OUT}.tmp"
mv "${OUT}.tmp" "${OUT}"
echo "env_prod_sops_encrypt: encrypted .env.prod -> ${OUT}"
echo "next: git add ${OUT} && git commit"
