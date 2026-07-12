#!/usr/bin/env bash
set -euo pipefail

# Token-free verification of GitHub Artifact Attestations through Sigstore.
# The Cosign runtime is immutable and intentionally runs as a container so the
# production host does not need a mutable CLI installation or GitHub token.
readonly COSIGN_IMAGE="ghcr.io/sigstore/cosign/cosign:v3.1.1@sha256:6bbe0d281d955c79f85b325f0f7e651c1bcab5a4fa4ad4903d74955178a3b2eb"
readonly GITHUB_REPOSITORY="jungt72/sealAI"
readonly OIDC_ISSUER="https://token.actions.githubusercontent.com"

IMAGE_REF="${1:-}"
EXPECTED_REVISION="${2:-}"
WORKFLOW_PATH="${3:-}"

if [[ "${IMAGE_REF}" != *@sha256:* || ! "${EXPECTED_REVISION}" =~ ^[0-9a-f]{40}$ || "${WORKFLOW_PATH}" != .github/workflows/*.yml ]]; then
  echo "usage: $0 IMAGE_TAG@sha256:DIGEST GIT_SHA .github/workflows/WORKFLOW.yml" >&2
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
tmp_dir="$(mktemp -d)"
trap 'rm -rf "${tmp_dir}"' EXIT

verify_one() {
  local predicate_type="$1" output_file="$2"
  docker run --rm "${COSIGN_IMAGE}" verify-attestation \
    --type "${predicate_type}" \
    --certificate-identity "${CERTIFICATE_IDENTITY}" \
    --certificate-oidc-issuer "${OIDC_ISSUER}" \
    "${IMAGE_REF}" >"${output_file}"
  python3 "${ROOT_DIR}/ops/verify_attestation_payload.py" "${output_file}" \
    --image-name "${IMAGE_NAME}" \
    --image-digest "${IMAGE_DIGEST}" \
    --predicate-type "${predicate_type}" \
    --expected-revision "${EXPECTED_REVISION}" \
    --repository "${GITHUB_REPOSITORY}" \
    --workflow-path "${WORKFLOW_PATH}" >/dev/null
}

verify_one "https://slsa.dev/provenance/v1" "${tmp_dir}/provenance.jsonl"
verify_one "https://spdx.dev/Document/v2.3" "${tmp_dir}/sbom.jsonl"
printf 'verified image attestations: %s (%s)\n' "${IMAGE_REF}" "${EXPECTED_REVISION}"
