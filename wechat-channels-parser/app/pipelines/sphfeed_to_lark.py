"""sphfeed → 视频号反查 → weixin-to-feishu 转录 → 推飞书。

调用链：
    1. sphfeed envelope 拿到 finder_username / nonce_id（或直接 url）
    2. 如果有 mp4 url 直接走 transcribe.py；否则调 channels_parser.parse_channels_video 反查
    3. 拿 weixin-to-feishu/scripts/transcribe.py 跑转写
    4. lark-cli docs +create + +update 写飞书文档
    5. lark-cli im +messages-send 推私信通知

⚠️ 这是 stub。本地接手时按真机 dump 决定走哪条路径（直接 url vs 反查）。
"""

from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

from app.channels_parser import ChannelsParseError, parse_channels_video
from app.config import get_settings
from app.msgaudit.models import MsgAuditEnvelope, SphfeedMessage
from app.utils.logger import logger

# 假设 weixin-to-feishu skill 与本项目并列 clone：~/cheng-skills/weixin-to-feishu/
WEIXIN_TO_FEISHU_TRANSCRIBE = Path("~/cheng-skills/weixin-to-feishu/scripts/transcribe.py").expanduser()


async def handle_sphfeed(envelope: MsgAuditEnvelope, sphfeed: SphfeedMessage) -> None:
    """处理一条视频号分享消息（端到端）。"""
    logger.info(
        "sphfeed_received",
        extra={
            "msgid": envelope.msgid,
            "from": envelope.from_userid,
            "feed_type": sphfeed.feed_type,
            "sph_name": sphfeed.sph_name,
            "feed_desc": sphfeed.feed_desc[:80],
            "finder_username": sphfeed.finder_username,
            "nonce_id": sphfeed.nonce_id,
            "has_url": bool(sphfeed.url),
        },
    )

    # 只处理视频类型；feed_type=2 图文 / 9 直播暂时跳过
    if sphfeed.feed_type != 4:
        logger.info(f"skipping non-video sphfeed (feed_type={sphfeed.feed_type})")
        return

    # 1. 拿到 mp4 url（直接给 / 反查二选一）
    video_url = sphfeed.url
    if not video_url:
        try:
            parsed = await parse_channels_video(
                finder_username=sphfeed.finder_username,
                nonce_id=sphfeed.nonce_id,
            )
            video_url = parsed.video_url
        except (ChannelsParseError, NotImplementedError) as exc:
            logger.error(f"channels_parser failed: {exc}")
            await _notify_lark_text(f"⚠️ 视频号反查失败 msgid={envelope.msgid}: {exc}")
            return

    # 2. 跑转写
    try:
        transcript = await _run_transcribe(video_url)
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"transcribe failed: {exc}")
        await _notify_lark_text(f"⚠️ 转写失败 msgid={envelope.msgid}: {exc}")
        return

    # 3. 写飞书文档
    title = sphfeed.sph_name + (f" — {sphfeed.feed_desc[:30]}" if sphfeed.feed_desc else "")
    doc_url = await _write_lark_doc(title=title, body=_format_doc_body(sphfeed, transcript))

    # 4. 推私信通知
    await _notify_lark_text(
        f"📚 **视频号转录完成**\n\n《{title}》\n\n🔗 {doc_url}\n\n来源：{sphfeed.sph_name}"
    )


# ────────────────────────────────────────────────────────────────────────────
# 辅助函数（stub 级别 — 本地接手时根据 weixin-to-feishu skill 实际接口调）

async def _run_transcribe(video_url: str) -> str:
    """跑 weixin-to-feishu/scripts/transcribe.py，返回转写文本。"""
    proc = await asyncio.create_subprocess_exec(
        "python3", str(WEIXIN_TO_FEISHU_TRANSCRIBE), video_url,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"transcribe.py exit={proc.returncode}: {stderr.decode()[-300:]}")
    data = json.loads(stdout.decode())
    if not data.get("ok"):
        raise RuntimeError(f"transcribe error: {data.get('error')}")
    return str(data.get("text", ""))


def _format_doc_body(sphfeed: SphfeedMessage, transcript: str) -> str:
    return (
        f"> 来源：{sphfeed.sph_name}\n"
        f"> 视频文案：{sphfeed.feed_desc}\n\n"
        f"---\n\n"
        f"{transcript}\n"
    )


async def _write_lark_doc(title: str, body: str) -> str:
    """两步法创建飞书文档，返回 doc_url。"""
    mini_path = Path("/tmp/feishu_mini.md")
    article_path = Path("/tmp/feishu_article.md")
    mini_path.write_text(f"# {title}\n\n正在写入...\n", encoding="utf-8")
    article_path.write_text(body, encoding="utf-8")

    create = await asyncio.create_subprocess_exec(
        "lark-cli", "docs", "+create", "--title", title, "--markdown", "@feishu_mini.md",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        cwd="/tmp",
    )
    create_out, _ = await create.communicate()
    raw = create_out.decode()
    raw = raw[raw.index("{"):raw.rindex("}") + 1]
    doc_id = json.loads(raw)["data"]["doc_id"]

    update = await asyncio.create_subprocess_exec(
        "lark-cli", "docs", "+update", "--doc", doc_id, "--mode", "overwrite",
        "--markdown", "@feishu_article.md",
        cwd="/tmp",
    )
    await update.wait()

    mini_path.unlink(missing_ok=True)
    article_path.unlink(missing_ok=True)
    return f"https://www.feishu.cn/docx/{doc_id}"


async def _notify_lark_text(markdown: str) -> None:
    """推飞书私信给 LARK_USER_OPEN_ID。"""
    s = get_settings()
    proc = await asyncio.create_subprocess_exec(
        "lark-cli", "im", "+messages-send",
        "--as", "bot", "--user-id", s.lark_user_open_id, "--markdown", markdown,
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
