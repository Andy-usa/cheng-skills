"""企业微信会话内容存档 SDK 包装层（stub）。

⚠️ Python 没有官方 SDK，本地接手时三选一（详见 docs/python_sdk_options.md）：
  A. 自行 ctypes 包 C SDK（libWeWorkFinanceSdk_C.so / .dll）
  B. 用第三方 PyPI 包（GitHub 上常见 wxwork-finance-sdk-python）
  C. 写独立 Go/Java 服务做 HTTP 隔离

本文件接口先按"理想 Python API"定义；具体实现等本地选定 SDK 后填充。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class EncryptedChatRecord:
    """GetChatData 返回的单条密文记录（结构来自官方文档）。"""

    seq: int
    msgid: str
    publickey_ver: int
    encrypt_random_key: str  # base64
    encrypt_chat_msg: str  # base64


class MsgAuditSDKError(RuntimeError):
    """SDK 初始化或调用失败。"""


class MsgAuditClient:
    """会话存档客户端封装。

    实际实现等本地接手时按选定 SDK 填充：
      - __init__: 初始化 SDK（corpid + msgaudit_secret）
      - get_chat_data: GetChatData(seq, limit, ...) → list[EncryptedChatRecord]
      - decrypt: RSA 解 random_key → AES 解 chat_msg → JSON dict
    """

    def __init__(self, corp_id: str, msgaudit_secret: str, rsa_private_key_pem: bytes) -> None:
        self.corp_id = corp_id
        self.msgaudit_secret = msgaudit_secret
        self.rsa_private_key_pem = rsa_private_key_pem
        # TODO(local): 初始化 C SDK 句柄 / 第三方 Python 包句柄

    def get_chat_data(self, seq: int, limit: int = 1000, timeout_seconds: int = 5) -> list[EncryptedChatRecord]:
        """调 GetChatData(seq, limit) 拉一批密文。

        ⚠️ stub：本地接手时按所选 SDK 实现。返回的记录已按 seq 升序。
        """
        raise NotImplementedError(
            "MsgAuditClient.get_chat_data 未实现——见 docs/python_sdk_options.md 选 SDK 并实现"
        )

    def decrypt(self, record: EncryptedChatRecord) -> dict[str, Any]:
        """对单条密文解密：RSA 解 random_key → AES 解 chat_msg → JSON。

        ⚠️ stub。
        publickey_ver 用于多版本 RSA 密钥滚动；目前我们只配一对，所以可以直接用现有私钥。
        如果 record.publickey_ver != 当前公钥版本号，记录告警并跳过。
        """
        raise NotImplementedError(
            "MsgAuditClient.decrypt 未实现——见 docs/python_sdk_options.md 选 SDK 并实现"
        )
