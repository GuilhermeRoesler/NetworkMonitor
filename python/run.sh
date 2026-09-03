#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

if [[ -x "venv/bin/python" ]]; then
  exec venv/bin/python main.py "$@"
fi

if command -v python3 >/dev/null 2>&1; then
  exec python3 main.py "$@"
fi

if command -v python >/dev/null 2>&1; then
  exec python main.py "$@"
fi

echo "[erro] Python nao encontrado. Crie um venv em python/venv ou instale Python 3.10+." >&2
exit 1
