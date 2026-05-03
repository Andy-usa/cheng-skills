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

## 工作流（6 步）

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

**标题（固定格式）：**

> **`<主人公名字>：<高晓松对他的一句话评价>`**

- **主人公名字**：本期口播在聊谁（王朔、李宗盛、朴树、老狼、王菲、罗大佑……）。中文姓名优先，没有就用大家熟知的称呼
- **冒号后**：抓高晓松原话里最精炼的一句"定性"，越具体越有画面感
- 整体长度 **≤ 14 字**最佳，**绝对不超过 18 字**

**正例：**

| ✅ 标题 | 提炼来源 |
|---|---|
| 王朔：八十年代最亮的灯塔 | "在这一众明亮的灯塔中间，王朔朔爷应该算是那个最最明亮的灯塔之一" |
| 李宗盛：一句词打磨到凌晨 | "讲李宗盛在录音室里怎么把一句歌词打磨到凌晨" |
| 朴树：闭关三天胡子没刮 | "讲朴树在棚里闭关三天三夜出来是胡子没刮的模样" |
| 王朔：起于草莽羽化成仙 | "应该说叫起于草莽吧 / 平虚御风 / 羽化成仙" |

**反例（不要这样写）：**

| ❌ 标题 | 原因 |
|---|---|
| 我目睹朔爷羽化成仙 | 缺主人公名字 + 冒号格式 |
| 写歌就是把旋律往外倒 | 抒情型 / 不是对人的评价 |
| 看王朔小说哭得跟鬼一样 | 讲自己感受不是对人的评价 |
| 八十年代群星璀璨 | 没有具体主人公 |
| 王朔：很厉害的作家 | 评价过于平庸，缺画面感 |

**操作步骤：**

1. 通读全文，确定主人公（出现频次最高 / 标题问"X是谁"答得出来的那个人）
2. 在原文里找最精炼、最有画面感的一句"定性句" — 通常含比喻或动作
3. 把那句话压缩到 4-10 字，去虚词留实词
4. 拼接：`<人名>：<压缩后的评价>`

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

### Step 4.7：在父节点正文里追加目录条目（编号 H3 + 简介 + 子文档卡片）

父节点正文里维护一份带预览的目录，**用户钦定的格式**：

```markdown
### N.<标题>

<开头 80-120 字简介，普通段落><mention-doc token="<子文档node_token>" type="wiki"><标题></mention-doc>
```

要点：
- **`### N.`** — H3 标题加编号点号（如 `### 1.王朔：80年代最亮的灯塔`），编号是当前父文档已有条目数 +1
- **简介** — 转录稿开头 80-120 字到自然句末（普通段落，**不要**用 `>` 引用块）
- **`<mention-doc>` 标签** — 飞书原生子文档卡片，**紧跟在简介末尾、不换行不空行**。参数 `token=<wiki node_token>`、`type="wiki"`、内文是子文档标题。会渲染成行内卡片
- H3 与简介之间用一个空行；简介和 mention-doc 在**同一段同一行**

**实操：**

```bash
# 4.7.1 拉父节点当前正文，确定下一个编号 N+1
NEXT_NUM=$(lark-cli docs +fetch --doc SlNsdSpsPonrHrxZmbschfAOngd 2>&1 | python3 -c "
import json, re, sys
raw = sys.stdin.read()
raw = raw[raw.index('{'):raw.rindex('}')+1]
md = json.loads(raw)['data'].get('markdown','')
nums = [int(m.group(1)) for m in re.finditer(r'^### (\d+)\.', md, re.MULTILINE)]
print((max(nums) if nums else 0) + 1)
")

# 4.7.2 取转录稿前 80-120 字作为简介，到自然句末截断
PREVIEW=$(python3 -c "
text = open('/root/feishu_article.md').read().strip()
end = -1
for i, ch in enumerate(text):
    if ch in '。？！' and 60 <= i <= 140:
        end = i + 1
        break
if end == -1:
    end = min(120, len(text))
print(text[:end])
")

# 4.7.3 拼出 markdown 并追加（mention-doc 紧跟简介末尾，**同行**）
cat > /root/parent_append.md <<EOF

### ${NEXT_NUM}.${TITLE}

${PREVIEW}<mention-doc token="${NODE_TOKEN}" type="wiki">${TITLE}</mention-doc>

EOF

# lark-cli +update 不接受绝对路径 --markdown，必须 cd 到文件目录后用相对路径
cd /root && lark-cli docs +update \
  --doc SlNsdSpsPonrHrxZmbschfAOngd \
  --mode append \
  --markdown @parent_append.md

rm -f /root/parent_append.md
```

**说明**：
- `SlNsdSpsPonrHrxZmbschfAOngd` 是父 wiki 节点底下绑定的 docx token（已锁定）
- `<mention-doc token>` 写的时候用 **wiki node_token + type="wiki"**；fetch 回来 lark-cli 会把它转换成 `obj_token + type="docx"`，**功能等价、飞书渲染一样**，不要折腾把它转回去
- 编号 N 自动从父文档现有最大值 +1，避免重号
- 简介就是开头一段，不加 `>`，不加任何样式
- mention-doc **紧跟简介句末，无空行无换行**

### ⚠️ 改标题时的踩坑提醒

要修改某条已发布的标题，需要**三处同步**：
1. 子文档（wiki node）title
2. 父节点的 H3 行
3. 父节点的 mention-doc 内文

**正确做法**（一次 overwrite 到位）：
- 子文档：`lark-cli docs +update --doc <obj_token> --mode overwrite --new-title "新标题" --markdown @article.md`
- 父节点：`fetch` 当前 markdown → Python 字符串替换 → `--mode overwrite` 整段重写

**绝对不要做**：
- 用 `--mode replace_range --selection-with-ellipsis` 单独打 H3 块（会变成 `### ###` 残留 + 留下孤悬空 H3）
- 用 `--mode replace_range` 单独改 mention-doc 块（会出现重复 mention-doc + token 类型乱跳）

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
《王朔：八十年代最亮的灯塔》
🔗 子文档：https://jmhm92ilup.feishu.cn/wiki/<NEW_NODE>
📚 总目录：https://jmhm92ilup.feishu.cn/wiki/BFKhw668hiWF0dkIU0QcNLm2nJW
```

打开「高晓松热门口播」wiki 树，会看到 **🔥 高晓松热门口播 → 王朔：八十年代最亮的灯塔** 这条新增子节点。

父节点正文末尾会多一条索引（用户钦定格式）：
```
### 2.李宗盛：一句词打磨到凌晨

各位朋友大家好咱们今天聊一个我特别敬重的音乐人李宗盛大哥，
他对于歌词那种近乎偏执的打磨在录音室里能从晚上一直熬到凌晨
......

📄 李宗盛：一句词打磨到凌晨    （飞书会渲染成子文档卡片）
```

打开子文档：
- 标题：王朔：八十年代最亮的灯塔
- 正文：一整段约 1500-3000 字纯口播文字（无任何排版字符）
- 文末：一张视频播放量截图（居中）
