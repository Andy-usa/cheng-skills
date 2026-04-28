#!/bin/bash
# Dump the current lark-cli and dreamina credential dirs as base64 blobs,
# ready to paste into Claude Code project secrets.
#
# Usage:
#   bash .claude/scripts/dump-creds.sh
#
# Run this AFTER you have logged in once via:
#   lark-cli config init --new && lark-cli auth login --recommend
#   dreamina  (then complete browser login when prompted)
#
# Then copy the printed values into Claude Code project settings as secrets:
#   LARK_CLI_CREDS_B64=<value>
#   DREAMINA_CLI_CREDS_B64=<value>
# The SessionStart hook will restore them on every future session.
set -euo pipefail

dump() {
  local dir="$1" name="$2"
  if [ ! -d "$dir" ] || [ -z "$(ls -A "$dir" 2>/dev/null)" ]; then
    echo "# $name: $dir not found or empty — skipping. Log in first." >&2
    return 0
  fi
  local blob
  blob="$(tar -czf - -C "$dir" . | base64 -w0)"
  echo
  echo "# ===== $name ====="
  echo "${name}=${blob}"
}

dump "$HOME/.lark-cli"     "LARK_CLI_CREDS_B64"
dump "$HOME/.dreamina_cli" "DREAMINA_CLI_CREDS_B64"
