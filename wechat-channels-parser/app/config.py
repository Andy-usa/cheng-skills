"""Application configuration loaded from environment variables."""

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

    # 企业微信基础信息
    wechat_corp_id: str = Field(..., description="企业 ID，ww 开头")
    wechat_kf_secret: str = Field(..., description="微信客服应用 Secret")

    # 回调凭据
    wechat_callback_token: str = Field(..., description="回调 Token")
    wechat_callback_aes_key: str = Field(..., description="EncodingAESKey，43 位")

    # 客服账号
    wechat_open_kfid: str = Field(..., description="客服账号 ID，wk 开头")

    # 运行参数
    log_level: str = "INFO"
    state_file_path: Path = Path("./data/state.json")
    host: str = "0.0.0.0"
    port: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
