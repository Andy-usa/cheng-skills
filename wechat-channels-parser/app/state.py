"""sync_msg 游标 + 已处理 msgid 持久化（JSON 文件）。

- 写入用 tmp file + os.replace 保证原子性
- processed_msgids 在内存以 set 存放，持久化时转 list 并按时间滚动淘汰至 MAX_PROCESSED
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from app.config import get_settings
from app.utils.logger import logger

MAX_PROCESSED: int = 10_000


@dataclass
class State:
    next_cursor: str = ""
    processed_msgids: list[str] = field(default_factory=list)  # ordered, oldest first
    last_updated: str = ""

    @property
    def processed_set(self) -> set[str]:
        return set(self.processed_msgids)

    def mark_processed(self, msgid: str) -> None:
        if msgid in self.processed_set:
            return
        self.processed_msgids.append(msgid)
        # rolling window
        if len(self.processed_msgids) > MAX_PROCESSED:
            drop = len(self.processed_msgids) - MAX_PROCESSED
            self.processed_msgids = self.processed_msgids[drop:]


_lock = asyncio.Lock()


def _path() -> Path:
    return Path(get_settings().state_file_path)


def load() -> State:
    path = _path()
    if not path.exists():
        return State()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(f"state file corrupted ({exc}); starting fresh")
        return State()
    return State(
        next_cursor=data.get("next_cursor", ""),
        processed_msgids=list(data.get("processed_msgids", [])),
        last_updated=data.get("last_updated", ""),
    )


async def save(state: State) -> None:
    async with _lock:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        state.last_updated = datetime.now(timezone.utc).isoformat()
        payload = {
            "next_cursor": state.next_cursor,
            "processed_msgids": state.processed_msgids,
            "last_updated": state.last_updated,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
