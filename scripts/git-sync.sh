#!/usr/bin/env bash
set -euo pipefail
cd /root/sealai
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
# Nur wenn etwas zu committen ist
if [[ -z "$(git status --porcelain)" ]]; then exit 0; fi
git add -A
git commit -m "chore(sync): $(hostname -s) $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
git pull --rebase --autostash origin "$BRANCH" || true
git push origin "HEAD:$BRANCH"
