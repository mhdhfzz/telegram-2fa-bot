import pytest
from bot import create_application


def test_bot_application_creation():
    app = create_application(bot_token="123456789:ABCDEF_mock_token_for_testing", db_path=":memory:")
    assert app is not None
    assert app.bot is not None

    # Check registered handlers (Command, CallbackQuery, Photo message, Document message, Text message)
    handler_count = sum(len(handlers) for handlers in app.handlers.values())
    assert handler_count == 5


@pytest.mark.asyncio
async def test_global_error_handler_filters_benign_exceptions(mocker):
    from bot import global_error_handler

    logger_mock = mocker.patch("bot.logger.error")
    context = mocker.MagicMock()

    # Benign exception should not log error
    context.error = Exception("Query is already answered")
    await global_error_handler(None, context)
    logger_mock.assert_not_called()

    context.error = Exception("Message can't be deleted")
    await global_error_handler(None, context)
    logger_mock.assert_not_called()

    # Real exception should log error
    context.error = RuntimeError("Database connection timeout")
    await global_error_handler(None, context)
    logger_mock.assert_called_once()


@pytest.mark.asyncio
async def test_text_message_dispatcher_awaiting_qr(mocker):
    from bot import text_message_dispatcher

    update = mocker.MagicMock()
    update.message.reply_text = mocker.AsyncMock()

    context = mocker.MagicMock()
    context.user_data = {"add_state": "awaiting_qr"}

    await text_message_dispatcher(update, context)
    update.message.reply_text.assert_awaited_once()
    args, kwargs = update.message.reply_text.call_args
    assert "Bot sedang menunggu kiriman foto" in args[0]
    assert kwargs.get("reply_markup") is not None

