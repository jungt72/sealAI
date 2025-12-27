#!/usr/bin/env bash
set -euo pipefail

EXPECTED_NEXT_VERSION="${EXPECTED_NEXT_VERSION:-16.0.10}"
BUILD_ID="${BUILD_ID:-$(git rev-parse --short HEAD 2>/dev/null || echo dev)}"
export BUILD_ID

echo "BUILD_ID=${BUILD_ID}"
echo "EXPECTED_NEXT_VERSION=${EXPECTED_NEXT_VERSION}"

compose_config="$(docker compose config)"
echo "${compose_config}" | grep -q "image: sealai-frontend:${BUILD_ID}"
echo "${compose_config}" | grep -q "context: ./frontend"
echo "${compose_config}" | grep -q "BUILD_ID: ${BUILD_ID}"

docker compose build --no-cache frontend
docker compose up -d --force-recreate frontend

next_from_node="$(docker exec frontend node -p "require('next/package.json').version")"
next_from_file="$(docker exec frontend cat /app/NEXT_VERSION)"
build_id_from_file="$(docker exec frontend cat /app/BUILD_ID)"
build_id_from_label="$(docker inspect frontend --format '{{ index .Config.Labels \"org.opencontainers.image.revision\" }}')"

echo "next (node)=${next_from_node}"
echo "next (/app/NEXT_VERSION)=${next_from_file}"
echo "build (/app/BUILD_ID)=${build_id_from_file}"
echo "build (label org.opencontainers.image.revision)=${build_id_from_label}"

test "${next_from_node}" = "${EXPECTED_NEXT_VERSION}"
test "${next_from_node}" = "${next_from_file}"
test "${build_id_from_file}" = "${BUILD_ID}"
test "${build_id_from_label}" = "${BUILD_ID}"
