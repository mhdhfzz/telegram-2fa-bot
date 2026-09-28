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

        if query.message and update.effective_chat:
            from handlers.view_code import cancel_view_code_jobs
            cancel_view_code_jobs(context, update.effective_chat.id, query.message.message_id)
            context.user_data.pop("active_view", None)

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
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
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
        await update.message.reply_text("Pencarian dibatalkan.")
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

    if not accounts:
        text = f"🔍 Hasil pencarian untuk '`{search_query}`':\n\n❌ Tidak ada akun yang cocok."
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Cari Lagi", callback_data="menu:search_account")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
        ])
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        return

    buttons = []
    for acc in accounts:
        emoji = get_issuer_emoji(acc.issuer)
        fav = " ⭐" if acc.is_favorite else ""
        buttons.append([InlineKeyboardButton(f"{emoji} {acc.label}{fav}", callback_data=f"view:select:{acc.id}")])

    buttons.append([InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")])
    markup = InlineKeyboardMarkup(buttons)

    text = f"🔍 Hasil pencarian untuk '`{search_query}`' ({len(accounts)} akun):\nPilih akun untuk melihat kode OTP:"
    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
