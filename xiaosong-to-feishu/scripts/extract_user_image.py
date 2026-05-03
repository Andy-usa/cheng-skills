#!/usr/bin/env python3
"""从当前 Claude session jsonl 里提取 user 上传的截图（base64）落地为本地文件。

Usage:
  python3 extract_user_image.py                  # 提取最新一张到 /tmp/user_image.<ext>
  python3 extract_user_image.py --index -1       # 同上
  python3 extract_user_image.py --index -2       # 倒数第二张
  python3 extract_user_image.py --out /tmp/x.jpg # 自定义输出路径

行为：
  - 自动寻找 ~/.claude/projects/*/*.jsonl 里 mtime 最新的一份 session
  - 收集所有 user message 中 type=image, source.type=base64 的内容
  - 按 base64 长度去重（同一图在多次 turn 重复出现只算一次）
  - 按对话顺序排列；--index 默认 -1（最新）
  - stdout 输出落地的本地文件路径，便于 shell 直接 $() 接管

退出码：
  0   成功，stdout = 文件路径
  2   找不到 session jsonl / 没有图片 / index 越界
"""

from __future__ import annotations

import argparse
import base64
import glob
import json
import os
import sys


def find_session_jsonl() -> str | None:
    candidates = sorted(
        glob.glob(os.path.expanduser("~/.claude/projects/*/*.jsonl")),
        key=lambda p: os.path.getmtime(p),
        reverse=True,
    )
    return candidates[0] if candidates else None


def extract_images(path: str) -> list[tuple[str, str, str]]:
    """Return list of (timestamp, base64_data, media_type)."""
    images: list[tuple[str, str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg = d.get("message") or {}
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = msg.get("content", [])
            if not isinstance(content, list):
                continue
            for c in content:
                if not isinstance(c, dict) or c.get("type") != "image":
                    continue
                src = c.get("source", {})
                if isinstance(src, dict) and src.get("type") == "base64":
                    images.append(
                        (
                            d.get("timestamp", ""),
                            src.get("data", ""),
                            src.get("media_type", "image/jpeg"),
                        )
                    )

    # Dedup by data length (same image often repeats across consecutive turns)
    seen: set[int] = set()
    unique: list[tuple[str, str, str]] = []
    for ts, data, mt in images:
        k = len(data)
        if k in seen:
            continue
        seen.add(k)
        unique.append((ts, data, mt))
    return unique


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=int, default=-1,
                    help="which image (default -1 = latest)")
    ap.add_argument("--out", default=None,
                    help="output file path; default /tmp/user_image.<ext>")
    ap.add_argument("--list", action="store_true",
                    help="只打印图片清单到 stderr，不落地")
    args = ap.parse_args()

    path = find_session_jsonl()
    if not path:
        print("ERROR: no session jsonl found", file=sys.stderr)
        return 2

    images = extract_images(path)
    if not images:
        print(f"ERROR: no images in {path}", file=sys.stderr)
        return 2

    if args.list:
        for i, (ts, data, mt) in enumerate(images):
            print(f"  [{i:+d}/{i - len(images):+d}] ts={ts} bytes={len(data)} type={mt}", file=sys.stderr)
        return 0

    try:
        ts, data, mt = images[args.index]
    except IndexError:
        print(f"ERROR: index {args.index} out of range (have {len(images)} images)", file=sys.stderr)
        return 2

    ext = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
        "image/gif": "gif",
    }.get(mt, "jpg")
    out = args.out or f"/tmp/user_image.{ext}"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "wb") as f:
        f.write(base64.b64decode(data))
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
