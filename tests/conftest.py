import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Ensure test environment defaults
os.environ.setdefault("BOT_TOKEN", "mock_bot_token_for_tests_123456789")
os.environ.setdefault("DB_PATH", ":memory:")
os.environ["PIN_LENGTH"] = "6"


