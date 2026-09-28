from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from crypto.cipher import encrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt, hash_pin
from db.models import Account, User
from db.session import init_db
from handlers.view_code import (
    handle_select_account_for_code,
    handle_view_code_menu,
    handle_view_code_pin_keypad,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seed_user_and_totp_account(session_factory):
    async with session_factory() as session:
        pin = "112233"
        pin_salt = generate_salt()
        kdf_salt = generate_salt()
        pin_hash = hash_pin(pin, pin_salt)

        user = User(
            telegram_user_id=303,
            pin_hash=pin_hash,
            pin_hash_salt=pin_salt,
            kdf_salt=kdf_salt,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Encrypt secret 'JBSWY3DPEHPK3PXP'
        key = derive_encryption_key(pin, kdf_salt)
        ciphertext, nonce = encrypt_secret(key, "JBSWY3DPEHPK3PXP")

        acc = Account(
            user_id=user.id,
            label="GitHub Test",
            issuer="GitHub",
            secret_encrypted=ciphertext,
            nonce=nonce,
            type="totp",
            digits=6,
            period=30,
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return user, acc


@pytest.mark.asyncio
async def test_view_code_menu_lists_accounts(session_factory, seed_user_and_totp_account):
    user, acc = seed_user_and_totp_account
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_view_code_menu(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args
    assert "Lihat Kode OTP" in args[0]
    kb = kwargs["reply_markup"].inline_keyboard
    texts = [btn.text for row in kb for btn in row]
    assert any("GitHub Test" in t for t in texts)


@pytest.mark.asyncio
async def test_view_code_correct_pin_displays_monospace_otp(
    session_factory, seed_user_and_totp_account
):
    user, acc = seed_user_and_totp_account
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {"view_account_id": acc.id}
    context.bot_data = {"session_factory": session_factory}
    context.job_queue.run_once = MagicMock()
    context.job_queue.run_repeating = MagicMock()

    # Enter correct PIN '112233'
    for digit in "112233":
        query.data = f"view_pin:key:{digit}"
        await handle_view_code_pin_keypad(update, context)

    # Monospace OTP code without space inside <code>...</code>
    last_text = query.edit_message_text.call_args[0][0]
    assert "<code>" in last_text
    assert "</code>" in last_text

    # Extract code between tags
    start = last_text.find("<code>") + 6
    end = last_text.find("</code>")
    otp_code = last_text[start:end]
    assert len(otp_code) == 6
    assert otp_code.isdigit()
    assert " " not in otp_code

    # Progress bar and auto-delete job
    assert "⏳" in last_text
    context.job_queue.run_once.assert_called_once()
    context.job_queue.run_repeating.assert_called_once()


@pytest.mark.asyncio
async def test_view_code_html_escaping_and_countdown_job(session_factory):
    from handlers.view_code import view_code_countdown_job

    job = MagicMock()
    job.data = {
        "chat_id": 999,
        "message_id": 888,
        "period": 30,
        "label": "<User & Team>",
        "emoji": "🔐",
        "code_html": "<code>123456</code>",
        "account_id": 1,
    }
    job.schedule_removal = MagicMock()

    context = MagicMock()
    context.job = job
    context.bot.edit_message_text = AsyncMock()

    await view_code_countdown_job(context)

    context.bot.edit_message_text.assert_called_once()
    edited_text = context.bot.edit_message_text.call_args[1]["text"]
    # Verify HTML escaping
    assert "&lt;User &amp; Team&gt;" in edited_text
    assert "<User & Team>" not in edited_text
    assert "<code>123456</code>" in edited_text


@pytest.mark.asyncio
async def test_view_code_countdown_job_generates_dynamic_otp():
    from handlers.view_code import view_code_countdown_job

    job = MagicMock()
    job.data = {
        "chat_id": 999,
        "message_id": 888,
        "secret": "JBSWY3DPEHPK3PXP",
        "period": 30,
        "digits": 6,
        "label": "Google",
        "emoji": "🔍",
        "account_id": 1,
    }
    job.schedule_removal = MagicMock()

    context = MagicMock()
    context.job = job
    context.bot.edit_message_text = AsyncMock()

    await view_code_countdown_job(context)

    context.bot.edit_message_text.assert_called_once()
    call_kwargs = context.bot.edit_message_text.call_args[1]
    edited_text = call_kwargs["text"]
    reply_markup = call_kwargs["reply_markup"]

    # Verify code was dynamically generated and wrapped in code tag
    assert "<code>" in edited_text
    assert "</code>" in edited_text
    # Verify Refresh button routes to view:refresh:1
    refresh_button = reply_markup.inline_keyboard[0][0]
    assert refresh_button.callback_data == "view:refresh:1"


@pytest.mark.asyncio
async def test_handle_refresh_code_active_session():
    import time
    from handlers.view_code import handle_refresh_code

    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update = MagicMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {
        "active_view": {
            "account_id": 1,
            "secret": "JBSWY3DPEHPK3PXP",
            "type": "totp",
            "period": 30,
            "digits": 6,
            "label": "GitHub",
            "emoji": "🐙",
            "expires_at": time.time() + 90,
        }
    }

    await handle_refresh_code(update, context, 1)

    # Should update the message directly without asking for PIN
    query.edit_message_text.assert_called_once()
    edited_text = query.edit_message_text.call_args[0][0]
    assert "<code>" in edited_text
    assert "🐙" in edited_text
    assert "GitHub" in edited_text
    query.answer.assert_called()


@pytest.mark.asyncio
async def test_cancel_view_code_jobs():
    from handlers.view_code import cancel_view_code_jobs

    countdown_job = MagicMock()
    autodel_job = MagicMock()

    context = MagicMock()
    context.job_queue.get_jobs_by_name = MagicMock(
        side_effect=lambda name: [countdown_job] if "countdown" in name else [autodel_job]
    )

    cancel_view_code_jobs(context, 123, 456)

    countdown_job.schedule_removal.assert_called_once()
    autodel_job.schedule_removal.assert_called_once()

