from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from crypto.cipher import decrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt, hash_pin
from db.models import Account, User
from db.session import init_db
from handlers.add_account import (
    handle_add_account_menu,
    handle_add_account_pin_keypad,
    handle_manual_secret_input,
    handle_manual_label_input,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest_asyncio.fixture
async def seed_user(session_factory):
    async with session_factory() as session:
        salt_pin = generate_salt()
        salt_kdf = generate_salt()
        pin_hash = hash_pin("654321", salt_pin)
        user = User(
            telegram_user_id=202,
            pin_hash=pin_hash,
            pin_hash_salt=salt_pin,
            kdf_salt=salt_kdf,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest.mark.asyncio
async def test_add_account_menu(session_factory, seed_user):
    update = MagicMock()
    update.effective_user.id = seed_user.telegram_user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    await handle_add_account_menu(update, context)

    query.edit_message_text.assert_called_once()
    args, kwargs = query.edit_message_text.call_args
    assert "Tambah Akun" in args[0]
    kb = kwargs["reply_markup"].inline_keyboard
    texts = [btn.text for row in kb for btn in row]
    assert any("Scan QR" in t for t in texts)
    assert any("Input Manual" in t for t in texts)


@pytest.mark.asyncio
async def test_manual_input_flow_and_pin_encryption(session_factory, seed_user):
    user_id = seed_user.telegram_user_id
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = "JBSWY3DPEHPK3PXP"
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {"add_state": "awaiting_manual_secret"}
    context.bot_data = {"session_factory": session_factory}

    # Step 1: Input Secret
    await handle_manual_secret_input(update, context)
    assert context.user_data.get("add_state") == "awaiting_manual_label"
    assert context.user_data.get("manual_secret") == "JBSWY3DPEHPK3PXP"

    # Step 2: Input Label
    update.message.text = "GitHub: alice"
    await handle_manual_label_input(update, context)
    assert "pending_account" in context.user_data
    pending = context.user_data["pending_account"]
    assert pending["label"] == "GitHub: alice"
    assert pending["issuer"] == "GitHub"

    # Step 3: Enter correct PIN "654321" via keypad
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    for digit in "654321":
        query.data = f"add_acc_pin:key:{digit}"
        await handle_add_account_pin_keypad(update, context)

    # Verify Account is in DB and correctly encrypted with user's PIN
    async with session_factory() as session:
        acc_stmt = select(Account).where(Account.user_id == seed_user.id)
        account = (await session.execute(acc_stmt)).scalars().first()
        assert account is not None
        assert account.label == "GitHub: alice"

        # Verify decrypted secret matches original
        key = derive_encryption_key("654321", seed_user.kdf_salt)
        decrypted = decrypt_secret(key, account.secret_encrypted, account.nonce)
        assert decrypted == "JBSWY3DPEHPK3PXP"
