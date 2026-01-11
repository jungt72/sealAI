#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BACKEND_DIR="$ROOT_DIR/backend"
LOCK_FILE="$BACKEND_DIR/requirements-lock.txt"

MODE=${MODE:-}
CONTAINER_NAME=${BACKEND_CONTAINER:-backend}
IMAGE_NAME=${BACKEND_IMAGE:-sealai-backend:dev}
BUILDER_IMAGE_NAME=${BACKEND_BUILDER_IMAGE:-sealai-backend-builder:latest}

if [ "$MODE" = "from-requirements-txt" ]; then
  echo "Generating lock from requirements.txt"
  docker build --target builder -t "$BUILDER_IMAGE_NAME" "$BACKEND_DIR" >/dev/null
  set +e
  output=$(docker run --rm \
    -v "$BACKEND_DIR:/opt/build" \
    -w /opt/build \
    "$BUILDER_IMAGE_NAME" \
    /bin/sh -lc '
set -e
python -m pip install -U pip >/dev/null
python -m pip install -r requirements.txt > /tmp/install.log 2>&1 || { cat /tmp/install.log; exit 1; }
python -m pip freeze
' 2>&1)
  status=$?
  set -e
  if [ $status -ne 0 ]; then
    echo "$output" | tail -n 80
    echo "Failed to resolve requirements.txt; lock not updated." >&2
    exit $status
  fi
  printf "%s\n" "$output" > "$LOCK_FILE"
else
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
fi

if [ ! -s "$LOCK_FILE" ]; then
  echo "Lock file generation failed: $LOCK_FILE" >&2
  exit 1
fi

echo "Wrote $LOCK_FILE"

echo "Key packages:"
key_packages='^(fastapi|starlette|pydantic|langgraph|langgraph-checkpoint-redis|qdrant-client|redis|httpx)=='
grep -E "$key_packages" "$LOCK_FILE" || true
