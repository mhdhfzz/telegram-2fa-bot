import asyncio
import logging
from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import get_settings
from db.session import get_async_engine, get_session_factory, init_db
from handlers.add_account import (
    handle_add_account_menu,
    handle_add_account_pin_keypad,
    handle_choose_manual,
    handle_choose_scan_qr,
    handle_manual_label_input,
    handle_manual_secret_input,
    handle_qr_photo,
)
from handlers.manage_account import (
    handle_delete_account_pin_keypad,
    handle_delete_prompt,
    handle_edit_label_prompt,
    handle_list_accounts_to_manage,
    handle_save_new_label,
    handle_show_account_detail,
    handle_toggle_favorite,
)
from handlers.menu import (
    handle_search_account_prompt,
    handle_search_query_message,
    show_main_menu,
)
from handlers.settings import (
    handle_change_pin_keypad,
    handle_change_pin_start,
    handle_confirm_phrase_settings,
    handle_export_backup_start,
    handle_export_passphrase_message,
    handle_export_pin_keypad,
    handle_import_backup_start,
    handle_import_file_document,
    handle_import_passphrase_message,
    handle_import_pin_keypad,
    handle_settings_menu,
    handle_view_logs_callback,
)
from handlers.start import (
    handle_confirm_phrase,
    handle_setup_pin_keypad,
    handle_start_command,
)
from handlers.view_code import (
    handle_refresh_code,
    handle_select_account_for_code,
    handle_view_code_menu,
    handle_view_code_pin_keypad,
)
from handlers.view_all_codes import (
    handle_view_all_codes_start,
    handle_view_all_page,
    handle_view_all_pin_keypad,
    handle_view_all_refresh,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data

    if data.startswith("setup_pin:") or data.startswith("setup_confirm:"):
        await handle_setup_pin_keypad(update, context)
    elif data == "confirm_phrase":
        await handle_confirm_phrase(update, context)
    elif data == "menu:back_to_main":
        await show_main_menu(update, context)
    elif data == "menu:add_account":
        await handle_add_account_menu(update, context)
    elif data == "menu:view_code":
        await handle_view_code_menu(update, context)
    elif data == "menu:view_all_codes":
        await handle_view_all_codes_start(update, context)
    elif data.startswith("view_all_pin:"):
        await handle_view_all_pin_keypad(update, context)
    elif data.startswith("view_all:page:"):
        try:
            page = int(data.split(":")[2])
        except (IndexError, ValueError):
            return
        await handle_view_all_page(update, context, page)
    elif data == "view_all:refresh":
        await handle_view_all_refresh(update, context)
    elif data == "menu:manage_account":
        await handle_list_accounts_to_manage(update, context)
    elif data == "menu:settings":
        await handle_settings_menu(update, context)
    elif data == "menu:favorite_accounts":
        await handle_view_code_menu(update, context, favorites_only=True)
    elif data == "menu:search_account":
        await handle_search_account_prompt(update, context)
    elif data == "add_acc:scan_qr":
        await handle_choose_scan_qr(update, context)
    elif data == "add_acc:manual":
        await handle_choose_manual(update, context)
    elif data.startswith("add_acc_pin:"):
        await handle_add_account_pin_keypad(update, context)
    elif data.startswith("view:select:"):
        try:
            acc_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return
        await handle_select_account_for_code(update, context, acc_id)
    elif data.startswith("view:refresh:"):
        try:
            acc_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return
        await handle_refresh_code(update, context, acc_id)
    elif data.startswith("view_pin:"):
        await handle_view_code_pin_keypad(update, context)
    elif data == "manage:list":
        await handle_list_accounts_to_manage(update, context)
    elif data.startswith("manage:detail:"):
        try:
            acc_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return
        await handle_show_account_detail(update, context, acc_id)
    elif data.startswith("manage:edit_label:"):
        try:
            acc_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return
        await handle_edit_label_prompt(update, context, acc_id)
    elif data.startswith("manage:fav:"):
        try:
            acc_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return
        await handle_toggle_favorite(update, context, acc_id)
    elif data.startswith("manage:del_prompt:"):
        try:
            acc_id = int(data.split(":")[2])
        except (IndexError, ValueError):
            return
        await handle_delete_prompt(update, context, acc_id)
    elif data.startswith("del_pin:"):
        await handle_delete_account_pin_keypad(update, context)
    elif data == "settings:change_pin":
        await handle_change_pin_start(update, context)
    elif data == "settings:confirm_phrase":
        await handle_confirm_phrase_settings(update, context)
    elif data.startswith("ch_pin_old:") or data.startswith("ch_pin_new1:") or data.startswith("ch_pin_new2:"):
        await handle_change_pin_keypad(update, context)
    elif data == "settings:export":
        await handle_export_backup_start(update, context)
    elif data.startswith("export_pin:"):
        await handle_export_pin_keypad(update, context)
    elif data == "settings:import":
        await handle_import_backup_start(update, context)
    elif data.startswith("import_pin:"):
        await handle_import_pin_keypad(update, context)
    elif data.startswith("settings:logs:"):
        await handle_view_logs_callback(update, context)


async def text_message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    add_state = context.user_data.get("add_state")
    if add_state == "awaiting_manual_secret":
        await handle_manual_secret_input(update, context)
        return
    elif add_state == "awaiting_manual_label":
        await handle_manual_label_input(update, context)
        return
    elif add_state == "awaiting_qr":
        await update.message.reply_text(
            "📷 Bot sedang menunggu kiriman foto / gambar QR Code.\n\n"
            "Jika Anda ingin memasukkan Secret Key secara manual lewat teks, silakan pilih tombol di bawah:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⌨️ Input Manual", callback_data="add_acc:manual")],
                [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
            ]),
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    manage_state = context.user_data.get("manage_state")
    if manage_state == "awaiting_new_label":
        await handle_save_new_label(update, context)
        return

    menu_state = context.user_data.get("menu_state")
    if menu_state == "awaiting_search_query":
        await handle_search_query_message(update, context)
        return

    settings_state = context.user_data.get("settings_state")
    if settings_state == "awaiting_export_passphrase":
        await handle_export_passphrase_message(update, context)
        return
    elif settings_state == "awaiting_import_passphrase":
        await handle_import_passphrase_message(update, context)
        return


async def document_message_dispatcher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings_state = context.user_data.get("settings_state")
    if settings_state == "awaiting_import_file":
        await handle_import_file_document(update, context)
        return

    add_state = context.user_data.get("add_state")
    if add_state == "awaiting_qr":
        await handle_qr_photo(update, context)
        return


async def on_startup(app: Application) -> None:
    engine = app.bot_data.get("engine")
    if engine:
        await init_db(engine)
        logger.info("Database initialized successfully.")


async def on_shutdown(app: Application) -> None:
    engine = app.bot_data.get("engine")
    if engine:
        await engine.dispose()
        logger.info("Database engine disposed cleanly.")


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log errors caused by updates and ignore benign Telegram API exceptions."""
    err = context.error
    if not err:
        return

    err_str = str(err)
    benign_messages = (
        "Message is not modified",
        "Query is too old",
        "Message to edit not found",
        "Query is already answered",
        "Message can't be deleted",
        "Message to delete not found",
    )
    if any(msg in err_str for msg in benign_messages):
        return

    logger.error("Unhandled exception while processing update:", exc_info=err)


def create_application(
    bot_token: Optional[str] = None, db_path: Optional[str] = None
) -> Application:
    settings = get_settings()
    token = bot_token or settings.bot_token
    database_path = db_path or settings.db_path

    engine = get_async_engine(database_path)
    session_factory = get_session_factory(engine)

    app = (
        ApplicationBuilder()
        .token(token)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )
    app.bot_data["engine"] = engine
    app.bot_data["session_factory"] = session_factory
    app.bot_data["settings"] = settings

    app.add_handler(CommandHandler("start", handle_start_command))
    app.add_handler(CallbackQueryHandler(callback_router))
    app.add_handler(MessageHandler(filters.PHOTO, handle_qr_photo))
    app.add_handler(MessageHandler(filters.Document.ALL, document_message_dispatcher))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_dispatcher))
    app.add_error_handler(global_error_handler)

    return app


def main() -> None:
    settings = get_settings()
    logging.getLogger().setLevel(settings.log_level.upper())
    logger.info("Starting Telegram 2FA Authenticator Bot in polling mode...")

    app = create_application()
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
