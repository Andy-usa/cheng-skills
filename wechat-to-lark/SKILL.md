---
name: wechat-to-lark
description: 微信内容 → 飞书文档。支持两种链接类型：(1) 微信公众号文章（mp.weixin.qq.com）自动抓取并格式化写入飞书；(2) 微信视频号视频（wxapp.tc.qq.com）自动转写为逐字稿写入飞书。无论哪种，最后都会推送一条飞书私信给你，里面带文档链接。触发词：保存到飞书、写入飞书、转写、视频转文字、推送到飞书。即使用户只是粘贴一个微信链接，也应触发。
---

# Skill：微信内容 → 飞书文档

把微信公众号文章或视频号视频一键转化为飞书文档，并把链接通过飞书私信推给用户。根据链接类型自动选择提取方案。

## 触发条件

用户发送以下任一类型的链接时自动触发：

| 链接类型 | 域名特征 | 处理方案 |
|---------|---------|---------|
| 公众号文章 | `mp.weixin.qq.com` | 方案 A：Playwright 抓取网页 |
| 视频号视频 | `wxapp.tc.qq.com` | 方案 B：ffmpeg 抽音 → qwen3-asr-flash |

## 方案 A：公众号文章提取

### A1. 抓取文章内容

**首选：Playwright 无头浏览器**

```python
import asyncio
from playwright.async_api import async_playwright

async def fetch_and_convert():
    async with async_playwright() as p:
        # 注意：sandbox / 受控网络环境下常有 TLS 拦截，必须忽略证书错误
        browser = await p.chromium.launch(
            headless=True,
            args=["--ignore-certificate-errors", "--no-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            locale="zh-CN",
            ignore_https_errors=True,
        )
        page = await context.new_page()
        await page.goto("文章URL", wait_until="networkidle", timeout=45000)
        await page.wait_for_timeout(2000)

        html = await page.content()
        if "环境异常" in html or "去验证" in html or "完成验证" in html:
            print("STATUS: SECURITY_BLOCK")
            await browser.close()
            return

        title = (await (await page.query_selector("#activity-name")).inner_text()).strip()
        author = (await (await page.query_selector("#js_name")).inner_text()).strip()
        time_el = await page.query_selector("#publish_time") or await page.query_selector("em#publish_time")
        pub_time = (await time_el.inner_text()).strip() if time_el else ""

        md = await page.evaluate("""() => { /* 见下方 JS 提取逻辑 */ }""")
        await browser.close()
```

**Playwright 不存在时**：`pip3 install -q playwright && python3 -m playwright install chromium`

JS 提取逻辑要点：
- 从 `#js_content` 容器递归遍历 DOM 节点
- `<section>`/`<p>`/`<div>` → 段落（前后加空行）
- `<strong>`/`<b>` 或 `font-weight >= 600` → `**加粗**`
- `<h1>`-`<h4>` → 对应 `#`-`####` 标题
- `<img>` → `![](data-src 或 src)`，过滤 icon/emoji 类小图（width<50 或 className 含 icon/emoji）
- `<blockquote>` → `> 引用`
- `<a href>` → `[文本](href)`，跳过 `javascript:`
- `<code>` → `` `代码` ``，`<pre>` → 代码块
- `<ul>/<ol>/<li>` → `- 列表项` 或 `1. 列表项`
- `<hr>`/`<br>` → `---`/换行
- 加粗短文本（≤80 字、无换行）+ font-size >= 18px → `## 标题`（识别公众号惯用的"伪标题"）
- 过滤 `display:none / visibility:hidden` 隐藏元素
- 末尾把 3+ 连续空行压缩到 2 行

**备选：Chrome MCP**

如果 Playwright 不可用但 `mcp__Claude_in_Chrome` 可用：
1. `mcp__Claude_in_Chrome__navigate` 打开文章 URL
2. 等待 2-3 秒页面加载
3. `mcp__Claude_in_Chrome__get_page_text` 获取全文

**最后手段：WebFetch**

微信大概率会触发安全验证，此时告知用户。

### A2. 提取结构化内容

| 字段 | 说明 | 必需 |
|------|------|------|
| 标题 | `#activity-name` | ✅ |
| 作者/公众号名称 | `#js_name` 或 `.rich_media_meta_nickname a` | 尽量提取 |
| 发布时间 | `#publish_time` 或 `em#publish_time` | 尽量提取 |
| 正文 | `#js_content` 内的所有结构化内容 | ✅ |

**必须过滤掉的内容：**
- 页脚导航、"阅读原文"链接
- 广告、推广内容、公众号关注引导
- 文末投票、评论区、"点赞、在看、转发"引导语
- 微信平台 UI 元素

### A3. 格式化为 Markdown

**文档头部：**
```markdown
> 来源：[公众号名称](原文URL) | 发布时间：xxxx-xx-xx

---
```

**正文规则：**
- 段落之间一个空行，保持段落完整性
- 文章大标题不在正文中重复（已作为飞书文档标题）
- 加粗 → `**文本**`，斜体 → `*文本*`
- 图片 → `![](图片URL)`，去除装饰性图片
- 引用 → `> 引用文本`
- 超链接保留：`[文本](URL)`
- emoji 和特殊符号原样保留

---

## 方案 B：视频号语音转写

### B1. 用 transcribe.py 做云端 ASR（首选）

```bash
python3 ~/cheng-skills/wechat-to-lark/scripts/transcribe.py "视频URL"
```

输出 JSON：`{"ok": true, "text": "...", "elapsed": 12.3, "duration": 168.0, "chunks": 1}`

**脚本内部做了什么：**
1. `ffmpeg` 流式从 URL 抽音轨为 16kHz/mono/32kbps mp3（不保存视频本体；100MB 视频也只产生 ~1MB mp3）
2. 若时长 > 185s，按 165s 切片（绕开 qwen3-asr-flash ~3 分钟单段上限）
3. 每段 base64 内联调用百炼 `qwen3-asr-flash`（OpenAI 兼容接口）
4. 拼接结果

**为什么不用 paraformer-v2 / dashscope SDK：**
- `dashscope` SDK 在某些环境装不上（cryptography ABI 冲突）
- paraformer 的 `file_urls` 由 Bailian 后端去拉视频文件；100+ MB 文件实测会超时
- 我们抽完音轨再发 base64，只走 ~1MB 数据，没有任何下载相关失败

**依赖：** `ffmpeg`（`apt-get install -y ffmpeg`），环境变量 `DASHSCOPE_API_KEY`

### B2. 文字修订

对转写文案做 **轻度** 修订：

**只改这些：**
- 错别字（同音错字）
- 明显的标点错误
- 语音识别乱码、无意义片段
- 末尾的广告推荐、关注引导等非正文内容

**不要改这些：**
- 正常的口语化表达和语气词
- 作者的个人用语风格
- 段落结构、叙事顺序、观点

**段落整理：**
- ASR 返回的是大段连续文字，需要按语义切分自然段
- 适当加 `## 小标题` 让长文易读

### B3. 生成标题

根据文案内容生成简洁有吸引力的中文标题。

---

## 通用步骤：写入飞书 + 推送私信

### 1. 检查 lark-cli 已登录

```bash
lark-cli auth status     # tokenStatus 应该是 "valid"
lark-cli auth list       # 拿到当前 user 的 userOpenId（用于推消息）
```

**如果未登录**：本仓库已经配了 SessionStart hook，会自动从 `.lark-cli-backup/` 还原 token。如果还原失败（比如首次使用、token 失效），按提示 `lark-cli config init --new` + `lark-cli auth login --recommend`，每次只是首次 setup，之后跨 session 都不用重做。

### 2. 写入文档（两步法，避免大文档 async 超时）

```bash
# 1) 把完整内容写到 ~/feishu_article.md，占位写到 ~/feishu_mini.md
# 2) 创建占位文档
cd ~ && lark-cli docs +create --title "标题" --markdown @feishu_mini.md
# → 拿到 doc_id 和 doc_url

# 3) 用完整内容覆盖
cd ~ && lark-cli docs +update --doc "{doc_id}" --mode overwrite --markdown @feishu_article.md

# 4) 清理临时文件
rm -f ~/feishu_article.md ~/feishu_mini.md
```

注意：
- `--markdown` 只接受 `@文件名`（相对路径）
- 临时文件用完即删
- 如果返回 `"status": "running"` 和 `task_id`，再执行一次同样的命令即可拿最终结果

### 3. 推送飞书私信（最后一步，必做）

```bash
USER_OPEN_ID=$(lark-cli auth list --jq '.[0].userOpenId' -r 2>/dev/null \
  || lark-cli auth list | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["userOpenId"])')

lark-cli im +messages-send --as bot --user-id "$USER_OPEN_ID" --markdown "📝 **已保存到飞书**

《文档标题》

🔗 https://www.feishu.cn/docx/{doc_id}

来源：xxx"
```

emoji 选择：公众号文章用 📰；视频转写用 📚 或 📝。

## 返回结果

**公众号文章：**
```
已创建飞书文档并推送私信：
标题：《文章标题》
来源：公众号名称 · 发布时间
链接：https://xxx.feishu.cn/docx/xxx
```

**视频号视频：**
```
已创建飞书文档并推送私信：
标题：《文章标题》
转写耗时：XX 秒（时长 XX:XX，X 段）
链接：https://xxx.feishu.cn/docx/xxx
```

## 错误处理

| 情况 | 处理方式 |
|------|---------|
| Playwright 报 `ERR_CERT_AUTHORITY_INVALID` | 加 `args=["--ignore-certificate-errors","--no-sandbox"]` 和 `ignore_https_errors=True` |
| Playwright 遇到微信安全验证 | 内容里有"环境异常"/"去验证"，告知用户，尝试 Chrome MCP |
| 公众号文章正文为空 | 大概率是 lazy-load，把 `wait_for_timeout` 提到 5000+，或换 networkidle |
| `transcribe.py` 报 ffmpeg 错 | `apt-get install -y ffmpeg` 后重试 |
| `transcribe.py` 报 "audio is too long" | 把 `CHUNK_SECONDS` 调小（如 120）后重试 |
| qwen3-asr-flash 超 base64 限制 | 同上，把 `CHUNK_SECONDS` 减小 |
| 视频 URL 已过期（HTTP 403/失败） | 告知用户重新抓一份新链接（视频号 URL 有时效） |
| `lark-cli auth status` 报 not configured | 看本文 §"通用步骤 1"，运行 config init + auth login（仅首次） |
| `lark-cli docs +update` 失败 | 检查 doc_id 是否正确；token 是否过期，必要时 `lark-cli auth login --recommend` |

## 依赖速查

| 工具 | 安装 | 用途 |
|---|---|---|
| ffmpeg | `apt-get install -y ffmpeg` | 抽音轨 |
| Playwright | `pip3 install playwright && python3 -m playwright install chromium` | 抓公众号 |
| lark-cli | `npm install -g @larksuite/cli` | 写飞书 + 发消息 |
| `DASHSCOPE_API_KEY` | 阿里云百炼控制台 | qwen3-asr-flash 鉴权 |

## 跨 Session 持久化（已配置）

本仓库的 `.claude/hooks/lark-cli-restore.sh` + `.claude/hooks/lark-cli-backup.sh` 会在 SessionStart / Stop 自动备份和还原 lark-cli 的 `~/.lark-cli/` 和 `~/.local/share/lark-cli/`（含 AES master.key 和 OAuth token）到 `.lark-cli-backup/`。备份目录已 gitignore，**绝不能提交**。

只要这两个 hook 在，远程 sandbox 重置后下次新 session 启动会自动登录态恢复，不用再走 OAuth。
