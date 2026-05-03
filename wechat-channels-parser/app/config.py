"""Application configuration loaded from environment variables.

会话存档路径（msgaudit）所需凭据，详见 docs/msgaudit_setup.md。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 企业微信基础信息（msgaudit 仍然需要 corpid，secret 用专属的「会话存档 Secret」）
    wechat_corp_id: str = Field(..., description="企业 ID，ww 开头")
    wechat_msgaudit_secret: str = Field(..., description="「管理工具 → 聊天内容存档」生成的专用 Secret")

    # 会话存档解密用 RSA 密钥
    rsa_private_key_path: Path = Field(
        ..., description="RSA 私钥 PEM 文件路径；公钥需上传到企业微信后台"
    )

    # 拉取参数
    msgaudit_poll_interval_seconds: int = Field(
        default=10, description="GetChatData 轮询间隔（秒）"
    )
    msgaudit_batch_limit: int = Field(
        default=1000, description="单次 GetChatData 拉取上限（官方最大 1000）"
    )

    # 飞书私信目标（拿到 sphfeed → 转录后通知给谁）
    lark_user_open_id: str = Field(
        default="ou_f0c95a038d620a1cdb7256bb681f149b",
        description="飞书私信收件人 open_id（默认是程万云）",
    )

    # 运行参数
    log_level: str = "INFO"
    state_file_path: Path = Path("./data/state.json")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
