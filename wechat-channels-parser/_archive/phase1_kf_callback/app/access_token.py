"""企业微信 access_token 缓存。

- 单例 + asyncio.Lock 防止并发重复刷新
- 提前 5 分钟视为过期
- 不持久化（access_token 默认有效期 7200s，进程重启重拉一次即可）
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.utils.logger import logger

_GETTOKEN_URL = "https://qyapi.weixin.qq.com/cgi-bin/gettoken"
_REFRESH_BUFFER_SECONDS = 5 * 60  # refresh 5 min before expiry


@dataclass
class _CachedToken:
    value: str
    expires_at: float  # epoch seconds


_cache: _CachedToken | None = None
_lock = asyncio.Lock()


def _is_fresh(token: _CachedToken | None) -> bool:
    return token is not None and time.time() + _REFRESH_BUFFER_SECONDS < token.expires_at


async def _fetch_new() -> _CachedToken:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            _GETTOKEN_URL,
            params={"corpid": settings.wechat_corp_id, "corpsecret": settings.wechat_kf_secret},
        )
    resp.raise_for_status()
    data = resp.json()
    if data.get("errcode", 0) != 0:
        logger.error("gettoken failed", extra={"errcode": data.get("errcode"), "errmsg": data.get("errmsg")})
        raise RuntimeError(f"gettoken errcode={data.get('errcode')} errmsg={data.get('errmsg')}")
    expires_in = int(data.get("expires_in", 7200))
    return _CachedToken(value=data["access_token"], expires_at=time.time() + expires_in)


async def get_access_token(*, force_refresh: bool = False) -> str:
    global _cache  # noqa: PLW0603
    if not force_refresh and _is_fresh(_cache):
        return _cache.value  # type: ignore[union-attr]
    async with _lock:
        if not force_refresh and _is_fresh(_cache):
            return _cache.value  # type: ignore[union-attr]
        _cache = await _fetch_new()
        logger.info("access_token refreshed", extra={"expires_at": _cache.expires_at})
        return _cache.value


def _reset_cache_for_tests() -> None:
    global _cache  # noqa: PLW0603
    _cache = None
