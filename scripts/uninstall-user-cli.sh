#!/usr/bin/env bash
# Remove the ~/.local/bin/backfield symlink installed by install-user-cli.sh.
set -euo pipefail

TARGET="${HOME}/.local/bin/backfield"

if [[ -L "$TARGET" ]]; then
  rm "$TARGET"
  echo "Removed $TARGET"
elif [[ -e "$TARGET" ]]; then
  echo "error: $TARGET exists but is not a symlink; remove it manually." >&2
  exit 1
else
  echo "Nothing to remove ($TARGET not found)."
fi
