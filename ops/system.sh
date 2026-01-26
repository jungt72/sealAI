#!/usr/bin/env bash
set -euo pipefail

./ops/system_snapshot.sh

latest="$(ls -1t ops/_snapshots/stack_snapshot_*.md | head -n 1)"

./ops/system_snapshot_bundle.sh "$latest"
./ops/system_snapshot_bundle_min.sh "$latest"

echo
echo "Latest bundles:"
ls -1t ops/_snapshots/LLM_CONTEXT_MIN_*.md | head -n 1
ls -1t ops/_snapshots/LLM_CONTEXT_BUNDLE_*.md | head -n 1
