import os
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# Ensure BOT_TOKEN is present for testing
os.environ.setdefault("BOT_TOKEN", "mock_bot_token_for_tests_123456789")
os.environ.setdefault("DB_PATH", ":memory:")
