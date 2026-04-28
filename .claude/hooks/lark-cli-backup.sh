#!/bin/bash
# Stop hook: snapshot CLI auth state (lark-cli + jimeng-cli) into the
# repo-local backups so the next remote session can restore it. Captures any
# token rotated this session. Skips logs/cache to keep backups small.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# ── lark-cli ─────────────────────────────────────────────────────────────────
LARK_BACKUP="$REPO/.lark-cli-backup"
if [ -f "$HOME/.lark-cli/config.json" ]; then
  mkdir -p "$LARK_BACKUP/.lark-cli" "$LARK_BACKUP/lark-cli-share"
  rsync -a --delete \
    --exclude 'cache/' \
    --exclude 'logs/' \
    --exclude 'update-state.json' \
    "$HOME/.lark-cli/" "$LARK_BACKUP/.lark-cli/"
  if [ -d "$HOME/.local/share/lark-cli" ]; then
    rsync -a --delete "$HOME/.local/share/lark-cli/" "$LARK_BACKUP/lark-cli-share/"
  fi
fi

# ── jimeng-cli ───────────────────────────────────────────────────────────────
JIMENG_BACKUP="$REPO/.jimeng-backup"
if [ -f "$HOME/.jimeng/token-pool.json" ]; then
  mkdir -p "$JIMENG_BACKUP"
  cp -a "$HOME/.jimeng/token-pool.json" "$JIMENG_BACKUP/token-pool.json"
fi
