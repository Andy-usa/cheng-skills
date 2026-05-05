---
name: english-to-video
description: |
  把一段英语短文（图片或纯文字均可）转成带 Aria 女声旁白、慢速清晰朗读、烧录字幕的小学生英语学习视频。
  适合小学/初一英语短文，使用蛋仔派对（Eggy Party）Q 萌画风。
  触发词：英语视频、英文视频、生成英语视频、英语短文视频、英文教学视频、把这篇英语做成视频。
  即使用户只是说"做成视频"并附上一段英文（图片 or 文字）也应触发。
permissions:
  exec: [python3, ffmpeg, ffprobe, dreamina]
  file_read: [~/Desktop/, ~/, /tmp/]
  file_write: [~/english_lessons/]
---

# English → Video Skill (v4)

把任意英语短文转成 Q 萌动画视频：**Aria 女声慢读 + 烧录字幕 + 蛋仔派对 Q 萌人物 + 静态切镜**。

## 核心理念

- **旁白驱动分镜**：先把整段旁白拆成 ~2 秒一段的"口播条"，每条口播条对应**一张分镜图**——分镜数量、节奏、字幕都由音频决定，反过来不行
- **分镜图既要好玩又要解释内容**：同时承担两个任务——(1) 蛋仔派对的趣味画风（圆滚滚 / 大眼睛 / 糖果色 / 道具夸张），让小朋友想看；(2) 直白地把这一段旁白说的事情画出来（人物、动作、表情、关键道具），让他能"看懂"英语
- **N 个候选并发生图**：每个分镜并发生 N 张候选（默认 3 张），任意一张成功即可——单点失败不再卡住整体
- **静态切镜，无 Ken Burns**：缩放/平移会裁掉底部字幕，已禁用
- **Aria 慢速旁白**：edge-tts `en-US-AriaNeural` rate `-30%` 优先（教学场景咬字更清晰）；不可用时自动 fallback 到百炼 Cherry + ffmpeg `atempo=0.77`
- **审稿步骤**：旁白拆分 + scenes.json 出来后先和用户对一遍再开跑

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

### Step 2：识别人物 + 场景

读完原文，列出：
- **角色**：姓名、外貌（年龄/发色/眼睛/身材/服装）。原文里没明说的（比如"a teacher"），自己补合理设定
- **场景地点**：教室、运动场、家、公园 等

### Step 3：⚠️ 旁白文稿拆分（关键，第一类工作流步骤）

**这一步在写 scenes.json 之前必做**——决定整个视频的节奏。

**做法**：把整段英文按"自然朗读节奏"切成 ~2 秒一段的"口播条"。每段长度上限大约 12 个英文单词；优先在标点（逗号、句号、引号、连接词 and/but/so 之前）处下刀。每段的文字 = 那张分镜图要烧的字幕 = 那段旁白朗读的内容（一一对应）。

**输出**：一张拆分表，列给用户审。例如这段：

> "But when Mr Brown sees her, he is very surprised and says to her, 'You had my class just now. Why do you come to my class again?'"

应该拆成：

| # | 旁白片段 | 估算时长 | 这张图要画什么 |
|---|---|---|---|
| 1 | But when Mr Brown sees her, | ~1.8s | Mr Brown 视线刚扫到 Mandy，目光停留 |
| 2 | he is very surprised | ~1.5s | Mr Brown 张嘴瞪眼夸张惊讶表情特写 |
| 3 | and says to her, | ~1.3s | Mr Brown 指着 Mandy 准备说话 |
| 4 | "You had my class just now." | ~2.4s | 对话气泡 + Mr Brown 困惑指 Mandy |
| 5 | "Why do you come to my class again?" | ~2.8s | Mandy 一脸懵 + Mr Brown 摊手 |

**用户拍板这张表后，再进 Step 4**。

> 时长估算可以粗算（每英文音节 ~0.18s @ 慢速朗读），不需要精确——下游 ffmpeg 会按实际 TTS 时长对齐画面。

### Step 4：每个口播条配画面 prompt

针对 Step 3 拆出的每一条，写 `prompt`：

- **要包含两层信息**：
  1. **蛋仔派对趣味画风**：圆滚滚 chibi、大眼睛、糖果色、夸张道具/表情、kawaii 氛围
  2. **直白解释这条旁白**：这段说"surprised"就一定要画到那个表情；说"red apple"就一定要有红苹果道具
- 镜头要求（close-up / medium / wide / low angle / over-shoulder）
- 角色动作 + 表情 + 关键道具
- 必要的环境细节（cherry blossoms / morning sunlight）
- 标注用哪个角色 ref / 场景 ref（image2image 的一致性根据）
- 显式写"leave bottom 25% of frame empty for subtitle"——主体往上移、底部留白给字幕

### Step 4.5：写 scenes.json

**人物 prompt 要求：**

- 蛋仔派对画风必须显式写在 `ref_prompt` 里
- 描述要具体：年龄、发型/发色、眼睛颜色、服装、表情
- 多个场景出现的同一人，描述要保持一致

**JSON 模板：**

```json
{
  "characters": [
    {
      "name": "Mandy",
      "description": "12-year-old girl, long golden blonde hair in twin braids, big sky-blue shiny eyes, rosy round cheeks, sweet warm smile, navy-and-white sailor school uniform with red bow tie",
      "ref_prompt": "Character turnaround sheet of a 12-year-old girl, Eggy Party style chibi cartoon, round egg-shaped body, oversized cute big sky-blue shiny eyes, large head, long golden blonde hair in twin braids, rosy round cheeks, navy-and-white sailor school uniform with red bow tie, sweet warm smile, full body front / 3-4 / side views, plain white background, soft pastel candy colors"
    }
  ],
  "locations": [
    {
      "name": "school sports field",
      "description": "Sunny school sports field with red running track and lush green grass",
      "ref_prompt": "Establishing wide shot of a sunny school sports field, Eggy Party style cartoon background, lush vibrant green grass, red running track curving around, white goal posts in distance, modern school building with red roof, bright blue sky with fluffy clouds, no characters, soft pastel candy colors, kid-friendly kawaii aesthetic"
    }
  ],
  "scenes": [
    {
      "text": "Mandy and Sandy are twin sisters.",
      "prompt": "Wide shot, two identical 12-year-old twin girls Mandy and Sandy standing side by side smiling warmly at camera, both with long golden blonde hair in twin braids, sky-blue shiny eyes, rosy cheeks, matching navy-white sailor uniforms with red bow ties, arms gently around each other, sunny school courtyard with cherry blossoms, vibrant warm colors",
      "char_ref": "Mandy",
      "loc_ref": null
    }
  ]
}
```

### Step 5：⚠️ 提示词审稿（必做）

把 scenes.json 写好后，**在跑 Phase 1 之前**，把以下两件事都列给用户过一遍：

**(a) 旁白拆分表**（来自 Step 3）：
- 每段是不是 ≤ 12 词？
- 切点是不是落在标点 / 连接词处？
- 哪段太长读着吃力？哪段太短显得碎？

**(b) 每张分镜的 prompt**：

- 是否包含蛋仔派对画风（chibi / 圆滚滚 / 糖果色 / 大眼睛）？
- 是否直白画出了对应旁白的内容（关键词都映射到画面元素了吗）？
- 是否写了 "leave bottom 25% of frame empty for subtitle"？
- 角色描述是否在每个场景重复了完整外貌？
- 是否有空镜（只有背景没角色没动作）？

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

所有句子并发合成。**主**：edge-tts Aria `-30%`（教学场景咬字优于 Jenny）；**备**：百炼 Cherry + ffmpeg `atempo=0.77`（自动切换，无需干预）。可通过环境变量 `EDGE_TTS_VOICE` / `EDGE_TTS_RATE` 临时切换音色和语速。

### Step 9：⚠️ QC 分镜图（关键）

用 Read 工具逐张审 `images/s01.jpg` ... `sNN.jpg`：

| 检查项 | 不合格处理 |
|---|---|
| 画面对应 text 内容 | 选另一张候选 `sNN_cK.jpg` 覆盖，或重写 prompt 重生 |
| 有角色 + 动作 + 表情 | 重生 |
| 角色外貌一致 | 重生时强化外貌描述 |
| 主体在画面**上 75%**，底部留白 | 重生（默认 STYLE_SUFFIX 已声明此约束） |
| 蛋仔派对 Q 萌画风 | 检查 prompt 是否漏了 style |

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
| 主 | edge-tts | en-US-AriaNeural | `rate=-30%` | 默认（教学场景咬字优）|
| 备 | 百炼 qwen3-tts-flash | Cherry | ffmpeg `atempo=0.77` | edge-tts 失败时自动切换 |

**音色选择思路**：Aria 的 Microsoft 官方定位是 "informational/cheerful"（教学/资讯播报），慢速 `-30%` 时辅音咬字比 Jenny 更清楚，鼻音更少，更适合小学英语听辨。如想换回 Jenny：`EDGE_TTS_VOICE=en-US-JennyNeural EDGE_TTS_RATE=-25% python make_video.py ...`。

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
