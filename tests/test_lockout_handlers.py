from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from telegram import Update
from telegram.ext import ContextTypes

from crypto.kdf import generate_salt, hash_pin
from db.models import Account, User
from db.session import init_db
from handlers.add_account import handle_add_account_pin_keypad
from handlers.manage_account import handle_delete_account_pin_keypad, handle_delete_prompt
from handlers.settings import (
    handle_change_pin_keypad,
    handle_change_pin_start,
    handle_export_backup_start,
    handle_export_pin_keypad,
    handle_import_pin_keypad,
)


@pytest_asyncio.fixture
async def setup_locked_env():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    pin_salt = generate_salt()
    kdf_salt = generate_salt()
    pin_hash_val = hash_pin("123456", pin_salt)

    async with session_factory() as session:
        user = User(
            telegram_user_id=999,
            pin_hash=pin_hash_val,
            pin_hash_salt=pin_salt,
            kdf_salt=kdf_salt,
            failed_pin_attempts=5,
            locked_until=datetime.now(timezone.utc) + timedelta(minutes=5),
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        acc = Account(
            user_id=user.id,
            label="Test Acc",
            secret_encrypted=b"cipher",
            nonce=b"nonce",
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        acc_id = acc.id

    yield session_factory, 999, acc_id
    await engine.dispose()


def make_mock_update_and_context(session_factory, user_id, callback_data):
    update = MagicMock(spec=Update)
    query = MagicMock()
    query.data = callback_data
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.message = MagicMock()
    query.message.message_id = 100
    update.callback_query = query
    update.effective_user.id = user_id
    update.effective_chat.id = user_id

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot_data = {"session_factory": session_factory}
    context.user_data = {}
    return update, context


@pytest.mark.asyncio
async def test_add_account_blocks_locked_user(setup_locked_env):
    session_factory, user_id, _ = setup_locked_env
    update, context = make_mock_update_and_context(session_factory, user_id, "add_acc_pin:key:submit")
    context.user_data["add_acc_pin"] = "123456"
    context.user_data["pending_account"] = {"label": "New", "secret": "JBSWY3DPEHPK3PXP"}

    await handle_add_account_pin_keypad(update, context)

    update.callback_query.edit_message_text.assert_called_once()
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text


@pytest.mark.asyncio
async def test_delete_account_blocks_locked_user(setup_locked_env):
    session_factory, user_id, acc_id = setup_locked_env

    # 1. Prompt blocks locked user
    update, context = make_mock_update_and_context(session_factory, user_id, f"manage:del_prompt:{acc_id}")
    await handle_delete_prompt(update, context, acc_id)
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text

    # 2. Keypad submission blocks locked user
    update, context = make_mock_update_and_context(session_factory, user_id, "del_pin:key:submit")
    context.user_data["del_acc_id"] = acc_id
    context.user_data["del_pin"] = "123456"
    await handle_delete_account_pin_keypad(update, context)
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text


@pytest.mark.asyncio
async def test_settings_change_pin_blocks_locked_user(setup_locked_env):
    session_factory, user_id, _ = setup_locked_env

    # 1. Start change pin blocks
    update, context = make_mock_update_and_context(session_factory, user_id, "settings:change_pin")
    await handle_change_pin_start(update, context)
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text

    # 2. Keypad submission blocks
    update, context = make_mock_update_and_context(session_factory, user_id, "ch_pin_old:key:submit")
    context.user_data["ch_pin_old"] = "123456"
    await handle_change_pin_keypad(update, context)
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text


@pytest.mark.asyncio
async def test_settings_export_backup_blocks_locked_user(setup_locked_env):
    session_factory, user_id, _ = setup_locked_env

    # 1. Start export blocks
    update, context = make_mock_update_and_context(session_factory, user_id, "settings:export")
    await handle_export_backup_start(update, context)
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text

    # 2. Keypad export blocks
    update, context = make_mock_update_and_context(session_factory, user_id, "export_pin:key:submit")
    context.user_data["export_pin"] = "123456"
    await handle_export_pin_keypad(update, context)
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text


@pytest.mark.asyncio
async def test_settings_import_backup_blocks_locked_user(setup_locked_env):
    session_factory, user_id, _ = setup_locked_env

    update, context = make_mock_update_and_context(session_factory, user_id, "import_pin:key:submit")
    context.user_data["import_pin"] = "123456"
    context.user_data["import_accounts_data"] = [{"label": "Imported", "secret": "JBSWY3DPEHPK3PXP"}]

    await handle_import_pin_keypad(update, context)
    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci" in call_text
