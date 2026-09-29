from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    db_path: str = "2fa_bot.db"
    log_level: str = "INFO"
    pin_length: int = 6
    auto_delete_seconds: int = 90
    mini_app_enabled: bool = True
    mini_app_host: str = "0.0.0.0"
    mini_app_port: int = 8080
    mini_app_url: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache()
def get_settings() -> Settings:
    return Settings()
