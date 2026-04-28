#!/bin/bash
# SessionStart hook: restore lark-cli auth state from the repo-local backup.
# Runs only in remote (Claude Code on the web) sessions where $HOME is ephemeral.
set -euo pipefail

# Skip on local dev — local $HOME is persistent.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Remote sandbox wipes npm global installs every session. Reinstall lark-cli
# silently so the user never has to do `npm install -g @larksuite/cli` again.
if ! command -v lark-cli >/dev/null 2>&1; then
  npm install -g @larksuite/cli >/dev/null 2>&1 || true
fi

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"
BACKUP="$REPO/.lark-cli-backup"

# Nothing to restore yet — first session.
if [ ! -d "$BACKUP" ]; then
  exit 0
fi

# Restore CLI config (appId, brand, current users).
if [ -d "$BACKUP/.lark-cli" ]; then
  mkdir -p "$HOME/.lark-cli"
  cp -a "$BACKUP/.lark-cli/." "$HOME/.lark-cli/"
fi

# Restore the encrypted secret store (master.key + appsecret/user .enc files).
if [ -d "$BACKUP/lark-cli-share" ]; then
  mkdir -p "$HOME/.local/share/lark-cli"
  cp -a "$BACKUP/lark-cli-share/." "$HOME/.local/share/lark-cli/"
  chmod 600 "$HOME/.local/share/lark-cli/"*.enc "$HOME/.local/share/lark-cli/master.key" 2>/dev/null || true
fi
