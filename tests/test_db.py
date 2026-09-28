import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.models import Base, User, Account, AccessLog
from db.session import init_db


@pytest_asyncio.fixture
async def async_session():
    # Use in-memory SQLite for async tests
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_create_user(async_session: AsyncSession):
    user = User(
        telegram_user_id=123456789,
        pin_hash="dummy_pin_hash",
        pin_hash_salt="dummy_pin_salt",
        kdf_salt="dummy_kdf_salt",
        recovery_phrase_hash="dummy_phrase_hash",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    assert user.id is not None
    assert user.telegram_user_id == 123456789
    assert user.failed_pin_attempts == 0
    assert user.locked_until is None
    assert user.created_at is not None


@pytest.mark.asyncio
async def test_multi_tenant_isolation(async_session: AsyncSession):
    user1 = User(
        telegram_user_id=11111,
        pin_hash="hash1",
        pin_hash_salt="salt1",
        kdf_salt="kdf1",
    )
    user2 = User(
        telegram_user_id=22222,
        pin_hash="hash2",
        pin_hash_salt="salt2",
        kdf_salt="kdf2",
    )
    async_session.add_all([user1, user2])
    await async_session.commit()

    account1 = Account(
        user_id=user1.id,
        label="GitHub User1",
        issuer="GitHub",
        secret_encrypted=b"secret1",
        nonce=b"nonce1",
    )
    account2 = Account(
        user_id=user2.id,
        label="Google User2",
        issuer="Google",
        secret_encrypted=b"secret2",
        nonce=b"nonce2",
    )
    async_session.add_all([account1, account2])
    await async_session.commit()

    # Querying accounts for user1 should never return account2
    res = await async_session.execute(select(Account).where(Account.user_id == user1.id))
    accounts = res.scalars().all()
    assert len(accounts) == 1
    assert accounts[0].label == "GitHub User1"


@pytest.mark.asyncio
async def test_cascade_delete(async_session: AsyncSession):
    user = User(
        telegram_user_id=99999,
        pin_hash="hash",
        pin_hash_salt="salt",
        kdf_salt="kdf",
    )
    async_session.add(user)
    await async_session.commit()

    account = Account(
        user_id=user.id,
        label="Test Account",
        secret_encrypted=b"enc",
        nonce=b"nonce",
    )
    log = AccessLog(
        user_id=user.id,
        action="add_account",
        success=True,
    )
    async_session.add_all([account, log])
    await async_session.commit()

    # Delete user
    await async_session.delete(user)
    await async_session.commit()

    # Verify accounts and logs are cascade deleted
    acc_res = await async_session.execute(select(Account).where(Account.user_id == user.id))
    assert acc_res.scalars().first() is None

    log_res = await async_session.execute(select(AccessLog).where(AccessLog.user_id == user.id))
    assert log_res.scalars().first() is None
