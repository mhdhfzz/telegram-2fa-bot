import os
import pytest
from config import Settings, get_settings


def test_default_settings(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("PIN_LENGTH", raising=False)
    monkeypatch.delenv("AUTO_DELETE_SECONDS", raising=False)
    settings = Settings(_env_file=None, bot_token="test_token_123")
    assert settings.bot_token == "test_token_123"
    assert settings.db_path == "2fa_bot.db"
    assert settings.log_level == "INFO"
    assert settings.pin_length == 6
    assert settings.auto_delete_seconds == 90


def test_custom_settings():
    settings = Settings(
        bot_token="custom_token",
        db_path="custom.db",
        log_level="DEBUG",
        pin_length=4,
        auto_delete_seconds=120,
    )
    assert settings.bot_token == "custom_token"
    assert settings.db_path == "custom.db"
    assert settings.log_level == "DEBUG"
    assert settings.pin_length == 4
    assert settings.auto_delete_seconds == 120


def test_get_settings_reads_env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "env_token_xyz")
    monkeypatch.setenv("DB_PATH", "env_test.db")
    get_settings.cache_clear()
    settings = get_settings()
    assert settings.bot_token == "env_token_xyz"
    assert settings.db_path == "env_test.db"


def test_mini_app_url_normalization():
    # Bare domain without scheme
    s1 = Settings(_env_file=None, bot_token="tok", mini_app_url="bot.example.com")
    assert s1.mini_app_url == "https://bot.example.com"

    # http scheme
    s2 = Settings(_env_file=None, bot_token="tok", mini_app_url="http://mybot.com")
    assert s2.mini_app_url == "https://mybot.com"

    # already https
    s3 = Settings(_env_file=None, bot_token="tok", mini_app_url="https://secure.bot.com")
    assert s3.mini_app_url == "https://secure.bot.com"

    # empty string
    s4 = Settings(_env_file=None, bot_token="tok", mini_app_url="")
    assert s4.mini_app_url == ""

