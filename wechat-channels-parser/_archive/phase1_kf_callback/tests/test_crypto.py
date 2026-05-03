"""End-to-end round-trip tests for WXBizMsgCrypt.

Strategy: encrypt a known plaintext, then decrypt the resulting envelope and
assert it matches. Also covers the GET-URL verification path and the
signature-mismatch / receive-id-mismatch failure modes.
"""

from __future__ import annotations

import base64
import struct

import pytest
import xmltodict

from app.crypto import (
    WXBizMsgCrypt,
    WXBizMsgCryptError,
    _pkcs7_pad,
    _pkcs7_unpad,
    _sign,
)

# A fresh 43-character EncodingAESKey (43 chars → 32 raw bytes after Base64).
TOKEN = "QDG6eK"
AES_KEY = "jWmYm7qr5nMoAUwZRjGtBxmz3KA1tkAj3ykkR6q2B2C"
RECEIVE_ID = "wx5823bf96d3bd56c7"


def _crypto() -> WXBizMsgCrypt:
    return WXBizMsgCrypt(token=TOKEN, encoding_aes_key=AES_KEY, receive_id=RECEIVE_ID)


# ────────────────────────────────────────────────────────────────────────────
# PKCS7

def test_pkcs7_round_trip_arbitrary_lengths() -> None:
    for length in (0, 1, 31, 32, 33, 100):
        data = b"x" * length
        padded = _pkcs7_pad(data)
        assert len(padded) % 32 == 0
        assert _pkcs7_unpad(padded) == data


def test_pkcs7_pad_full_block_when_aligned() -> None:
    data = b"a" * 32
    padded = _pkcs7_pad(data)
    assert len(padded) == 64  # full extra block per spec


# ────────────────────────────────────────────────────────────────────────────
# Signature

def test_signature_is_sorted_sha1() -> None:
    sig = _sign("t", "1", "n", "e")
    # Same inputs in different order yield the same signature
    assert sig == _sign("e", "n", "1", "t")


# ────────────────────────────────────────────────────────────────────────────
# Constructor validation

def test_invalid_aes_key_length_rejected() -> None:
    with pytest.raises(WXBizMsgCryptError, match="43 chars"):
        WXBizMsgCrypt(token=TOKEN, encoding_aes_key="too_short", receive_id=RECEIVE_ID)


# ────────────────────────────────────────────────────────────────────────────
# Decrypt round-trip

def test_decrypt_round_trip_returns_original_plaintext() -> None:
    crypto = _crypto()
    plain_xml = (
        "<xml><ToUserName><![CDATA[corp]]></ToUserName>"
        "<MsgType><![CDATA[event]]></MsgType>"
        "<Event><![CDATA[kf_msg_or_event]]></Event>"
        "<Token><![CDATA[ENCKEY12345]]></Token>"
        "<OpenKfId><![CDATA[wkAAAAAAAAAAAAAA]]></OpenKfId></xml>"
    )
    envelope, signature, timestamp, nonce = crypto.encrypt(plain_xml)
    decrypted = crypto.decrypt_msg(signature, timestamp, nonce, envelope)
    assert decrypted["MsgType"] == "event"
    assert decrypted["Event"] == "kf_msg_or_event"
    assert decrypted["Token"] == "ENCKEY12345"
    assert decrypted["OpenKfId"] == "wkAAAAAAAAAAAAAA"


def test_decrypt_signature_mismatch_raises() -> None:
    crypto = _crypto()
    envelope, _sig, ts, nonce = crypto.encrypt("<xml><a>1</a></xml>")
    with pytest.raises(WXBizMsgCryptError, match="signature mismatch"):
        crypto.decrypt_msg("0" * 40, ts, nonce, envelope)


def test_decrypt_wrong_receive_id_raises() -> None:
    crypto = _crypto()
    envelope, sig, ts, nonce = crypto.encrypt("<xml><a>1</a></xml>")
    other = WXBizMsgCrypt(token=TOKEN, encoding_aes_key=AES_KEY, receive_id="someone_else")
    with pytest.raises(WXBizMsgCryptError, match="receive_id mismatch"):
        other.decrypt_msg(_sig_for(other, ts, nonce, _encrypt_payload(envelope)), ts, nonce, envelope)


def _encrypt_payload(envelope_xml: str) -> str:
    return xmltodict.parse(envelope_xml)["xml"]["Encrypt"]


def _sig_for(crypto: WXBizMsgCrypt, ts: str, nonce: str, encrypt: str) -> str:
    return _sign(crypto.token, ts, nonce, encrypt)


# ────────────────────────────────────────────────────────────────────────────
# GET URL verification

def test_verify_url_returns_decrypted_echostr() -> None:
    crypto = _crypto()
    # echostr is what WeWork sends during URL verification — itself a Base64
    # AES-encrypted random nonce. We synthesise one via our own encrypt().
    _envelope, sig, ts, nonce = crypto.encrypt("hello")
    encrypted = _encrypt_payload(_envelope)
    decrypted = crypto.verify_url(sig, ts, nonce, encrypted)
    assert decrypted == "hello"


# ────────────────────────────────────────────────────────────────────────────
# Defensive parsing

def test_decrypt_short_payload_raises() -> None:
    crypto = _crypto()
    short = base64.b64encode(b"x" * 32).decode("ascii")  # decrypts but layout invalid
    with pytest.raises(WXBizMsgCryptError):
        crypto.decrypt(short)


def test_decrypt_declared_msglen_overflow_raises() -> None:
    """If msg_len in the layout exceeds the actual payload, fail loudly."""
    crypto = _crypto()
    bad_payload = b"R" * 16 + struct.pack(">I", 9_999) + b"short msg" + RECEIVE_ID.encode()
    from Crypto.Cipher import AES

    cipher = AES.new(crypto._aes_key, AES.MODE_CBC, crypto._iv)
    enc = base64.b64encode(cipher.encrypt(_pkcs7_pad(bad_payload))).decode("ascii")
    with pytest.raises(WXBizMsgCryptError, match="msg_len"):
        crypto.decrypt(enc)
