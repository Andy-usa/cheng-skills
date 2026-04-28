#!/bin/bash
# SessionStart hook for cheng-skills repo on Claude Code (web).
# - Installs python deps + ffmpeg
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

# 4) Register skills as user-level skills via symlink.
# SKILL.md files reference both ~/.claude/skills/ and ~/.agents/skills/ paths,
# so we expose both.
mkdir -p "$HOME/.claude/skills" "$HOME/.agents/skills"
ln -sfn "$PROJECT_DIR/wechat-to-lark"            "$HOME/.claude/skills/wechat-to-lark"
ln -sfn "$PROJECT_DIR/english-picture-to-video"  "$HOME/.claude/skills/english-picture-to-video"
ln -sfn "$PROJECT_DIR/wechat-to-lark"            "$HOME/.agents/skills/wechat-to-lark"
ln -sfn "$PROJECT_DIR/english-picture-to-video"  "$HOME/.agents/skills/english-picture-to-video"
log "Skills registered: wechat-to-lark, english-picture-to-video"

# 5) Persist a hint about secrets / CLIs the user must supply themselves.
# (DASHSCOPE_API_KEY, lark-cli login, dreamina login — can't auto-provision.)
log "Setup complete."
log "Manual prerequisites still required for full functionality:"
log "  - export DASHSCOPE_API_KEY=<key>   (视频号转写)"
log "  - lark-cli installed & 'lark-cli auth login --recommend' done   (写入飞书)"
log "  - dreamina CLI installed & logged in   (英语视频生图)"
