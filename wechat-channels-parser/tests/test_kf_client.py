"""kf_client 单测：覆盖 happy path、has_more 分页、token 自动刷新、errcode 失败。

外部 HTTP 调用全部用 respx mock。
"""

from __future__ import annotations

import os

import pytest
import respx
from httpx import Response

# Set required env BEFORE importing app modules that read settings.
os.environ.setdefault("WECHAT_CORP_ID", "ww_test")
os.environ.setdefault("WECHAT_KF_SECRET", "secret_test")
os.environ.setdefault("WECHAT_CALLBACK_TOKEN", "token_test")
os.environ.setdefault("WECHAT_CALLBACK_AES_KEY", "x" * 43)
os.environ.setdefault("WECHAT_OPEN_KFID", "wk_test")

from app import access_token, kf_client  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_token_cache():
    access_token._reset_cache_for_tests()
    yield
    access_token._reset_cache_for_tests()


@respx.mock
async def test_sync_msg_happy_path() -> None:
    respx.get("https://qyapi.weixin.qq.com/cgi-bin/gettoken").mock(
        return_value=Response(200, json={"errcode": 0, "access_token": "TOK", "expires_in": 7200})
    )
    respx.post("https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg").mock(
        return_value=Response(200, json={
            "errcode": 0,
            "next_cursor": "cur_next",
            "has_more": 0,
            "msg_list": [{"msgid": "m1"}, {"msgid": "m2"}],
        })
    )
    result = await kf_client.sync_msg(token="cb_token", open_kfid="wk_test")
    assert result.next_cursor == "cur_next"
    assert result.has_more is False
    assert [m["msgid"] for m in result.msg_list] == ["m1", "m2"]


@respx.mock
async def test_sync_msg_all_paginates_until_no_more() -> None:
    respx.get("https://qyapi.weixin.qq.com/cgi-bin/gettoken").mock(
        return_value=Response(200, json={"errcode": 0, "access_token": "TOK", "expires_in": 7200})
    )
    route = respx.post("https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg").mock(
        side_effect=[
            Response(200, json={"errcode": 0, "next_cursor": "c2", "has_more": 1, "msg_list": [{"msgid": "a"}]}),
            Response(200, json={"errcode": 0, "next_cursor": "c3", "has_more": 1, "msg_list": [{"msgid": "b"}]}),
            Response(200, json={"errcode": 0, "next_cursor": "c4", "has_more": 0, "msg_list": [{"msgid": "c"}]}),
        ]
    )
    final_cursor, msgs = await kf_client.sync_msg_all(token="cb_token", open_kfid="wk_test")
    assert final_cursor == "c4"
    assert [m["msgid"] for m in msgs] == ["a", "b", "c"]
    assert route.call_count == 3


@respx.mock
async def test_send_msg_returns_msgid() -> None:
    respx.get("https://qyapi.weixin.qq.com/cgi-bin/gettoken").mock(
        return_value=Response(200, json={"errcode": 0, "access_token": "TOK", "expires_in": 7200})
    )
    respx.post("https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg").mock(
        return_value=Response(200, json={"errcode": 0, "msgid": "ret_msgid_xyz"})
    )
    msgid = await kf_client.send_msg(
        touser="wmAAA",
        open_kfid="wk_test",
        msgtype="text",
        content=kf_client.text_message("hello"),
    )
    assert msgid == "ret_msgid_xyz"


@respx.mock
async def test_send_msg_propagates_api_error() -> None:
    respx.get("https://qyapi.weixin.qq.com/cgi-bin/gettoken").mock(
        return_value=Response(200, json={"errcode": 0, "access_token": "TOK", "expires_in": 7200})
    )
    respx.post("https://qyapi.weixin.qq.com/cgi-bin/kf/send_msg").mock(
        return_value=Response(200, json={"errcode": 60020, "errmsg": "not allowed"})
    )
    with pytest.raises(kf_client.KFAPIError) as exc_info:
        await kf_client.send_msg(
            touser="wmAAA",
            open_kfid="wk_test",
            msgtype="text",
            content=kf_client.text_message("hi"),
        )
    assert exc_info.value.errcode == 60020


@respx.mock
async def test_token_refresh_on_invalid_token_error(monkeypatch) -> None:
    monkeypatch.setattr(kf_client, "_MAX_RETRIES", 3)
    # gettoken called twice (initial + force-refresh after 42001)
    respx.get("https://qyapi.weixin.qq.com/cgi-bin/gettoken").mock(
        side_effect=[
            Response(200, json={"errcode": 0, "access_token": "TOK_OLD", "expires_in": 7200}),
            Response(200, json={"errcode": 0, "access_token": "TOK_NEW", "expires_in": 7200}),
        ]
    )
    sync_route = respx.post("https://qyapi.weixin.qq.com/cgi-bin/kf/sync_msg").mock(
        side_effect=[
            Response(200, json={"errcode": 42001, "errmsg": "access_token expired"}),
            Response(200, json={"errcode": 0, "next_cursor": "c", "has_more": 0, "msg_list": []}),
        ]
    )
    # Patch sleep to skip backoff in tests
    import asyncio
    async def _no_sleep(_):
        pass
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)

    result = await kf_client.sync_msg(token="cb", open_kfid="wk_test")
    assert sync_route.call_count == 2
    assert result.next_cursor == "c"
