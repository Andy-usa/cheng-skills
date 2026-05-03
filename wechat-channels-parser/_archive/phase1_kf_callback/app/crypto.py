"""企业微信回调加解密 (WXBizMsgCrypt)

参照官方 Python demo 实现，遵循以下规范：

  signature = SHA1( sort([token, timestamp, nonce, encrypt]).join("") )

  AESKey = Base64_Decode( EncodingAESKey + "=" )                        # 32 bytes
  IV     = AESKey[:16]
  plain  = AES_CBC_Decrypt( Base64_Decode(encrypt), AESKey, IV )
  plain  = PKCS7_Unpad( plain )
  layout = random(16) || msg_len_be(4) || msg || receiveid

加密流程（用于回包，本服务暂不会主动构造加密回包，但保留对称实现以便单测）：
  payload = random(16) || msg_len_be(4) || msg || receiveid
  cipher  = Base64_Encode( AES_CBC_Encrypt( PKCS7_Pad(payload), AESKey, IV ) )
"""

from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
from dataclasses import dataclass
from typing import Final

import xmltodict
from Crypto.Cipher import AES

BLOCK_SIZE: Final[int] = 32  # bytes — PKCS7 block size used by WeWork


class WXBizMsgCryptError(Exception):
    """All crypto / signature failures funnel into this."""


def _pkcs7_pad(text: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    pad_len = block_size - (len(text) % block_size)
    if pad_len == 0:
        pad_len = block_size
    return text + bytes([pad_len] * pad_len)


def _pkcs7_unpad(text: bytes, block_size: int = BLOCK_SIZE) -> bytes:
    if not text:
        raise WXBizMsgCryptError("empty plaintext")
    pad_len = text[-1]
    if pad_len < 1 or pad_len > block_size:
        # Treat invalid padding as no padding — still safer than crashing
        # because some malformed payloads have shown up in production.
        return text
    return text[:-pad_len]


def _sign(token: str, timestamp: str, nonce: str, encrypt: str) -> str:
    """SHA1 of sorted concatenation."""
    parts = sorted([token, timestamp, nonce, encrypt])
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


@dataclass
class WXBizMsgCrypt:
    """Stateless crypto helper bound to a single (token, aes_key, receiveid) triple."""

    token: str
    encoding_aes_key: str
    receive_id: str  # corp_id for WeWork

    def __post_init__(self) -> None:
        if len(self.encoding_aes_key) != 43:
            raise WXBizMsgCryptError(
                f"EncodingAESKey must be 43 chars, got {len(self.encoding_aes_key)}"
            )
        try:
            self._aes_key = base64.b64decode(self.encoding_aes_key + "=")
        except Exception as exc:  # noqa: BLE001
            raise WXBizMsgCryptError(f"invalid EncodingAESKey: {exc}") from exc
        if len(self._aes_key) != 32:
            raise WXBizMsgCryptError(
                f"decoded AES key must be 32 bytes, got {len(self._aes_key)}"
            )
        self._iv = self._aes_key[:16]

    # ────────────────────────────────────────────────────────────────────
    # Signature

    def verify_signature(
        self, msg_signature: str, timestamp: str, nonce: str, encrypt: str
    ) -> None:
        expected = _sign(self.token, timestamp, nonce, encrypt)
        if expected != msg_signature:
            raise WXBizMsgCryptError(
                f"signature mismatch: expected {expected}, got {msg_signature}"
            )

    # ────────────────────────────────────────────────────────────────────
    # Decrypt

    def decrypt(self, encrypted_b64: str) -> str:
        cipher_bytes = base64.b64decode(encrypted_b64)
        cipher = AES.new(self._aes_key, AES.MODE_CBC, self._iv)
        plain = cipher.decrypt(cipher_bytes)
        plain = _pkcs7_unpad(plain)

        # Layout: 16-byte random || 4-byte big-endian msg_len || msg || receive_id
        if len(plain) < 20:
            raise WXBizMsgCryptError("decrypted payload too short")
        msg_len = struct.unpack(">I", plain[16:20])[0]
        if 20 + msg_len > len(plain):
            raise WXBizMsgCryptError(
                f"declared msg_len {msg_len} exceeds payload {len(plain) - 20}"
            )
        msg = plain[20 : 20 + msg_len]
        recv_id = plain[20 + msg_len :].decode("utf-8")
        if recv_id != self.receive_id:
            raise WXBizMsgCryptError(
                f"receive_id mismatch: expected {self.receive_id}, got {recv_id}"
            )
        return msg.decode("utf-8")

    # ────────────────────────────────────────────────────────────────────
    # GET URL verification

    def verify_url(
        self, msg_signature: str, timestamp: str, nonce: str, echostr: str
    ) -> str:
        """Return decrypted echostr (raises on failure)."""
        self.verify_signature(msg_signature, timestamp, nonce, echostr)
        return self.decrypt(echostr)

    # ────────────────────────────────────────────────────────────────────
    # POST callback decrypt

    def decrypt_msg(
        self,
        msg_signature: str,
        timestamp: str,
        nonce: str,
        post_data: str,
    ) -> dict:
        """Decrypt a callback POST body (XML wrapper)."""
        envelope = xmltodict.parse(post_data)["xml"]
        encrypted = envelope["Encrypt"]
        self.verify_signature(msg_signature, timestamp, nonce, encrypted)
        plain_xml = self.decrypt(encrypted)
        return xmltodict.parse(plain_xml)["xml"]

    # ────────────────────────────────────────────────────────────────────
    # Encrypt (kept for round-trip tests; not used by the kf-callback path)

    def encrypt(self, msg: str, nonce: str | None = None) -> tuple[str, str, str, str]:
        """Return (xml_envelope, msg_signature, timestamp, nonce)."""
        nonce = nonce or _random_nonce()
        timestamp = _now_ts()
        random_prefix = os.urandom(16)
        msg_bytes = msg.encode("utf-8")
        payload = (
            random_prefix
            + struct.pack(">I", len(msg_bytes))
            + msg_bytes
            + self.receive_id.encode("utf-8")
        )
        cipher = AES.new(self._aes_key, AES.MODE_CBC, self._iv)
        encrypted_bytes = cipher.encrypt(_pkcs7_pad(payload))
        encrypted_b64 = base64.b64encode(encrypted_bytes).decode("ascii")
        signature = _sign(self.token, timestamp, nonce, encrypted_b64)
        envelope = (
            "<xml>"
            f"<Encrypt><![CDATA[{encrypted_b64}]]></Encrypt>"
            f"<MsgSignature><![CDATA[{signature}]]></MsgSignature>"
            f"<TimeStamp>{timestamp}</TimeStamp>"
            f"<Nonce><![CDATA[{nonce}]]></Nonce>"
            "</xml>"
        )
        return envelope, signature, timestamp, nonce


def _now_ts() -> str:
    import time

    return str(int(time.time()))


def _random_nonce(length: int = 10) -> str:
    import secrets
    import string

    return "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))


# Suppress the unused-import warning for socket (kept for symmetry with official demo)
_ = socket
