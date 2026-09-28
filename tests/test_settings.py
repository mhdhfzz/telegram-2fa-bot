from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from crypto.cipher import decrypt_secret, encrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt, hash_pin
from db.models import Account, AccessLog, User
from db.session import init_db
from handlers.settings import (
    handle_change_pin_keypad,
    handle_settings_menu,
    handle_view_logs_callback,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seed_user_with_secret(session_factory):
    async with session_factory() as session:
        old_pin = "111222"
        salt_pin = generate_salt()
        salt_kdf = generate_salt()
        pin_hash = hash_pin(old_pin, salt_pin)

        user = User(
            telegram_user_id=404,
            pin_hash=pin_hash,
            pin_hash_salt=salt_pin,
            kdf_salt=salt_kdf,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        # Encrypt an account with old PIN
        old_key = derive_encryption_key(old_pin, salt_kdf)
        ciphertext, nonce = encrypt_secret(old_key, "SECRET_FOR_USER_404")

        acc = Account(
            user_id=user.id,
            label="Service A",
            issuer="ServiceA",
            secret_encrypted=ciphertext,
            nonce=nonce,
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)

        return user, acc


@pytest.mark.asyncio
async def test_settings_menu_options(session_factory, seed_user_with_secret):
    user, _ = seed_user_with_secret
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    await handle_settings_menu(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args
    assert "Pengaturan" in args[0]
    kb = kwargs["reply_markup"].inline_keyboard
    texts = [btn.text for row in kb for btn in row]
    assert any("Ganti PIN" in t for t in texts)
    assert any("Export" in t for t in texts)
    assert any("Import" in t for t in texts)
    assert any("Log Akses" in t for t in texts)


@pytest.mark.asyncio
async def test_change_pin_re_encrypts_all_accounts(session_factory, seed_user_with_secret):
    user, acc = seed_user_with_secret
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {"ch_pin_step": "old"}
    context.bot_data = {"session_factory": session_factory}
    context.job_queue.run_once = MagicMock()

    # Step 1: Input Old PIN '111222'
    for digit in "111222":
        query.data = f"ch_pin_old:key:{digit}"
        await handle_change_pin_keypad(update, context)

    assert context.user_data.get("ch_pin_step") == "new1"

    # Step 2: Input New PIN '999888'
    for digit in "999888":
        query.data = f"ch_pin_new1:key:{digit}"
        await handle_change_pin_keypad(update, context)

    assert context.user_data.get("ch_pin_step") == "new2"

    # Step 3: Confirm New PIN '999888'
    for digit in "999888":
        query.data = f"ch_pin_new2:key:{digit}"
        await handle_change_pin_keypad(update, context)

    # Verify Account in DB can now ONLY be decrypted with new PIN '999888'
    async with session_factory() as session:
        updated_user = await session.get(User, user.id)
        updated_acc = await session.get(Account, acc.id)

        # Decrypt with new PIN key
        new_key = derive_encryption_key("999888", updated_user.kdf_salt)
        decrypted = decrypt_secret(new_key, updated_acc.secret_encrypted, updated_acc.nonce)
        assert decrypted == "SECRET_FOR_USER_404"

        # Attempting decryption with old PIN key fails
        old_key = derive_encryption_key("111222", updated_user.kdf_salt)
        with pytest.raises(ValueError):
            decrypt_secret(old_key, updated_acc.secret_encrypted, updated_acc.nonce)


@pytest.mark.asyncio
async def test_view_logs_paginated(session_factory, seed_user_with_secret):
    user, _ = seed_user_with_secret
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    query.data = "settings:logs:1"
    update.callback_query = query

    context = MagicMock()
    context.bot_data = {"session_factory": session_factory}

    # Seed 15 logs
    async with session_factory() as session:
        for i in range(15):
            session.add(AccessLog(user_id=user.id, action=f"action_{i}", success=True))
        await session.commit()

    await handle_view_logs_callback(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args
    assert "Log Akses" in args[0]
    kb = kwargs["reply_markup"].inline_keyboard
    texts = [btn.text for row in kb for btn in row]
    # Page 1 of 2 should have Next button
    assert any("Next" in t or "▶️" in t for t in texts)
