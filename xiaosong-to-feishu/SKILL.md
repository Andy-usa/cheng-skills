---
name: xiaosong-to-feishu
description: |
  把高晓松的视频号口播视频转录成纯文字逐字稿，作为 wiki 子节点收录到「高晓松热门口播」飞书 wiki 下，
  文末附视频播放量截图。文档纯一段文字、无任何 ## 标题/引用/加粗，方便复制到提词器口播。
  触发词：高晓松口播、高晓松热门、xiaosong-to-feishu。
  即使用户只是粘贴一个 wxapp.tc.qq.com 链接 + 一张截图、并提到"高晓松"，也应触发。
---

# Skill：高晓松视频号 → 飞书提词稿（wiki 子节点）

把高晓松的视频号视频转成 **可直接复制到提词器** 的纯口播稿，作为「高晓松热门口播」wiki 的子节点保存，文末附用户给的播放量截图。

## 父节点信息（已锁定）

| 项 | 值 |
|---|---|
| Wiki space ID | `7527486992573399041` |
| 父节点 token | `BFKhw668hiWF0dkIU0QcNLm2nJW` |
| 父节点底层 docx token | `SlNsdSpsPonrHrxZmbschfAOngd` |
| 父节点 URL | https://jmhm92ilup.feishu.cn/wiki/BFKhw668hiWF0dkIU0QcNLm2nJW |
| 标题 | 🔥 高晓松热门口播 |
| Owner | 程万云（`ou_f0c95a038d620a1cdb7256bb681f149b`） |

## 触发条件

用户提供：
- 一个 `wxapp.tc.qq.com` 视频链接
- 一张播放量截图（图片附件 / 本地路径）
- 上下文有"高晓松"或"热门口播"提示

## 工作流（5 步）

### Step 1：转录（复用 wechat-to-lark）

```bash
python3 ~/cheng-skills/wechat-to-lark/scripts/transcribe.py "<视频URL>"
```

返回 JSON：`{"ok": true, "text": "...", "elapsed": 12.3}`。

### Step 2：文字修订 + 标题提炼

**修订（轻度）：**
- 同音错字（视频号转写常见错字，按上下文判断）
- 标点错误
- ASR 切片缝隙（chunk 边界处可能切断词，前后拼接处肉眼能看出来）

**绝对不动：**
- 「啊/呢/嘛/吧」等语气词
- 口头禅、重复句式
- 句子顺序
- 末尾的「关注/下次见」类口头收尾——保留高晓松的人设语气

**标题（精炼）：**
- ≤ 10 个汉字最佳，最多不超过 14 个
- 抓最有记忆点的关键词
- 不用副标题、不用冒号断句
- 例：✅「我这辈子没打过工」/「写歌就是把旋律往外倒」/「李宗盛打磨一句词到凌晨」  
       ❌「高晓松谈我这辈子没给任何人打过工的人生哲学」（太长）

### Step 3：组装纯文本逐字稿

**关键约束**（比一般视频号转录严格得多）：
- ❌ **不要** `##` / `###` 任何标题
- ❌ **不要** `---` 分割线
- ❌ **不要** `>` 引用块
- ❌ **不要** `**加粗**` / `*斜体*`
- ❌ **不要** 多段空行分割（**全文只有一段**）
- ❌ **不要** 列表 `-` / `1.`
- ✅ 全部内容拼成一整段连续文字
- ✅ 句末用句号、问号、感叹号；句中用逗号顿号
- ✅ 直接引语用中文引号 `"…"`

**为什么**：用户要复制到提词器一气呵成念，任何排版字符都会干扰朗读节奏。

把整段文字写到 `~/feishu_article.md`（虽然是 .md 后缀，内容就是一整段纯文字，**没有任何 markdown 字符**）。

### Step 4：创建 wiki 子节点 + 写入正文 + 追加截图

```bash
# 4.1 在「高晓松热门口播」下创建子节点（一行搞定，自动挂载到父节点）
RESP=$(lark-cli wiki +node-create \
  --space-id 7527486992573399041 \
  --parent-node-token BFKhw668hiWF0dkIU0QcNLm2nJW \
  --obj-type docx \
  --title "<精炼标题>")

# 4.2 从响应里抠出新节点的 obj_token（实际 docx token）和 node_token
OBJ_TOKEN=$(echo "$RESP" | python3 -c "
import json, sys
raw = sys.stdin.read()
raw = raw[raw.index('{'):raw.rindex('}')+1]
print(json.loads(raw)['data']['node']['obj_token'])
")
NODE_TOKEN=$(echo "$RESP" | python3 -c "
import json, sys
raw = sys.stdin.read()
raw = raw[raw.index('{'):raw.rindex('}')+1]
print(json.loads(raw)['data']['node']['node_token'])
")

# 4.3 写正文（一整段纯文字）
cd ~ && lark-cli docs +update \
  --doc "$OBJ_TOKEN" \
  --mode overwrite \
  --markdown @feishu_article.md

# 4.4 追加截图到文末
lark-cli docs +media-insert \
  --doc "$OBJ_TOKEN" \
  --file "<截图本地绝对路径>" \
  --type image \
  --align center

# 4.5 拼出 wiki 子节点的可分享 URL
DOC_URL="https://jmhm92ilup.feishu.cn/wiki/$NODE_TOKEN"

# 4.6 清理临时文件
rm -f ~/feishu_article.md
```

⚠️ **不需要**手动给父节点追加链接条目——wiki 子节点天然挂在 `BFKhw668hiWF0dkIU0QcNLm2nJW` 下，会自动出现在父节点的"子文档"列表里。

### Step 5：推飞书私信通知

```bash
lark-cli im +messages-send --as bot \
  --user-id ou_f0c95a038d620a1cdb7256bb681f149b \
  --markdown "🎙 **高晓松口播已收录**

《<精炼标题>》

🔗 子文档：$DOC_URL
📚 总目录：https://jmhm92ilup.feishu.cn/wiki/BFKhw668hiWF0dkIU0QcNLm2nJW

来源：微信视频号"
```

## 错误处理

| 情况 | 处理 |
|---|---|
| 转录失败 | 看 `transcribe.py` stderr；多半是视频号 URL 过期或 DASHSCOPE_API_KEY 失效 |
| 截图找不到 | 让用户重发图片（必须是本地文件路径，不能是 URL） |
| `wiki +node-create` 报权限 | 需要 `wiki:node:create` scope，必要时 `lark-cli auth login --recommend` 重授权 |
| `docs +media-insert` 报权限 | 需要 `docs:document.media:upload` scope |
| 子文档创建成功但截图插入失败 | 子文档保留，截图可后续手动补；推消息时说明这一点 |
| 父节点 token 失效（用户改了文档结构） | 用 `lark-cli api GET /open-apis/wiki/v2/spaces/get_node --params '{"token":"BFKhw668hiWF0dkIU0QcNLm2nJW"}'` 重查；改 SKILL.md |

## 用户偏好

- 简体中文回复（`~/.claude/CLAUDE.md`）
- 紧凑段落、TodoWrite 跟进度
- 不主动建 PR

## 依赖

- `python3 ~/cheng-skills/wechat-to-lark/scripts/transcribe.py`
- `lark-cli`（user-level OAuth 已持久化）
- 环境变量 `DASHSCOPE_API_KEY`

## 输出范例

成功后用户应看到飞书私信：
```
🎙 高晓松口播已收录
《我这辈子没打过工》
🔗 子文档：https://jmhm92ilup.feishu.cn/wiki/<NEW_NODE>
📚 总目录：https://jmhm92ilup.feishu.cn/wiki/BFKhw668hiWF0dkIU0QcNLm2nJW
```

打开「高晓松热门口播」wiki 树，会看到 **🔥 高晓松热门口播 → 我这辈子没打过工** 这条新增子节点。

打开子文档：
- 标题：我这辈子没打过工
- 正文：一整段约 1500-3000 字纯口播文字（无任何排版字符）
- 文末：一张视频播放量截图（居中）
