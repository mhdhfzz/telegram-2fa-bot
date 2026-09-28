from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes


def get_main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [
            InlineKeyboardButton("➕ Tambah Akun", callback_data="menu:add_account"),
            InlineKeyboardButton("🔑 Lihat Kode", callback_data="menu:view_code"),
        ],
        [
            InlineKeyboardButton("🔍 Cari Akun", callback_data="menu:search_account"),
            InlineKeyboardButton("⭐ Favorit", callback_data="menu:favorite_accounts"),
        ],
        [
            InlineKeyboardButton("✏️ Kelola Akun", callback_data="menu:manage_account"),
            InlineKeyboardButton("⚙️ Pengaturan", callback_data="menu:settings"),
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🔐 **Telegram 2FA Authenticator**\n\n"
        "Pilih menu di bawah ini untuk melihat kode OTP atau mengelola akun Anda:"
    )
    keyboard = get_main_menu_keyboard()

    if update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
        except Exception:
            pass
        await query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
