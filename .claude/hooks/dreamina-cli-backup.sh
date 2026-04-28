#!/bin/bash
# Stop hook: snapshot dreamina-cli auth state into the repo-local backup so the
# next remote session can restore it. Captures any token rotated this session.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BACKUP="$REPO/.dreamina-cli-backup"

if [ ! -f "$HOME/.dreamina_cli/credential.json" ]; then
  exit 0
fi

mkdir -p "$BACKUP/.dreamina_cli"

rsync -a --delete \
  --exclude 'logs/' \
  --exclude 'tasks.db' \
  --exclude 'cache/' \
  "$HOME/.dreamina_cli/" "$BACKUP/.dreamina_cli/"
