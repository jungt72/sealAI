#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BACKEND_DIR="$ROOT_DIR/backend"
LOCK_FILE="$BACKEND_DIR/requirements-lock.txt"

CONTAINER_NAME=${BACKEND_CONTAINER:-backend}
IMAGE_NAME=${BACKEND_IMAGE:-sealai-backend:dev}

if docker ps --format '{{.Names}}' | grep -qx "$CONTAINER_NAME"; then
  echo "Using running container: $CONTAINER_NAME"
  docker exec "$CONTAINER_NAME" python3 -m pip freeze > "$LOCK_FILE"
else
  if docker image inspect "$IMAGE_NAME" >/dev/null 2>&1; then
    echo "Using existing image: $IMAGE_NAME"
  else
    echo "Building image: $IMAGE_NAME"
    docker build -t "$IMAGE_NAME" "$BACKEND_DIR"
  fi
  docker run --rm "$IMAGE_NAME" python3 -m pip freeze > "$LOCK_FILE"
fi

if [ ! -s "$LOCK_FILE" ]; then
  echo "Lock file generation failed: $LOCK_FILE" >&2
  exit 1
fi

echo "Wrote $LOCK_FILE"

echo "Key packages:"
key_packages='^(fastapi|starlette|pydantic|langgraph|langgraph-checkpoint-redis|qdrant-client|redis|httpx)=='
grep -E "$key_packages" "$LOCK_FILE" || true
