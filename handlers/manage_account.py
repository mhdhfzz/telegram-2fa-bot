from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from crypto.kdf import verify_pin
from db.models import Account, User
from handlers.keypad import (
    build_keypad_keyboard,
    clear_keypad_buffer,
    get_pin_length,
    handle_keypad_press,
    render_pin_display,
)
from services.icon_service import get_issuer_emoji
from services.lockout_service import record_failed_pin_attempt, record_successful_pin_attempt
from services.log_service import log_action


async def handle_list_accounts_to_manage(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display accounts list to select for management."""
    query = update.callback_query
    if query:
        await query.answer()

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    accounts = []
    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                acc_stmt = (
                    select(Account)
                    .where(Account.user_id == user.id)
                    .order_by(Account.is_favorite.desc(), Account.label.asc())
                )
                accounts = list((await session.execute(acc_stmt)).scalars().all())

    buttons = []
    for acc in accounts:
        emoji = get_issuer_emoji(acc.issuer)
        fav = " ⭐" if acc.is_favorite else ""
        text = f"{emoji} {acc.label}{fav}"
        buttons.append([InlineKeyboardButton(text, callback_data=f"manage:detail:{acc.id}")])

    buttons.append([InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu:back_to_main")])
    markup = InlineKeyboardMarkup(buttons)

    msg_text = "✏️ **Kelola Akun**\n\nPilih akun yang ingin Anda edit, ubah status favorit, atau hapus:"
    if not accounts:
        msg_text = "✏️ **Kelola Akun**\n\nBelum ada akun tersimpan. Gunakan menu *➕ Tambah Akun* untuk menambahkan."

    if query:
        await query.edit_message_text(msg_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(msg_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_show_account_detail(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int
) -> None:
    """Show management options for a single account."""
    query = update.callback_query
    if query:
        await query.answer()

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    account = None
    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                acc_stmt = select(Account).where(Account.id == account_id, Account.user_id == user.id)
                account = (await session.execute(acc_stmt)).scalars().first()

    if not account:
        if query:
            await query.edit_message_text("❌ Akun tidak ditemukan.")
        return

    emoji = get_issuer_emoji(account.issuer)
    fav_status = "⭐ Ya" if account.is_favorite else "Tidak"
    fav_button_text = "☆ Hapus dari Favorit" if account.is_favorite else "⭐ Jadikan Favorit"

    detail_text = (
        f"{emoji} **Detail Akun: {account.label}**\n\n"
        f"• **Issuer**: {account.issuer or '-'}\n"
        f"• **Tipe**: {account.type.upper()}\n"
        f"• **Digits**: {account.digits}\n"
        f"• **Favorit**: {fav_status}\n"
    )

    keyboard = [
        [InlineKeyboardButton("✏️ Ganti Label", callback_data=f"manage:edit_label:{account.id}")],
        [InlineKeyboardButton(fav_button_text, callback_data=f"manage:fav:{account.id}")],
        [InlineKeyboardButton("🗑️ Hapus Akun", callback_data=f"manage:del_prompt:{account.id}")],
        [InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="manage:list")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(detail_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_edit_label_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int
) -> None:
    """Prompt user to send new label for an account."""
    query = update.callback_query
    if query:
        await query.answer()

    context.user_data["manage_state"] = "awaiting_new_label"
    context.user_data["edit_acc_id"] = account_id

    text = (
        "✏️ **Ganti Label Akun**\n\n"
        "Ketik dan kirimkan nama label baru untuk akun ini:"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Batal", callback_data=f"manage:detail:{account_id}")]
    ])
    if query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_save_new_label(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Save new label in DB and confirm to user."""
    if context.user_data.get("manage_state") != "awaiting_new_label":
        return

    new_label = (update.message.text or "").strip()
    account_id = context.user_data.pop("edit_acc_id", None)
    context.user_data.pop("manage_state", None)

    if not new_label or not account_id:
        await update.message.reply_text("Label tidak boleh kosong. Perubahan dibatalkan.")
        return

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                acc_stmt = select(Account).where(Account.id == account_id, Account.user_id == user.id)
                account = (await session.execute(acc_stmt)).scalars().first()
                if account:
                    account.label = new_label
                    await session.commit()
                    await log_action(session, user.id, "manage_account", True, account_id=account.id)
                    success_kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔍 Lihat Detail", callback_data=f"manage:detail:{account_id}")],
                        [InlineKeyboardButton("🔙 Daftar Akun", callback_data="manage:list")],
                    ])
                    await update.message.reply_text(
                        f"✅ Label berhasil diperbarui menjadi: **{new_label}**",
                        reply_markup=success_kb,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return

    await update.message.reply_text("❌ Gagal memperbarui label akun.")


async def handle_toggle_favorite(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int
) -> None:
    """Toggle is_favorite flag on an account."""
    query = update.callback_query
    if query:
        await query.answer()

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                acc_stmt = select(Account).where(Account.id == account_id, Account.user_id == user.id)
                account = (await session.execute(acc_stmt)).scalars().first()
                if account:
                    account.is_favorite = not account.is_favorite
                    await session.commit()
                    await log_action(session, user.id, "manage_account", True, account_id=account.id)

    await handle_show_account_detail(update, context, account_id)


async def handle_delete_prompt(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int
) -> None:
    """Prompt user for PIN before deleting account."""
    query = update.callback_query
    await query.answer()

    context.user_data["del_acc_id"] = account_id
    clear_keypad_buffer(context.user_data, "del_pin")

    pin_len = get_pin_length(context)
    text = (
        "⚠️ **Konfirmasi Hapus Akun**\n\n"
        f"Tindakan ini tidak dapat dibatalkan. Masukkan PIN {pin_len} digit Anda untuk mengonfirmasi:\n\n"
        f"`{render_pin_display(0, max_length=pin_len)}`"
    )
    markup = build_keypad_keyboard("del_pin", show_cancel=True)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_delete_account_pin_keypad(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process keypad entry for account deletion."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    key_val = parts[2]
    pin_len = get_pin_length(context)
    buf, is_complete, is_cancel = handle_keypad_press(
        context.user_data, "del_pin", key_val, max_length=pin_len
    )

    account_id = context.user_data.get("del_acc_id")

    if is_cancel:
        clear_keypad_buffer(context.user_data, "del_pin")
        context.user_data.pop("del_acc_id", None)
        if account_id:
            await handle_show_account_detail(update, context, account_id)
        else:
            await handle_list_accounts_to_manage(update, context)
        return

    if is_complete:
        session_factory = context.bot_data.get("session_factory")
        user_id = update.effective_user.id

        if session_factory:
            async with session_factory() as session:
                user_stmt = select(User).where(User.telegram_user_id == user_id)
                user = (await session.execute(user_stmt)).scalars().first()
                if user:
                    if not verify_pin(buf, user.pin_hash_salt, user.pin_hash):
                        await record_failed_pin_attempt(session, user)
                        await log_action(session, user.id, "delete_account", False, account_id=account_id)
                        clear_keypad_buffer(context.user_data, "del_pin")
                        context.user_data.pop("del_acc_id", None)

                        fail_text = "❌ **PIN Salah!**\nPenghapusan akun dibatalkan demi keamanan."
                        fail_kb = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="manage:list")]
                        ])
                        await query.edit_message_text(fail_text, reply_markup=fail_kb, parse_mode=ParseMode.MARKDOWN)
                        return

                    # Correct PIN
                    await record_successful_pin_attempt(session, user)
                    acc_stmt = select(Account).where(Account.id == account_id, Account.user_id == user.id)
                    account = (await session.execute(acc_stmt)).scalars().first()
                    if account:
                        await session.delete(account)
                        await session.commit()
                        await log_action(session, user.id, "delete_account", True, account_id=None)

        clear_keypad_buffer(context.user_data, "del_pin")
        context.user_data.pop("del_acc_id", None)

        success_text = "🗑️ **Akun Berhasil Dihapus Permanen.**"
        success_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Kembali ke Daftar", callback_data="manage:list")]
        ])
        await query.edit_message_text(success_text, reply_markup=success_kb, parse_mode=ParseMode.MARKDOWN)
    else:
        text = (
            "⚠️ **Konfirmasi Hapus Akun**\n\n"
            f"Masukkan PIN {pin_len} digit Anda untuk mengonfirmasi:\n\n"
            f"`{render_pin_display(len(buf), max_length=pin_len)}`"
        )
        markup = build_keypad_keyboard("del_pin", show_cancel=True)
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
