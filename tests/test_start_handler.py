from unittest.mock import AsyncMock, MagicMock
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from db.models import User
from db.session import init_db
from handlers.start import (
    handle_start_command,
    handle_setup_pin_keypad,
    handle_confirm_phrase,
)


@pytest_asyncio.fixture
async def session_factory():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    await init_db(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.mark.asyncio
async def test_start_new_user_prompts_pin(session_factory):
    update = MagicMock()
    update.effective_user.id = 12345
    update.message.reply_text = AsyncMock()

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    await handle_start_command(update, context)

    # Should ask user to enter PIN
    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    assert "PIN 6 digit" in args[0]
    assert "PIN: _ _ _ _ _ _" in args[0]
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_setup_pin_match_creates_user(session_factory):
    user_id = 999
    update = MagicMock()
    update.effective_user.id = user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}
    context.job_queue.run_once = MagicMock()

    # Step 1: Input 6 digits (e.g. 123456)
    for digit in "123456":
        query.data = f"setup_pin:key:{digit}"
        await handle_setup_pin_keypad(update, context)

    # Should prompt for PIN confirmation
    assert query.edit_message_text.call_count == 6
    last_text = query.edit_message_text.call_args[0][0]
    assert "konfirmasi ulang" in last_text

    # Step 2: Input same 6 digits for confirmation
    for digit in "123456":
        query.data = f"setup_confirm:key:{digit}"
        await handle_setup_pin_keypad(update, context)

    # User should now be saved in DB
    async with session_factory() as session:
        user = await session.get(User, 1)
        assert user is not None
        assert user.telegram_user_id == user_id
        assert user.pin_hash is not None
        assert user.recovery_phrase_hash is not None

    # Job queue should be scheduled for auto-delete
    context.job_queue.run_once.assert_called_once()
    # User data PIN buffers must be wiped clean
    assert "setup_pin_1" not in context.user_data
    assert "setup_pin_2" not in context.user_data


@pytest.mark.asyncio
async def test_setup_pin_mismatch_resets(session_factory):
    user_id = 888
    update = MagicMock()
    update.effective_user.id = user_id
    query = MagicMock()
    query.answer = AsyncMock()
    query.edit_message_text = AsyncMock()
    update.callback_query = query

    context = MagicMock()
    context.user_data = {}
    context.bot_data = {"session_factory": session_factory}

    # Step 1: Enter 123456
    for digit in "123456":
        query.data = f"setup_pin:key:{digit}"
        await handle_setup_pin_keypad(update, context)

    # Step 2: Enter different digits 654321
    for digit in "654321":
        query.data = f"setup_confirm:key:{digit}"
        await handle_setup_pin_keypad(update, context)

    # Should notify mismatch and reset to step 1
    last_text = query.edit_message_text.call_args[0][0]
    assert "tidak cocok" in last_text

    # No user created
    async with session_factory() as session:
        from sqlalchemy import select
        res = await session.execute(select(User).where(User.telegram_user_id == user_id))
        assert res.scalars().first() is None
