#!/usr/bin/env python3
"""
微信视频号 / 任意视频音频 URL → 飞书可读的纯文本转写。

策略（按可靠性优先级）：
1. ffmpeg 流式抽出低码率 mp3（不落大文件），按 165 秒一段切片
2. 每段 base64 内联调用百炼 qwen3-asr-flash（OpenAI 兼容接口）
3. 拼接结果输出 JSON: {"ok": true, "text": "...", "elapsed": 12.3}

为什么不用 paraformer-v2：
- 依赖 dashscope SDK，部分环境装不上（cryptography ABI 冲突）
- paraformer 的下载器对大文件 / 个别 CDN 会超时（视频号 100+MB 文件实测会失败）
- ffmpeg 抽音轨后只发 ~10KB/秒的 mp3，规避了所有下载相关问题

依赖：ffmpeg 已安装；环境变量 DASHSCOPE_API_KEY。
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

CHUNK_SECONDS = 165          # qwen3-asr-flash 单段约 3 分钟上限，留点余量
SINGLE_SHOT_MAX = 185        # 略微宽放：≤ 这个时长就一次性发，不切片
ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
MODEL = "qwen3-asr-flash"


def _run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def extract_audio(url: str, out_path: str) -> float:
    """流式抽音轨为 16kHz/mono/32kbps mp3。返回时长（秒）。"""
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", url, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
        "-f", "mp3", out_path,
    ])
    dur = _run([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "csv=p=0", out_path,
    ]).stdout.strip()
    return float(dur)


def split_audio(src: str, chunk_dir: str, chunk_seconds: int = CHUNK_SECONDS) -> list:
    """按 chunk_seconds 切片，返回片段路径列表。"""
    pattern = os.path.join(chunk_dir, "chunk_%03d.mp3")
    _run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-i", src, "-c", "copy", "-f", "segment",
        "-segment_time", str(chunk_seconds), "-reset_timestamps", "1",
        pattern,
    ])
    return sorted(
        os.path.join(chunk_dir, f) for f in os.listdir(chunk_dir)
        if f.startswith("chunk_") and f.endswith(".mp3")
    )


def transcribe_chunk(api_key: str, mp3_path: str) -> str:
    with open(mp3_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": [{"type": "text", "text": ""}]},
            {"role": "user", "content": [{
                "type": "input_audio",
                "input_audio": {"data": f"data:audio/mp3;base64,{b64}", "format": "mp3"},
            }]},
        ],
    }
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data["choices"][0]["message"]["content"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body}") from None


def transcribe(url: str) -> dict:
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY not set")
    start = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, "audio.mp3")
        duration = extract_audio(url, audio)
        if duration <= SINGLE_SHOT_MAX:
            chunks = [audio]
        else:
            chunk_dir = os.path.join(tmp, "chunks")
            os.makedirs(chunk_dir)
            chunks = split_audio(audio, chunk_dir)
        parts = [transcribe_chunk(api_key, c) for c in chunks]
    text = "\n".join(p.strip() for p in parts if p.strip())
    return {"ok": True, "text": text, "elapsed": round(time.time() - start, 1),
            "duration": round(duration, 1), "chunks": len(chunks)}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: transcribe.py <video_url>", file=sys.stderr)
        sys.exit(1)
    try:
        print(json.dumps(transcribe(sys.argv[1]), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
