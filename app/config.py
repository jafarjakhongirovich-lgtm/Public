"""Ilova sozlamalari (.env faylidan o'qiladi)."""

from __future__ import annotations

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    secret_key: str = "dev-insecure-secret-key"
    database_url: str = "sqlite:///./tabel.db"
    timezone: str = "Asia/Tashkent"

    bot_token: str = ""
    bot_username: str = ""
    report_chat_id: str = ""

    qr_refresh_seconds: int = 15
    qr_ttl_seconds: int = 25

    admin_username: str = "admin"
    admin_password: str = "change-me"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
