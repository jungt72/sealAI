#!/bin/bash -p
# Run eval-REPLAY in the exact RC image against isolated, attested RC data and a
# deterministic local provider stub. Stub model IDs make the result explicitly
# non-eligible; production eligibility requires a separate approved evidence lane.
set -euo pipefail
readonly PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH

readonly SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
readonly REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd -P)"
cd "${REPO_ROOT}"

# rc.env is parsed as strict literal data. Inherited provider/serving/Docker
# variables are rejected before any Git or Docker operation.
# shellcheck source=staging/rc-contract.sh
source "${REPO_ROOT}/ops/staging/rc-contract.sh"
rc_contract_load "${REPO_ROOT}" eval
rc_contract_assert_nonproduction_checkout "${REPO_ROOT}"

readonly TREE_HASH="$(/bin/bash -p ops/tree-hash.sh)"
readonly GIT_SHA="$(/usr/bin/git rev-parse HEAD)"
[[ "${TREE_HASH}" =~ ^[0-9a-f]{40}$ ]] || {
  printf '%s\n' 'ops/run_eval.sh: invalid served-tree hash' >&2
  exit 78
}
[[ "${GIT_SHA}" =~ ^[0-9a-f]{40}([0-9a-f]{24})?$ ]] || {
  printf '%s\n' 'ops/run_eval.sh: invalid Git commit' >&2
  exit 78
}
rc_contract_assert_served_tree_binding "${REPO_ROOT}" "${GIT_SHA}"

readonly EVAL_IMAGE="localhost/sealai-rc-backend:eval-${TREE_HASH:0:12}"
readonly COMPOSE_FILE="${REPO_ROOT}/ops/staging/docker-compose.staging.yml"

# External seeders must create these exact hash-derived volumes and label their
# successful non-empty/sanitized verification. A missing/blank/unattested volume
# blocks before build or container creation.
rc_contract_assert_snapshot_volumes /usr/bin/docker

COMPOSE=(
  /usr/bin/env -i
  HOME=/nonexistent
  PATH=/usr/sbin:/usr/bin:/sbin:/bin
  LANG=C
  LC_ALL=C
  DOCKER_HOST=unix:///var/run/docker.sock
  COMPOSE_DISABLE_ENV_FILE=1
  "RC_BACKEND_IMAGE=${EVAL_IMAGE}"
  "RC_TREE_HASH=${TREE_HASH}"
  "RC_GIT_SHA=${GIT_SHA}"
  /usr/bin/docker compose
  --env-file "${RC_ENV_FILE}"
  -f "${COMPOSE_FILE}"
  --profile rc-eval
)

"${COMPOSE[@]}" build rc-eval

readonly POST_BUILD_TREE_HASH="$(/bin/bash -p ops/tree-hash.sh)"
[[ "${POST_BUILD_TREE_HASH}" == "${TREE_HASH}" ]] || {
  printf '%s\n' 'ops/run_eval.sh: served tree changed during candidate build' >&2
  exit 78
}

readonly IMAGE_ID="$(
  /usr/bin/env -i \
    HOME=/nonexistent \
    PATH=/usr/sbin:/usr/bin:/sbin:/bin \
    DOCKER_HOST=unix:///var/run/docker.sock \
    /usr/bin/docker image inspect --format '{{.Id}}' "${EVAL_IMAGE}"
)"
[[ "${IMAGE_ID}" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  printf '%s\n' 'ops/run_eval.sh: candidate image has no immutable image ID' >&2
  exit 78
}

# Re-resolve the service with the immutable ID, not the mutable build tag. A
# concurrent retag therefore cannot change the image executed by the replay.
EVAL_COMPOSE=(
  /usr/bin/env -i
  HOME=/nonexistent
  PATH=/usr/sbin:/usr/bin:/sbin:/bin
  LANG=C
  LC_ALL=C
  DOCKER_HOST=unix:///var/run/docker.sock
  COMPOSE_DISABLE_ENV_FILE=1
  "RC_BACKEND_IMAGE=${IMAGE_ID}"
  "RC_TREE_HASH=${TREE_HASH}"
  "RC_GIT_SHA=${GIT_SHA}"
  /usr/bin/docker compose
  --env-file "${RC_ENV_FILE}"
  -f "${COMPOSE_FILE}"
  --profile rc-eval
)

/bin/mkdir -p backend/sealai_v2/eval/runs
readonly HOST_UID="$(/usr/bin/id -u)"
readonly HOST_GID="$(/usr/bin/id -g)"

printf '%s\n' \
  'RC_STUB_NON_ELIGIBLE: isolated runtime/retrieval check only; never production evidence.' >&2

# --no-deps is load-bearing: this command never creates a blank database/Qdrant
# or silently starts an unattested provider. The independently prepared RC data
# and stub services must already be healthy on their isolated RC networks.
"${EVAL_COMPOSE[@]}" run --rm --no-deps \
  --user "${HOST_UID}:${HOST_GID}" \
  --entrypoint /bin/sh \
  -e "SEALAI_EVAL_TREE_HASH=${TREE_HASH}" \
  -e "SEALAI_EVAL_GIT_SHA=${GIT_SHA}" \
  -e "SEALAI_EVAL_IMAGE_DIGEST=${IMAGE_ID}" \
  -e SEALAI_EVAL_DIRTY=false \
  rc-eval -c '
set -eu
python - <<PY
from sqlalchemy import create_engine, text
from qdrant_client import QdrantClient
import httpx
import re

from sealai_v2.config.settings import Settings

settings = Settings()
if (
    settings.retriever_backend != "qdrant"
    or not settings.database_url
    or settings.qdrant_url != "http://rc-qdrant:6333"
    or settings.mistral_base_url != "http://rc-llm-stub:8080/v1"
    or re.fullmatch(
        r"sha256:[0-9a-f]{64}", settings.knowledge_authority_epoch or ""
    ) is None
):
    raise SystemExit("RC preflight: invalid DB/Qdrant/provider contract")

try:
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        table_count = connection.execute(
            text(
                "SELECT count(*) FROM pg_catalog.pg_tables "
                "WHERE schemaname NOT IN (\047pg_catalog\047, \047information_schema\047)"
            )
        ).scalar_one()
except Exception:
    raise SystemExit("RC preflight: Postgres unavailable") from None
if table_count < 2:
    raise SystemExit("RC preflight: Postgres snapshot is empty")

try:
    qdrant = QdrantClient(url=settings.qdrant_url, timeout=10)
    knowledge = qdrant.get_collection(settings.qdrant_collection)
    qdrant.get_collection(settings.memory_qdrant_collection)
except Exception:
    raise SystemExit("RC preflight: Qdrant unavailable or collection missing") from None
if not isinstance(knowledge.points_count, int) or knowledge.points_count < 1:
    raise SystemExit("RC preflight: Qdrant knowledge collection is empty")

try:
    response = httpx.get("http://rc-llm-stub:8080/health", timeout=5)
    response.raise_for_status()
except Exception:
    raise SystemExit("RC preflight: provider stub unavailable") from None
PY
exec python -m sealai_v2.eval "$@"
' sh "$@"
