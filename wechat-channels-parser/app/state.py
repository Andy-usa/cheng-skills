"""msgaudit seq 游标 + 已处理 msgid 持久化（JSON 文件）。

会话存档与微信客服回调的不同点：
  - 微信客服用 string 型的 next_cursor
  - 会话存档用 int 型的 seq（GetChatData 入参，从 0 开始递增）

`processed_msgids` 用 set 在内存判重，持久化滚动淘汰至 MAX_PROCESSED 条。
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
    msgaudit_seq: int = 0
    processed_msgids: list[str] = field(default_factory=list)  # ordered, oldest first
    last_updated: str = ""

    @property
    def processed_set(self) -> set[str]:
        return set(self.processed_msgids)

    def mark_processed(self, msgid: str) -> None:
        if msgid in self.processed_set:
            return
        self.processed_msgids.append(msgid)
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
        msgaudit_seq=int(data.get("msgaudit_seq", 0)),
        processed_msgids=list(data.get("processed_msgids", [])),
        last_updated=data.get("last_updated", ""),
    )


async def save(state: State) -> None:
    async with _lock:
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        state.last_updated = datetime.now(timezone.utc).isoformat()
        payload = {
            "msgaudit_seq": state.msgaudit_seq,
            "processed_msgids": state.processed_msgids,
            "last_updated": state.last_updated,
        }
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)
