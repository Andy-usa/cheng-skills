"""End-to-end tests for FastAPI routes via TestClient.

Covers:
  - GET /health
  - GET /wechat/callback (URL verification: success + signature failure)
  - POST /wechat/callback (encrypted payload accepted; handler scheduled in background)
"""

from __future__ import annotations

import os

import pytest

# Required env BEFORE importing app modules.
os.environ.setdefault("WECHAT_CORP_ID", "wx5823bf96d3bd56c7")
os.environ.setdefault("WECHAT_KF_SECRET", "secret_test")
os.environ.setdefault("WECHAT_CALLBACK_TOKEN", "QDG6eK")
os.environ.setdefault("WECHAT_CALLBACK_AES_KEY", "jWmYm7qr5nMoAUwZRjGtBxmz3KA1tkAj3ykkR6q2B2C")
os.environ.setdefault("WECHAT_OPEN_KFID", "wk_test")

from fastapi.testclient import TestClient  # noqa: E402

from app import handlers  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.crypto import WXBizMsgCrypt  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def crypto() -> WXBizMsgCrypt:
    """Build the crypto helper from live Settings so it always matches what
    `app.main._crypto()` will use, regardless of which other test ran first."""
    s = get_settings()
    return WXBizMsgCrypt(
        token=s.wechat_callback_token,
        encoding_aes_key=s.wechat_callback_aes_key,
        receive_id=s.wechat_corp_id,
    )


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_verify_callback_returns_decrypted_echostr(client: TestClient, crypto: WXBizMsgCrypt) -> None:
    envelope, sig, ts, nonce = crypto.encrypt("hello-echostr")
    # The actual echostr query param is the inner Encrypt blob (not the envelope)
    encrypt_b64 = _extract_encrypt(envelope)
    r = client.get(
        "/wechat/callback",
        params={"msg_signature": sig, "timestamp": ts, "nonce": nonce, "echostr": encrypt_b64},
    )
    assert r.status_code == 200
    assert r.text == "hello-echostr"


def test_verify_callback_rejects_bad_signature(client: TestClient, crypto: WXBizMsgCrypt) -> None:
    envelope, _sig, ts, nonce = crypto.encrypt("hello")
    encrypt_b64 = _extract_encrypt(envelope)
    r = client.get(
        "/wechat/callback",
        params={"msg_signature": "0" * 40, "timestamp": ts, "nonce": nonce, "echostr": encrypt_b64},
    )
    assert r.status_code == 401


def test_receive_callback_returns_success_and_schedules_handler(
    client: TestClient, crypto: WXBizMsgCrypt, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: list[dict] = []

    async def fake_handle(event):
        captured.append(event)

    monkeypatch.setattr("app.main.handle_callback_event", fake_handle)

    inner_xml = (
        "<xml><ToUserName><![CDATA[corp]]></ToUserName>"
        "<MsgType><![CDATA[event]]></MsgType>"
        "<Event><![CDATA[kf_msg_or_event]]></Event>"
        "<Token><![CDATA[CB_TOKEN_X]]></Token>"
        "<OpenKfId><![CDATA[wk_test]]></OpenKfId></xml>"
    )
    envelope, sig, ts, nonce = crypto.encrypt(inner_xml)

    r = client.post(
        "/wechat/callback",
        params={"msg_signature": sig, "timestamp": ts, "nonce": nonce},
        content=envelope,
    )
    assert r.status_code == 200
    assert r.text == "success"
    # BackgroundTasks executes after the response is sent in TestClient
    assert len(captured) == 1
    assert captured[0]["Token"] == "CB_TOKEN_X"
    assert captured[0]["OpenKfId"] == "wk_test"


def test_receive_callback_rejects_bad_signature(client: TestClient, crypto: WXBizMsgCrypt) -> None:
    envelope, _sig, ts, nonce = crypto.encrypt("<xml/>")
    r = client.post(
        "/wechat/callback",
        params={"msg_signature": "0" * 40, "timestamp": ts, "nonce": nonce},
        content=envelope,
    )
    assert r.status_code == 400


# ────────────────────────────────────────────────────────────────────────────
# Helpers

def _extract_encrypt(envelope_xml: str) -> str:
    import xmltodict

    return xmltodict.parse(envelope_xml)["xml"]["Encrypt"]
