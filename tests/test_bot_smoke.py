import pytest
from bot import create_application


def test_bot_application_creation():
    app = create_application(bot_token="123456789:ABCDEF_mock_token_for_testing", db_path=":memory:")
    assert app is not None
    assert app.bot is not None

    # Check registered handlers (Command, CallbackQuery, Photo message, Text message)
    handler_count = sum(len(handlers) for handlers in app.handlers.values())
    assert handler_count == 4
