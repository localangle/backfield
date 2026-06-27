#!/usr/bin/env bash
# Copy scripts/backfield into .venv/bin/backfield after uv sync (make bootstrap).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/scripts/backfield"
TARGET="$ROOT/.venv/bin/backfield"

if [[ ! -f "$SOURCE" ]]; then
  echo "error: missing $SOURCE" >&2
  exit 1
fi
if [[ ! -d "$ROOT/.venv/bin" ]]; then
  echo "error: $ROOT/.venv/bin not found; run 'make bootstrap' (uv sync) first." >&2
  exit 1
fi

install -m 755 "$SOURCE" "$TARGET"
