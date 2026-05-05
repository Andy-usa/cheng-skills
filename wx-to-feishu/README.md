# wx-to-feishu

> **状态：WIP（占位）。** 等 chatlog 类工具对 macOS 微信 4.1.7.x 的兼容性确认后再补全 worker 实现。
> 当前先把**部署文档 + chatlog 探路指引**沉淀下来，避免重复踩坑。

监听 Mac 微信「文件传输助手」的消息流，把转发进来的公众号文章 / 视频号视频自动写入飞书云文档，飞书私信通知。

完整设计见 `SKILL.md`。

---

## ⚠️ 兼容性现状（重要，先读这一段）

| 工具 | 测试到的最高 Mac 微信版本 | HTTP API / 实时监听 | 4.1.7.x 兼容性 |
|---|---|---|---|
| sjzar/chatlog（**已下架**）| 3.x / 4.0 | ✅ | ❌ 已停更，2025-10-20 因合规警告下架 |
| WechatRagAgent/chatlog-new（fork）| 3.x / 4.0 | ✅ | ❌ 停留在 v0.0.16（2025-07） |
| **Thearas/wechat-db-decrypt-macos** | **4.1.2.241** | ❌ 只解密 + MCP | ⚠️ 4.1.2 之后未测，4.1.7 不确定 |
| ylytdeng/wechat-decrypt | 4.0 | ✅ real-time monitor | ❌ 4.0 时代设计 |
| teest114514/chatlog_alpha（fork）| 承诺"尽可能同步最新解密源码" | ✅ | ⚠️ 不确定，但有维护意愿 |

**结论**：当前没有任何工具明确测试支持 4.1.7.2。**部署前必须先做探路实验**（见下面）。

## 🔬 探路实验（部署前必做）

iMac 上跑以下命令，确认密钥能否成功提取：

```bash
# 前置
brew install go
# Mac 微信必须运行（前台或后台都行，不能完全退出）

# 候选 1：Thearas/wechat-db-decrypt-macos —— 唯一明确针对 4.1 系列的工具
git clone https://github.com/Thearas/wechat-db-decrypt-macos ~/wxdb-thearas
cd ~/wxdb-thearas
# 按 README 跑，看是否能输出 db key（如 "key: 0xabcdef..." 之类）

# 候选 2：teest114514/chatlog_alpha —— chatlog fork，集成度最高
git clone https://github.com/teest114514/chatlog_alpha ~/chatlog-alpha
cd ~/chatlog-alpha && go build -o chatlog .
./chatlog                          # 启 TUI，按提示选择"自动解密 + 启动 HTTP 服务"
# 启动成功后另起终端：
curl http://127.0.0.1:5030/api/v1/contact | head    # 看是否返回联系人列表
curl "http://127.0.0.1:5030/api/v1/chatlog?talker=filehelper&time=今天&format=json" | head
```

**判定**：

- ✅ **chatlog_alpha 跑通 + HTTP API 返回真实数据** → 走完整 wx-to-feishu 部署
- ⚠️ **只有 Thearas 解密通、没 HTTP API** → 需要写一个适配层，从 SQLite 直接轮询
- ❌ **两个都报 key 提取失败** → 4.1.7.2 内存布局变了，**当前没有现成方案**，三个选择：
  1. 把 Mac 微信降回 4.1.2.x（找老 dmg + 注意登录态）
  2. 等社区跟进（关注上面三个仓库的 issues）
  3. 改走 iPhone Shortcuts 路径处理公众号文章，视频号继续手动复制

## 🚀 完整部署（探路成功后才适用）

> 以下步骤假设你已确认 chatlog_alpha 能解密并启 HTTP 服务。

### 1. 配置 chatlog 自启动

```bash
mkdir -p ~/Library/LaunchAgents
cp deploy/com.cheng.chatlog.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cheng.chatlog.plist
launchctl list | grep chatlog
```

### 2. 配置 wx-to-feishu

```bash
cd ~/cheng-skills/wx-to-feishu
cp .env.example .env
$EDITOR .env                                  # 填 LARK_USER_OPEN_ID 等
pip install -e .
python scripts/worker.py --once               # 处理最近一条新消息然后退出，验证全链路
```

### 3. worker 自启动

```bash
cp deploy/com.cheng.wx-to-feishu.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.cheng.wx-to-feishu.plist
launchctl list | grep wx-to-feishu
```

### 4. 验证端到端

手机微信里把任意一篇公众号文章转发给文件传输助手 → 等 5~10 秒 → 飞书机器人应该推一条私信，附带文档链接。

## 🔧 排错速查

| 症状 | 排查命令 |
|---|---|
| 转发后无反应 | `curl http://127.0.0.1:5030/api/v1/chatlog?talker=filehelper\&time=今天 \| head` |
| chatlog 启动报 "key timeout" | 确认 Mac 微信运行；Apple Silicon 用户检查是否 Rosetta 模式 |
| 公众号抓取失败 | 确认 `weixin-to-feishu` skill 的 Playwright 跑得起来 |
| 视频号转录失败 | CDN 链接通常几小时过期，重新转发即可 |
| 写飞书失败 | `lark-cli auth status` 看登录态 |
| worker 进程没跑起来 | `launchctl list | grep wx-to-feishu`；看 `~/Library/Logs/wx-to-feishu.log` |

## 📁 文件结构

```
wx-to-feishu/
├── SKILL.md                # 给 Claude Code 用的 skill 描述
├── README.md               # 本文件（部署 + 排错）
├── pyproject.toml          # （WIP）
├── .env.example            # 环境变量模板
├── .gitignore
├── scripts/                # （WIP）
│   ├── worker.py           # 主 worker
│   ├── parser.py           # XML 消息解析
│   ├── handlers.py         # 公众号 / 视频号处理
│   └── store.py            # SQLite 去重
├── data/                   # 运行时状态
└── deploy/                 # （WIP）
    ├── com.cheng.chatlog.plist
    └── com.cheng.wx-to-feishu.plist
```

## ⚖️ 合规声明

本 skill 的核心数据流是**在用户本机解密用户自己的微信数据库**：

- ✅ 仅本地运行，不对外提供服务
- ✅ 不分享解密后的数据
- ✅ 不用于商业目的
- ⚠️ chatlog 主仓库于 2025-10-20 因腾讯合规警告主动下架。使用 fork 仍存在合规风险，**完全自负**

如不接受此风险，请改用 iPhone Shortcuts 处理公众号文章 + 手动复制视频号链接的混合方案。
