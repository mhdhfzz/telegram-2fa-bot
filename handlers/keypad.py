from typing import Dict, Optional, Tuple
from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def get_pin_length(context: Optional[object] = None) -> int:
    """
    Get the configured PIN length from context.bot_data["settings"]
    or fallback to global settings.
    """
    if context and hasattr(context, "bot_data") and isinstance(context.bot_data, dict):
        settings = context.bot_data.get("settings")
        if settings and hasattr(settings, "pin_length"):
            return int(settings.pin_length)
    try:
        from config import get_settings
        return int(get_settings().pin_length)
    except Exception:
        return 6


def build_keypad_keyboard(action_prefix: str, show_cancel: bool = True) -> InlineKeyboardMarkup:
    """
    Build a standard 3x4 inline keypad with backspace, submit, and optional cancel button.
    """
    keyboard = [
        [
            InlineKeyboardButton("1", callback_data=f"{action_prefix}:key:1"),
            InlineKeyboardButton("2", callback_data=f"{action_prefix}:key:2"),
            InlineKeyboardButton("3", callback_data=f"{action_prefix}:key:3"),
        ],
        [
            InlineKeyboardButton("4", callback_data=f"{action_prefix}:key:4"),
            InlineKeyboardButton("5", callback_data=f"{action_prefix}:key:5"),
            InlineKeyboardButton("6", callback_data=f"{action_prefix}:key:6"),
        ],
        [
            InlineKeyboardButton("7", callback_data=f"{action_prefix}:key:7"),
            InlineKeyboardButton("8", callback_data=f"{action_prefix}:key:8"),
            InlineKeyboardButton("9", callback_data=f"{action_prefix}:key:9"),
        ],
        [
            InlineKeyboardButton("⌫", callback_data=f"{action_prefix}:key:backspace"),
            InlineKeyboardButton("0", callback_data=f"{action_prefix}:key:0"),
            InlineKeyboardButton("✅", callback_data=f"{action_prefix}:key:submit"),
        ],
    ]
    if show_cancel:
        keyboard.append([
            InlineKeyboardButton("❌ Batal", callback_data=f"{action_prefix}:key:cancel")
        ])

    return InlineKeyboardMarkup(keyboard)


def render_pin_display(length: int, max_length: Optional[int] = None) -> str:
    """
    Render masked PIN display (e.g., 'PIN: • • • _ _ _').
    Actual PIN digits are NEVER included.
    If max_length is not specified, uses the configured pin_length.
    """
    if max_length is None or max_length <= 0:
        max_length = max(1, get_pin_length())
    length = max(0, min(length, max_length))
    bullets = ["•"] * length
    underscores = ["_"] * (max_length - length)
    display = " ".join(bullets + underscores)
    return f"PIN: {display}"


def handle_keypad_press(
    user_data: Dict,
    buffer_key: str,
    key_val: str,
    max_length: Optional[int] = None,
) -> Tuple[str, bool, bool]:
    """
    Update memory buffer based on pressed keypad key.
    Returns:
        (current_buffer: str, is_completed: bool, is_cancelled: bool)
    If max_length is not specified, uses the configured pin_length.
    """
    if max_length is None or max_length <= 0:
        max_length = max(1, get_pin_length())
    buffer = user_data.get(buffer_key, "")

    if key_val.isdigit():
        if len(buffer) < max_length:
            buffer += key_val
        is_completed = len(buffer) == max_length
        is_cancelled = False
    elif key_val == "backspace":
        buffer = buffer[:-1]
        is_completed = False
        is_cancelled = False
    elif key_val == "submit":
        is_completed = len(buffer) == max_length
        is_cancelled = False
    elif key_val == "cancel":
        buffer = ""
        is_completed = False
        is_cancelled = True
    else:
        is_completed = False
        is_cancelled = False

    user_data[buffer_key] = buffer
    return buffer, is_completed, is_cancelled


def clear_keypad_buffer(user_data: Dict, buffer_key: str) -> None:
    """Wipe PIN buffer from user session dictionary."""
    user_data.pop(buffer_key, None)
