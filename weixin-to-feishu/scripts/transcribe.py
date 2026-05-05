#!/usr/bin/env python3
"""
微信视频号 / 任意音视频 URL → 飞书可读纯文本转写。

ASR provider:
  默认: 火山引擎「录音文件识别大模型 标准版」
  fallback: 阿里云百炼 qwen3-asr-flash（火山失败时自动启用）

通过环境变量 ASR_PROVIDER=volc|dashscope|auto（默认 auto）切换。

火山 BigASR 标准版优势：
  - 单次支持长音频（≤5h, ≤1GB），无需切片
  - 异步任务模式，submit 秒返
  - 中文识别准确率 + 标点 + ITN 比 qwen3-asr-flash 好

策略：
  1. ffmpeg 流式抽 16kHz/32kbps mp3（不下载视频，只读音频流）
  2. base64 内联调火山 submit + poll
  3. 失败自动 fallback 到百炼（保留切片逻辑）

依赖：ffmpeg；环境变量按 provider 配置。
"""

import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid


class ASRError(RuntimeError):
    pass


class ASRProvider:
    name = "abstract"

    def transcribe(self, mp3_path: str, duration: float) -> str:
        raise NotImplementedError


# ===========================================
# 火山引擎：录音文件识别大模型 标准版
#   doc: https://www.volcengine.com/docs/6561/1354868
# ===========================================

class VolcanoASR(ASRProvider):
    name = "volc"
    SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
    QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"
    RESOURCE_ID = "volc.bigasr.auc"
    POLL_INTERVAL = 2.0
    POLL_TIMEOUT = 600.0

    def __init__(self):
        self.app_key = (
            os.environ.get("VOLC_ASR_APP_KEY")
            or os.environ.get("VOLC_APP_ID")
            or os.environ.get("VOLC_APP_KEY")
        )
        self.access_key = (
            os.environ.get("VOLC_ASR_ACCESS_KEY")
            or os.environ.get("VOLC_ACCESS_TOKEN")
            or os.environ.get("VOLC_ACCESS_KEY")
        )
        if not self.app_key or not self.access_key:
            raise ASRError(
                "Volc ASR credentials missing. "
                "set VOLC_ASR_APP_KEY + VOLC_ASR_ACCESS_KEY"
            )

    def _headers(self, request_id: str, *, with_sequence: bool = False) -> dict:
        h = {
            "X-Api-App-Key": self.app_key,
            "X-Api-Access-Key": self.access_key,
            "X-Api-Resource-Id": self.RESOURCE_ID,
            "X-Api-Request-Id": request_id,
            "Content-Type": "application/json",
        }
        if with_sequence:
            h["X-Api-Sequence"] = "-1"
        return h

    def _post(self, url: str, headers: dict, body: dict):
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                resp_headers = {k.lower(): v for k, v in r.getheaders()}
                raw = r.read().decode("utf-8")
                resp_body = json.loads(raw) if raw else {}
                return resp_headers, resp_body
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", errors="replace")
            raise ASRError(f"Volc HTTP {e.code} {url}: {text}") from None

    def transcribe(self, mp3_path: str, duration: float) -> str:
        with open(mp3_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode("ascii")
        request_id = str(uuid.uuid4())

        # ---- submit ----
        submit_body = {
            "user": {"uid": "weixin-to-feishu"},
            "audio": {
                "data": audio_b64,
                "format": "mp3",
                "codec": "raw",
            },
            "request": {
                "model_name": "bigmodel",
                "model_version": "400",
                "enable_itn": True,
                "enable_punc": True,
                "enable_ddc": True,
                "show_utterances": False,
            },
        }
        resp_h, resp_b = self._post(
            self.SUBMIT_URL,
            self._headers(request_id, with_sequence=True),
            submit_body,
        )
        status = resp_h.get("x-api-status-code")
        log_id = resp_h.get("x-tt-logid")
        if status != "20000000":
            raise ASRError(
                f"Volc submit rejected: status={status} headers={resp_h} body={resp_b}"
            )
        if not log_id:
            raise ASRError(f"Volc submit missing X-Tt-Logid: {resp_h}")

        # ---- poll ----
        # status codes:
        #   20000000 完成；20000001 排队中；20000002 处理中；20000003 完成但无人声内容
        query_h = self._headers(request_id, with_sequence=False)
        query_h["X-Tt-Logid"] = log_id
        deadline = time.time() + self.POLL_TIMEOUT
        while time.time() < deadline:
            time.sleep(self.POLL_INTERVAL)
            resp_h, resp_b = self._post(self.QUERY_URL, query_h, {})
            status = resp_h.get("x-api-status-code")
            if status in ("20000000", "20000003"):
                return ((resp_b or {}).get("result") or {}).get("text", "")
            if status in ("20000001", "20000002"):
                continue
            raise ASRError(f"Volc query failed: status={status} body={resp_b}")
        raise ASRError(f"Volc poll timeout after {self.POLL_TIMEOUT}s (logid={log_id})")


# ===========================================
# 阿里云百炼：qwen3-asr-flash (fallback)
# ===========================================

class DashscopeASR(ASRProvider):
    name = "dashscope"
    ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    MODEL = "qwen3-asr-flash"
    CHUNK_SECONDS = 165
    SINGLE_SHOT_MAX = 185

    def __init__(self):
        self.api_key = os.environ.get("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise ASRError("DASHSCOPE_API_KEY not set")

    def transcribe(self, mp3_path: str, duration: float) -> str:
        if duration <= self.SINGLE_SHOT_MAX:
            return self._one(mp3_path)
        chunk_dir = tempfile.mkdtemp(prefix="dashscope_chunks_")
        try:
            chunks = self._split(mp3_path, chunk_dir)
            parts = [self._one(c).strip() for c in chunks]
            return "\n".join(p for p in parts if p)
        finally:
            shutil.rmtree(chunk_dir, ignore_errors=True)

    def _split(self, src: str, chunk_dir: str) -> list:
        pattern = os.path.join(chunk_dir, "chunk_%03d.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", src, "-c", "copy", "-f", "segment",
                "-segment_time", str(self.CHUNK_SECONDS), "-reset_timestamps", "1",
                pattern,
            ],
            check=True, capture_output=True, text=True,
        )
        return sorted(
            os.path.join(chunk_dir, f) for f in os.listdir(chunk_dir)
            if f.startswith("chunk_") and f.endswith(".mp3")
        )

    def _one(self, mp3_path: str) -> str:
        with open(mp3_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        payload = {
            "model": self.MODEL,
            "messages": [
                {"role": "system", "content": [{"type": "text", "text": ""}]},
                {"role": "user", "content": [{
                    "type": "input_audio",
                    "input_audio": {"data": f"data:audio/mp3;base64,{b64}", "format": "mp3"},
                }]},
            ],
        }
        req = urllib.request.Request(
            self.ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read().decode("utf-8"))
                return data["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            raise ASRError(
                f"Dashscope HTTP {e.code}: {e.read().decode('utf-8', errors='replace')}"
            ) from None


# ===========================================
# Audio extraction & main
# ===========================================

def extract_audio(url: str, out_path: str) -> float:
    """流式抽 16kHz/mono/32kbps mp3，不下载视频。返回时长（秒）。"""
    subprocess.run(
        [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", url, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
            "-f", "mp3", out_path,
        ],
        check=True, capture_output=True, text=True,
    )
    dur = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "csv=p=0", out_path,
        ],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    return float(dur)


def _build(name: str) -> ASRProvider:
    if name == "volc":
        return VolcanoASR()
    if name == "dashscope":
        return DashscopeASR()
    raise ASRError(f"unknown ASR_PROVIDER: {name}")


def transcribe(url: str) -> dict:
    mode = os.environ.get("ASR_PROVIDER", "auto").lower()
    start = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        audio = os.path.join(tmp, "audio.mp3")
        duration = extract_audio(url, audio)
        last_err = None
        order = ["volc", "dashscope"] if mode == "auto" else [mode]
        for n in order:
            try:
                provider = _build(n)
            except ASRError as e:
                last_err = e
                continue
            try:
                text = provider.transcribe(audio, duration)
                return {
                    "ok": True,
                    "text": text.strip(),
                    "elapsed": round(time.time() - start, 1),
                    "duration": round(duration, 1),
                    "provider": provider.name,
                }
            except ASRError as e:
                last_err = e
                if mode != "auto":
                    raise
                print(f"[warn] {n} failed: {e}; trying next provider", file=sys.stderr)
                continue
        raise ASRError(f"all providers failed; last error: {last_err}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: transcribe.py <video_url>", file=sys.stderr)
        sys.exit(1)
    try:
        print(json.dumps(transcribe(sys.argv[1]), ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)
