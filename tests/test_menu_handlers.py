from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from crypto.kdf import generate_salt, hash_pin
from db.models import Account, User
from db.session import init_db
from handlers.manage_account import (
    handle_delete_account_pin_keypad,
    handle_list_accounts_to_manage,
    handle_show_account_detail,
    handle_toggle_favorite,
)
from handlers.menu import show_main_menu


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seed_user_and_accounts(session_factory):
    async with session_factory() as session:
        salt = generate_salt()
        pin_hash = hash_pin("123456", salt)
        user = User(
            telegram_user_id=101,
            pin_hash=pin_hash,
            pin_hash_salt=salt,
            kdf_salt=generate_salt(),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        acc1 = Account(
            user_id=user.id,
            label="GitHub",
            issuer="GitHub",
            secret_encrypted=b"dummy_enc1",
            nonce=b"dummy_nonce1",
            is_favorite=False,
        )
        acc2 = Account(
            user_id=user.id,
            label="Google",
            issuer="Google",
            secret_encrypted=b"dummy_enc2",
            nonce=b"dummy_nonce2",
            is_favorite=True,
        )
        session.add_all([acc1, acc2])
        await session.commit()
        return user.id


@pytest.mark.asyncio
async def test_list_accounts_to_manage(session_factory, seed_user_and_accounts):
    update = MagicMock()
    update.effective_user.id = 101
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_list_accounts_to_manage(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args
    assert "Kelola Akun" in args[0]
    kb = kwargs["reply_markup"].inline_keyboard
    # Should list both accounts + Back button
    labels = [btn.text for row in kb for btn in row]
    assert any("GitHub" in l for l in labels)
    assert any("Google" in l for l in labels)


@pytest.mark.asyncio
async def test_toggle_favorite(session_factory, seed_user_and_accounts):
    update = MagicMock()
    update.effective_user.id = 101
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "manage:fav:1"
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    # Toggle account 1 (GitHub) to favorite
    await handle_toggle_favorite(update, context, account_id=1)

    async with session_factory() as session:
        acc = await session.get(Account, 1)
        assert acc.is_favorite is True


@pytest.mark.asyncio
async def test_delete_account_with_pin(session_factory, seed_user_and_accounts):
    user_id = 101
    update = MagicMock()
    update.effective_user.id = user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {"del_acc_id": 2}
    context.bot_data = {"session_factory": session_factory}

    # Enter correct PIN "123456" for deletion
    for digit in "123456":
        query.data = f"del_pin:key:{digit}"
        await handle_delete_account_pin_keypad(update, context)

    # Account 2 should be deleted from DB
    async with session_factory() as session:
        acc = await session.get(Account, 2)
        assert acc is None
