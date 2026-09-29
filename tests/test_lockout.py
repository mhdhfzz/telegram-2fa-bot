from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.models import User
from db.session import init_db
from services.lockout_service import (
    check_lockout,
    record_failed_pin_attempt,
    record_successful_pin_attempt,
)
from services.log_service import log_action, get_user_logs


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_lockout_escalation(session: AsyncSession):
    user = User(
        telegram_user_id=123,
        pin_hash="hash",
        pin_hash_salt="salt",
        kdf_salt="kdf",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Initial state
    is_locked, remaining = check_lockout(user)
    assert not is_locked
    assert remaining == 0

    # Attempts 1 to 4: not locked yet
    for attempt in range(1, 5):
        is_locked, rem = await record_failed_pin_attempt(session, user)
        assert not is_locked
        assert user.failed_pin_attempts == attempt

    # Attempt 5: triggers 5-minute lockout
    is_locked, rem = await record_failed_pin_attempt(session, user)
    assert is_locked
    assert 280 <= rem <= 300  # ~300 seconds (5 min)
    assert user.failed_pin_attempts == 5

    # Simulate lockout expired: set locked_until to past
    user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=10)
    await session.commit()
    is_locked, rem = check_lockout(user)
    assert not is_locked

    # Next failure: escalates to 15 minutes (900 seconds)
    is_locked, rem = await record_failed_pin_attempt(session, user)
    assert is_locked
    assert 880 <= rem <= 900
    assert user.failed_pin_attempts == 6

    # Next failure after expiration: escalates to 60 minutes (3600 seconds)
    user.locked_until = datetime.now(timezone.utc) - timedelta(seconds=10)
    await session.commit()
    is_locked, rem = await record_failed_pin_attempt(session, user)
    assert is_locked
    assert 3580 <= rem <= 3600
    assert user.failed_pin_attempts == 7

    # Correct PIN resets counter and lock
    await record_successful_pin_attempt(session, user)
    assert user.failed_pin_attempts == 0
    assert user.locked_until is None
    is_locked, rem = check_lockout(user)
    assert not is_locked


@pytest.mark.asyncio
async def test_audit_logging_and_pagination(session: AsyncSession):
    user = User(
        telegram_user_id=456,
        pin_hash="hash",
        pin_hash_salt="salt",
        kdf_salt="kdf",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)

    # Add 25 log entries
    for i in range(25):
        await log_action(session, user.id, f"action_{i}", success=(i % 2 == 0))

    # Page 1 (10 entries)
    logs_p1, total_pages = await get_user_logs(session, user.id, page=1, page_size=10)
    assert len(logs_p1) == 10
    assert total_pages == 3
    # Most recent first
    assert logs_p1[0].action == "action_24"

    # Page 3 (5 entries)
    logs_p3, total_pages = await get_user_logs(session, user.id, page=3, page_size=10)
    assert len(logs_p3) == 5
    assert logs_p3[-1].action == "action_0"

    # Test edge cases: page_size=0 and negative numbers shouldn't raise ZeroDivisionError
    logs_zero, total_pages_zero = await get_user_logs(session, user.id, page=0, page_size=0)
    assert len(logs_zero) == 10
    assert total_pages_zero == 3

    # Out of bounds page clamped to total_pages
    logs_oob, total_pages_oob = await get_user_logs(session, user.id, page=999, page_size=-5)
    assert len(logs_oob) == 5
    assert total_pages_oob == 3

