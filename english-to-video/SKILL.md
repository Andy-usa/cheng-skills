---
name: english-to-video
description: |
  把一段英语短文（图片或纯文字均可）转成带 Jenny 女声旁白、慢速清晰朗读、烧录字幕的小学生英语学习视频。
  适合小学/初一英语短文，使用蛋仔派对（Eggy Party）Q 萌画风。
  触发词：英语视频、英文视频、生成英语视频、英语短文视频、英文教学视频、把这篇英语做成视频。
  即使用户只是说"做成视频"并附上一段英文（图片 or 文字）也应触发。
permissions:
  exec: [python3, ffmpeg, ffprobe, dreamina]
  file_read: [~/Desktop/, ~/, /tmp/]
  file_write: [~/english_lessons/]
---

# English → Video Skill (v4)

把任意英语短文转成 Q 萌动画视频：**Jenny 女声慢读 + 烧录字幕 + 蛋仔派对 Q 萌人物 + 静态切镜**。

## 核心理念

- **每 ~2 秒切一镜**：视频不能呆板，长句子要切成多个分镜（不再"一句一镜"）
- **N 个候选并发生图**：每个分镜并发生 N 张候选（默认 3 张），任意一张成功即可——单点失败不再卡住整体
- **静态切镜，无 Ken Burns**：缩放/平移会裁掉底部字幕，已禁用
- **Jenny 慢速旁白**：edge-tts `en-US-JennyNeural` 优先；不可用时自动 fallback 到百炼 Cherry + ffmpeg 减速
- **蛋仔派对画风**：圆润、糖果色、大眼睛 Q 萌，对小朋友吸引力大
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

### Step 2：识别人物 + 场景

读完原文，列出：
- **角色**：姓名、外貌（年龄/发色/眼睛/身材/服装）。原文里没明说的（比如"a teacher"），自己补合理设定
- **场景地点**：教室、运动场、家、公园 等

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
