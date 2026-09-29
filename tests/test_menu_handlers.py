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


@pytest.mark.asyncio
async def test_edit_account_label(session_factory, seed_user_and_accounts):
    from handlers.manage_account import handle_edit_label_prompt, handle_save_new_label

    update = MagicMock()
    update.effective_user.id = 101
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    # Step 1: Prompt edit label
    await handle_edit_label_prompt(update, context, account_id=1)
    assert context.user_data["manage_state"] == "awaiting_new_label"
    assert context.user_data["edit_acc_id"] == 1

    # Step 2: User sends new label
    msg_update = MagicMock()
    msg_update.effective_user.id = 101
    msg_update.message.text = "GitHub Work"
    msg_update.message.reply_text = AsyncMock()
    msg_update.message.delete = AsyncMock()

    await handle_save_new_label(msg_update, context)

    msg_update.message.delete.assert_awaited_once()

    # Verify label changed in DB
    async with session_factory() as session:
        acc = await session.get(Account, 1)
        assert acc.label == "GitHub Work"


@pytest.mark.asyncio
async def test_search_accounts(session_factory, seed_user_and_accounts):
    from handlers.menu import handle_search_account_prompt, handle_search_query_message

    update = MagicMock()
    update.effective_user.id = 101
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    # Step 1: Prompt
    await handle_search_account_prompt(update, context)
    assert context.user_data["menu_state"] == "awaiting_search_query"

    # Step 2: Send matching search query
    msg_update = MagicMock()
    msg_update.effective_user.id = 101
    msg_update.message.text = "git"
    msg_update.message.reply_text = AsyncMock()
    msg_update.message.delete = AsyncMock()

    await handle_search_query_message(msg_update, context)

    msg_update.message.delete.assert_awaited_once()
    msg_update.message.reply_text.assert_called_once()
    args, kwargs = msg_update.message.reply_text.call_args
    assert "Hasil pencarian" in args[0]
    kb = kwargs["reply_markup"].inline_keyboard
    labels = [btn.text for row in kb for btn in row]
    assert any("GitHub" in l for l in labels)


@pytest.mark.asyncio
async def test_search_accounts_with_markdown_special_characters(session_factory, seed_user_and_accounts):
    from handlers.menu import handle_search_query_message

    context = MagicMock()
    context.user_data = {"menu_state": "awaiting_search_query"}
    context.bot_data = {"session_factory": session_factory}

    msg_update = MagicMock()
    msg_update.effective_user.id = 101
    msg_update.message.text = "test_user*query[1]"
    msg_update.message.reply_text = AsyncMock()
    msg_update.message.delete = AsyncMock()

    await handle_search_query_message(msg_update, context)
    msg_update.message.reply_text.assert_called_once()
    args, _ = msg_update.message.reply_text.call_args
    # Verify escaped string is used (v1 escapes _, *, `, [)
    assert "test\\_user\\*query\\[1]" in args[0]


@pytest.mark.asyncio
async def test_edit_account_label_validation(session_factory, seed_user_and_accounts):
    from handlers.manage_account import handle_save_new_label

    context = MagicMock()
    context.user_data = {"manage_state": "awaiting_new_label", "edit_acc_id": 1}
    context.bot_data = {"session_factory": session_factory}

    # Label exceeding 64 chars
    msg_update = MagicMock()
    msg_update.effective_user.id = 101
    msg_update.message.text = "A" * 70
    msg_update.message.reply_text = AsyncMock()
    msg_update.message.delete = AsyncMock()

    await handle_save_new_label(msg_update, context)
    msg_update.message.reply_text.assert_called_once()
    args, _ = msg_update.message.reply_text.call_args
    assert "terlalu panjang" in args[0]


def test_main_menu_keyboard_has_view_all_button():
    from handlers.menu import get_main_menu_keyboard

    markup = get_main_menu_keyboard()
    all_callbacks = [
        btn.callback_data for row in markup.inline_keyboard for btn in row
    ]
    assert "menu:view_all_codes" in all_callbacks
    # Verify button text
    view_all_btn = next(
        btn for row in markup.inline_keyboard for btn in row if btn.callback_data == "menu:view_all_codes"
    )
    assert "👁️ Semua Kode" in view_all_btn.text


def test_clear_user_workflow_state_clears_view_all():
    from handlers.menu import clear_user_workflow_state

    user_data = {
        "active_view_all": {"dummy": "data"},
        "view_all_pin": "123",
        "some_other_key": 42,
    }
    clear_user_workflow_state(user_data)
    assert "active_view_all" not in user_data
    assert "view_all_pin" not in user_data
    assert user_data["some_other_key"] == 42


@pytest.mark.asyncio
async def test_view_code_menu_contains_view_all_button(session_factory, seed_user_and_accounts):
    from handlers.view_code import handle_view_code_menu

    user_id = seed_user_and_accounts
    update = MagicMock()
    update.effective_user.id = 101
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_view_code_menu(update, context)

    query.edit_message_text.assert_called_once()
    markup = query.edit_message_text.call_args[1]["reply_markup"]
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert "menu:view_all_codes" in callbacks
    btn = next(btn for row in markup.inline_keyboard for btn in row if btn.callback_data == "menu:view_all_codes")
    assert "👁️ Lihat Semua Kode Sekaligus" in btn.text


