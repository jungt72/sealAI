#!/usr/bin/env bash
set -euo pipefail
cd /root/sealai
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
git fetch origin
git merge --ff-only "origin/$BRANCH" || true
if [[ -n "$(git status --porcelain)" ]]; then
  git add -A
  git commit -m "chore(sync): $(hostname -s) $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
  git pull --rebase --autostash origin "$BRANCH" || true
  git push origin "HEAD:$BRANCH"
fi
