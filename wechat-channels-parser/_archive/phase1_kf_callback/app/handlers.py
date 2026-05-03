"""业务处理：回调事件 → sync_msg → 按 msgtype 分发。

设计原则（来自需求文档）：
  - sync_msg 必须循环到 has_more=False
  - msgid 判重，已处理过的 skip
  - 只处理 origin=3（客户发的），跳过自己发的（避免死循环）
  - channels 消息：提取 finder_username + nonce_id，调 channels_parser，回 link 消息
  - 其他类型：text 提示「请直接转发视频号视频」，未知类型回「暂不支持」
"""

from __future__ import annotations

import time
from typing import Any

from app import kf_client, state as state_mod
from app.channels_parser import ChannelsParseError, parse_channels_video
from app.config import get_settings
from app.utils.logger import logger

# Origin codes per WeWork docs:
#   3 = 客户 (the customer / external user)
#   4 = 客服 (the kf operator, i.e. us)
ORIGIN_CUSTOMER = 3


async def handle_callback_event(event: dict) -> None:
    """收到 kf_msg_or_event 后触发：拉消息 → 分发。

    event 是回调解密后的 XML dict，包含 Token / OpenKfId 等字段。
    """
    cb_token = event.get("Token")
    open_kfid = event.get("OpenKfId") or get_settings().wechat_open_kfid
    if not cb_token:
        logger.warning("callback event missing Token", extra={"event": event})
        return

    state = state_mod.load()
    starting_cursor = state.next_cursor or None
    final_cursor, msgs = await kf_client.sync_msg_all(
        token=cb_token,
        open_kfid=open_kfid,
        starting_cursor=starting_cursor,
    )
    logger.info(
        "sync_msg_all done",
        extra={
            "open_kfid": open_kfid,
            "fetched": len(msgs),
            "starting_cursor": starting_cursor,
            "final_cursor": final_cursor,
        },
    )

    for msg in msgs:
        await process_message(msg, state)

    state.next_cursor = final_cursor
    await state_mod.save(state)


async def process_message(msg: dict[str, Any], state: state_mod.State) -> None:
    """单条消息分发。"""
    msgid = msg.get("msgid", "")
    msgtype = msg.get("msgtype", "")
    origin = int(msg.get("origin", 0) or 0)
    started = time.perf_counter()

    if msgid in state.processed_set:
        logger.debug("skip duplicate", extra={"msgid": msgid})
        return
    if origin != ORIGIN_CUSTOMER:
        logger.debug("skip non-customer message", extra={"msgid": msgid, "origin": origin})
        state.mark_processed(msgid)  # still mark to avoid re-processing on cursor replay
        return

    # Phase 1: dump full message body for offline schema verification.
    logger.info(
        "msg_received",
        extra={
            "msgid": msgid,
            "msgtype": msgtype,
            "external_userid": msg.get("external_userid"),
            "open_kfid": msg.get("open_kfid"),
            "raw": msg,
        },
    )

    try:
        if msgtype == "channels":
            await _handle_channels(msg)
        elif msgtype == "text":
            await _handle_text(msg)
        else:
            await _reply_unknown(msg)
    except Exception as exc:  # noqa: BLE001 — never let one bad msg break the batch
        logger.exception(f"process_message failed for msgid={msgid}: {exc}")
    finally:
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info(
            "msg_processed",
            extra={"msgid": msgid, "msgtype": msgtype, "elapsed_ms": round(elapsed_ms, 1)},
        )
        state.mark_processed(msgid)


# ────────────────────────────────────────────────────────────────────────────
# Per-msgtype handlers

async def _handle_channels(msg: dict[str, Any]) -> None:
    channels = msg.get("channels") or {}
    finder_username = channels.get("finder_username", "")
    nonce_id = channels.get("nonce_id", "")
    try:
        parsed = await parse_channels_video(finder_username, nonce_id)
    except (ChannelsParseError, NotImplementedError) as exc:
        await kf_client.send_msg(
            touser=msg["external_userid"],
            open_kfid=msg["open_kfid"],
            msgtype="text",
            content=kf_client.text_message(f"解析失败：{exc}"),
        )
        return

    await kf_client.send_msg(
        touser=msg["external_userid"],
        open_kfid=msg["open_kfid"],
        msgtype="link",
        content=kf_client.link_message(
            title=parsed.title,
            desc=f"作者：{parsed.author_nickname}",
            url=parsed.video_url,
        ),
    )


async def _handle_text(msg: dict[str, Any]) -> None:
    await kf_client.send_msg(
        touser=msg["external_userid"],
        open_kfid=msg["open_kfid"],
        msgtype="text",
        content=kf_client.text_message("请直接转发视频号视频给我，我会帮你解析出原始链接。"),
    )


async def _reply_unknown(msg: dict[str, Any]) -> None:
    await kf_client.send_msg(
        touser=msg["external_userid"],
        open_kfid=msg["open_kfid"],
        msgtype="text",
        content=kf_client.text_message(
            f"暂不支持此消息类型（{msg.get('msgtype')}），请转发视频号视频。"
        ),
    )
