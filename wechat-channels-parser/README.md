# WeChat Channels Parser

把客户在微信里转发给员工的**视频号视频**，自动转录到飞书。

## 架构（路径 1：会话内容存档）

```
客户 → 微信里转发视频号给企业员工
            │
            ▼
企业微信「会话内容存档」捕获消息
            │
            ▼
[本服务] msgaudit worker（长驻进程）
   • GetChatData(seq, limit) 主动轮询
   • RSA 解 random_key → AES 解 chat_msg → JSON 明文
   • 过滤 msgtype=sphfeed
            │
            ▼
[拿到视频号元数据 / mp4 url]
            │
            ▼
[wechat-to-lark skill]
   • transcribe.py → 阿里云百炼 qwen3-asr-flash 转录
   • lark-cli docs +create / +update → 写飞书文档
   • lark-cli im +messages-send → 推飞书私信通知
            │
            ▼
你打开飞书 → 看到转录好的文档
```

**重点**：完全不向客户回复，纯单向 ETL。客户那边的体感跟普通转发给员工一样。

## 项目状态

| 模块 | 状态 |
|---|---|
| 项目骨架 + 配置 + state | ✅ 完成 |
| msgaudit 主循环骨架 | ✅ 写好（依赖 client 实现） |
| sphfeed → lark 管道骨架 | ✅ 写好（依赖 SDK 选定） |
| msgaudit C SDK Python 集成 | ⚠️ Stub（详见 `docs/python_sdk_options.md`） |
| sphfeed 字段假设 | ⚠️ 待真机 dump 校正 |
| 视频号反查（如果 sphfeed 不直接给 mp4） | ⚠️ Stub（`channels_parser.py`） |

**完整下一步实施清单**：见 `PHASE2_PLAN.md`。
**给本地 Claude Code 的交接说明**：见 `HANDOFF.md`。

## 快速开始（本地）

### 1. 准备
```bash
cp .env.example .env
# 编辑 .env 填入会话存档凭据 + RSA 私钥路径
pip install -e ".[dev]"
```

### 2. 跑测试
```bash
python3 -m pytest -v
```
当前应有 6 个测试通过（仅 state.py，其他模块要 SDK 集成完才能测）。

### 3. 启动 worker
```bash
python3 -m app.msgaudit.worker
```
**会失败**——因为 `MsgAuditClient` 还是 stub（`NotImplementedError`）。先按 `docs/python_sdk_options.md` 选 SDK 实现 client，再启动。

## 关键文档

| 文档 | 用途 |
|---|---|
| `HANDOFF.md` | **下一个 Agent 接手前必读**：方向调整背景 + 任务清单 + 禁忌 |
| `PHASE2_PLAN.md` | 详细实施步骤（开通 → SDK 集成 → 真机 dump → 端到端） |
| `docs/msgaudit_setup.md` | 企业微信会话存档怎么开通 |
| `docs/python_sdk_options.md` | C SDK ↔ Python 集成方案对比 |
| `docs/channels_reverse_eng.md` | 视频号反查（如果 sphfeed 不直接给 mp4 url 才需要） |
| `_archive/phase1_kf_callback/` | 旧的微信客服路径代码（已废弃但保留作参考） |

## 项目结构

```
wechat-channels-parser/
├── README.md                  ← 本文
├── HANDOFF.md                 ← v2：方向调整后的交接说明
├── PHASE2_PLAN.md             ← 实施步骤
├── pyproject.toml             ← v0.2.0
├── .env.example
├── .gitignore
│
├── app/
│   ├── config.py              ← msgaudit 凭据配置
│   ├── state.py               ← seq 游标 + msgid 滚动窗口持久化
│   ├── channels_parser.py     ← 视频号反查（Phase 2 stub）
│   ├── msgaudit/
│   │   ├── client.py          ← ⚠️ MsgAuditClient stub（待选 SDK）
│   │   ├── models.py          ← 解密后消息 dataclass（sphfeed 字段待真机校正）
│   │   └── worker.py          ← 主循环
│   ├── pipelines/
│   │   └── sphfeed_to_lark.py ← sphfeed → transcribe → lark 链路
│   └── utils/logger.py
│
├── tests/
│   └── test_state.py          ← 6 个测试
│
├── docs/
│   ├── msgaudit_setup.md
│   ├── python_sdk_options.md
│   └── channels_reverse_eng.md
│
├── _archive/
│   └── phase1_kf_callback/    ← 旧的微信客服路径代码（已废弃）
│
└── data/.gitkeep
```

## License

MIT
