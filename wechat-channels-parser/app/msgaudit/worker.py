"""msgaudit 主循环 worker。

设计：
  - 长驻进程（systemd / supervisor / nohup &）
  - 每 N 秒一轮：load(state) → GetChatData(seq, 1000) → 解密 → 过滤 sphfeed → 调 pipeline → 更新 seq → save(state)
  - 优雅停机：SIGTERM / SIGINT 时把当前 seq 持久化再退出
  - 异常隔离：单条消息处理失败不影响 batch；batch 整体失败下一轮重试
"""

from __future__ import annotations

import asyncio
import signal
import time
from pathlib import Path

from app import state as state_mod
from app.config import get_settings
from app.msgaudit.client import MsgAuditClient, MsgAuditSDKError
from app.msgaudit.models import parse_envelope, parse_sphfeed
from app.pipelines.sphfeed_to_lark import handle_sphfeed
from app.utils.logger import logger, setup_logger

_should_stop = False


def _install_signal_handlers() -> None:
    def _handler(signum, _frame) -> None:
        global _should_stop  # noqa: PLW0603
        logger.info(f"received signal {signum}, will stop after current batch")
        _should_stop = True

    signal.signal(signal.SIGTERM, _handler)
    signal.signal(signal.SIGINT, _handler)


def _build_client() -> MsgAuditClient:
    s = get_settings()
    pem = Path(s.rsa_private_key_path).read_bytes()
    return MsgAuditClient(
        corp_id=s.wechat_corp_id,
        msgaudit_secret=s.wechat_msgaudit_secret,
        rsa_private_key_pem=pem,
    )


async def run_once(client: MsgAuditClient, state: state_mod.State) -> int:
    """跑一轮 GetChatData + 处理。返回本轮处理的消息数。"""
    s = get_settings()
    try:
        records = client.get_chat_data(seq=state.msgaudit_seq, limit=s.msgaudit_batch_limit)
    except (MsgAuditSDKError, NotImplementedError) as exc:
        logger.error(f"GetChatData failed: {exc}")
        return 0

    if not records:
        return 0

    handled = 0
    max_seq = state.msgaudit_seq
    for record in records:
        max_seq = max(max_seq, record.seq)
        if record.msgid in state.processed_set:
            continue

        try:
            decrypted = client.decrypt(record)
        except (MsgAuditSDKError, NotImplementedError) as exc:
            logger.warning(f"decrypt failed for msgid={record.msgid}: {exc}")
            state.mark_processed(record.msgid)  # don't retry forever on the same broken record
            continue

        envelope = parse_envelope(decrypted)
        # Phase 1 关注的视频号转发；其他类型先全部 dump 到日志做样本采集
        if envelope.msgtype == "sphfeed":
            sphfeed = parse_sphfeed(envelope)
            try:
                await handle_sphfeed(envelope, sphfeed)
            except Exception as exc:  # noqa: BLE001
                logger.exception(f"handle_sphfeed failed for msgid={envelope.msgid}: {exc}")
        else:
            logger.info(
                "non_sphfeed_msg",
                extra={"msgid": envelope.msgid, "msgtype": envelope.msgtype, "raw": envelope.raw},
            )

        state.mark_processed(envelope.msgid or record.msgid)
        handled += 1

    state.msgaudit_seq = max_seq
    await state_mod.save(state)
    return handled


async def main() -> None:
    setup_logger()
    s = get_settings()
    _install_signal_handlers()

    client = _build_client()
    state = state_mod.load()
    logger.info(
        "msgaudit worker starting",
        extra={"start_seq": state.msgaudit_seq, "poll_interval": s.msgaudit_poll_interval_seconds},
    )

    while not _should_stop:
        try:
            count = await run_once(client, state)
            logger.info("batch done", extra={"handled": count, "next_seq": state.msgaudit_seq})
        except Exception as exc:  # noqa: BLE001
            logger.exception(f"batch loop crashed: {exc}; sleeping then retrying")

        # Sleep in small chunks so SIGTERM is responsive
        slept = 0.0
        while slept < s.msgaudit_poll_interval_seconds and not _should_stop:
            await asyncio.sleep(0.5)
            slept += 0.5

    logger.info("msgaudit worker stopped cleanly", extra={"final_seq": state.msgaudit_seq})


if __name__ == "__main__":
    asyncio.run(main())
