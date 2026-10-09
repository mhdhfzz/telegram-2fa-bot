from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.models import AccessLog, User
from db.session import init_db
from services.maintenance_service import (
    purge_old_access_logs,
    checkpoint_wal,
    trim_memory,
    run_full_maintenance,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_purge_old_access_logs(session_factory):
    async with session_factory() as session:
        user = User(telegram_user_id=999, pin_hash="h", pin_hash_salt="s", kdf_salt="k")
        session.add(user)
        await session.commit()
        await session.refresh(user)

        now = datetime.now(timezone.utc)
        old_time = now - timedelta(days=40)
        recent_time = now - timedelta(days=5)

        log_old = AccessLog(user_id=user.id, action="old_action", success=True, created_at=old_time)
        log_recent = AccessLog(user_id=user.id, action="recent_action", success=True, created_at=recent_time)
        session.add_all([log_old, log_recent])
        await session.commit()

    deleted = await purge_old_access_logs(session_factory, retention_days=30)
    assert deleted == 1

    async with session_factory() as session:
        res = await session.execute(select(AccessLog))
        remaining = res.scalars().all()
        assert len(remaining) == 1
        assert remaining[0].action == "recent_action"


@pytest.mark.asyncio
async def test_purge_old_access_logs_zero_or_negative(session_factory):
    deleted = await purge_old_access_logs(session_factory, retention_days=0)
    assert deleted == 0


@pytest.mark.asyncio
async def test_checkpoint_wal(tmp_path):
    from db.session import get_async_engine
    db_file = tmp_path / "maint_wal.db"
    engine = get_async_engine(str(db_file))
    await init_db(engine)
    # Should execute without error
    await checkpoint_wal(engine)
    await engine.dispose()


def test_trim_memory_runs_safely():
    # Should execute gc.collect and malloc_trim safely on any platform
    trim_memory()


@pytest.mark.asyncio
async def test_run_full_maintenance(session_factory):
    from sqlalchemy.ext.asyncio import create_async_engine
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    mock_runner = MagicMock()
    mock_runner.session_manager = MagicMock()

    res = await run_full_maintenance(
        engine=engine,
        session_factory=session_factory,
        mini_app_runner=mock_runner,
        application=None,
        retention_days=30,
    )
    assert "deleted_logs" in res
    assert "wal_checkpoint" in res
    assert res["wal_checkpoint"] is True
    assert res["sessions_cleaned"] is True
    mock_runner.session_manager.cleanup_expired.assert_called_once()
    await engine.dispose()
