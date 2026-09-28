import os
import pytest
from config import Settings, get_settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("PIN_LENGTH", raising=False)
    settings = Settings(bot_token="test_token_123")
    assert settings.bot_token == "test_token_123"
    assert settings.db_path == "2fa_bot.db"
    assert settings.log_level == "INFO"
    assert settings.pin_length == 6


def test_custom_settings():
    settings = Settings(
        bot_token="custom_token",
        db_path="custom.db",
        log_level="DEBUG",
        pin_length=4,
    )
    assert settings.bot_token == "custom_token"
    assert settings.db_path == "custom.db"
    assert settings.log_level == "DEBUG"
    assert settings.pin_length == 4


def test_get_settings_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "env_token_xyz")
    monkeypatch.setenv("DB_PATH", "env_test.db")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.bot_token == "env_token_xyz"
    assert settings.db_path == "env_test.db"
