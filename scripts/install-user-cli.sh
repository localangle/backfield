#!/usr/bin/env bash
# Symlink scripts/backfield into ~/.local/bin for use without activating .venv.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/scripts/backfield"
TARGET="${HOME}/.local/bin/backfield"

if [[ ! -f "$SOURCE" ]]; then
  echo "error: missing $SOURCE" >&2
  exit 1
fi

mkdir -p "${HOME}/.local/bin"
ln -sf "$SOURCE" "$TARGET"
chmod +x "$SOURCE"

echo "Installed $TARGET -> $SOURCE"
echo "Ensure ~/.local/bin is on your PATH, then run: backfield up"
