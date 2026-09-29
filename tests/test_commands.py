from unittest.mock import AsyncMock, MagicMock
import pytest
from telegram import Update
from telegram.ext import ContextTypes

from bot import handle_cancel_command, handle_help_command
from handlers.menu import show_main_menu


@pytest.mark.asyncio
async def test_handle_help_command():
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.callback_query = None

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)

    await handle_help_command(update, context)
    update.message.reply_text.assert_called_once()
    args, kwargs = update.message.reply_text.call_args
    assert "Panduan Penggunaan" in args[0]
    assert kwargs.get("reply_markup") is not None


@pytest.mark.asyncio
async def test_handle_cancel_command():
    update = MagicMock(spec=Update)
    update.message = AsyncMock()
    update.callback_query = None

    context = MagicMock(spec=ContextTypes.DEFAULT_TYPE)
    context.user_data = {"add_state": "awaiting_qr", "pending_account": {"label": "Test"}}
    context.bot_data = {}

    await handle_cancel_command(update, context)

    # Workflow state should be cleared
    assert "add_state" not in context.user_data
    assert "pending_account" not in context.user_data
    assert update.message.reply_text.call_count >= 1
    first_call_args = update.message.reply_text.call_args_list[0][0]
    assert "dibatalkan" in first_call_args[0]
