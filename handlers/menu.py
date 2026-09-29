from typing import Optional
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import get_settings


def get_main_menu_keyboard(mini_app_url: Optional[str] = None) -> InlineKeyboardMarkup:
    raw_url = mini_app_url or get_settings().mini_app_url
    url = ""
    if raw_url:
        val = str(raw_url).strip()
        if val:
            if val.startswith("http://"):
                url = "https://" + val[7:]
            elif not val.startswith("https://"):
                url = f"https://{val}"
            else:
                url = val

    keyboard = []

    # Mini App Button
    if url:
        keyboard.append([
            InlineKeyboardButton("📱 Buka Mini App", web_app=WebAppInfo(url=url)),
        ])
    else:
        keyboard.append([
            InlineKeyboardButton("📱 Mini App Web", callback_data="menu:miniapp_info"),
        ])

    keyboard.extend([
        [
            InlineKeyboardButton("➕ Tambah Akun", callback_data="menu:add_account"),
            InlineKeyboardButton("🔑 Lihat Kode", callback_data="menu:view_code"),
        ],
        [
            InlineKeyboardButton("👁️ Semua Kode", callback_data="menu:view_all_codes"),
            InlineKeyboardButton("🔍 Cari Akun", callback_data="menu:search_account"),
        ],
        [
            InlineKeyboardButton("⭐ Favorit", callback_data="menu:favorite_accounts"),
            InlineKeyboardButton("✏️ Kelola Akun", callback_data="menu:manage_account"),
        ],
        [
            InlineKeyboardButton("⚙️ Pengaturan", callback_data="menu:settings"),
        ],
    ])
    return InlineKeyboardMarkup(keyboard)


def clear_user_workflow_state(user_data: dict) -> None:
    """Clear all pending interactive workflow states and buffers from user_data."""
    if not isinstance(user_data, dict):
        return
    keys_to_clear = [
        "add_state",
        "manual_secret",
        "pending_account",
        "manage_state",
        "edit_acc_id",
        "del_acc_id",
        "menu_state",
        "settings_state",
        "export_auth_pin",
        "import_file_bytes",
        "import_accounts_data",
        "prompt_msg_id",
        "view_account_id",
        "active_view",
        "active_view_all",
        "verified_old_pin",
        "temp_new_pin",
        "ch_pin_step",
    ]
    for key in keys_to_clear:
        user_data.pop(key, None)

    keypad_prefixes = [
        "setup_pin_1",
        "setup_pin_2",
        "add_acc_pin",
        "view_pin",
        "view_all_pin",
        "del_pin",
        "ch_pin_old",
        "ch_pin_new1",
        "ch_pin_new2",
        "export_pin",
        "import_pin",
    ]
    from handlers.keypad import clear_keypad_buffer
    for prefix in keypad_prefixes:
        clear_keypad_buffer(user_data, prefix)


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "🔐 **Telegram 2FA Authenticator**\n\n"
        "Pilih menu di bawah ini untuk melihat kode OTP atau mengelola akun Anda:"
    )
    keyboard = get_main_menu_keyboard()

    active_view = context.user_data.get("active_view")
    if active_view and isinstance(active_view, dict) and update.effective_chat:
        mid = active_view.get("message_id")
        if mid:
            from handlers.view_code import cancel_view_code_jobs
            cancel_view_code_jobs(context, update.effective_chat.id, mid)

    active_view_all = context.user_data.get("active_view_all")
    if active_view_all and isinstance(active_view_all, dict) and update.effective_chat:
        mid = active_view_all.get("message_id")
        if mid:
            from handlers.view_all_codes import cancel_view_all_jobs
            cancel_view_all_jobs(context, update.effective_chat.id, mid)

    clear_user_workflow_state(context.user_data)

    if update.callback_query:
        query = update.callback_query
        try:
            await query.answer()
        except Exception:
            pass

        if query.message and update.effective_chat:
            from handlers.view_code import cancel_view_code_jobs
            cancel_view_code_jobs(context, update.effective_chat.id, query.message.message_id)
            from handlers.view_all_codes import cancel_view_all_jobs
            cancel_view_all_jobs(context, update.effective_chat.id, query.message.message_id)

        try:
            await query.edit_message_text(
                text,
                reply_markup=keyboard,
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception as e:
            if "Message is not modified" in str(e):
                pass
            elif update.effective_chat:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode=ParseMode.MARKDOWN,
                )
    elif update.message:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )


async def handle_search_account_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt user to input search query."""
    query = update.callback_query
    if query:
        await query.answer()

    context.user_data["menu_state"] = "awaiting_search_query"
    text = (
        "🔍 **Cari Akun**\n\n"
        "Ketik kata kunci nama akun atau issuer yang ingin dicari:"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
    ])
    if query:
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            if "Message is not modified" not in str(e):
                pass
        if query.message:
            context.user_data["prompt_msg_id"] = query.message.message_id
    elif update.message:
        sent = await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        if sent and hasattr(sent, "message_id"):
            context.user_data["prompt_msg_id"] = sent.message_id


async def handle_search_query_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process user search query and list matching accounts."""
    if context.user_data.get("menu_state") != "awaiting_search_query":
        return

    search_query = (update.message.text or "").strip()
    context.user_data.pop("menu_state", None)

    # Automatically delete user message with search query
    try:
        await update.message.delete()
    except Exception:
        pass

    # Automatically delete previous prompt message
    old_prompt_id = context.user_data.pop("prompt_msg_id", None)
    if old_prompt_id and update.effective_chat:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=old_prompt_id)
        except Exception:
            pass

    if not search_query:
        cancel_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
        ])
        await update.message.reply_text("Pencarian dibatalkan.", reply_markup=cancel_kb)
        return

    from sqlalchemy import select
    from db.models import Account, User
    from services.icon_service import get_issuer_emoji

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    accounts = []
    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                pattern = f"%{search_query}%"
                acc_stmt = (
                    select(Account)
                    .where(
                        Account.user_id == user.id,
                        (Account.label.ilike(pattern) | Account.issuer.ilike(pattern)),
                    )
                    .order_by(Account.label.asc())
                )
                accounts = list((await session.execute(acc_stmt)).scalars().all())

    from telegram.helpers import escape_markdown
    safe_query = escape_markdown(search_query, version=1)

    if not accounts:
        text = f"🔍 Hasil pencarian untuk '`{safe_query}`':\n\n❌ Tidak ada akun yang cocok."
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Cari Lagi", callback_data="menu:search_account")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
        ])
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        return

    buttons = []
    display_accounts = accounts[:20]
    for acc in display_accounts:
        emoji = get_issuer_emoji(acc.issuer)
        fav = " ⭐" if acc.is_favorite else ""
        buttons.append([InlineKeyboardButton(f"{emoji} {acc.label}{fav}", callback_data=f"view:select:{acc.id}")])

    buttons.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")])
    markup = InlineKeyboardMarkup(buttons)

    limit_note = "\n_(Menampilkan 20 hasil teratas)_" if len(accounts) > 20 else ""
    text = (
        f"🔍 Hasil pencarian untuk '`{safe_query}`' ({len(accounts)} akun):{limit_note}\n"
        "Pilih akun untuk melihat kode OTP:"
    )
    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_miniapp_info(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display Mini App details, server status, and BotFather setup instructions."""
    query = update.callback_query
    if query:
        await query.answer()

    settings = get_settings()
    server_status = "🟢 Aktif" if settings.mini_app_enabled else "🔴 Nonaktif"
    port = settings.mini_app_port
    url = settings.mini_app_url

    url_display = f"`{url}`" if url else "_(Belum diatur di .env / MINI_APP_URL)_"

    text = (
        "📱 **Telegram Mini App (Web App) 2FA**\n\n"
        "Mini App menghadirkan antarmuka web interaktif langsung di dalam Telegram dengan fitur:\n"
        "• ⚡ Countdown timer detik demi detik tanpa lag\n"
        "• 🎨 Logo platform resmi dari **Simple Icons** (simpleicons.org)\n"
        "• 📋 1-tap copy kode OTP ke clipboard\n"
        "• 📷 Scan QR Code langsung lewat kamera Telegram\n"
        "• 🔐 Otentikasi aman terenkripsi PIN Master Anda\n\n"
        "⚙️ **Status Server:**\n"
        f"• Web Server: {server_status} (Port `{port}`)\n"
        f"• Public URL: {url_display}\n\n"
        "💡 **Cara Menghubungkan ke BotFather:**\n"
        "1. Pasang HTTPS (via Nginx SSL, Cloudflare Tunnel, atau ngrok).\n"
        "2. Buka @BotFather -> `/setmenubutton` atau `/newapp`.\n"
        "3. Masukkan URL HTTPS Mini App Anda.\n"
        "4. Tambahkan `MINI_APP_URL=https://domain-anda.com` ke file `.env`.\n\n"
        "_Lihat panduan lengkap di panduan `docs/BOTFATHER_MINI_APP_GUIDE.md`._"
    )

    buttons = []
    if url:
        buttons.append([InlineKeyboardButton("🚀 Buka Mini App", web_app=WebAppInfo(url=url))])
    buttons.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")])

    markup = InlineKeyboardMarkup(buttons)

    if query:
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

