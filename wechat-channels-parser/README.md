# WeChat Channels Parser

企业微信「微信客服」 → 视频号链接解析服务。

用户在微信里把**视频号视频**转发给企业微信客服号，本服务接收回调、识别 channels 类型消息、调用解析器拿到视频 URL，再通过客服消息把链接回复给用户。

> **状态**：Phase 1 通路打通完成，channels 解析器留 stub（Phase 2 由人工逆向接入）。

---

## 快速开始

### 1. 准备凭据

在企业微信管理后台 → 「应用管理 → 微信客服」拿到：

- `WECHAT_CORP_ID`：企业 ID（ww 开头）
- `WECHAT_KF_SECRET`：微信客服应用 Secret
- `WECHAT_OPEN_KFID`：客服账号 ID（wk 开头）
- `WECHAT_CALLBACK_TOKEN` + `WECHAT_CALLBACK_AES_KEY`：在「接收消息配置」生成

### 2. 安装与配置

```bash
cp .env.example .env
# 编辑 .env 填入上一步的真实凭据

pip install -e .            # 或 uv pip install -e .
```

### 3. 启动

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. 暴露公网（开发用）

```bash
ngrok http 8000
# 假设拿到 https://xxxx.ngrok-free.app
```

### 5. 在企业微信后台填回调 URL

「应用管理 → 微信客服 → 接收消息配置」：

- URL：`https://xxxx.ngrok-free.app/wechat/callback`
- Token：与 `.env` 的 `WECHAT_CALLBACK_TOKEN` 一致
- EncodingAESKey：与 `.env` 的 `WECHAT_CALLBACK_AES_KEY` 一致

点击「保存」，企业微信会调 `GET /wechat/callback` 验签——通过即生效。

### 6. 真机测试

详见 `PHASE1_VERIFY.md` 的验证步骤。

---

## 项目结构

```
wechat-channels-parser/
├── app/
│   ├── main.py             # FastAPI 入口
│   ├── config.py           # pydantic Settings（读 .env / env vars）
│   ├── crypto.py           # WXBizMsgCrypt：AES-CBC + SHA1 签名
│   ├── access_token.py     # access_token 缓存（内存 + lock）
│   ├── kf_client.py        # 微信客服 API 封装（sync_msg / send_msg + 重试）
│   ├── state.py            # 游标 + 已处理 msgid 持久化（JSON 文件）
│   ├── channels_parser.py  # 视频号反查（⚠️ Phase 2 stub，由人工接入）
│   ├── handlers.py         # 业务分发：按 msgtype 处理
│   └── utils/logger.py     # loguru 配置（JSON 输出）
├── tests/                  # pytest，32 个测试覆盖核心路径
└── data/state.json         # 运行时生成；游标 + msgid 持久化
```

---

## 设计要点

| 关注点 | 实现 |
|---|---|
| **不能丢消息** | 游标持久化；BackgroundTasks 失败时游标不前进 |
| **不能重复处理** | msgid set 判重，滚动窗口最多 1 万条 |
| **5 秒内回 200** | POST 主路径只做解密，业务全走 `BackgroundTasks` |
| **配置不进代码** | 全走环境变量 + `.env` 文件 |
| **日志可追溯** | loguru JSON 输出，每条消息记录 msgid / external_userid / msgtype / 处理耗时 |
| **可本地跑** | uvicorn + ngrok 即可；无强依赖云服务 |

### 回调流程

```
[微信用户] 转发视频号视频给客服号
      │
      ▼
[企业微信] POST /wechat/callback?msg_signature=...
      │   (推送的是「有新消息」事件，不带消息内容；带 Token)
      ▼
[crypto.decrypt_msg]  验签 + AES 解密 envelope
      │
      ▼
[BackgroundTasks → handle_callback_event]  立刻返回 'success'
      │
      ▼
[kf_client.sync_msg_all]  循环拉到 has_more=False
      │
      ▼
[handlers.process_message]  按 msgtype 分发
      │
      ├── text     → 提示「请直接转发视频号视频」
      ├── channels → channels_parser → send_msg(link 类型)
      └── 其他      → 「暂不支持」
```

### Origin 字段

`origin=3` 才是客户发的；`origin=4` 是客服自己发出去的。**只处理 3，跳过 4**，避免回复死循环。

---

## 测试

```bash
python3 -m pytest -v
```

32 个用例，覆盖：

- crypto AES 加解密 + 签名验证 + 各种异常路径（10）
- state JSON 原子读写 + msgid 滚动窗口（6）
- kf_client happy path + has_more 分页 + token 自动刷新 + errcode 失败（5）
- handlers 各 msgtype 分发 + origin 过滤 + msgid 判重（6）
- main FastAPI 三个端点（5）

---

## Phase 2 — 视频号反查解析器

`app/channels_parser.py` 当前是 stub，返回固定 mock。Phase 2 需要：

1. 用真机抓包确认 channels 消息的真实字段（`finder_username` / `nonce_id` 是否准确）
2. 逆向腾讯接口拿 mp4 直链
3. 把实现填进 `parse_channels_video()`

**绝对不要让 LLM 凭记忆写反查逻辑。** 必须基于真机抓包和实际接口响应迭代。详见 `docs/channels_reverse_eng.md`。

---

## License

MIT
