#!/bin/bash
# SessionStart hook: bootstrap remote sandbox for skills in this repo.
#  - install lark-cli + jimeng-cli (npm, wiped each session)
#  - install ffmpeg + fonts (apt, wiped each session)
#  - install python deps (edge-tts, pillow)
#  - restore lark-cli + jimeng-cli auth state from repo-local backups
# Runs only in remote (Claude Code on the web) sessions where $HOME is ephemeral.
set -euo pipefail

# Skip on local dev — local $HOME is persistent.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# ── npm CLIs ─────────────────────────────────────────────────────────────────
if ! command -v lark-cli >/dev/null 2>&1; then
  npm install -g @larksuite/cli >/dev/null 2>&1 || true
fi
if ! command -v jimeng >/dev/null 2>&1; then
  npm install -g jimeng-cli >/dev/null 2>&1 || true
fi

# Expose the dreamina shim (translates dreamina CLI calls to jimeng-cli) so
# the english-picture-to-video skill can call `dreamina` from anywhere.
DREAMINA_SHIM="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}/english-picture-to-video/bin/dreamina"
if [ -x "$DREAMINA_SHIM" ] && ! command -v dreamina >/dev/null 2>&1; then
  ln -sf "$DREAMINA_SHIM" /usr/local/bin/dreamina 2>/dev/null || true
fi

# ── ffmpeg + fonts (for english-picture-to-video) ────────────────────────────
if ! command -v ffmpeg >/dev/null 2>&1; then
  apt-get update >/dev/null 2>&1 || true
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    ffmpeg fonts-dejavu-core fonts-noto-cjk >/dev/null 2>&1 || true
fi

# ── python deps (for english-picture-to-video) ───────────────────────────────
python3 -c "import edge_tts, PIL" 2>/dev/null || \
  pip3 install --quiet --no-input edge-tts pillow >/dev/null 2>&1 || true

REPO="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/../.." && pwd)}"

# ── restore lark-cli auth ────────────────────────────────────────────────────
LARK_BACKUP="$REPO/.lark-cli-backup"
if [ -d "$LARK_BACKUP/.lark-cli" ]; then
  mkdir -p "$HOME/.lark-cli"
  cp -a "$LARK_BACKUP/.lark-cli/." "$HOME/.lark-cli/"
fi
if [ -d "$LARK_BACKUP/lark-cli-share" ]; then
  mkdir -p "$HOME/.local/share/lark-cli"
  cp -a "$LARK_BACKUP/lark-cli-share/." "$HOME/.local/share/lark-cli/"
  chmod 600 "$HOME/.local/share/lark-cli/"*.enc "$HOME/.local/share/lark-cli/master.key" 2>/dev/null || true
fi

# ── restore jimeng-cli token pool ────────────────────────────────────────────
JIMENG_BACKUP="$REPO/.jimeng-backup"
if [ -f "$JIMENG_BACKUP/token-pool.json" ]; then
  mkdir -p "$HOME/.jimeng"
  cp -a "$JIMENG_BACKUP/token-pool.json" "$HOME/.jimeng/token-pool.json"
  chmod 600 "$HOME/.jimeng/token-pool.json" 2>/dev/null || true
fi
