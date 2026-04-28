---
name: dreamina-login
description: |
  即梦/Dreamina 登录辅助技能。通过 Playwright 打开网页让用户手动登录，捕获 cookie/session
  存到 ~/.dreamina/auth.json，供 `dreamina` CLI 或其他依赖即梦登录态的脚本复用。
  支持 login / status / logout / refresh 四个子命令。
  触发词：即梦登录、登录即梦、dreamina login、即梦掉线、即梦重新登录、jimeng 登录、刷新即梦登录态。
  当用户说"我想登录即梦"或"即梦登录失效了帮我重新登录"也应触发。
permissions:
  exec:
    - python3
  file_read:
    - ~/.dreamina/
    - ~/.claude/skills/dreamina-login/
  file_write:
    - ~/.dreamina/
---

# Skill：即梦 / Dreamina 登录辅助

完整 auth helper：login / status / logout / refresh 四件套，统一管理即梦登录态。

## 凭证存储

- 登录态保存在 `~/.dreamina/auth.json`（Playwright `storage_state` 格式，含 cookies 与 localStorage）
- 文件权限自动设为 `0600`
- 其他技能（如 `english-picture-to-video` 调用的 `dreamina` CLI）应从此文件读取 cookie

## 站点支持

| `--site` | 域名 | 适用 |
|----------|------|------|
| `jimeng` (默认) | `https://jimeng.jianying.com/` | 中国大陆即梦 |
| `dreamina` | `https://dreamina.capcut.com/` | 海外 Dreamina |

## 子命令

### 1. login — 首次登录

```bash
python3 ~/.claude/skills/dreamina-login/scripts/auth.py login \
  --site=jimeng --timeout=300
```

行为：
1. 启动 **非 headless** Chromium，打开登录页
2. 等待用户在浏览器里手动完成登录（扫码 / 短信 / 第三方）
3. 检测到登录态后（页面出现 avatar 元素且登录按钮消失），保存 `storage_state`
4. 写入 `~/.dreamina/auth.json`，输出 JSON 结果

输出示例：
```json
{"ok": true, "auth_file": "/home/user/.dreamina/auth.json", "site": "jimeng", "cookie_count": 18}
```

超时（默认 300 秒）未检测到登录则返回 `{"ok": false, "error": "login_timeout"}`，退出码 2。

### 2. status — 检查登录态

```bash
python3 ~/.claude/skills/dreamina-login/scripts/auth.py status --site=jimeng
```

行为：
1. 用保存的 `auth.json` 启动 headless 浏览器
2. 打开主页，检测页面元素判断是否仍然登录
3. 输出 `{"logged_in": true/false, "site": "..."}`，退出码 `0`=已登录，`1`=未登录

加 `--verbose` 还会返回 `cookie_count` 和 `auth_file` 路径。

### 3. logout — 清除登录态

```bash
python3 ~/.claude/skills/dreamina-login/scripts/auth.py logout
```

直接删除 `~/.dreamina/auth.json`。不调用任何线上接口。

### 4. refresh — 失效才重登

```bash
python3 ~/.claude/skills/dreamina-login/scripts/auth.py refresh --site=jimeng
```

行为：
1. 先跑 `status`
2. 如果仍登录 → 不打扰用户，退出 0
3. 如果失效或无文件 → 自动进入 `login` 流程

适合在其他脚本里"用前自检"。

---

## 典型调用流程

### 场景 A：用户第一次接入即梦

```bash
python3 ~/.claude/skills/dreamina-login/scripts/auth.py login --site=jimeng
```

提示用户在弹出的浏览器里完成扫码登录。完成后告知保存路径与 cookie 数量。

### 场景 B：另一个技能要生图前先确认登录

```bash
python3 ~/.claude/skills/dreamina-login/scripts/auth.py refresh --site=jimeng \
  || { echo "登录失败"; exit 1; }
# 然后调用 dreamina 生图命令
```

### 场景 C：用户切换账号

```bash
python3 ~/.claude/skills/dreamina-login/scripts/auth.py logout
python3 ~/.claude/skills/dreamina-login/scripts/auth.py login --site=jimeng
```

---

## 集成到现有 dreamina CLI

如果 `dreamina` CLI 支持读取 cookie 文件，将下方路径注入其配置：

```
~/.dreamina/auth.json
```

或在调用前用 `jq` 把 cookies 字段导出为 Netscape 格式喂给 CLI（视具体 CLI 实现而定）。

---

## 错误处理

| 情况 | 输出 | 处理建议 |
|------|------|---------|
| Playwright 未安装 | `ModuleNotFoundError: playwright` | `pip3 install playwright && python3 -m playwright install chromium` |
| 登录超时 | `{"ok": false, "error": "login_timeout"}` | 提示用户加大 `--timeout` 或重试 |
| 主页加载超时 | `{"logged_in": false, "reason": "page_load_timeout"}` | 检查网络后重跑 `refresh` |
| `auth.json` 不存在 | `{"logged_in": false, "reason": "no_auth_file"}` | 跑 `login` 子命令 |
| 头像选择器变更（站点改版） | `status` 误报未登录 | 更新 `SITES[*].logged_in_selector` |

## 依赖

- Python 3.9+
- `playwright`（首次：`pip3 install playwright && python3 -m playwright install chromium`）
- 一个图形界面（`login` 子命令需要非 headless 浏览器；headless 环境无法手动扫码）
