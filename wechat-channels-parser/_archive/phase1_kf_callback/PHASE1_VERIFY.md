# Phase 1 真机验证报告

## 自动化验证（已通过）

```bash
$ python3 -m pytest -v
============================== 32 passed in 4.32s ==============================
```

| 模块 | 用例数 | 覆盖范围 |
|---|---|---|
| `test_crypto.py` | 10 | PKCS7、签名、加解密往返、签名错、receive_id 错、msglen 越界 |
| `test_state.py` | 6 | JSON 原子读写、滚动窗口、损坏文件容错 |
| `test_kf_client.py` | 5 | sync_msg、has_more 分页、token 刷新、errcode 失败 |
| `test_handlers.py` | 6 | 各 msgtype 分发、origin 过滤、msgid 判重 |
| `test_main.py` | 5 | health、URL 验签、POST 解密 + BackgroundTasks 调度 |

---

## 真机验证步骤

### 前置准备

1. ✅ `.env` 已填入真实凭据
2. ✅ 服务跑起来：`uvicorn app.main:app --host 0.0.0.0 --port 8000`
3. ✅ ngrok（或类似工具）暴露：`ngrok http 8000`
4. ✅ 企业微信后台填回调 URL，看到「保存成功」

### Step 1：URL 配置验签

**操作**：在企业微信「微信客服 → 接收消息配置」点「保存」。

**预期**：
- 后台返回「保存成功」
- 服务端日志看到 `GET /wechat/callback?msg_signature=...&echostr=...` 200 响应

**如果失败**：检查 `WECHAT_CALLBACK_TOKEN` / `WECHAT_CALLBACK_AES_KEY` / `WECHAT_CORP_ID` 三者是否与企业微信后台填的完全一致。

---

### Step 2：text 消息往返

**操作**：用一个微信号添加客服号为好友 → 发送 "hello"。

**预期**：
- 客户端：客服号秒回「请直接转发视频号视频给我，我会帮你解析出原始链接。」
- 服务端日志依次出现：
  1. `callback_received` — POST /wechat/callback 收到
  2. `sync_msg_all done` — 拉了 N 条消息（应当 ≥ 1）
  3. `msg_received` — `msgtype=text`，`origin=3`，**完整 raw msg dump**
  4. `msg_processed` — `elapsed_ms=...`

**关键检查**：日志里 `raw` 字段应包含 `msgid` / `external_userid` / `open_kfid` / `text.content`。

---

### Step 3：channels 消息真机 dump（**Phase 1 核心验证项**）

**操作**：用一个微信号在视频号里随便点开一个视频 → 转发给客服号。

**预期**：
- 服务端日志看到 `msg_received`，`msgtype=channels`
- `raw.channels` 字段必须包含 `finder_username` / `nonce_id`（**这两个字段是 Phase 2 解析器的输入**）
- 客户端：客服号回一条 link 消息，标题为 `[STUB] 视频号解析未实现`（这是 stub 行为，符合预期）

**把这条 raw 消息体保存到 `tests/fixtures/sample_channels_msg.json`，作为 Phase 2 解析器的真实输入样本。**

---

### Step 4：防重复处理

**操作**：在企业微信后台手动重发一次同一条 channels 消息（或在收到回调后立刻 kill 服务再重启 — 模拟回调重试）。

**预期**：
- 第二次推送时，`msg_received` 不会重复打印同一个 msgid
- 看到 `skip duplicate` 日志（debug 级别，调高 LOG_LEVEL=DEBUG 可见）
- 客户端不会收到重复回复

---

### Step 5：origin 过滤（避免死循环）

**操作**：服务运行中，从企业微信「客服会话」面板里手动发一条消息给客户。

**预期**：
- `sync_msg` 拉到这条 origin=4 的消息
- 日志看到 `skip non-customer message`
- 不会触发 send_msg 二次回复（否则会无限循环）

---

## 验收清单

- [ ] Step 1 URL 配置验签通过
- [ ] Step 2 text 消息能拿到完整 dump 并自动回复
- [ ] **Step 3 channels 消息体里能看到 `finder_username` 和 `nonce_id`**（Phase 2 必备前提）
- [ ] Step 4 重复推送不会重复处理
- [ ] Step 5 客服自己发的消息不会触发回复

---

## 已知风险

1. **5 秒超时**：BackgroundTasks 是同进程后台任务，如果 sync_msg + 处理 100 条消息超过 5s，企业微信会重试。msgid 判重保证幂等，但日志会有噪音。Phase 2 之后如果遇到这种情况，把 `handle_callback_event` 改成丢进真正的 task queue（Celery / RQ / arq）。
2. **state.json 单点**：单实例进程读写本地 JSON。如果横向扩展多实例，必须换成共享 KV（Redis / 数据库）。当前规模无需考虑。
3. **channels 字段名假设**：当前 `_handle_channels` 假设字段叫 `finder_username` / `nonce_id`。**Step 3 真机 dump 之后必须根据实际响应修正** `app/handlers.py:_handle_channels`。
