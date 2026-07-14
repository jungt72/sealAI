#!/bin/bash -p
set -euo pipefail
readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

# Token-free verification of GitHub Artifact Attestations through Sigstore.
# The Cosign runtime is immutable and intentionally runs as a container so the
# production host does not need a mutable CLI installation or GitHub token.
readonly COSIGN_IMAGE="ghcr.io/sigstore/cosign/cosign:v3.1.1@sha256:6bbe0d281d955c79f85b325f0f7e651c1bcab5a4fa4ad4903d74955178a3b2eb"
readonly GITHUB_REPOSITORY="jungt72/sealAI"
readonly OIDC_ISSUER="https://token.actions.githubusercontent.com"
readonly SCAN_PREDICATE_TYPE="https://sealingai.com/attestations/trivy-scan/v1"

IMAGE_REF="${1:-}"
EXPECTED_REVISION="${2:-}"
WORKFLOW_PATH="${3:-}"
EXPECTED_TREE_HASH="${4:-}"

if [[ ! "${IMAGE_REF}" =~ ^ghcr\.io/jungt72/sealai-backend-v2:[A-Za-z0-9][A-Za-z0-9._-]{0,127}@sha256:[0-9a-f]{64}$ || ! "${EXPECTED_REVISION}" =~ ^[0-9a-f]{40}$ || "${WORKFLOW_PATH}" != ".github/workflows/build-and-push.yml" ]]; then
  echo "usage: $0 ghcr.io/jungt72/sealai-backend-v2:TAG@sha256:DIGEST GIT_SHA .github/workflows/build-and-push.yml [TREE_HASH]" >&2
  exit 2
fi

name_with_tag="${IMAGE_REF%@sha256:*}"
last_component="${name_with_tag##*/}"
if [[ "${last_component}" == *:* ]]; then
  IMAGE_NAME="${name_with_tag%:*}"
else
  IMAGE_NAME="${name_with_tag}"
fi
IMAGE_DIGEST="sha256:${IMAGE_REF##*@sha256:}"
CERTIFICATE_IDENTITY="https://github.com/${GITHUB_REPOSITORY}/${WORKFLOW_PATH}@refs/heads/main"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${EXPECTED_TREE_HASH}" ]]; then
  EXPECTED_TREE_HASH="$(cd "${ROOT_DIR}" && /bin/bash -p ops/tree-hash.sh)"
fi
[[ "${EXPECTED_TREE_HASH}" =~ ^[0-9a-f]{40}$ ]] || {
  echo "expected tree hash is invalid" >&2
  exit 2
}
POLICY_SHA256="$(/usr/bin/sha256sum "${ROOT_DIR}/security/supply-chain-policy.json" | /usr/bin/awk '{print $1}')"
EXCEPTIONS_SHA256="$(/usr/bin/sha256sum "${ROOT_DIR}/security/supply-chain-exceptions.json" | /usr/bin/awk '{print $1}')"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

verify_one() {
  local predicate_type="$1" output_file="$2"
  /usr/bin/docker run --rm "${COSIGN_IMAGE}" verify-attestation \
    --type "${predicate_type}" \
    --certificate-identity "${CERTIFICATE_IDENTITY}" \
    --certificate-oidc-issuer "${OIDC_ISSUER}" \
    "${IMAGE_REF}" >"${output_file}"
  /usr/bin/python3 -I "${ROOT_DIR}/ops/verify_attestation_payload.py" "${output_file}" \
    --image-name "${IMAGE_NAME}" \
    --image-digest "${IMAGE_DIGEST}" \
    --predicate-type "${predicate_type}" \
    --expected-revision "${EXPECTED_REVISION}" \
    --expected-tree-hash "${EXPECTED_TREE_HASH}" \
    --repository "${GITHUB_REPOSITORY}" \
    --workflow-path "${WORKFLOW_PATH}" \
    --policy-sha256 "${POLICY_SHA256}" \
    --exceptions-sha256 "${EXCEPTIONS_SHA256}" >/dev/null
}

verify_one "https://slsa.dev/provenance/v1" "${tmp_dir}/provenance.jsonl"
verify_one "https://spdx.dev/Document/v2.3" "${tmp_dir}/sbom.jsonl"
verify_one "${SCAN_PREDICATE_TYPE}" "${tmp_dir}/scan.jsonl"
printf 'verified image attestations: %s (%s)\n' "${IMAGE_REF}" "${EXPECTED_REVISION}"
