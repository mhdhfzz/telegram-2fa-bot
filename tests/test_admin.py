"""
Unit tests for Admin Dashboard, Command List, and Broadcast feature.
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import pytest_asyncio
from telegram import Update, User as TgUser, Message, CallbackQuery
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from config import get_settings
from db.models import Base, User, Account
from handlers.admin import (
    handle_admin_command,
    handle_stats_command,
    handle_broadcast_start,
    handle_broadcast_content_input,
    handle_broadcast_confirm_callback,
    handle_broadcast_cancel_callback,
    check_admin_access,
)
from handlers.menu import get_main_menu_keyboard


@pytest.fixture
def admin_settings(monkeypatch):
    monkeypatch.setenv("ADMIN_USER_IDS", "999888,111222")
    get_settings.cache_clear()
    settings = get_settings()
    yield settings
    get_settings.cache_clear()


@pytest_asyncio.fixture
async def memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield session_factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_admin_authorization_rejected(admin_settings):
    # User 12345 is not an admin
    update = MagicMock(spec=Update)
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = 12345
    update.effective_user = tg_user
    msg = AsyncMock(spec=Message)
    update.effective_message = msg
    update.callback_query = None

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    assert check_admin_access(update) is False

    await handle_admin_command(update, context)
    msg.reply_text.assert_called_once()
    assert "Akses Ditolak" in msg.reply_text.call_args[0][0]

    # Test callback rejection
    cb_update = MagicMock(spec=Update)
    cb_update.effective_user = tg_user
    cb = AsyncMock(spec=CallbackQuery)
    cb_update.callback_query = cb
    cb_update.effective_message = None

    await handle_stats_command(cb_update, context)
    cb.answer.assert_called_once()
    assert "Khusus Administrator" in cb.answer.call_args[0][0]


@pytest.mark.asyncio
async def test_admin_dashboard_success(admin_settings):
    # User 999888 is an admin
    update = MagicMock(spec=Update)
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = 999888
    update.effective_user = tg_user
    msg = AsyncMock(spec=Message)
    update.effective_message = msg
    update.callback_query = None

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {"admin_state": "some_old_state"}

    assert check_admin_access(update) is True

    await handle_admin_command(update, context)

    # Lingering state should be cleared
    assert "admin_state" not in context.user_data

    msg.reply_text.assert_called_once()
    text = msg.reply_text.call_args[0][0]
    markup = msg.reply_text.call_args[1].get("reply_markup")

    assert "PANEL KONTROL ADMINISTRATOR" in text
    assert "/broadcast" in text
    assert "/stats" in text
    assert "/admin" in text

    # Verify inline keyboard buttons
    buttons_data = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "admin:broadcast_start" in buttons_data
    assert "admin:stats" in buttons_data
    assert "admin:menu" in buttons_data


@pytest.mark.asyncio
async def test_admin_stats_command(admin_settings, memory_db):
    # Populate memory_db with test user and account
    async with memory_db() as session:
        u1 = User(telegram_user_id=101, pin_hash="h1", pin_hash_salt="s1", kdf_salt="k1")
        session.add(u1)
        await session.flush()
        acc = Account(user_id=u1.id, label="Google", secret_encrypted=b"sec", nonce=b"nonce", type="totp")
        session.add(acc)
        await session.commit()

    update = MagicMock(spec=Update)
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = 999888
    update.effective_user = tg_user
    msg = AsyncMock(spec=Message)
    update.effective_message = msg
    update.callback_query = None

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot_data = {"session_factory": memory_db}

    await handle_stats_command(update, context)

    msg.reply_text.assert_called_once()
    text = msg.reply_text.call_args[0][0]

    assert "STATISTIK SISTEM & PENGGUNA BOT" in text
    assert "Total Pengguna Terdaftar: <b>1</b>" in text
    assert "Total Akun 2FA Terenkripsi: <b>1</b>" in text
    # Verify database name is enclosed in <code> tags to prevent parsing errors
    import os
    assert f"<code>{os.path.basename(admin_settings.db_path)}</code>" in text

    # Test callback query flow with BadRequest parse error fallback
    cb_update = MagicMock(spec=Update)
    cb_update.effective_user = tg_user
    cb = AsyncMock(spec=CallbackQuery)
    # First call with parse_mode fails with entity parse error, second call without parse_mode succeeds
    cb.edit_message_text.side_effect = [
        BadRequest("Can't parse entities: can't find end of the entity starting at byte offset 374"),
        AsyncMock(),
    ]
    cb_update.callback_query = cb
    cb_update.effective_message = None

    await handle_stats_command(cb_update, context)
    assert cb.edit_message_text.call_count == 2
    # Second call should not have parse_mode argument
    fallback_kwargs = cb.edit_message_text.call_args_list[1][1]
    assert "parse_mode" not in fallback_kwargs


@pytest.mark.asyncio
async def test_admin_broadcast_flow(admin_settings, memory_db):
    # Insert 3 test users into DB
    async with memory_db() as session:
        session.add(User(telegram_user_id=1001, pin_hash="h1", pin_hash_salt="s1", kdf_salt="k1"))
        session.add(User(telegram_user_id=1002, pin_hash="h2", pin_hash_salt="s2", kdf_salt="k2"))
        session.add(User(telegram_user_id=1003, pin_hash="h3", pin_hash_salt="s3", kdf_salt="k3"))
        await session.commit()

    # Step 1: /broadcast start
    update = MagicMock(spec=Update)
    tg_user = MagicMock(spec=TgUser)
    tg_user.id = 999888
    update.effective_user = tg_user
    msg = AsyncMock(spec=Message)
    update.effective_message = msg
    update.callback_query = None

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot_data = {"session_factory": memory_db}
    context.user_data = {}

    await handle_broadcast_start(update, context)
    assert context.user_data.get("admin_state") == "awaiting_broadcast_content"
    assert "KIRIM PESAN BROADCAST" in msg.reply_text.call_args[0][0]

    # Step 2: Admin sends text message with Telegram HTML format
    msg.reply_text.reset_mock()
    msg.text = "🚨 <b>Pemberitahuan:</b> Server akan restart pada pukul <code>00:00 WIB</code>. Info: <a href='https://example.com'>Klik Di Sini</a>"
    await handle_broadcast_content_input(update, context)

    assert context.user_data.get("broadcast_draft") == msg.text
    preview_call = msg.reply_text.call_args
    assert "PRATINJAU BROADCAST (PREVIEW)" in preview_call[0][0]
    assert "<b>Pemberitahuan:</b>" in preview_call[0][0]
    assert preview_call[1].get("parse_mode") == ParseMode.HTML

    # Step 3: Admin cancels broadcast
    cb_cancel_update = MagicMock(spec=Update)
    cb_cancel_update.effective_user = tg_user
    cb_cancel = AsyncMock(spec=CallbackQuery)
    cb_cancel_update.callback_query = cb_cancel
    cb_cancel_update.effective_message = None

    await handle_broadcast_cancel_callback(cb_cancel_update, context)
    assert "admin_state" not in context.user_data
    assert "broadcast_draft" not in context.user_data
    cb_cancel.edit_message_text.assert_called_once()
    assert "dibatalkan" in cb_cancel.edit_message_text.call_args[0][0]

    # Step 4: Admin confirms broadcast execution with HTML content
    context.user_data["broadcast_draft"] = "🎉 <b>Update v2.0:</b> Fitur Mini App & <i>HTML Broadcast</i> telah aktif!"
    cb_confirm_update = MagicMock(spec=Update)
    cb_confirm_update.effective_user = tg_user
    cb_confirm = AsyncMock(spec=CallbackQuery)
    status_msg = AsyncMock(spec=Message)
    cb_confirm.edit_message_text = AsyncMock(return_value=status_msg)
    cb_confirm_update.callback_query = cb_confirm
    cb_confirm_update.effective_message = None

    # Mock send_message behavior: user 1001 ok, user 1002 blocked (Forbidden), user 1003 BadRequest then ok
    async def mock_send_message(chat_id, text, **kwargs):
        if chat_id == 1002:
            raise Forbidden("Bot was blocked by the user")
        elif chat_id == 1003 and kwargs.get("parse_mode") == ParseMode.HTML:
            raise BadRequest("Can't parse entities")
        return MagicMock()

    context.bot = AsyncMock()
    context.bot.send_message.side_effect = mock_send_message

    with patch("asyncio.sleep", new_callable=AsyncMock):
        await handle_broadcast_confirm_callback(cb_confirm_update, context)

    # State cleared
    assert "admin_state" not in context.user_data
    assert "broadcast_draft" not in context.user_data

    # Report edited on status_msg
    status_msg.edit_text.assert_called_once()
    report_text = status_msg.edit_text.call_args[0][0]

    assert "BROADCAST SELESAI DIKIRIMKAN" in report_text
    assert "Total Target: <b>3</b>" in report_text
    assert "Berhasil Terkirim: <b>2</b>" in report_text
    assert "Diblokir / Akun Nonaktif: <b>1</b>" in report_text


def test_main_menu_admin_button(admin_settings):
    # Non-admin user 555
    kb_user = get_main_menu_keyboard(user_id=555)
    callbacks_user = [btn.callback_data for row in kb_user.inline_keyboard for btn in row if btn.callback_data]
    assert "admin:menu" not in callbacks_user

    # Admin user 999888
    kb_admin = get_main_menu_keyboard(user_id=999888)
    callbacks_admin = [btn.callback_data for row in kb_admin.inline_keyboard for btn in row if btn.callback_data]
    assert "admin:menu" in callbacks_admin
