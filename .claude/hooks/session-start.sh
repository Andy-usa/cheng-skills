#!/bin/bash
# SessionStart hook for cheng-skills repo on Claude Code (web).
# - Installs python deps + ffmpeg
# - Installs lark-cli (npm) and dreamina (curl|bash)
# - Restores cached lark-cli / dreamina credentials from secret env vars
# - Registers wechat-to-lark and english-picture-to-video as user-level skills
set -euo pipefail

# Web only — local sessions already have whatever they need.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$(pwd)}"

log() { echo ">>> [cheng-skills] $*"; }

# 1) System packages: ffmpeg / ffprobe (used by english-picture-to-video)
if ! command -v ffmpeg >/dev/null 2>&1; then
  log "Installing ffmpeg"
  if command -v sudo >/dev/null 2>&1; then
    sudo apt-get update -qq
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg
  else
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ffmpeg
  fi
fi

# 2) Python deps (idempotent — pip will skip already-installed).
# cffi + cryptography are pulled explicitly because the system-apt cryptography
# in some images ships rust bindings that fail to find _cffi_backend.
log "Installing Python packages (playwright, dashscope, pillow, edge-tts, cffi, cryptography)"
pip3 install --quiet --disable-pip-version-check \
  playwright dashscope pillow edge-tts cffi cryptography

# 3) Playwright Chromium (needed by wechat-to-lark for公众号文章抓取)
if [ ! -d "$HOME/.cache/ms-playwright" ] || [ -z "$(ls -A "$HOME/.cache/ms-playwright" 2>/dev/null)" ]; then
  log "Installing Playwright Chromium"
  python3 -m playwright install chromium
  python3 -m playwright install-deps chromium 2>/dev/null || true
fi

# 4) lark-cli (Feishu CLI) via npm
if ! command -v lark-cli >/dev/null 2>&1; then
  if command -v npm >/dev/null 2>&1; then
    log "Installing @larksuite/cli"
    npm install -g @larksuite/cli >/dev/null 2>&1 || log "WARN: lark-cli install failed"
  else
    log "WARN: npm not available — skipping lark-cli install"
  fi
fi

# 5) dreamina CLI (ByteDance Jimeng) via official installer
if ! command -v dreamina >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/dreamina" ]; then
  log "Installing dreamina CLI"
  curl -fsSL --max-time 60 https://jimeng.jianying.com/cli | bash 2>&1 | tail -5 || \
    log "WARN: dreamina install failed (network may be restricted)"
fi
# Make sure ~/.local/bin is on PATH for this session and future ones
if [ -d "$HOME/.local/bin" ]; then
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *)
      export PATH="$HOME/.local/bin:$PATH"
      [ -n "${CLAUDE_ENV_FILE:-}" ] && echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
      ;;
  esac
fi

# 6) Restore credentials from secret env vars (set once per cloud project).
# To produce these blobs, run scripts/dump-creds.sh after logging in once.
restore_creds() {
  local var_name="$1" target_dir="$2" label="$3"
  local b64="${!var_name:-}"
  [ -z "$b64" ] && return 0
  # Skip if already populated with real files (avoid clobbering a fresh login)
  if [ -d "$target_dir" ] && [ -n "$(find "$target_dir" -type f -print -quit 2>/dev/null)" ]; then
    log "$label credentials already present, skipping restore"
    return 0
  fi
  log "Restoring $label credentials from \$$var_name"
  mkdir -p "$target_dir"
  printf '%s' "$b64" | base64 -d | tar -xzf - -C "$target_dir" 2>/dev/null \
    || log "WARN: failed to decode $var_name (check the secret value)"
}
restore_creds LARK_CLI_CREDS_B64    "$HOME/.lark-cli"     "lark-cli"
restore_creds DREAMINA_CLI_CREDS_B64 "$HOME/.dreamina_cli" "dreamina"

# 7) Register skills as user-level skills via symlink.
# SKILL.md files reference both ~/.claude/skills/ and ~/.agents/skills/ paths,
# so we expose both.
mkdir -p "$HOME/.claude/skills" "$HOME/.agents/skills"
ln -sfn "$PROJECT_DIR/wechat-to-lark"            "$HOME/.claude/skills/wechat-to-lark"
ln -sfn "$PROJECT_DIR/english-picture-to-video"  "$HOME/.claude/skills/english-picture-to-video"
ln -sfn "$PROJECT_DIR/wechat-to-lark"            "$HOME/.agents/skills/wechat-to-lark"
ln -sfn "$PROJECT_DIR/english-picture-to-video"  "$HOME/.agents/skills/english-picture-to-video"
log "Skills registered: wechat-to-lark, english-picture-to-video"

# 8) Surface DASHSCOPE_API_KEY into env file if set as a project secret
if [ -n "${DASHSCOPE_API_KEY:-}" ] && [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export DASHSCOPE_API_KEY=\"$DASHSCOPE_API_KEY\"" >> "$CLAUDE_ENV_FILE"
fi

log "Setup complete."
log "Status:"
log "  - lark-cli:  $(command -v lark-cli >/dev/null && echo installed || echo MISSING)"
log "  - dreamina:  $(command -v dreamina >/dev/null || [ -x "$HOME/.local/bin/dreamina" ] && echo installed || echo MISSING)"
log "  - DASHSCOPE_API_KEY: $([ -n "${DASHSCOPE_API_KEY:-}" ] && echo set || echo NOT SET)"
lark_auth_status() {
  command -v lark-cli >/dev/null 2>&1 || { echo "MISSING"; return; }
  if lark-cli auth status >/dev/null 2>&1; then echo "present"; else echo "NEEDS LOGIN"; fi
}
dreamina_auth_status() {
  local d="${HOME}/.local/bin/dreamina"
  [ -x "$d" ] || { echo "MISSING"; return; }
  if "$d" user_credit >/dev/null 2>&1; then echo "present"; else echo "NEEDS LOGIN"; fi
}
log "  - lark-cli auth: $(lark_auth_status)"
log "  - dreamina auth: $(dreamina_auth_status)"
