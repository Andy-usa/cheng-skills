# 项目交接文件 — 给下一个 Claude Code Agent

> **你（Agent）现在接手的是一个 Phase 1 已完成的项目。**
> 优先读完本文 + `PHASE1_VERIFY.md`，再开始任何动作。
> **绝对不要凭记忆改业务代码或外部 API 调用。**

---

## 项目身份

- **名字**：wechat-channels-parser
- **现版本**：0.1.0（Phase 1 完成）
- **目的**：用户在微信里把视频号视频转发给企业微信客服号 → 服务端识别 → 解析视频 URL → 客服消息回复给用户
- **原始 spec**：用户提供的 10 节需求文档，已严格遵循（核心约束见 §"不能干的事"）

## 现状（移交时）

| 模块 | 状态 |
|---|---|
| 项目骨架 + pyproject.toml + .env.example | ✅ 完成 |
| `app/crypto.py` WXBizMsgCrypt | ✅ 完成 + 10 单测 |
| `app/access_token.py` | ✅ 完成 |
| `app/state.py` 持久化 | ✅ 完成 + 6 单测 |
| `app/kf_client.py` sync_msg / send_msg | ✅ 完成 + 5 单测（respx mock）|
| `app/handlers.py` 业务分发 | ✅ 完成 + 6 单测 |
| `app/main.py` FastAPI 端点 | ✅ 完成 + 5 单测（TestClient）|
| `app/channels_parser.py` | ⚠️ **Stub**（返回 mock，等 Phase 2 接入真实反查）|
| 真机验证 | ❌ 未做（沙箱跑不了，必须在本地 + 真实企业微信账号）|

**测试现状**：`python3 -m pytest -v` → 32 passed in ~5s

## 你的任务清单（按优先级）

### 1. 让项目在本地跑起来（先打通环境）

```bash
cd wechat-channels-parser
cp .env.example .env
# 编辑 .env 填入用户提供的真实企业微信凭据（5 个必填项）

pip install -e ".[dev]"      # 或 uv pip install -e ".[dev]"
python3 -m pytest             # 验证 32 测试全绿
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

如果用户暂时没凭据，**不要往下走真机部分**，等他给。

### 2. Phase 1 真机验证（关键）

按 `PHASE1_VERIFY.md` 5 步走完。**特别注意 Step 3**：

> 用一个微信号在视频号里随便点开一个视频 → 转发给客服号
> **必须**在日志里看到 channels 消息的完整 raw 体
> **必须**把这个 raw 消息保存到 `tests/fixtures/sample_channels_msg.json` 替换占位

为什么 Step 3 关键？因为 `app/handlers.py:_handle_channels` 当前对字段名（`finder_username` / `nonce_id`）的假设是基于需求文档的推测，**真机数据出来之后必须根据实际字段名修正这一段代码**，否则 Phase 2 解析器拿不到正确的输入。

### 3. Phase 2 — 视频号反查解析器

**只在 Phase 1 完全验证通过、有真机抓包样本之后再开始。**

入口：`docs/channels_reverse_eng.md`（占位文档）。
唯一改动点：`app/channels_parser.py:parse_channels_video()` 函数体。
调用方（`handlers._handle_channels`）无需改。

---

## 不能干的事（禁忌清单）

这些是用户在 spec 里反复强调的、**踩坑必出问题**的边界：

1. ❌ **不要凭记忆写视频号反查接口**。Phase 2 必须基于真机抓包（mitmproxy / Charles），所有接口路径、签名算法、必备 header 都要有实际证据。
2. ❌ **不要凭记忆改企业微信 API 路径和字段**。当前 `kf_client.py` 用的是 spec 里指定的 3 个 URL；如果你想加新接口，先开 fetch 工具查官方文档。
3. ❌ **不要在没真机抓包前修改 `_handle_channels` 的字段名假设**。先看真实日志再改。
4. ❌ **不要把 callback 主路径改成同步处理**。企业微信 5s 不响应会重试 3 次，必须立刻返回 'success'，业务全走 BackgroundTasks。
5. ❌ **不要把 secret 写进代码或 commit**。`.env` 已经在 `.gitignore` 里。
6. ❌ **不要去掉 origin=3 检查**。客服自己发的消息（origin=4）必须跳过，否则会无限循环回复自己。
7. ❌ **不要把 `state.json` 拿出来 commit**。它是运行时数据，已 gitignore。

## 重要文件 / 行号指引

| 任务 | 文件 |
|---|---|
| Phase 1 真机验证步骤 | `PHASE1_VERIFY.md` |
| Phase 2 起点（占位） | `docs/channels_reverse_eng.md` |
| channels 字段名假设 | `app/handlers.py:_handle_channels` |
| stub 返回（Phase 2 替换点） | `app/channels_parser.py:parse_channels_video` |
| 配置项清单 | `app/config.py` + `.env.example` |
| 真机 dump 占位 | `tests/fixtures/sample_channels_msg.json` |

## 架构权衡（用户已拍板，不要再争）

- **不用数据库**：游标 + msgid 用 JSON 文件持久化，单实例够用。
- **BackgroundTasks 而不是 Celery**：当前规模不需要 task queue。如果 Phase 2 之后单次回调处理 > 5s 才考虑升级。
- **loguru JSON 日志**：方便后续接日志聚合。
- **httpx + asyncio**：因为 FastAPI 原生 async，统一异步栈。
- **pycryptodome 而不是 cryptography**：和企业微信官方 demo 一致。

## 常用命令

```bash
# 跑测试
python3 -m pytest -v                      # 全部
python3 -m pytest tests/test_crypto.py    # 单文件

# 启动服务（本地开发）
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 暴露公网（需先安装 ngrok）
ngrok http 8000

# 看日志（loguru 输出 JSON 行到 stderr）
uvicorn app.main:app 2>&1 | tee server.log

# 实时格式化日志（可选）
uvicorn app.main:app 2>&1 | python3 -c "
import json, sys
for line in sys.stdin:
    try: d = json.loads(line); print(f\"[{d['record']['level']['name']:7}] {d['record']['message']}\")
    except: print(line, end='')
"
```

## 如果你有疑问

按这个顺序自查：
1. 先翻代码（每个文件都有 module docstring 和函数注释）
2. 再翻 `PHASE1_VERIFY.md` / `README.md` / `docs/channels_reverse_eng.md`
3. 还不清楚就**停下来问用户**，不要乱猜

---

**最后一条**：用户偏好简体中文回复 + 紧凑段落 + 不主动建 PR + commit message 中文。详见 `~/.claude/CLAUDE.md`（如果在他本地能看到的话）。
