#!/usr/bin/env bash
set -euo pipefail
cd /root/sealai
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
before="$(git rev-parse HEAD)"

git fetch origin
git merge --ff-only "origin/$BRANCH" || true
after="$(git rev-parse HEAD)"

changed=false
if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -m "chore(sync): $(hostname -s) $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  git pull --rebase --autostash origin "$BRANCH" || true
  git push origin "HEAD:$BRANCH"
  changed=true
fi

# Rebuild, wenn Pull oder Commit den HEAD geändert hat
if [[ "$before" != "$after" || "$changed" == true ]]; then
  docker compose -f /root/sealai/docker-compose.yml up -d --build backend
fi
