# 项目交接文件 v2 — 给下一个 Claude Code Agent

> **重要：项目方向已经从 Phase 1 调整。** 旧的微信客服路径（kf-callback）已归档到 `_archive/phase1_kf_callback/`，**不要复用**。
> 优先读完本文 + `PHASE2_PLAN.md`，再开始任何动作。
> **绝对不要凭记忆写企业微信 SDK 调用或视频号反查接口。**

---

## 为什么方向变了

Phase 1 走的是「企业微信微信客服」回调路径。但用户实测发现：**微信原生的"转发"菜单里找不到微信客服会话**（微信客服没有独立聊天入口，要从企业微信小程序进），所以客户根本没法把视频号视频转发给微信客服号。

**真正可行的路径**：让员工的企业微信号作为"客户联系"普通好友，客户转发到员工 → 用「**会话内容存档（msgaudit）**」拿到消息密文 → 解密 → 拉视频号信息 → 调 wechat-to-lark 转录。

**一个关键约束**：会话存档**只能"读"，不能"代替员工回复客户"**——这是腾讯的红线。所以产品定位也变了：不再回复客户，转录结果直接推飞书私信给运营者本人（用户：程万云）。

## 项目身份

- **名字**：wechat-channels-parser
- **现版本**：0.2.0（v1 归档；v2 重新搭骨架，等本地 SDK 集成）
- **目的**：客户给员工发视频号 → msgaudit 解出 sphfeed → 调 wechat-to-lark 转录到飞书
- **不再做**：回复客户、即时双向对话

## 现状

| 模块 | 状态 |
|---|---|
| `app/config.py` 加 msgaudit 字段 | ✅ |
| `app/state.py` 改成 msgaudit_seq | ✅ + 6 测试通过 |
| `app/channels_parser.py` stub | ✅（如果 sphfeed 不直接给 mp4 url 才会用到） |
| `app/msgaudit/models.py` | ⚠️ **Stub**：sphfeed 字段名是猜的，**真机 dump 后改** |
| `app/msgaudit/client.py` | ⚠️ **Stub**：等本地选 SDK（`docs/python_sdk_options.md`） |
| `app/msgaudit/worker.py` | ✅ 骨架，依赖 client 实现 |
| `app/pipelines/sphfeed_to_lark.py` | ✅ 骨架，依赖 wechat-to-lark skill 在本机 |
| 会话存档开通 | ❌ 用户必须人工去后台搞（认证 + 付费 + 上传公钥 + 员工授权） |
| 真机 dump sphfeed 样本 | ❌ Step 4，开通后第一件事 |
| Phase 2 视频号反查 | ❌ 仅当 sphfeed 不直接给 mp4 url 才需要 |

**测试现状**：`python3 -m pytest -v` → 6 passed（state.py）

## 你的任务清单（按顺序）

详见 `PHASE2_PLAN.md`，关键步骤：

### 1. 跑测试 + 看代码
```bash
cd wechat-channels-parser
pip install -e ".[dev]"
python3 -m pytest -v   # 应该 6 个 state 测试通过
```
逐文件 ls：`app/msgaudit/`、`app/pipelines/`、`docs/`、`PHASE2_PLAN.md`，把骨架代码和文档过一遍，理解我留的 stub 边界。

### 2. 跟用户确认开通会话存档的进度
按 `docs/msgaudit_setup.md` 走完后台流程：
- 企业认证
- 购买聊天内容存档功能
- 后台拿 Secret，写入 `.env` 的 `WECHAT_MSGAUDIT_SECRET`
- 本地生成 RSA 密钥对，公钥上传后台拿 `publickey_ver`
- 私钥保存到本地，路径写入 `.env` 的 `RSA_PRIVATE_KEY_PATH`
- **被存档员工本人**在企业微信 App 内点「同意被存档」

**如果用户还没开通，停下来等**。这一步必须用户自己去后台操作，你帮不了。

### 3. 选 Python SDK 集成方案
看 `docs/python_sdk_options.md`，三选一。**默认推荐方案 B**（先试 PyPI 上的第三方包，failback 到 A）。

### 4. 实现 `app/msgaudit/client.py`
按所选 SDK 填三个方法（接口已经定义好，不要改签名）：
- `__init__`
- `get_chat_data(seq, limit)` → `list[EncryptedChatRecord]`
- `decrypt(record)` → `dict`

写 `tests/test_msgaudit_client.py`，**用 SDK 自带的 demo 密文样本**做单测（C SDK 包里通常有 test_data 目录）。

### 5. ⭐ 真机 dump
启动 worker → 让被存档员工的微信号收一条客户发来的：
- text 消息：验证解密链路通
- 视频号转发：拿到 sphfeed 真实结构

worker 日志里 `non_sphfeed_msg` 和 `sphfeed_received` 都会 dump `raw` 字段。**完整复制 sphfeed 那条 raw 到 `tests/fixtures/sample_sphfeed_msg.json`**。

### 6. 修正 sphfeed 字段假设
基于 Step 5 的真机 dump，重写 `app/msgaudit/models.py:parse_sphfeed`：
- 真实字段名（`finder_username` 还是其他？`nonce_id` 还是 `feed_id`？`url` 是不是直接 mp4？）
- 字段在 envelope 里的路径

### 7. 决定要不要做 Phase 2 视频号反查
- **sphfeed 直接给 mp4 url** → `pipelines/sphfeed_to_lark.py` 直接用，跳过 channels_parser
- **只给 finder_username + nonce_id** → 实现 `app/channels_parser.py:parse_channels_video`，参考 `docs/channels_reverse_eng.md`

### 8. 端到端验证
1. 客户从手机微信转发视频号给员工
2. worker 日志：sphfeed 解密成功
3. transcribe.py 跑通
4. 飞书文档创建成功
5. 飞书私信收到通知（`LARK_USER_OPEN_ID`）

### 9. 守护进程化
配 systemd / supervisor，详见 `PHASE2_PLAN.md` Step 8。

## 不能干的事（禁忌）

1. ❌ **不要凭记忆写 SDK 调用** — 必须看官方头文件 / 第三方包文档
2. ❌ **不要在没真机 dump 之前修 `parse_sphfeed`** 字段
3. ❌ **不要凭记忆写视频号反查接口** — 必须真机抓包腾讯接口（`docs/channels_reverse_eng.md`）
4. ❌ **不要用会话存档去"自动回复客户"** — 红线，会被腾讯封号
5. ❌ **不要把 worker 改成 webhook 模式** — 会话存档没有 push，只有 pull
6. ❌ **不要把 SDK 阻塞调用直接放 asyncio 主循环** — 用 `asyncio.to_thread` 包一下
7. ❌ **不要把 `rsa_private_key.pem` 提交到 git** — `.gitignore` 已加
8. ❌ **不要删 `_archive/phase1_kf_callback/`** — 留作产品方向回退的备份

## 关键文档锚点

- 会话存档总览：https://developer.work.weixin.qq.com/document/path/91774
- 使用前帮助：https://developer.work.weixin.qq.com/document/path/91361
- 常见问题：https://developer.work.weixin.qq.com/document/path/91552

## 用户偏好（从 ~/.claude/CLAUDE.md 同步）

- 简体中文回复，思考过程也用中文
- 紧凑段落、少用 `##` 嵌套深的标题
- 长任务用 TodoWrite 跟踪进度
- 提交 git 前不主动建 PR
- commit message 用中文
- 文件路径用反引号包裹

## 如果你有疑问

按这个顺序自查：
1. 翻代码（每个文件都有 module docstring 和函数注释）
2. 翻 `PHASE2_PLAN.md` / `docs/*.md`
3. 翻 `_archive/phase1_kf_callback/PHASE1_VERIFY.md`（看历史决策的上下文）
4. 还不清楚就**停下来问用户**，别乱猜
