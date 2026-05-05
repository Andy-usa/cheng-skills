---
name: wx-to-feishu
description: 监听 Mac 微信文件传输助手的消息，自动把转发进来的公众号文章和视频号视频写入飞书云文档，并通过飞书机器人推送通知。依赖 chatlog 镜像 fork 解密本地数据库。仅本地自用，不对外提供服务。触发词：转发到文件传输助手、自动转录、wx-to-feishu、监听文件传输助手。
---

# Skill: 微信文件传输助手 → 飞书自动转录

## 这个 skill 是什么

一个**常驻在 iMac 上**的本地服务。当你在手机微信里把公众号文章或视频号视频转发到「文件传输助手」时，它会：

1. 通过 chatlog 拿到这条消息的完整 XML
2. 判断是公众号文章还是视频号视频
3. 自动调用 `wechat-to-lark` skill 跑转录/抓取
4. 写入飞书云文档
5. 飞书私信推送文档链接给你

**整套链路完全本地、不对外开放任何端口**。chatlog 只在 `127.0.0.1` 上监听，wx-to-feishu worker 只读 chatlog 本地 API。

## 重要前提：合规与风险

⚠️ **chatlog 主仓库（sjzar/chatlog）已于 2025-10-20 因腾讯合规警告主动下架**。本 skill 依赖 chatlog 镜像 fork（如 `WechatRagAgent/chatlog-new`）。使用前请确认：

- ✅ **仅本地自用、不对外提供服务、不分享解密后的数据**
- ✅ 接受腾讯可能针对此类工具的使用方采取的合规措施（封号风险虽低但非零）
- ✅ Mac 微信版本与 chatlog fork 版本兼容（fork 停留在 v0.0.16 时支持微信 3.x / 4.0）

如果你不接受以上前提，**请停止使用本 skill，改用 iPhone Shortcuts + 手动复制视频号链接**的混合方案。

## 触发条件（给 Claude Code 的）

当用户说出以下任一意图时，引导用户走部署流程或排查现有部署：

- "帮我装一下 wx-to-feishu"
- "我转发到文件传输助手没反应"
- "chatlog 启动失败 / 解密失败"
- "wx-to-feishu worker 挂了"
- "我升级了微信版本，转录不工作了"

## 系统架构

```
[手机微信] 转发文章/视频号
       ↓
[iMac 微信] 收到消息，写入本地 SQLite（加密）
       ↓
[chatlog daemon @ 127.0.0.1:5030]
   - 解密 SQLite
   - HTTP API 暴露消息
       ↓
[wx-to-feishu worker]
   - 每 5 秒轮询 chatlog
   - 过滤 talker=filehelper + MsgType=49
   - 解析 XML → article / sph
   - SQLite 去重（避免重复处理）
       ↓
   ├─ 公众号文章 → wechat-to-lark 抓正文 → lark-cli 写飞书
   └─ 视频号视频 → wechat-to-lark transcribe → lark-cli 写飞书
       ↓
[飞书机器人] 推私信通知
```

## 文件清单

```
wx-to-feishu/
├── SKILL.md                    # 本文件
├── README.md                   # 详细部署 / 排错文档
├── pyproject.toml              # Python 依赖
├── .env.example                # 环境变量模板
├── .gitignore
├── scripts/
│   ├── worker.py               # 主 worker
│   ├── parser.py               # XML 消息解析
│   ├── handlers.py             # 公众号 / 视频号处理
│   └── store.py                # SQLite 去重
├── data/                       # 运行时状态（state.db），git 忽略
└── deploy/
    ├── com.cheng.chatlog.plist        # chatlog 自启动
    └── com.cheng.wx-to-feishu.plist   # worker 自启动
```

## 部署速查

完整步骤见 `README.md`，核心 4 步：

```bash
# 1. 装 chatlog（镜像 fork 版本）
brew install go
git clone https://github.com/WechatRagAgent/chatlog-new ~/chatlog
cd ~/chatlog && go build -o chatlog .
# 首次跑 chatlog server 完成 key 解密 + 启动 HTTP

# 2. 装 wx-to-feishu
cd ~/cheng-skills/wx-to-feishu
cp .env.example .env  # 填飞书 open_id 和 wechat-to-lark 路径
pip install -e .

# 3. 测试单条
python scripts/worker.py --once  # 处理一条最新消息然后退出

# 4. 守护进程化
cp deploy/*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cheng.chatlog.plist
launchctl load ~/Library/LaunchAgents/com.cheng.wx-to-feishu.plist
```

## 已知限制

1. **微信必须前台或后台运行**——chatlog 需要从内存读 key，微信完全退出后无法解密新消息
2. **iMac 必须常开**——息屏可以，进入睡眠会暂停 chatlog 心跳，唤醒后继续
3. **微信大版本更新可能 break chatlog**——遇到这种情况升级 chatlog fork 或临时回滚 Mac 微信版本
4. **24 小时内重复转发同一条消息只处理一次**——store.py 用 msg_id 去重
5. **CDN 链接时效性**——视频号 mediaUrl 通常几小时过期，wx-to-feishu 检测到后立即调 transcribe，不延迟

## 如何排错

| 症状 | 排查 |
|---|---|
| 转发后无反应 | `curl http://127.0.0.1:5030/api/v1/chatlog?talker=filehelper&time=今天 | head` 看 chatlog API 是否通 |
| chatlog 启动报 "key timeout" | Mac 微信没运行 / Rosetta 模式问题，参考 README 的 Apple Silicon 章节 |
| 公众号文章抓取失败 | 检查 `wechat-to-lark` Playwright 的代理 / TLS 配置 |
| 视频号转录失败 | CDN 链接过期，重新转发即可 |
| worker 写飞书失败 | `lark-cli auth status` 看登录态 |

## 相关 skill

- `wechat-to-lark`: 实际的"链接 → 飞书文档"实现，wx-to-feishu 在底层调用它
- `xiaosong-to-feishu`: 视频号的 wiki 子文档收录模板，可选集成
