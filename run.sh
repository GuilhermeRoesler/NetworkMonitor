#!/usr/bin/env bash
# Roteia para a versao Python (padrao).
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/python/run.sh" "$@"
