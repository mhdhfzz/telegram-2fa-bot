import html
import time
from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from telegram.constants import ParseMode

from crypto.cipher import encrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt, hash_pin
from db.models import Account, User
from db.session import init_db
from handlers.view_all_codes import (
    cancel_view_all_jobs,
    handle_view_all_codes_start,
    handle_view_all_page,
    handle_view_all_pin_keypad,
    handle_view_all_refresh,
    render_view_all_page,
    view_all_auto_delete_job,
    view_all_countdown_job,
)


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
        pin = "123456"
        pin_salt = generate_salt()
        kdf_salt = generate_salt()
        pin_hash = hash_pin(pin, pin_salt)

        user = User(
            telegram_user_id=777,
            pin_hash=pin_hash,
            pin_hash_salt=pin_salt,
            kdf_salt=kdf_salt,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        key = derive_encryption_key(pin, kdf_salt)

        accounts = []
        for i in range(1, 15):
            ct, nonce = encrypt_secret(key, "JBSWY3DPEHPK3PXP")
            acc = Account(
                user_id=user.id,
                label=f"Service {i}",
                issuer="GitHub" if i % 2 == 0 else "Google",
                secret_encrypted=ct,
                nonce=nonce,
                type="totp",
                digits=6,
                period=30,
            )
            session.add(acc)
            accounts.append(acc)

        await session.commit()
        return user, accounts


def test_render_view_all_page_single_page():
    accounts = [
        {
            "id": 1,
            "label": "GitHub: alice",
            "issuer": "GitHub",
            "type": "totp",
            "digits": 6,
            "period": 30,
            "secret": "JBSWY3DPEHPK3PXP",
            "emoji": "🐙",
            "hotp_counter": 0,
        },
        {
            "id": 2,
            "label": "Google Work",
            "issuer": "Google",
            "type": "totp",
            "digits": 6,
            "period": 30,
            "secret": "JBSWY3DPEHPK3PXP",
            "emoji": "🌐",
            "hotp_counter": 0,
        },
    ]
    text, markup = render_view_all_page(accounts, page=1, total_pages=1, auto_del_secs=90)
    assert "Semua Kode OTP (Halaman 1/1)" in text
    assert "1. 🐙 <b>GitHub: alice</b>: <code>" in text
    assert "2. 🌐 <b>Google Work</b>: <code>" in text
    assert "Tap kode di atas untuk menyalin ke clipboard." in text
    # No pagination row because total_pages == 1
    buttons = markup.inline_keyboard
    assert len(buttons) == 1
    assert buttons[0][0].text == "🔄 Refresh Semua"
    assert buttons[0][1].text == "🔙 Menu Utama"


def test_render_view_all_page_multi_page_pagination_buttons():
    accounts = [
        {
            "id": i,
            "label": f"Account {i}",
            "issuer": "Test",
            "type": "totp",
            "digits": 6,
            "period": 30,
            "secret": "JBSWY3DPEHPK3PXP",
            "emoji": "🔐",
            "hotp_counter": 0,
        }
        for i in range(1, 11)
    ]
    text, markup = render_view_all_page(accounts, page=1, total_pages=3, auto_del_secs=90)
    assert "Semua Kode OTP (Halaman 1/3)" in text
    buttons = markup.inline_keyboard
    assert len(buttons) == 2
    # Row 1 is pagination
    assert buttons[0][0].callback_data == "view_all:page:1"
    assert buttons[0][1].text == "1 / 3"
    assert buttons[0][2].callback_data == "view_all:page:2"
    # Row 2 is actions
    assert buttons[1][0].text == "🔄 Refresh Semua"
    assert buttons[1][1].text == "🔙 Menu Utama"


@pytest.mark.asyncio
async def test_handle_view_all_codes_start_no_accounts(session_factory):
    async with session_factory() as session:
        user = User(
            telegram_user_id=888,
            pin_hash="hash",
            pin_hash_salt="salt",
            kdf_salt="salt",
        )
        session.add(user)
        await session.commit()

    update = MagicMock()
    update.effective_user.id = 888
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_view_all_codes_start(update, context)

    query.edit_message_text.assert_called_once()
    msg = query.edit_message_text.call_args[0][0]
    assert "Belum ada akun tersimpan" in msg


@pytest.mark.asyncio
async def test_handle_view_all_codes_start_shows_keypad(session_factory, seed_user_and_accounts):
    user, _ = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_view_all_codes_start(update, context)

    query.edit_message_text.assert_called_once()
    msg = query.edit_message_text.call_args[0][0]
    assert "Buka Semua Kode OTP (14 Akun)" in msg
    assert "Masukkan PIN 6 digit" in msg


@pytest.mark.asyncio
async def test_handle_view_all_pin_wrong_pin(session_factory, seed_user_and_accounts):
    user, _ = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    # Input 5 digits first
    for digit in "00000":
        query.data = f"view_all_pin:press:{digit}"
        await handle_view_all_pin_keypad(update, context)

    # 6th digit wrong
    query.data = "view_all_pin:press:0"
    await handle_view_all_pin_keypad(update, context)

    query.edit_message_text.assert_called()
    last_msg = query.edit_message_text.call_args[0][0]
    assert "PIN Salah!" in last_msg


@pytest.mark.asyncio
async def test_handle_view_all_pin_correct_renders_and_schedules_jobs(
    session_factory, seed_user_and_accounts
):
    user, accounts = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    update.effective_chat.id = 12345
    query = MagicMock()
    query.message.message_id = 99
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    job_queue = MagicMock()
    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}
    context.job_queue = job_queue

    # Enter correct PIN: 123456
    for digit in "12345":
        query.data = f"view_all_pin:press:{digit}"
        await handle_view_all_pin_keypad(update, context)

    query.data = "view_all_pin:press:6"
    await handle_view_all_pin_keypad(update, context)

    # Active view all session should be set in user_data
    assert "active_view_all" in context.user_data
    session_data = context.user_data["active_view_all"]
    assert len(session_data["accounts"]) == 14
    assert session_data["page"] == 1
    assert session_data["total_pages"] == 2

    # Verify query.edit_message_text was called with HTML formatted page
    query.edit_message_text.assert_called()
    last_call = query.edit_message_text.call_args
    assert "Semua Kode OTP (Halaman 1/2)" in last_call[0][0]
    assert last_call[1]["parse_mode"] == ParseMode.HTML

    # Verify job_queue jobs scheduled: run_once (auto delete) & run_repeating (countdown)
    job_queue.run_once.assert_called_once()
    job_queue.run_repeating.assert_called_once()


@pytest.mark.asyncio
async def test_handle_view_all_page_switching(session_factory, seed_user_and_accounts):
    user, _ = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {
        "active_view_all": {
            "accounts": [{"label": f"Acc {i}", "secret": "JBSWY3DPEHPK3PXP", "type": "totp", "digits": 6, "period": 30} for i in range(1, 16)],
            "page": 1,
            "total_pages": 2,
            "expires_at": time.time() + 60,
        }
    }

    # Switch to Page 2
    await handle_view_all_page(update, context, page=2)

    assert context.user_data["active_view_all"]["page"] == 2
    query.edit_message_text.assert_called_once()
    msg = query.edit_message_text.call_args[0][0]
    assert "Semua Kode OTP (Halaman 2/2)" in msg
    assert "11. 🔐 <b>Acc 11</b>:" in msg


@pytest.mark.asyncio
async def test_handle_view_all_refresh(session_factory, seed_user_and_accounts):
    user, _ = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {
        "active_view_all": {
            "accounts": [{"label": "Acc 1", "secret": "JBSWY3DPEHPK3PXP", "type": "totp", "digits": 6, "period": 30}],
            "page": 1,
            "total_pages": 1,
            "expires_at": time.time() + 60,
        }
    }

    await handle_view_all_refresh(update, context)

    query.edit_message_text.assert_called_once()
    query.answer.assert_called_with("🔄 Semua kode OTP diperbarui!")


@pytest.mark.asyncio
async def test_view_all_jobs_execution():
    bot = MagicMock()
    bot.edit_message_text = AsyncMock()
    bot.delete_message = AsyncMock()
    bot.send_message = AsyncMock()

    context = MagicMock()
    context.bot = bot
    context.user_data = {
        "active_view_all": {
            "accounts": [{"label": "Acc 1", "secret": "JBSWY3DPEHPK3PXP", "type": "totp", "digits": 6, "period": 30}],
            "page": 1,
            "total_pages": 1,
            "expires_at": time.time() + 60,
        }
    }
    context.bot_data = {}

    # Test Countdown Job
    job = MagicMock()
    job.data = {"chat_id": 111, "message_id": 222, "user_id": 333}
    context.job = job

    await view_all_countdown_job(context)
    bot.edit_message_text.assert_called_once()
    assert bot.edit_message_text.call_args[1]["chat_id"] == 111
    assert bot.edit_message_text.call_args[1]["message_id"] == 222

    # Test Auto-Delete Job
    del_job = MagicMock()
    del_job.chat_id = 111
    del_job.data = 222
    del_job.user_id = 333
    context.job = del_job

    await view_all_auto_delete_job(context)
    bot.delete_message.assert_called_once_with(chat_id=111, message_id=222)
    assert "active_view_all" not in context.user_data
    bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_bot_callback_router_routes_view_all_actions(monkeypatch):
    from bot import callback_router

    mock_start = AsyncMock()
    mock_keypad = AsyncMock()
    mock_page = AsyncMock()
    mock_refresh = AsyncMock()

    monkeypatch.setattr("bot.handle_view_all_codes_start", mock_start)
    monkeypatch.setattr("bot.handle_view_all_pin_keypad", mock_keypad)
    monkeypatch.setattr("bot.handle_view_all_page", mock_page)
    monkeypatch.setattr("bot.handle_view_all_refresh", mock_refresh)

    update = MagicMock()
    context = MagicMock()

    # Route 1: menu:view_all_codes
    update.callback_query.data = "menu:view_all_codes"
    await callback_router(update, context)
    mock_start.assert_awaited_once_with(update, context)

    # Route 2: view_all_pin:press:5
    update.callback_query.data = "view_all_pin:press:5"
    await callback_router(update, context)
    mock_keypad.assert_awaited_once_with(update, context)

    # Route 3: view_all:page:2
    update.callback_query.data = "view_all:page:2"
    await callback_router(update, context)
    mock_page.assert_awaited_once_with(update, context, 2)

    # Route 4: view_all:refresh
    update.callback_query.data = "view_all:refresh"
    await callback_router(update, context)
    mock_refresh.assert_awaited_once_with(update, context)


@pytest.mark.asyncio
async def test_view_all_lockout_prevents_access(session_factory, seed_user_and_accounts):
    import datetime
    user, _ = seed_user_and_accounts

    # Set user as locked out
    async with session_factory() as session:
        from db.models import User
        u = await session.get(User, user.id)
        u.failed_pin_attempts = 5
        u.locked_until = datetime.datetime.utcnow() + datetime.timedelta(minutes=5)
        await session.commit()

    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_view_all_codes_start(update, context)

    query.edit_message_text.assert_called_once()
    msg = query.edit_message_text.call_args[0][0]
    assert "Akun Terkunci!" in msg


@pytest.mark.asyncio
async def test_view_all_cancel_keypad_returns_to_main_menu(session_factory, seed_user_and_accounts):
    user, _ = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "view_all_pin:press:cancel"
    update.callback_query = query

    context = MagicMock()
    context.user_data = {"view_all_pin": "123"}
    context.bot_data = {"session_factory": session_factory}

    await handle_view_all_pin_keypad(update, context)

    assert "view_all_pin" not in context.user_data
    # Main menu was edited into the message
    query.edit_message_text.assert_called_once()
    assert "Telegram 2FA Authenticator" in query.edit_message_text.call_args[0][0]


@pytest.mark.asyncio
async def test_view_all_session_expired_redirects_to_pin(session_factory, seed_user_and_accounts):
    user, _ = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    # Expired session (expires_at in past)
    context.user_data = {
        "active_view_all": {
            "accounts": [],
            "page": 1,
            "total_pages": 1,
            "expires_at": time.time() - 10,
        }
    }
    context.bot_data = {"session_factory": session_factory}

    # Test page switch on expired session
    await handle_view_all_page(update, context, page=2)
    query.answer.assert_any_call("⏱️ Sesi telah berakhir. Masukkan PIN kembali.", show_alert=True)
    # Re-prompted for PIN
    assert "Buka Semua Kode OTP" in query.edit_message_text.call_args[0][0]

    # Test refresh on expired session
    query.reset_mock()
    await handle_view_all_refresh(update, context)
    query.answer.assert_any_call("⏱️ Sesi telah berakhir. Masukkan PIN kembali.", show_alert=True)
    assert "Buka Semua Kode OTP" in query.edit_message_text.call_args[0][0]


@pytest.mark.asyncio
async def test_view_all_page_clamping(session_factory, seed_user_and_accounts):
    user, _ = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {
        "active_view_all": {
            "accounts": [{"label": f"Acc {i}", "secret": "JBSWY3DPEHPK3PXP", "type": "totp", "digits": 6, "period": 30} for i in range(1, 15)],
            "page": 1,
            "total_pages": 2,
            "expires_at": time.time() + 60,
        }
    }

    # Request Page 99 -> Clamped to 2
    await handle_view_all_page(update, context, page=99)
    assert context.user_data["active_view_all"]["page"] == 2
    assert "Halaman 2/2" in query.edit_message_text.call_args[0][0]

    # Request Page -5 -> Clamped to 1
    await handle_view_all_page(update, context, page=-5)
    assert context.user_data["active_view_all"]["page"] == 1
    assert "Halaman 1/2" in query.edit_message_text.call_args[0][0]


