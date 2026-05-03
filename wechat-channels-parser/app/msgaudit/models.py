"""Decrypted msgaudit message dataclasses.

⚠️ Phase 2 stub。实际 sphfeed 消息体的字段需要本地接手时基于一条真机解密样本核对。
官方文档（developer.work.weixin.qq.com/document/path/91774 等）只列了 sph_name /
feed_desc / feed_type 三个字段，但实际响应里大概率还有 finder_username / nonce_id /
url 之类——必须真机 dump 才知道。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MsgAuditEnvelope:
    """会话存档解密后顶层信封 — 所有 msgtype 共享的字段。"""

    msgid: str
    action: str  # "send" / "recall" / "switch"
    from_userid: str  # 发送者（员工 userid 或客户 external_userid）
    tolist: list[str]  # 接收者列表
    roomid: str  # 群聊 ID（单聊为空）
    msgtime: int  # 毫秒时间戳
    msgtype: str  # text / image / channels-like (sphfeed) / ...
    raw: dict[str, Any]  # 原始解密 JSON，留作 Phase 2 校验


@dataclass
class SphfeedMessage:
    """视频号分享消息（msgtype=sphfeed）。

    ⚠️ 这些字段名是 placeholder——本地接手时基于真机 dump 修正：
        - 是否有 finder_username？
        - 是否有 nonce_id / feed_id？
        - 是否直接给 mp4 url，还是只给元数据需要二次反查？
    把真机 dump 存到 tests/fixtures/sample_sphfeed_msg.json，再据此修正。
    """

    feed_type: int  # 2=图文 / 4=视频 / 9=直播
    sph_name: str  # 视频号名称
    feed_desc: str  # 视频文案
    finder_username: str = ""  # ⚠️ 待真机确认字段名
    nonce_id: str = ""  # ⚠️ 待真机确认字段名
    url: str = ""  # ⚠️ 真机若直接给 url，这里直接拿；否则走 channels_parser 反查
    extra: dict[str, Any] = field(default_factory=dict)


def parse_envelope(decrypted_json: dict[str, Any]) -> MsgAuditEnvelope:
    """把会话存档 SDK 解出来的明文 JSON 包成 envelope。"""
    return MsgAuditEnvelope(
        msgid=str(decrypted_json.get("msgid", "")),
        action=str(decrypted_json.get("action", "send")),
        from_userid=str(decrypted_json.get("from", "")),
        tolist=list(decrypted_json.get("tolist", []) or []),
        roomid=str(decrypted_json.get("roomid", "") or ""),
        msgtime=int(decrypted_json.get("msgtime", 0) or 0),
        msgtype=str(decrypted_json.get("msgtype", "")),
        raw=decrypted_json,
    )


def parse_sphfeed(envelope: MsgAuditEnvelope) -> SphfeedMessage:
    """从 envelope 抽取 sphfeed 子结构。

    ⚠️ 实际字段路径（envelope.raw['sphfeed']['nonce_id'] 还是其他位置）需要根据真机 dump 校正。
    """
    body = envelope.raw.get("sphfeed", envelope.raw) or {}
    return SphfeedMessage(
        feed_type=int(body.get("feed_type", 0) or 0),
        sph_name=str(body.get("sph_name", "")),
        feed_desc=str(body.get("feed_desc", "")),
        finder_username=str(body.get("finder_username", "")),  # ⚠️ stub key
        nonce_id=str(body.get("nonce_id", "")),  # ⚠️ stub key
        url=str(body.get("url", "")),  # ⚠️ stub key
        extra={k: v for k, v in body.items()
               if k not in {"feed_type", "sph_name", "feed_desc", "finder_username", "nonce_id", "url"}},
    )
