from typing import Optional
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from crypto.cipher import decrypt_secret
from crypto.kdf import derive_encryption_key, verify_pin
from db.models import Account, User
from handlers.keypad import (
    build_keypad_keyboard,
    clear_keypad_buffer,
    handle_keypad_press,
    render_pin_display,
)
from services.icon_service import get_issuer_emoji
from services.lockout_service import (
    check_lockout,
    record_failed_pin_attempt,
    record_successful_pin_attempt,
)
from services.log_service import log_action
from services.otp_service import (
    format_otp_display,
    generate_hotp_code,
    generate_totp_code,
    get_totp_remaining_seconds,
    render_countdown_bar,
)


async def view_code_auto_delete_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete OTP message after 30 seconds lifetime."""
    try:
        chat_id = context.job.chat_id
        message_id = context.job.data
        if chat_id and message_id:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def handle_view_code_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display list of accounts to generate OTP code."""
    query = update.callback_query
    if query:
        await query.answer()

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    accounts = []
    user = None
    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                is_locked, remaining_seconds = check_lockout(user)
                if is_locked:
                    mins, secs = divmod(remaining_seconds, 60)
                    locked_text = (
                        "🔒 **Fitur Terkunci Sementara**\n\n"
                        f"Terlalu banyak percobaan PIN salah. Silakan coba kembali dalam "
                        f"**{mins} menit {secs} detik**."
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                    ])
                    if query:
                        await query.edit_message_text(locked_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                    elif update.message:
                        await update.message.reply_text(locked_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                    return

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
        buttons.append([InlineKeyboardButton(text, callback_data=f"view:select:{acc.id}")])

    if len(accounts) > 8:
        buttons.insert(0, [InlineKeyboardButton("🔍 Cari Akun", callback_data="menu:search_account")])

    buttons.append([InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu:back_to_main")])
    markup = InlineKeyboardMarkup(buttons)

    msg_text = "🔑 **Lihat Kode OTP**\n\nPilih akun untuk melihat kode autentikasi:"
    if not accounts:
        msg_text = "🔑 **Lihat Kode OTP**\n\nBelum ada akun tersimpan. Gunakan menu *➕ Tambah Akun* terlebih dahulu."

    if query:
        await query.edit_message_text(msg_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(msg_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_select_account_for_code(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int
) -> None:
    """Prompt user for PIN before decrypting and showing code."""
    query = update.callback_query
    if query:
        await query.answer()

    context.user_data["view_account_id"] = account_id
    clear_keypad_buffer(context.user_data, "view_pin")

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    account_label = "Akun"
    if session_factory:
        async with session_factory() as session:
            stmt = select(Account).where(Account.id == account_id)
            acc = (await session.execute(stmt)).scalars().first()
            if acc:
                account_label = acc.label

    text = (
        f"🔑 **Buka Kode: {account_label}**\n\n"
        "Masukkan PIN 6 digit Anda:\n\n"
        f"`{render_pin_display(0)}`"
    )
    markup = build_keypad_keyboard("view_pin", show_cancel=True)

    if query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_view_code_pin_keypad(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process keypad entry for viewing OTP code."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    key_val = parts[2]
    buf, is_complete, is_cancel = handle_keypad_press(
        context.user_data, "view_pin", key_val, max_length=6
    )

    account_id = context.user_data.get("view_account_id")

    if is_cancel:
        clear_keypad_buffer(context.user_data, "view_pin")
        context.user_data.pop("view_account_id", None)
        await handle_view_code_menu(update, context)
        return

    if is_complete:
        session_factory = context.bot_data.get("session_factory")
        user_id = update.effective_user.id

        if not session_factory:
            await query.edit_message_text("❌ Database tidak tersedia.")
            return

        async with session_factory() as session:
            user_stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(user_stmt)).scalars().first()
            if not user:
                await query.edit_message_text("❌ User tidak terdaftar.")
                return

            # Check lockout
            is_locked, remaining_seconds = check_lockout(user)
            if is_locked:
                mins, secs = divmod(remaining_seconds, 60)
                await query.edit_message_text(
                    f"🔒 **Akun Terkunci!** Coba lagi dalam {mins}m {secs}s.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                    ]),
                )
                clear_keypad_buffer(context.user_data, "view_pin")
                return

            if not verify_pin(buf, user.pin_hash_salt, user.pin_hash):
                locked_now, rem = await record_failed_pin_attempt(session, user)
                await log_action(session, user.id, "pin_fail", False, account_id=account_id)
                clear_keypad_buffer(context.user_data, "view_pin")

                if locked_now:
                    mins, secs = divmod(rem, 60)
                    fail_msg = f"🔒 **Akun Terkunci!** Terlalu banyak percobaan PIN salah. Coba lagi dalam {mins}m {secs}s."
                else:
                    attempts_left = max(0, 5 - user.failed_pin_attempts)
                    fail_msg = f"❌ **PIN Salah!** Sisa percobaan sebelum terkunci: {attempts_left} kali."

                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data=f"view:select:{account_id}")],
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
                ])
                await query.edit_message_text(fail_msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                return

            # PIN correct: Reset lockout
            await record_successful_pin_attempt(session, user)

            acc_stmt = select(Account).where(Account.id == account_id, Account.user_id == user.id)
            account = (await session.execute(acc_stmt)).scalars().first()
            if not account:
                await query.edit_message_text("❌ Akun tidak ditemukan.")
                clear_keypad_buffer(context.user_data, "view_pin")
                return

            # Decrypt secret
            key = derive_encryption_key(buf, user.kdf_salt)
            clear_keypad_buffer(context.user_data, "view_pin")
            context.user_data.pop("view_account_id", None)

            try:
                secret = decrypt_secret(key, account.secret_encrypted, account.nonce)
            except Exception:
                await query.edit_message_text("❌ Gagal mendekripsi secret akun.")
                return

            emoji = get_issuer_emoji(account.issuer)

            if account.type == "hotp":
                code = generate_hotp_code(secret, account.hotp_counter, digits=account.digits)
                account.hotp_counter += 1
                await session.commit()
                await log_action(session, user.id, "view_code", True, account_id=account.id)

                code_html = format_otp_display(code)
                msg_text = (
                    f"{emoji} **{account.label}** (Counter #{account.hotp_counter})\n\n"
                    f"{code_html}\n\n"
                    "Tap kode di atas untuk menyalin ke clipboard.\n\n"
                    "⏱️ *Pesan ini akan otomatis dihapus dalam 30 detik.*"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔢 Generate Kode Berikutnya", callback_data=f"view:select:{account.id}")],
                    [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")],
                ])
            else:
                code = generate_totp_code(secret, digits=account.digits, interval=account.period)
                await log_action(session, user.id, "view_code", True, account_id=account.id)

                remaining_sec = get_totp_remaining_seconds(interval=account.period)
                countdown_bar = render_countdown_bar(remaining_sec, total_period=account.period)
                code_html = format_otp_display(code)

                msg_text = (
                    f"{emoji} **{account.label}**\n\n"
                    f"{code_html}\n\n"
                    f"{countdown_bar}\n\n"
                    "Tap kode di atas untuk menyalin ke clipboard.\n\n"
                    "⏱️ *Pesan ini akan otomatis dihapus dalam 30 detik.*"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh Kode", callback_data=f"view:select:{account.id}")],
                    [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")],
                ])

            await query.edit_message_text(
                msg_text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )

            # Schedule auto-deletion after 30 seconds
            if context.job_queue and update.effective_chat:
                context.job_queue.run_once(
                    view_code_auto_delete_job,
                    when=30,
                    chat_id=update.effective_chat.id,
                    data=query.message.message_id,
                )
    else:
        text = (
            "🔑 **Buka Kode Akun**\n\n"
            "Masukkan PIN 6 digit Anda:\n\n"
            f"`{render_pin_display(len(buf))}`"
        )
        markup = build_keypad_keyboard("view_pin", show_cancel=True)
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
