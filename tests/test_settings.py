from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from telegram.constants import ParseMode
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

    # Seed 15 logs with view_all_codes and view_all_pin_fail as newest (page 1)
    async with session_factory() as session:
        for i in range(13):
            session.add(AccessLog(user_id=user.id, action=f"action_{i}", success=True))
        session.add(AccessLog(user_id=user.id, action="view_all_codes", success=True))
        session.add(AccessLog(user_id=user.id, action="view_all_pin_fail", success=False))
        await session.commit()

    await handle_view_logs_callback(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args
    assert "Log Akses" in args[0]
    assert "Lihat Semua Kode (✅ Sukses)" in args[0]
    assert "PIN Semua Kode Salah (❌ Gagal)" in args[0]
    assert kwargs.get("parse_mode") == ParseMode.HTML
    kb = kwargs["reply_markup"].inline_keyboard
    texts = [btn.text for row in kb for btn in row]
    # Page 1 of 2 should have Next button
    assert any("Next" in t or "▶️" in t for t in texts)

    # Test malformed page parameter
    query.data = "settings:logs:invalid_page"
    await handle_view_logs_callback(update, context)
    assert query.edit_message_text.call_count == 2


@pytest.mark.asyncio
async def test_view_logs_with_underscores_and_special_chars(session_factory, seed_user_with_secret):
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

    async with session_factory() as session:
        session.add(AccessLog(user_id=user.id, action="miniapp_login", success=True))
        session.add(AccessLog(user_id=user.id, action="miniapp_view_codes", success=True))
        session.add(AccessLog(user_id=user.id, action="custom_unknown_action", success=False))
        session.add(AccessLog(user_id=user.id, action="<dangerous_tag>", success=True))
        await session.commit()

    await handle_view_logs_callback(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args
    rendered_text = args[0]
    assert kwargs.get("parse_mode") == ParseMode.HTML
    assert "Login Mini App (✅ Sukses)" in rendered_text
    assert "Lihat Kode (Mini App) (✅ Sukses)" in rendered_text
    assert "Custom Unknown Action (❌ Gagal)" in rendered_text
    # Verify HTML escaping
    assert "&lt;Dangerous Tag&gt;" in rendered_text
    assert "<dangerous_tag>" not in rendered_text


@pytest.mark.asyncio
async def test_view_logs_telegram_parse_error_fallback(session_factory, seed_user_with_secret):
    user, _ = seed_user_with_secret
    update = MagicMock()
    update.effective_user.id = user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()

    # First call with parse_mode raises entity parsing error, second call (fallback) succeeds
    query.edit_message_text = AsyncMock(side_effect=[Exception("Can't parse entities"), None])
    query.data = "settings:logs:1"
    update.callback_query = query

    context = MagicMock()
    context.bot_data = {"session_factory": session_factory}

    async with session_factory() as session:
        session.add(AccessLog(user_id=user.id, action="miniapp_login", success=True))
        await session.commit()

    await handle_view_logs_callback(update, context)

    assert query.edit_message_text.call_count == 2
    # Fallback call should not specify parse_mode (plain text)
    fallback_kwargs = query.edit_message_text.call_args_list[1][1]
    assert "parse_mode" not in fallback_kwargs


@pytest.mark.asyncio
async def test_import_backup_flow(session_factory, seed_user_with_secret):
    from handlers.settings import (
        handle_import_backup_start,
        handle_import_file_document,
        handle_import_passphrase_message,
        handle_import_pin_keypad,
    )
    from services.backup_service import export_accounts_backup

    user, _ = seed_user_with_secret
    user_id = user.telegram_user_id

    # Create dummy backup payload
    raw_backup = [
        {
            "label": "Imported Slack",
            "issuer": "Slack",
            "secret": "JBSWY3DPEHPK3PXP",
            "type": "totp",
            "digits": 6,
            "period": 30,
        }
    ]
    passphrase = "my_secure_passphrase"
    backup_bytes = export_accounts_backup(raw_backup, passphrase)

    # Step 1: Start import
    update = MagicMock()
    update.effective_user.id = user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_import_backup_start(update, context)
    assert context.user_data["settings_state"] == "awaiting_import_file"

    # Step 2: Upload document
    doc_update = MagicMock()
    doc_update.effective_user.id = user_id
    doc_file = MagicMock()
    doc_file.download_as_bytearray = AsyncMock(return_value=bytearray(backup_bytes))
    doc_update.message.document.get_file = AsyncMock(return_value=doc_file)
    doc_update.message.reply_text = AsyncMock()
    doc_update.message.delete = AsyncMock()

    await handle_import_file_document(doc_update, context)
    doc_update.message.delete.assert_awaited_once()
    assert context.user_data["settings_state"] == "awaiting_import_passphrase"
    assert context.user_data["import_file_bytes"] == backup_bytes

    # Step 3: Send passphrase
    pass_update = MagicMock()
    pass_update.effective_user.id = user_id
    pass_update.message.text = passphrase
    pass_update.message.reply_text = AsyncMock()
    pass_update.message.delete = AsyncMock()

    await handle_import_passphrase_message(pass_update, context)
    pass_update.message.delete.assert_awaited_once()
    assert len(context.user_data["import_accounts_data"]) == 1
    assert context.user_data["import_accounts_data"][0]["label"] == "Imported Slack"

    # Step 4: PIN Keypad confirmation with user PIN "111222"
    keypad_update = MagicMock()
    keypad_update.effective_user.id = user_id
    keypad_query = MagicMock()
    keypad_query.answer = AsyncMock()
    keypad_query.edit_message_text = AsyncMock()
    keypad_update.callback_query = keypad_query

    for digit in "111222":
        keypad_query.data = f"import_pin:key:{digit}"
        await handle_import_pin_keypad(keypad_update, context)

    # Step 5: Verify account is in DB and decryptable with user's PIN
    async with session_factory() as session:
        acc_stmt = select(Account).where(Account.label == "Imported Slack")
        imported_acc = (await session.execute(acc_stmt)).scalars().first()
        assert imported_acc is not None
        assert imported_acc.issuer == "Slack"

        db_user = await session.get(User, user.id)
        key = derive_encryption_key("111222", db_user.kdf_salt)
        decrypted_secret = decrypt_secret(key, imported_acc.secret_encrypted, imported_acc.nonce)
        assert decrypted_secret == "JBSWY3DPEHPK3PXP"


@pytest.mark.asyncio
async def test_handle_confirm_phrase_settings_cancels_job_and_returns_to_settings(session_factory):
    from handlers.settings import handle_confirm_phrase_settings

    query = MagicMock()
    query.answer = AsyncMock()
    query.message.message_id = 888
    query.message.delete = AsyncMock()
    # Message was deleted so edit_message_text fails with Message to edit not found
    query.edit_message_text = AsyncMock(side_effect=Exception("Message to edit not found"))

    update = MagicMock()
    update.callback_query = query
    update.effective_chat.id = 6666
    update.effective_user.id = 12345
    update.message = None

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}
    context.bot.send_message = AsyncMock()

    job = MagicMock()
    context.job_queue.get_jobs_by_name = MagicMock(
        side_effect=lambda name: [job] if "auto_del_phrase_set" in name else []
    )

    await handle_confirm_phrase_settings(update, context)

    query.answer.assert_called()
    query.message.delete.assert_called_once()
    job.schedule_removal.assert_called_once()

    # Falls back to send_message because edit_message_text failed
    context.bot.send_message.assert_called_once()
    call_kwargs = context.bot.send_message.call_args[1]
    assert call_kwargs["chat_id"] == 6666
    assert "Pengaturan & Keamanan" in call_kwargs["text"]


@pytest.mark.asyncio
async def test_import_file_validation_extension_and_size():
    from handlers.settings import handle_import_file_document

    update = MagicMock()
    doc = MagicMock()
    doc.file_name = "backup.txt"
    doc.file_size = 1000
    update.message.document = doc
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"settings_state": "awaiting_import_file"}

    # Test invalid extension
    await handle_import_file_document(update, context)
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "Format file tidak didukung" in args[0]
    assert kwargs.get("reply_markup") is not None

    # Test oversized file (> 5MB)
    update.message.reply_text.reset_mock()
    doc.file_name = "backup.json"
    doc.file_size = 10 * 1024 * 1024  # 10MB
    await handle_import_file_document(update, context)
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "Ukuran file terlalu besar" in args[0]
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_settings_unregistered_and_mismatch_pin_length(session_factory, seed_user_with_secret):
    from handlers.settings import (
        handle_change_pin_start,
        handle_export_backup_start,
        handle_import_backup_start,
    )

    update = MagicMock()
    update.effective_user.id = 9999
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    # Case 1: Change PIN start unregistered
    await handle_change_pin_start(update, context)
    assert "❌ Pengguna tidak terdaftar." in query.edit_message_text.call_args[0][0]

    # Case 2: Export backup start unregistered
    await handle_export_backup_start(update, context)
    assert "❌ Pengguna tidak terdaftar." in query.edit_message_text.call_args[0][0]

    # Case 3: Import backup start unregistered
    await handle_import_backup_start(update, context)
    assert "❌ Pengguna tidak terdaftar." in query.edit_message_text.call_args[0][0]

    # Case 4: PIN confirmation mismatch with 4-digit PIN setting
    user, _ = seed_user_with_secret
    update.effective_user.id = user.telegram_user_id
    context.bot_data["settings"] = MagicMock(pin_length=4)
    context.user_data = {
        "ch_pin_step": "new2",
        "temp_new_pin": "1234",
        "verified_old_pin": "111222",
    }
    # Enter mismatched 4-digit PIN "9999"
    for digit in "9999":
        query.data = f"ch_pin_new2:key:{digit}"
        await handle_change_pin_keypad(update, context)

    call_text = query.edit_message_text.call_args[0][0]
    assert "Konfirmasi PIN baru tidak cocok!" in call_text
    # Verify it displays 4 underscores, not 6
    assert "PIN: _ _ _ _" in call_text


@pytest.mark.asyncio
async def test_export_backup_start_empty_accounts(session_factory):
    from handlers.settings import handle_export_backup_start

    # Create registered user with no accounts
    async with session_factory() as session:
        user = User(
            telegram_user_id=77777,
            pin_hash="dummy_hash",
            pin_hash_salt="dummy_salt",
            kdf_salt="dummy_kdf",
        )
        session.add(user)
        await session.commit()

    update = MagicMock()
    update.effective_user.id = 77777
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_export_backup_start(update, context)

    query.edit_message_text.assert_called_once()
    assert "Belum ada akun tersimpan untuk diekspor" in query.edit_message_text.call_args[0][0]
    # Keypad buffer should not be created
    assert "export_pin" not in context.user_data



