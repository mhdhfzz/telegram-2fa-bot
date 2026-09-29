import pytest
from telegram import InlineKeyboardMarkup
from handlers.keypad import (
    build_keypad_keyboard,
    render_pin_display,
    handle_keypad_press,
    clear_keypad_buffer,
    get_pin_length,
)
from unittest.mock import MagicMock
from config import Settings



def test_build_keypad_keyboard():
    markup = build_keypad_keyboard(action_prefix="auth_pin")
    assert isinstance(markup, InlineKeyboardMarkup)
    keyboard = markup.inline_keyboard
    # 5 rows (3x3 numbers + backspace/0/submit + cancel)
    assert len(keyboard) == 5
    # Row 1 has 3 buttons: 1, 2, 3
    assert len(keyboard[0]) == 3
    assert keyboard[0][0].callback_data == "auth_pin:key:1"
    # Row 4 has backspace, 0, submit
    assert keyboard[3][0].callback_data == "auth_pin:key:backspace"
    assert keyboard[3][1].callback_data == "auth_pin:key:0"
    assert keyboard[3][2].callback_data == "auth_pin:key:submit"
    # Row 5 has cancel
    assert keyboard[4][0].callback_data == "auth_pin:key:cancel"


def test_render_pin_display():
    assert render_pin_display(0, max_length=6) == "PIN: _ _ _ _ _ _"
    assert render_pin_display(3, max_length=6) == "PIN: • • • _ _ _"
    assert render_pin_display(6, max_length=6) == "PIN: • • • • • •"
    # max_length <= 0 clamps to get_pin_length()
    assert render_pin_display(0, max_length=0) == "PIN: _ _ _ _ _ _"
    assert render_pin_display(0, max_length=-5) == "PIN: _ _ _ _ _ _"



def test_handle_keypad_press_digits_and_backspace():
    user_data = {}
    buf_key = "test_pin"

    # Enter '1'
    buf, is_complete, is_cancel = handle_keypad_press(user_data, buf_key, "1", max_length=6)
    assert buf == "1"
    assert not is_complete
    assert not is_cancel

    # Enter '2', '3'
    handle_keypad_press(user_data, buf_key, "2", max_length=6)
    buf, _, _ = handle_keypad_press(user_data, buf_key, "3", max_length=6)
    assert buf == "123"

    # Backspace
    buf, _, _ = handle_keypad_press(user_data, buf_key, "backspace", max_length=6)
    assert buf == "12"

    # Complete 6 digits
    handle_keypad_press(user_data, buf_key, "3", max_length=6)
    handle_keypad_press(user_data, buf_key, "4", max_length=6)
    handle_keypad_press(user_data, buf_key, "5", max_length=6)
    buf, is_complete, _ = handle_keypad_press(user_data, buf_key, "6", max_length=6)
    assert buf == "123456"
    assert is_complete is True

    # Pressing extra digit won't exceed max_length
    buf, is_complete, _ = handle_keypad_press(user_data, buf_key, "7", max_length=6)
    assert buf == "123456"
    assert is_complete is True


def test_handle_keypad_press_cancel_and_clear():
    user_data = {}
    buf_key = "test_pin"
    handle_keypad_press(user_data, buf_key, "1", max_length=6)
    buf, is_complete, is_cancel = handle_keypad_press(user_data, buf_key, "cancel", max_length=6)
    assert buf == ""
    assert is_cancel is True

    # Test clear buffer
    user_data[buf_key] = "123456"
    clear_keypad_buffer(user_data, buf_key)
    assert buf_key not in user_data


def test_get_pin_length():
    # From context.bot_data["settings"]
    context = MagicMock()
    context.bot_data = {"settings": Settings(bot_token="test", pin_length=4)}
    assert get_pin_length(context) == 4

    # Fallback to get_settings()
    assert isinstance(get_pin_length(), int)


def test_dynamic_pin_length_4_digits():
    user_data = {}
    buf_key = "test_pin4"

    # Display with max_length=4
    assert render_pin_display(0, max_length=4) == "PIN: _ _ _ _"
    assert render_pin_display(2, max_length=4) == "PIN: • • _ _"
    assert render_pin_display(4, max_length=4) == "PIN: • • • •"

    # Keypad input with 4 digits
    buf, is_complete, _ = handle_keypad_press(user_data, buf_key, "1", max_length=4)
    assert not is_complete
    handle_keypad_press(user_data, buf_key, "2", max_length=4)
    handle_keypad_press(user_data, buf_key, "3", max_length=4)
    buf, is_complete, _ = handle_keypad_press(user_data, buf_key, "4", max_length=4)
    assert buf == "1234"
    assert is_complete is True
