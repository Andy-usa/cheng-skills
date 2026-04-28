# Cloud setup for cheng-skills

## What the SessionStart hook auto-installs

Every cloud Claude Code session that opens this repo runs `.claude/hooks/session-start.sh`, which installs:

- `ffmpeg` / `ffprobe` (apt)
- Python: `playwright` + Chromium, `dashscope`, `pillow`, `edge-tts`, `cffi`, `cryptography`
- `lark-cli` (`@larksuite/cli` from npm)
- `dreamina` CLI (from `https://jimeng.jianying.com/cli`)
- Symlinks `wechat-to-lark` and `english-picture-to-video` into `~/.claude/skills/` and `~/.agents/skills/`

## One-time login flow (do this once)

You only need to do this **once**. After it's done, every future cloud session restores the credentials automatically.

### 1. Log in inside a cloud Claude Code session

Open this repo in cloud Claude Code, then in the terminal:

```bash
# Lark / Feishu
lark-cli config init --new
lark-cli auth login --recommend     # complete the device-flow login

# Dreamina
dreamina                             # follow the browser-login prompt
```

### 2. Set your DashScope API key

`wechat-to-lark` needs `DASHSCOPE_API_KEY` (Aliyun Bailian). Set it as a **project secret** in cloud Claude Code project settings — the hook will surface it into the env each session.

### 3. Dump the credentials and store as project secrets

After both logins are done, in the same session:

```bash
bash .claude/scripts/dump-creds.sh
```

Copy the two `KEY=VALUE` lines and paste them into the project's secret settings as:

- `LARK_CLI_CREDS_B64`
- `DREAMINA_CLI_CREDS_B64`

From the next session onward, the hook will auto-restore both before Claude does anything.

## Verifying setup

The hook prints a status line at the end of each session start:

```
>>> [cheng-skills]   - lark-cli:  installed
>>> [cheng-skills]   - dreamina:  installed
>>> [cheng-skills]   - DASHSCOPE_API_KEY: set
>>> [cheng-skills]   - lark-cli auth: present
>>> [cheng-skills]   - dreamina auth: present
```

If any line shows `MISSING`, `NOT SET`, or `NEEDS LOGIN`, follow the corresponding step above.
