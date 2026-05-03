# Phase 2 实施计划（路径 1：会话内容存档）

## 全局目标

**用户在微信里转发视频号给员工 → msgaudit 拉到密文 → 解密 → 提取 sphfeed → 调 wechat-to-lark 转录 → 推飞书私信**。完全不回复客户。

## 已完成 / 待完成

| 项 | 状态 | 备注 |
|---|---|---|
| 项目骨架 + pyproject.toml | ✅ | 已升 v0.2.0 |
| `app/config.py` | ✅ | 加了 msgaudit 字段 |
| `app/state.py`（msgaudit_seq）| ✅ | 测试 6 个全绿 |
| `app/channels_parser.py` stub | ✅ | Phase 2 视频号反查依然要做 |
| `app/msgaudit/models.py` | ⚠️ stub | sphfeed 字段名是猜的，**真机 dump 后修正** |
| `app/msgaudit/client.py` | ⚠️ stub | NotImplementedError，等本地选 SDK |
| `app/msgaudit/worker.py` | ✅ 骨架 | 主循环逻辑已写完，依赖 client 实现 |
| `app/pipelines/sphfeed_to_lark.py` | ✅ 骨架 | 调 transcribe.py + lark-cli 链路 |
| 会话存档开通 | ❌ | 你必须人工去后台搞，详见 docs/msgaudit_setup.md |
| Python ↔ C SDK 集成 | ❌ | 三条路选一，详见 docs/python_sdk_options.md |
| 真机 dump sphfeed 样本 | ❌ | 上线后第一件事 |
| Phase 2 视频号反查 | ❌ | 仅当 sphfeed 不直接给 mp4 url 时才需要 |

## 实施步骤（按顺序）

### Step 1: 开通会话存档
看 `docs/msgaudit_setup.md`：
- 企业认证（如果还没认证）
- 后台开通 + 购买
- 选择被存档员工
- 生成 RSA 密钥对、上传公钥、保存私钥到 `RSA_PRIVATE_KEY_PATH`
- 员工本人在企业微信 App 点「同意被存档」

### Step 2: 选 Python SDK 方案
看 `docs/python_sdk_options.md`，三选一。建议先试方案 B（第三方 PyPI 包），不行退到方案 A（ctypes）。

### Step 3: 实现 `app/msgaudit/client.py`
按所选 SDK 填三个方法：
- `__init__`：初始化 SDK
- `get_chat_data(seq, limit)`：返回 `list[EncryptedChatRecord]`
- `decrypt(record)`：返回 dict（解密后的明文 JSON）

写个 `tests/test_msgaudit_client.py`，用 C SDK 自带的 demo 密文数据验证（一般 SDK 包里有 `test_data` 目录）。

### Step 4: 真机 dump
- 跑 `python3 -m app.msgaudit.worker`
- 用一个被存档的员工微信号
- 让客户给他发：
  - 一条 text → 验证解密链路通
  - 一条视频号转发 → 拿到 sphfeed 真实字段结构
- 打印的 `non_sphfeed_msg` 和 `sphfeed_received` 日志里都有 `raw` 字段，**完整 dump**
- 把 sphfeed 的 raw JSON 存到 `tests/fixtures/sample_sphfeed_msg.json`

### Step 5: 修正 sphfeed 字段假设
基于 Step 4 的真机 dump，**重写 `app/msgaudit/models.py:parse_sphfeed`**：
- 真实字段名是不是 `finder_username` / `nonce_id` / `url`？
- 这些值的位置是 `envelope.raw['sphfeed'][...]` 还是其他路径？
- 视频是不是直接给 mp4 url？还是只给元数据要走 Phase 2 反查？

### Step 6: 决定要不要做视频号反查
- **如果 sphfeed 直接给 mp4 url** → `pipelines/sphfeed_to_lark.py` 直接用，`channels_parser` 用不上
- **如果只给 finder_username + nonce_id** → 必须实现 `app/channels_parser.py:parse_channels_video`，方法是手机端抓包腾讯接口（详见 `docs/channels_reverse_eng.md`）

### Step 7: 端到端验证
1. 客户从手机微信转发视频号给员工
2. worker 日志看到 sphfeed 解密成功
3. transcribe.py 跑通（依赖 `~/cheng-skills/wechat-to-lark/scripts/transcribe.py` 在本机）
4. 飞书文档创建成功
5. 飞书私信收到通知

### Step 8: 守护进程化
不要一直 `python3 -m app.msgaudit.worker` 在 nohup 里跑，配个 systemd unit 或者 supervisor：

```ini
# /etc/systemd/system/wechat-channels-parser.service
[Unit]
Description=WeChat Channels Parser (msgaudit worker)
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/wechat-channels-parser
EnvironmentFile=/path/to/wechat-channels-parser/.env
ExecStart=/usr/bin/python3 -m app.msgaudit.worker
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## 不要犯的错

1. ❌ 不要凭记忆写 SDK 调用 — 必须看官方头文件 / SDK 文档
2. ❌ 不要在没真机 dump 之前修 `parse_sphfeed` 字段
3. ❌ 不要把 `rsa_private_key.pem` 提交到 git — 已在 `.gitignore`
4. ❌ 不要尝试用会话存档去"代替员工回复客户" — 该路径不允许，会被腾讯封号
5. ❌ 不要把 worker 跑成 webhook 模式 — 会话存档没有 push，只有 pull
6. ❌ 不要把 SDK 阻塞调用直接放进 asyncio 主循环 — 用 `asyncio.to_thread` 包一下，否则 event loop 会卡

## 旧代码（Phase 1 微信客服路径）

放在 `_archive/phase1_kf_callback/`，**不要删**。如果哪天产品方向变（比如改用微信客服 + 引导用户从客服小程序入口发），整套代码可以挪回来直接用。当时的设计文档见 `_archive/phase1_kf_callback/PHASE1_VERIFY.md`。
