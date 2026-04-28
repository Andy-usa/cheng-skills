#!/bin/bash
# Stop hook: snapshot lark-cli auth state into the repo-local backup so the
# next remote session can restore it. Captures any token rotated this session.
# Skips logs/cache to keep the backup small and rsync-friendly.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BACKUP="$REPO/.lark-cli-backup"

# No auth on this machine yet — nothing to back up.
if [ ! -f "$HOME/.lark-cli/config.json" ]; then
  exit 0
fi

mkdir -p "$BACKUP/.lark-cli" "$BACKUP/lark-cli-share"

# Sync the user-facing config dir, dropping volatile bits.
rsync -a --delete \
  --exclude 'cache/' \
  --exclude 'logs/' \
  --exclude 'update-state.json' \
  "$HOME/.lark-cli/" "$BACKUP/.lark-cli/"

# Sync the encrypted secret store (master.key + .enc files).
if [ -d "$HOME/.local/share/lark-cli" ]; then
  rsync -a --delete "$HOME/.local/share/lark-cli/" "$BACKUP/lark-cli-share/"
fi
