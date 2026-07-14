#!/bin/bash -p
set -euo pipefail

readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin

exec /usr/bin/env -i PATH="${PATH}" \
  /usr/bin/python3 -I /usr/local/libexec/sealai/redis_capacity_guard.py "$@"
