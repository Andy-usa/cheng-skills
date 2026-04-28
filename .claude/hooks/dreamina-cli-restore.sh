#!/bin/bash
# SessionStart hook: restore dreamina-cli auth state from the repo-local backup.
# Runs only in remote (Claude Code on the web) sessions where $HOME is ephemeral.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BACKUP="$REPO/.dreamina-cli-backup"

if [ ! -d "$BACKUP" ]; then
  exit 0
fi

if [ -d "$BACKUP/.dreamina_cli" ]; then
  mkdir -p "$HOME/.dreamina_cli"
  cp -a "$BACKUP/.dreamina_cli/." "$HOME/.dreamina_cli/"
  chmod 600 "$HOME/.dreamina_cli/credential.json" 2>/dev/null || true
fi
