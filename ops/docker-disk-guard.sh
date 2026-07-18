#!/bin/bash -p
set -euo pipefail

readonly PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH

exec /usr/bin/python3 -I /usr/local/libexec/sealai/docker_disk_guard.py "$@"
