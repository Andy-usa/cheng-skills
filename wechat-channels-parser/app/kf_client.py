"""微信客服 API 封装。

只覆盖本服务真正用到的两个端点：
  - sync_msg: 拉取客服会话消息（基于事件回调中携带的 token）
  - send_msg: 主动回复消息

接口路径来自企业微信官方文档（不要凭记忆）。
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass
from typing import Any

import httpx

from app.access_token import get_access_token
from app.utils.logger import logger

_SYNC_MSG_URL = "https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg"
_SEND_MSG_URL = "https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg"

_REQUEST_TIMEOUT_SECONDS = 10.0
_MAX_RETRIES = 3


@dataclass
class SyncMsgResult:
    next_cursor: str
    has_more: bool
    msg_list: list[dict[str, Any]]


class KFAPIError(RuntimeError):
    """企业微信 API 返回 errcode != 0。"""

    def __init__(self, errcode: int, errmsg: str, *, endpoint: str) -> None:
        super().__init__(f"{endpoint} errcode={errcode} errmsg={errmsg}")
        self.errcode = errcode
        self.errmsg = errmsg
        self.endpoint = endpoint


# ────────────────────────────────────────────────────────────────────────────
# Internal: HTTP with retry + auto-refresh access_token on 40014/42001

async def _post_with_retry(
    url: str,
    *,
    body: dict[str, Any],
    endpoint: str,
) -> dict[str, Any]:
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            access_token = await get_access_token(force_refresh=attempt > 0 and _last_was_token_error())
            params = {"access_token": access_token}
            async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
                resp = await client.post(url, params=params, json=body)
            resp.raise_for_status()
            data = resp.json()
            errcode = data.get("errcode", 0)
            if errcode == 0:
                return data
            # token expired / invalid → refresh & retry
            if errcode in (40014, 42001):
                logger.warning("access_token invalid, refreshing", extra={"errcode": errcode})
                _mark_token_error()
                continue
            raise KFAPIError(errcode, data.get("errmsg", ""), endpoint=endpoint)
        except (httpx.HTTPError, KFAPIError) as exc:
            last_exc = exc
            backoff = (2**attempt) + random.random()
            logger.warning(
                f"{endpoint} attempt {attempt + 1}/{_MAX_RETRIES} failed: {exc}; sleeping {backoff:.1f}s",
            )
            if attempt < _MAX_RETRIES - 1:
                await asyncio.sleep(backoff)
    raise last_exc if last_exc else RuntimeError(f"{endpoint} failed after retries")


# Tiny module-local flag so we only force-refresh when the previous failure
# was an auth-class error, not a generic 5xx.
_token_error_flag = False


def _mark_token_error() -> None:
    global _token_error_flag  # noqa: PLW0603
    _token_error_flag = True


def _last_was_token_error() -> bool:
    global _token_error_flag  # noqa: PLW0603
    flag = _token_error_flag
    _token_error_flag = False
    return flag


# ────────────────────────────────────────────────────────────────────────────
# Public

async def sync_msg(
    *,
    token: str,
    open_kfid: str,
    cursor: str | None = None,
    limit: int = 1000,
) -> SyncMsgResult:
    """单次调用 sync_msg；调用方负责按 has_more 循环。"""
    body: dict[str, Any] = {
        "token": token,
        "open_kfid": open_kfid,
        "limit": limit,
    }
    if cursor:
        body["cursor"] = cursor
    data = await _post_with_retry(_SYNC_MSG_URL, body=body, endpoint="kf/sync_msg")
    return SyncMsgResult(
        next_cursor=data.get("next_cursor", ""),
        has_more=bool(data.get("has_more", 0)),
        msg_list=list(data.get("msg_list", [])),
    )


async def sync_msg_all(
    *,
    token: str,
    open_kfid: str,
    starting_cursor: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """循环 sync_msg 直到 has_more=False，返回 (final_cursor, all_msgs)。"""
    cursor = starting_cursor or ""
    all_msgs: list[dict[str, Any]] = []
    while True:
        result = await sync_msg(token=token, open_kfid=open_kfid, cursor=cursor or None)
        all_msgs.extend(result.msg_list)
        cursor = result.next_cursor or cursor
        if not result.has_more:
            return cursor, all_msgs


async def send_msg(
    *,
    touser: str,
    open_kfid: str,
    msgtype: str,
    content: dict[str, Any],
) -> str:
    """发送主动消息。返回服务端 msgid。

    content 由调用方按 msgtype 构造，例如：
      msgtype="text",  content={"text": {"content": "hi"}}
      msgtype="link",  content={"link": {"title": "...", "desc": "...", "url": "...", "thumb_media_id": "..."}}
    """
    body: dict[str, Any] = {
        "touser": touser,
        "open_kfid": open_kfid,
        "msgtype": msgtype,
        **content,
    }
    data = await _post_with_retry(_SEND_MSG_URL, body=body, endpoint="kf/send_msg")
    return str(data.get("msgid", ""))


# ────────────────────────────────────────────────────────────────────────────
# Convenience builders

def text_message(content: str) -> dict[str, Any]:
    return {"text": {"content": content}}


def link_message(*, title: str, desc: str, url: str, thumb_media_id: str = "") -> dict[str, Any]:
    return {
        "link": {
            "title": title,
            "desc": desc,
            "url": url,
            "thumb_media_id": thumb_media_id,
        }
    }
