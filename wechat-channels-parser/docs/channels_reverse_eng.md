# 视频号解析器逆向笔记

> ⚠️ 此文档为 **Phase 2 占位**。本文不应包含任何 LLM 凭记忆写出来的接口细节。

## 任务

实现 `app/channels_parser.py:parse_channels_video()`：根据 `finder_username` 和 `nonce_id` 拿到视频号视频的真实 mp4 直链 + 标题/作者/封面/时长等元数据。

## 必备前置

1. **真机抓包样本**：跑过 `PHASE1_VERIFY.md Step 3`，得到至少一条真实的 channels 消息体，存到 `tests/fixtures/sample_channels_msg.json`。
2. **明确 finder_username / nonce_id 的真实字段名**：可能与本仓库当前假设（`finder_username` / `nonce_id`）不同，以真机日志为准。

## 工作步骤建议

1. 用 mitmproxy / Charles / Wireshark 抓取微信视频号 App 加载视频时的请求
2. 找到返回 mp4 直链的关键接口，记录请求方法 / URL / 必备 header / 必备签名
3. 在本文档里把抓到的接口、必备字段、签名算法写清楚（**不能凭记忆，要有实际抓包证据**）
4. 用 `httpx` 在 `parse_channels_video()` 里复现请求，写单测用真实 fixture 校验
5. 错误处理：接口返回非 0 时抛 `ChannelsParseError`，由 `handlers._handle_channels` 转成给用户的「解析失败」回复

## 风险提示

- 视频号接口未公开，**腾讯随时可能改动**。Phase 2 上线后要做好接口失效监控，触发告警时人工介入更新。
- 反爬虫策略可能逐步加强，注意请求频率、User-Agent、cookie / token 注入。
- 强烈建议这个客服账号挂在独立企业主体下，封了不影响主线业务。

## 现状

```python
# app/channels_parser.py
async def parse_channels_video(finder_username, nonce_id, extra=None) -> ChannelsVideo:
    # Phase 1 stub: returns mock data with title="[STUB] 视频号解析未实现"
    ...
```

替换该函数的实现即可，调用方（`handlers._handle_channels`）无需修改。
