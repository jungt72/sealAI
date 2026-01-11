#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BACKEND_DIR="$ROOT_DIR/backend"
IMAGE_NAME=${BACKEND_BUILDER_IMAGE:-sealai-backend-builder:latest}

if [ ! -f "$BACKEND_DIR/requirements.txt" ]; then
  echo "Missing $BACKEND_DIR/requirements.txt" >&2
  exit 1
fi

echo "Building backend builder image: $IMAGE_NAME"
docker build --target builder -t "$IMAGE_NAME" "$BACKEND_DIR" >/dev/null

set +e
output=$(docker run --rm \
  -v "$BACKEND_DIR:/opt/build" \
  -w /opt/build \
  "$IMAGE_NAME" \
  /bin/sh -lc '
set -e
python -m pip install -U pip >/dev/null
python -m pip install -r requirements.txt
python - <<PY
import fastapi, starlette, pydantic, langgraph, redis, httpx, qdrant_client
print("versions:",
      f"fastapi={fastapi.__version__}",
      f"starlette={starlette.__version__}",
      f"pydantic={pydantic.__version__}",
      f"langgraph={langgraph.__version__}",
      f"redis={redis.__version__}",
      f"qdrant-client={qdrant_client.__version__}",
      f"httpx={httpx.__version__}")
PY
' 2>&1)
status=$?
set -e

if [ $status -ne 0 ]; then
  echo "$output" | tail -n 80
  if echo "$output" | grep -E -q "ResolutionImpossible|conflict|conflicting"; then
    echo "Detected dependency conflict while resolving requirements.txt" >&2
  fi
  exit $status
fi

echo "$output" | grep -E "^versions:"
