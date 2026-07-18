#!/bin/bash
# Reclaims Docker disk space from sealAI's own image repos: deletes superseded
# untagged builds unconditionally and keeps only the KEEP_TAGGED most recent
# tagged images per repo (rollback/eval snapshots included). Never touches an
# image referenced by any container (running or stopped, checked by image ID,
# not by tag), and never removes -f -- a plain `docker rmi` still refuses if
# an image is actually in use, which is a deliberate second safety net on top
# of the protected-set check below. Never touches any repo outside the
# sealAI allowlist: this host also runs unrelated projects (prelon, crm,
# erpnext, aktien-research, paperless, rybbit, ...) whose images are not ours
# to manage here. Idempotent, safe to run repeatedly.
set -euo pipefail

KEEP_TAGGED="${KEEP_TAGGED:-5}"
DRY_RUN="${DRY_RUN:-0}"
BUILD_CACHE_MAX_AGE="${BUILD_CACHE_MAX_AGE:-168h}"

# sealAI-owned image repos only. Extend this list explicitly for new repos --
# never widen it via a wildcard/pattern match.
REPOS=(
  "ghcr.io/jungt72/sealai-backend-v2"
  "ghcr.io/jungt72/sealai-backend"
  "ghcr.io/jungt72/sealai-frontend"
  "ghcr.io/jungt72/sealai-keycloak"
  "sealai-backend-v2"
  "sealai-backend-v2-staging"
  "sealai-frontend"
  "sealai-keycloak"
)

mapfile -t protected < <(docker ps -aq | xargs -r -n1 docker inspect --format '{{.Image}}' 2>/dev/null | sed 's/^sha256://')

is_protected() {
  local id="$1"
  for p in "${protected[@]}"; do
    [[ "$p" == "$id"* || "$id" == "$p"* ]] && return 0
  done
  return 1
}

total_repos=0
total_deleted=0
total_skipped_protected=0

for repo in "${REPOS[@]}"; do
  mapfile -t rows < <(docker images "$repo" --format '{{.ID}}|{{.Tag}}|{{.CreatedAt}}' 2>/dev/null)
  [ "${#rows[@]}" -eq 0 ] && continue
  total_repos=$((total_repos + 1))

  untagged=()
  tagged=()
  for row in "${rows[@]}"; do
    IFS='|' read -r id tag created <<< "$row"
    if is_protected "$id"; then
      total_skipped_protected=$((total_skipped_protected + 1))
      continue
    fi
    if [ "$tag" = "<none>" ]; then
      untagged+=("$id")
    else
      tagged+=("$row")
    fi
  done

  for id in "${untagged[@]}"; do
    if [ "$DRY_RUN" = "1" ]; then
      echo "would delete (untagged): $repo@$id"
      total_deleted=$((total_deleted + 1))
    elif docker rmi "$id" >/dev/null 2>&1; then
      echo "deleted (untagged): $repo@$id"
      total_deleted=$((total_deleted + 1))
    else
      echo "skip (in use, dependent image, or already gone): $repo@$id"
    fi
  done

  if [ "${#tagged[@]}" -gt "$KEEP_TAGGED" ]; then
    mapfile -t sorted_tagged < <(printf '%s\n' "${tagged[@]}" | sort -t'|' -k3 -r)
    to_delete=("${sorted_tagged[@]:$KEEP_TAGGED}")
    for row in "${to_delete[@]}"; do
      IFS='|' read -r id tag created <<< "$row"
      ref="$repo:$tag"
      if [ "$DRY_RUN" = "1" ]; then
        echo "would delete (tagged, beyond keep=$KEEP_TAGGED): $ref"
        total_deleted=$((total_deleted + 1))
      elif docker rmi "$ref" >/dev/null 2>&1; then
        echo "deleted (tagged): $ref"
        total_deleted=$((total_deleted + 1))
      else
        echo "skip (in use or already gone): $ref"
      fi
    done
  fi
done

verb="deleted"
[ "$DRY_RUN" = "1" ] && verb="would delete"
echo "rotate_docker_images: ${total_repos} sealAI repo(s) scanned, ${total_skipped_protected} protected (in-use) image(s) skipped, ${total_deleted} image(s) ${verb}"

if [ "$DRY_RUN" = "1" ]; then
  echo "would run: docker builder prune -f --filter until=${BUILD_CACHE_MAX_AGE}"
else
  docker builder prune -f --filter "until=${BUILD_CACHE_MAX_AGE}"
fi
