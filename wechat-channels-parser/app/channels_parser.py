"""视频号解析模块。

⚠️ 本模块依赖视频号未公开接口，需要单独逆向实现。
   Phase 1 仅提供 stub，Phase 2 真实实现请见 docs/channels_reverse_eng.md。

调用方约定：
  - finder_username 是视频号 ID（v2_xxxxx@finder 格式）
  - nonce_id 是单条视频的随机 ID
  - extra 留给后续可能需要的额外字段（export_id / cookie / 等）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChannelsVideo:
    video_url: str
    cover_url: str
    title: str
    description: str
    duration_seconds: int
    author_nickname: str
    raw_meta: dict[str, Any] = field(default_factory=dict)


class ChannelsParseError(RuntimeError):
    """视频号解析失败。"""


async def parse_channels_video(
    finder_username: str,
    nonce_id: str,
    extra: dict[str, Any] | None = None,
) -> ChannelsVideo:
    """Phase 1 stub.

    返回固定 mock 数据，让上层串接逻辑可以独立验证。
    Phase 2 接入真实反查时直接替换本函数实现即可。
    """
    if not finder_username or not nonce_id:
        raise ChannelsParseError(
            f"missing required fields: finder_username={finder_username!r} nonce_id={nonce_id!r}"
        )
    return ChannelsVideo(
        video_url=f"https://example.invalid/stub/{nonce_id}.mp4",
        cover_url=f"https://example.invalid/stub/{nonce_id}_cover.jpg",
        title="[STUB] 视频号解析未实现",
        description=f"finder={finder_username} nonce={nonce_id}",
        duration_seconds=0,
        author_nickname="[stub]",
        raw_meta={"_stub": True, "extra": extra or {}},
    )
