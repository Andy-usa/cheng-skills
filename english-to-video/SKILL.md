---
name: english-to-video
description: |
  把一段英语短文（图片或纯文字均可）转成带 Jenny 女声旁白、慢速清晰朗读、烧录字幕的小学生英语学习视频。
  适合小学/初一英语短文，使用冰雪奇缘（Frozen）迪士尼 3D 电影画风，把课文角色映射到艾莎 / 安娜 / 克里斯托夫等原版人物身上。
  触发词：英语视频、英文视频、生成英语视频、英语短文视频、英文教学视频、把这篇英语做成视频。
  即使用户只是说"做成视频"并附上一段英文（图片 or 文字）也应触发。
permissions:
  exec: [python3, ffmpeg, ffprobe, dreamina]
  file_read: [~/Desktop/, ~/, /tmp/]
  file_write: [~/english_lessons/]
---

# English → Video Skill (v5)

把任意英语短文转成迪士尼电影感动画视频：**Jenny 女声慢读 + 烧录字幕 + 冰雪奇缘原版角色 + 静态切镜**。

## 核心理念

- **每 ~2 秒切一镜**：视频不能呆板，长句子要切成多个分镜（不再"一句一镜"）
- **N 个候选并发生图**：每个分镜并发生 N 张候选（默认 3 张），任意一张成功即可——单点失败不再卡住整体
- **静态切镜，无 Ken Burns**：缩放/平移会裁掉底部字幕，已禁用
- **Jenny 慢速旁白**：edge-tts `en-US-JennyNeural` 优先；不可用时自动 fallback 到百炼 Cherry + ffmpeg 减速
- **冰雪奇缘画风**：迪士尼 3D 卡通、电影级光影、唯美童话，课文里的人物映射到艾莎 / 安娜 / 克里斯托夫等原版角色，借力 Disney 模型一致性
- **审稿步骤**：scenes.json 出来后先和用户对一遍 prompt 再开跑

## 核心脚本

```
~/cheng-skills/english-to-video/scripts/make_video.py
```

四阶段，可独立执行（QC 友好）：

```bash
python3 .../make_video.py <out_dir> --json scenes.json --phase refs     # 角色 + 场景参考图
python3 .../make_video.py <out_dir> --json scenes.json --phase tts      # 全部 TTS（并发）
python3 .../make_video.py <out_dir> --json scenes.json --phase images   # 全部分镜图（并发 + 候选）
python3 .../make_video.py <out_dir> --json scenes.json --phase video    # 字幕烧录 + 拼接
python3 .../make_video.py <out_dir> --json scenes.json --phase all      # 一把梭
```

可选参数：
- `--concurrency N`：并发上限（默认 6，过高会被 dreamina 限流）
- `--candidates N`：每张分镜的候选数（默认 3）

---

## 工作流

### Step 1：拿到英文原文

支持两种来源：
- **图片**：用户发英语课本/作业图片，从图像 OCR 出完整正文，跳过中文注释、二维码、页码
- **纯文字**：用户直接贴英文段落

提取后**和用户确认一遍**，文字模糊或不全时先问清楚再继续。

### Step 2：识别人物 + 场景 + 冰雪奇缘映射

读完原文，列出：
- **角色**：姓名、外貌（年龄/发色/眼睛/身材/服装），并把每个角色**映射到冰雪奇缘原版人物**（艾莎 Elsa、安娜 Anna、克里斯托夫 Kristoff、奥拉夫 Olaf、雪宝 Sven 等）。原文里没明说的（比如"a teacher"），用 Frozen 里的角色改写适配
- **场景地点**：教室、运动场、家、公园 等。背景统一往冰雪城堡 / 冬日校园 / 冰雪森林 这种 Frozen 世界靠

> 例：双胞胎姐妹 Mandy & Sandy → 艾莎 + 安娜（金发同身高）；体育老师 Mr Brown → 克里斯托夫换装体育老师造型（棕短发 + 休闲运动穿搭）

### Step 3：精细化分镜规划（关键）

**目标：每个分镜对应约 2 秒音频**，不再"一句一镜"。把长句子按短语切：

> "But when Mr Brown sees her, he is very surprised and says to her, 'You had my class just now. Why do you come to my class again?'"

切成 5 个分镜：

1. "But when Mr Brown sees her,"
2. "he is very surprised"
3. "and says to her,"
4. "'You had my class just now.'"
5. "'Why do you come to my class again?'"

每个分镜：
- 是一个**独立的视觉时刻**，prompt 描述该时刻该看到什么
- text 是要朗读 + 烧字幕的那段（短，≤ 12 词最好）
- 标注用哪个角色 ref / 场景 ref（i2i 一致性的根据）
- 镜头要求（close-up / medium / wide / low angle / over-shoulder）
- 表情/动作（surprised, smiling, pointing）
- 必要的环境细节（cherry blossoms, sunlight from left, etc.）

### Step 4：写 scenes.json

**统一固定后缀（每条 prompt 末尾会自动追加 `STYLE_SUFFIX`，等价于以下中文表述）：**

> 冰雪奇缘电影画风，迪士尼 3D 卡通，电影级光影，16:9，高细节，超清渲染，柔和冰雪质感，唯美童话场景，角色高度还原冰雪奇缘原版人物，画面生动童趣，儿童动画质感，电影抽帧镜头感

所以你写每条 `prompt` 时**不要**重复这串后缀——`make_video.py` 已经在最后拼好。只写**这一镜独有**的内容（人物、动作、表情、镜头、环境）。

**人物 prompt 要求：**

- 角色 `ref_prompt` 显式声明所映射的冰雪奇缘原版人物（艾莎 / 安娜 / 克里斯托夫 / ……）
- 描述要具体：年龄、发型/发色、眼睛颜色、服装、表情
- 多个场景出现的同一人，描述要保持一致（同一套服饰、同一发型）

**JSON 模板：**

```json
{
  "characters": [
    {
      "name": "Mandy",
      "frozen_ref": "Elsa",
      "description": "12-year-old girl mapped to Disney's Elsa from Frozen, faithfully matching the original Elsa Disney 3D model, long platinum-blonde French braid over the shoulder, large sky-blue eyes, gentle warm smile, light icy-blue princess dress",
      "ref_prompt": "Character turnaround sheet of Disney Frozen's Elsa, Frozen movie style, Disney 3D cartoon, faithful to the original Elsa model, long platinum-blonde French braid, sky-blue eyes, light icy-blue princess dress, gentle warm smile, full body front / 3-4 / side views, plain soft white background, cinematic lighting"
    },
    {
      "name": "Sandy",
      "frozen_ref": "Anna",
      "description": "12-year-old girl mapped to Disney's Anna from Frozen, twin-pigtails strawberry-blonde hair (re-colored to match Elsa's blonde for the twin look), bright teal-green eyes, freckles, light pastel princess dress matching Elsa's, same height as Elsa",
      "ref_prompt": "Character turnaround sheet of Disney Frozen's Anna, Frozen movie style, Disney 3D cartoon, faithful to the original Anna model, twin pigtails of platinum-blonde hair to match Elsa, large bright eyes, freckles, light pastel princess dress identical to Elsa's, same height as Elsa, full body front / 3-4 / side views, plain soft white background, cinematic lighting"
    },
    {
      "name": "Mr Brown",
      "frozen_ref": "Kristoff",
      "description": "Disney's Kristoff from Frozen, restyled as a school PE teacher, short brown hair, casual sporty outfit (track jacket + whistle), kind but firm expression",
      "ref_prompt": "Character turnaround sheet of Disney Frozen's Kristoff restyled as a PE teacher, Frozen movie style, Disney 3D cartoon, faithful to the original Kristoff model, short brown hair, casual sporty track jacket with whistle around neck, kind but firm expression, full body front / 3-4 / side views, plain soft white background, cinematic lighting"
    }
  ],
  "locations": [
    {
      "name": "frozen school sports field",
      "description": "Winter outdoor sports field of a fairytale ice-castle school: green lawn dusted with snow, soft sunlight through cool air",
      "ref_prompt": "Establishing wide shot of a fairytale winter school sports field, Frozen movie style background, green lawn lightly dusted with snow, ice-castle school building in the distance with frosted spires, pale blue sky, no characters, cinematic lighting"
    }
  ],
  "scenes": [
    {
      "text": "Mandy and Sandy are twin sisters.",
      "prompt": "Wide shot, courtyard of an ice castle, Elsa and Anna standing shoulder to shoulder, both blonde, identical height, matching light pastel princess dresses, warm gaze at each other, fresh winter setting, soft natural light",
      "char_ref": "Mandy",
      "loc_ref": null
    }
  ]
}
```

### Step 5：⚠️ 提示词审稿（必做）

把 scenes.json 写好后，**在跑 Phase 1 之前**，把所有 `ref_prompt` 和 `prompt` 列给用户过一遍：

- 是否每个 prompt 包含蛋仔派对画风？
- 角色描述是否在每个场景重复了完整外貌？
- 每个分镜是否有明确动作 / 表情 / 镜头？
- 是否有空镜（只有背景没角色）？

用户拍板后再开跑。

### Step 6：Phase 1 — 参考图

```bash
python3 .../make_video.py <dir> --json scenes.json --phase refs
```

每个角色和场景并发生成 N 个候选，自动选第一个成功的为最终 ref。**审一遍 ref 图**——不合格的删掉对应文件重跑。

### Step 7：Phase 2 — 分镜图（并发 + 候选）

```bash
python3 .../make_video.py <dir> --json scenes.json --phase images
```

12 个分镜 × 3 候选 = 36 个并发任务（受 `--concurrency` 限流到 6 个同时跑）。任意候选成功即赢家，候选文件保留在 `images/sNN_cK.jpg` 供 QC 替换。

### Step 8：Phase 3 — TTS（并发）

```bash
python3 .../make_video.py <dir> --json scenes.json --phase tts
```

所有句子并发合成。**主**：edge-tts Jenny `-25%`；**备**：百炼 Cherry + ffmpeg `atempo=0.8`（自动切换，无需干预）。

### Step 9：⚠️ QC 分镜图（关键）

用 Read 工具逐张审 `images/s01.jpg` ... `sNN.jpg`：

| 检查项 | 不合格处理 |
|---|---|
| 画面对应 text 内容 | 选另一张候选 `sNN_cK.jpg` 覆盖，或重写 prompt 重生 |
| 有角色 + 动作 + 表情 | 重生 |
| 角色外貌一致 | 重生时强化外貌描述 |
| 主体在画面**上 75%**，底部留白 | 重生（默认 STYLE_SUFFIX 已声明此约束） |
| 冰雪奇缘电影画风 | 检查 prompt 是否漏了 style，或映射到的 Frozen 角色不对 |
| 角色还原冰雪奇缘原版人物 | 重生时强化 "faithful to original Disney model" |

替换某张图：`cp images/s05_c2.jpg images/s05.jpg` 即可（Phase 4 用 `s05.jpg`）。

### Step 10：Phase 4 — 视频合成

```bash
python3 .../make_video.py <dir> --json scenes.json --phase video
```

每个分镜：静态图 + 字幕烧录（底部 60% 透明黑背景白字）+ 对齐音频长度。然后 ffmpeg concat 用绝对路径拼接。输出 `final/english_lesson.mp4`。

---

## 字幕规则

- 字体：Liberation Sans Bold 48pt（Linux）/ Helvetica（macOS），自动选择
- 位置：底部 ~50px 处，居中
- 背景：半透明黑（α=175）
- 描边：黑色 2px 描边 + 白色字
- 自动按 48 字宽度折行

主体构图必须把字幕区让出来：`STYLE_SUFFIX` 里强制要求 "leave bottom 25% of frame empty for subtitle"。

---

## TTS 行为说明

| 主备 | 引擎 | 声音 | 速度控制 | 何时使用 |
|---|---|---|---|---|
| 主 | edge-tts | en-US-JennyNeural | `rate=-25%` | 默认 |
| 备 | 百炼 qwen3-tts-flash | Cherry | ffmpeg `atempo=0.8` | edge-tts 失败时自动切换 |

edge-tts 失败常见原因：

- 沙箱 TLS 拦截（已用 `_patch_edge_tts_ssl()` 修）
- 微软对云 IP 段直接 403（不可修，只能 fallback）

百炼 Cherry 在 `~/.claude/.dreamina-backup/` 的 token 持久化由用户级 SessionStart hook 自动还原，**不需要每次重新登录**。

---

## 错误处理

| 情况 | 处理 |
|---|---|
| 某个分镜 N 个候选全失败 | 看错误信息：upload 失败 → DNS 抖动，重跑；content 拒绝 → 改写 prompt |
| TTS 整体失败（edge-tts + Bailian 都挂） | 检查 `DASHSCOPE_API_KEY`；检查百炼可达性 |
| 视频后半段画面缺失 | `--phase video` 跳过 missing 图，只用已有的；先补图再重跑 |
| 字幕被画面盖住 | prompt 漏了 "leave bottom 25% empty"，重生该分镜 |
| `dreamina: command not found` | `~/.claude/dreamina-restore.sh` 是否跑过；二进制在 `~/.claude/bin/dreamina` |

---

## 依赖速查

| 工具 | 安装 | 用途 |
|---|---|---|
| ffmpeg | `apt-get install -y ffmpeg` | 字幕烧录 + 减速 + 拼接 |
| Pillow | `pip3 install pillow` | 字幕 PIL 绘图 |
| edge-tts | `pip3 install edge-tts` | 主 TTS |
| dreamina (即梦) | `~/.claude/bin/dreamina` | 文生图 / 图生图 |
| `DASHSCOPE_API_KEY` | env var | 百炼备用 TTS 鉴权 |

---

## 输出结构

```
~/english_lessons/<lesson_name>/
├── scenes.json                  # 分镜规划
├── references/
│   ├── char_<name>.jpg          # 角色参考图（赢家）
│   ├── char_<name>_c{0,1,2}.jpg # 候选
│   └── loc_<name>*.jpg
├── images/
│   ├── s01.jpg ... sNN.jpg      # 分镜图（赢家）
│   └── s01_c{0,1,2}.jpg ...     # 候选（QC 时可替换）
├── images_sub/
│   └── s01.jpg ... sNN.jpg      # 烧字幕版
├── audio/
│   └── s01.mp3 ... sNN.mp3
├── clips/
│   └── clip_01.mp4 ... clip_NN.mp4
└── final/
    └── english_lesson.mp4       # 最终交付
```

## 交付

写完后用 lark-cli 把 mp4 推到飞书私信：

```bash
cd ~/english_lessons/<lesson_name>/final/
ffmpeg -y -ss 1 -i english_lesson.mp4 -frames:v 1 cover.jpg
USER_OPEN_ID=$(lark-cli auth list | python3 -c 'import json,sys; print(json.load(sys.stdin)[0]["userOpenId"])')
lark-cli im +messages-send --as bot --user-id "$USER_OPEN_ID" \
  --video english_lesson.mp4 --video-cover cover.jpg
```

(lark-cli 要在 `final/` 目录下跑，`--video` / `--video-cover` 必须传**相对路径**)

---

## 附录：20 分镜冰雪奇缘批量生图模板

下面是为「Mandy & Sandy 双胞胎 + Mr Brown 体育老师」这类 4-5 年级英语短文设计的 20 镜参考模板。**直接落到 dreamina CLI 的 `--prompt`，不需要再叠 `STYLE_SUFFIX`**——这些 prompt 已经写明了 16:9、电影抽帧等通用要求。换其他短文时，先把课文角色映射到艾莎/安娜/克里斯托夫等 Frozen 原版人物，再按下面的镜头序列改写动作即可。

### 全程统一固定参数

> 冰雪奇缘电影画风，迪士尼 3D 卡通，电影级光影，16:9，高细节，超清渲染，柔和冰雪质感，唯美童话场景，角色高度还原冰雪奇缘原版人物，画面生动童趣，儿童动画质感，电影抽帧镜头感

### 20 镜序列

| # | 课文内容 | 镜头 prompt（中文，写入 `prompt` 字段） |
|---|---|---|
| 1 | 双胞胎介绍 | 冰雪奇缘画风，全景镜头，城堡庭院场景，艾莎与安娜并肩站立，两位金发公主，身形身高一致，同款浅色长裙，温柔对视，冬日清新环境，柔和自然光，迪士尼电影质感，16:9，电影抽帧画面 |
| 2 | 长金发 | 冰雪奇缘画风，中景特写，艾莎长发金发细节刻画，柔顺金色长发，精致五官，冰雪城堡背景，柔和漫反射光线，童话风配色，高清细节，16:9 |
| 3 | 同身高 | 冰雪奇缘画风，全身镜头，安娜笔直站立，标准身高比例，优雅体态，城堡露台场景，淡蓝色冰雪色调，唯美氛围感，迪士尼3D建模质感，16:9 |
| 4 | 同款连衣裙 | 冰雪奇缘画风，双人中景，艾莎和安娜身穿一模一样的公主连衣裙，款式配色完全相同，并肩行走在城堡走廊，暖柔室内光影，童趣可爱，16:9 |
| 5 | 长得很像 | 冰雪奇缘画风，双人正面镜头，艾莎安娜五官长相相似，容貌酷似，并肩微笑对视，冰雪森林远景背景，电影级构图，16:9 |
| 6 | 同一所中学 | 冰雪奇缘画风，远景镜头，宏伟冰雪城堡学校建筑群，艾莎安娜一同走入校园，童话风校园场景，白雪点缀环境，16:9 |
| 7 | 不同班级 | 冰雪奇缘画风，分隔画面，左右对比，艾莎安娜走进不同教室门牌，虽同校不同班级，柔和冷色调，校园走廊场景，细腻画面细节，16:9 |
| 8 | 同一位体育老师 | 冰雪奇缘画风，中景人物，冰雪奇缘原版克里斯托夫换装体育老师造型，棕色短发，休闲运动穿搭，温和严肃神态，操场背景，16:9 |
| 9 | 第一节体育课 | 冰雪奇缘画风，操场全景镜头，冬日户外运动场，绿植与白雪结合，体育课堂场景搭建，空旷唯美环境，电影镜头感，16:9 |
| 10 | 艾莎和同学一起去 | 冰雪奇缘画风，群像中景，艾莎跟随一群小伙伴走在操场，结伴前往体育课，孩童活泼动态，轻松欢乐氛围，16:9 |
| 11 | 课开始 | 冰雪奇缘画风，近景镜头，操场场地画面，体育课正式开始，阳光洒落地面，简洁干净户外场景，柔和光影层次，16:9 |
| 12 | 老师看见她很惊讶 | 冰雪奇缘画风，特写镜头，体育老师克里斯托夫皱眉惊讶表情，目光看向前方的艾莎，神态疑惑，表情生动夸张，16:9 |
| 13 | 老师对她说 | 冰雪奇缘画风，双人对话镜头，体育老师面对艾莎，抬手疑惑询问，肢体动作自然，操场背景虚化，聚焦人物互动，16:9 |
| 14 | "你刚才上过我的课了" | 冰雪奇缘画风，人物近景，体育老师开口说话神态，神情不解，户外自然光打亮人物，迪士尼细腻表情刻画，16:9 |
| 15 | 艾莎也很惊讶 | 冰雪奇缘画风，艾莎正面特写，满脸意外惊讶的神情，双眼睁大，呆萌可爱表情，浅淡冰雪背景，16:9 |
| 16 | 但她很快理解了 | 冰雪奇缘画风，艾莎半身镜头，瞬间恍然大悟的神态，眼神灵动，情绪转变自然，童话风色彩搭配，16:9 |
| 17 | 她微笑着说 | 冰雪奇缘画风，艾莎微笑侧身，温柔礼貌的笑容，气质优雅，冬日操场环境，柔和氛围感，电影抽帧质感，16:9 |
| 18 | "您可能弄错了" | 冰雪奇缘画风，互动中景，艾莎对着体育老师从容解释，肢体放松，沟通姿态自然，清新治愈画面，16:9 |
| 19 | "我有一个双胞胎姐姐" | 冰雪奇缘画风，回忆感远景，画面角落虚化浮现安娜身影，暗示双胞胎姐妹设定，朦胧唯美特效，16:9 |
| 20 | 收尾 | 冰雪奇缘画风，双人收尾镜头，体育老师恍然大悟微笑，艾莎从容站立，冬日操场全景收尾，画面完整和谐，童趣治愈，16:9 |

### 适配说明

1. 全程绑定冰雪奇缘原版人物建模，艾莎/安娜替代原文双胞胎姐妹，体育老师用克里斯托夫改写适配，人物还原度拉满。
2. 全部 16:9 画幅、电影抽帧质感，完美适配旁白动画剪辑。
3. 语气、画面节奏贴合 4 年级英文旁白，画风低龄友好、生动童趣，适合课本动画使用。
