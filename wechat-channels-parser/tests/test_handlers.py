"""Handler dispatch tests.

Mock kf_client.send_msg and exercise process_message for each msgtype branch:
  - text → reply with prompt
  - channels → call parser → reply with link
  - unknown → reply with "unsupported"
  - origin != 3 → skip silently (no send_msg call)
  - duplicate msgid → skip
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("WECHAT_CORP_ID", "ww_test")
os.environ.setdefault("WECHAT_KF_SECRET", "secret_test")
os.environ.setdefault("WECHAT_CALLBACK_TOKEN", "token_test")
os.environ.setdefault("WECHAT_CALLBACK_AES_KEY", "x" * 43)
os.environ.setdefault("WECHAT_OPEN_KFID", "wk_test")

from app import handlers, kf_client, state as state_mod  # noqa: E402


@pytest.fixture
def captured_sends(monkeypatch):
    sent: list[dict] = []

    async def fake_send_msg(*, touser, open_kfid, msgtype, content):
        sent.append({"touser": touser, "open_kfid": open_kfid, "msgtype": msgtype, "content": content})
        return "fake_msgid"

    monkeypatch.setattr(kf_client, "send_msg", fake_send_msg)
    return sent


async def test_text_msg_replies_with_prompt(captured_sends) -> None:
    state = state_mod.State()
    msg = {
        "msgid": "m1",
        "msgtype": "text",
        "origin": 3,
        "external_userid": "wmAAA",
        "open_kfid": "wk_test",
    }
    await handlers.process_message(msg, state)

    assert len(captured_sends) == 1
    assert captured_sends[0]["msgtype"] == "text"
    assert "视频号" in captured_sends[0]["content"]["text"]["content"]
    assert "m1" in state.processed_set


async def test_channels_msg_calls_parser_and_sends_link(captured_sends, monkeypatch) -> None:
    from app import channels_parser

    async def fake_parse(finder, nonce, extra=None):
        return channels_parser.ChannelsVideo(
            video_url="https://example.com/v.mp4",
            cover_url="https://example.com/cover.jpg",
            title="Test Video",
            description="desc",
            duration_seconds=60,
            author_nickname="@alice",
        )

    monkeypatch.setattr(handlers, "parse_channels_video", fake_parse)

    state = state_mod.State()
    msg = {
        "msgid": "m_chn",
        "msgtype": "channels",
        "origin": 3,
        "external_userid": "wmBBB",
        "open_kfid": "wk_test",
        "channels": {"finder_username": "v2_X@finder", "nonce_id": "N123"},
    }
    await handlers.process_message(msg, state)

    assert len(captured_sends) == 1
    assert captured_sends[0]["msgtype"] == "link"
    link = captured_sends[0]["content"]["link"]
    assert link["title"] == "Test Video"
    assert link["url"] == "https://example.com/v.mp4"
    assert "@alice" in link["desc"]


async def test_channels_parse_failure_replies_with_text(captured_sends, monkeypatch) -> None:
    from app import channels_parser

    async def boom(finder, nonce, extra=None):
        raise channels_parser.ChannelsParseError("not implemented")

    monkeypatch.setattr(handlers, "parse_channels_video", boom)

    state = state_mod.State()
    msg = {
        "msgid": "m_fail",
        "msgtype": "channels",
        "origin": 3,
        "external_userid": "wmCCC",
        "open_kfid": "wk_test",
        "channels": {"finder_username": "v2_X@finder", "nonce_id": "N999"},
    }
    await handlers.process_message(msg, state)

    assert len(captured_sends) == 1
    assert captured_sends[0]["msgtype"] == "text"
    assert "解析失败" in captured_sends[0]["content"]["text"]["content"]


async def test_unknown_msgtype_replies_with_unsupported(captured_sends) -> None:
    state = state_mod.State()
    msg = {
        "msgid": "m_unk",
        "msgtype": "image",
        "origin": 3,
        "external_userid": "wmDDD",
        "open_kfid": "wk_test",
    }
    await handlers.process_message(msg, state)

    assert len(captured_sends) == 1
    assert "暂不支持" in captured_sends[0]["content"]["text"]["content"]


async def test_origin_not_customer_is_skipped_silently(captured_sends) -> None:
    state = state_mod.State()
    msg = {
        "msgid": "m_self",
        "msgtype": "text",
        "origin": 4,  # 客服 — that's us; never reply
        "external_userid": "wmEEE",
        "open_kfid": "wk_test",
    }
    await handlers.process_message(msg, state)

    assert captured_sends == []
    # Still marked processed so cursor replay doesn't re-trigger logic
    assert "m_self" in state.processed_set


async def test_duplicate_msgid_is_skipped(captured_sends) -> None:
    state = state_mod.State(processed_msgids=["m_dup"])
    msg = {
        "msgid": "m_dup",
        "msgtype": "text",
        "origin": 3,
        "external_userid": "wm_X",
        "open_kfid": "wk_test",
    }
    await handlers.process_message(msg, state)
    assert captured_sends == []
