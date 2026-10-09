import html
import time
from typing import Optional
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.helpers import escape_markdown
from crypto.cipher import decrypt_secret
from crypto.kdf import async_derive_encryption_key, async_verify_pin, derive_encryption_key, verify_pin
from db.models import Account, User
from handlers.keypad import (
    build_keypad_keyboard,
    clear_keypad_buffer,
    get_pin_length,
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


def cancel_view_code_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    """Cancel any active countdown or auto-delete jobs associated with a message."""
    if not context.job_queue:
        return
    for name in [f"countdown_{chat_id}_{message_id}", f"autodel_{chat_id}_{message_id}"]:
        jobs = context.job_queue.get_jobs_by_name(name)
        for job in jobs:
            job.schedule_removal()


async def view_code_auto_delete_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete OTP message after configured lifetime and restore main menu."""
    job = context.job
    chat_id = job.chat_id if job else None
    message_id = job.data if job else None

    if chat_id and message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass
        cancel_view_code_jobs(context, chat_id, message_id)

    if context.user_data:
        context.user_data.pop("active_view", None)
    user_id = getattr(job, "user_id", None)
    if user_id and hasattr(context, "application") and context.application and hasattr(context.application, "user_data") and context.application.user_data:
        context.application.user_data.get(user_id, {}).pop("active_view", None)

    if chat_id:
        try:
            from handlers.menu import get_main_menu_keyboard
            menu_text = (
                "🔐 **Telegram 2FA Authenticator**\n\n"
                "Pilih menu di bawah ini untuk melihat kode OTP atau mengelola akun Anda:"
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=menu_text,
                reply_markup=get_main_menu_keyboard(),
                parse_mode=ParseMode.MARKDOWN,
            )
        except Exception:
            pass


async def view_code_countdown_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Edit message every 5 seconds to update TOTP progress bar and regenerate code until expiration."""
    job = context.job
    data = job.data or {}
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    period = data.get("period", 30)
    digits = data.get("digits", 6)
    secret = data.get("secret")
    label = data.get("label", "")
    emoji = data.get("emoji", "🔐")
    acc_id = data.get("account_id")

    settings = context.bot_data.get("settings")
    auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90

    if "expires_at" in data and time.time() >= data["expires_at"]:
        job.schedule_removal()
        return

    remaining_sec = get_totp_remaining_seconds(interval=period)
    countdown_bar = render_countdown_bar(remaining_sec, total_period=period)

    # Automatically generate the latest OTP code for the current second
    if secret:
        current_code = generate_totp_code(secret, digits=digits, interval=period)
        code_html = format_otp_display(current_code)
    else:
        code_html = data.get("code_html", "")

    safe_label = html.escape(label)
    new_text = (
        f"{emoji} <b>{safe_label}</b>\n\n"
        f"{code_html}\n\n"
        f"{countdown_bar}\n\n"
        "Tap kode di atas untuk menyalin ke clipboard.\n\n"
        f"⏱️ <i>Pesan ini akan otomatis dihapus dalam {auto_del_secs} detik.</i>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Refresh Kode", callback_data=f"view:refresh:{acc_id}")],
        [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")],
    ])

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=new_text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        if "Message is not modified" in str(e):
            return
        job.schedule_removal()


async def handle_refresh_code(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int
) -> None:
    """Manually refresh OTP code without re-entering PIN if session is still active."""
    query = update.callback_query
    if not query:
        return

    active_view = context.user_data.get("active_view") if isinstance(context.user_data, dict) else None
    expires_at = active_view.get("expires_at", 0) if isinstance(active_view, dict) else 0
    if not isinstance(expires_at, (int, float)):
        expires_at = 0

    # Verify active view is valid, for this account, and not expired
    if (
        active_view
        and isinstance(active_view, dict)
        and active_view.get("account_id") == account_id
        and time.time() < expires_at
    ):
        secret = active_view["secret"]
        acc_type = active_view.get("type", "totp")
        period = active_view.get("period", 30)
        digits = active_view.get("digits", 6)
        label = active_view.get("label", "")
        emoji = active_view.get("emoji", "🔐")
        safe_label = html.escape(label)
        settings = context.bot_data.get("settings")
        auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90

        if acc_type == "hotp":
            session_factory = context.bot_data.get("session_factory")
            user_id = update.effective_user.id
            if session_factory:
                async with session_factory() as session:
                    user_stmt = select(User).where(User.telegram_user_id == user_id)
                    user = (await session.execute(user_stmt)).scalars().first()
                    if user:
                        stmt = select(Account).where(Account.id == account_id, Account.user_id == user.id)
                        acc = (await session.execute(stmt)).scalars().first()
                        if not acc:
                            kb = InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")]
                            ])
                            await query.edit_message_text("❌ Akun tidak ditemukan.", reply_markup=kb)
                            return
                        acc.hotp_counter += 1
                        code = generate_hotp_code(secret, acc.hotp_counter, digits=digits)
                        await session.commit()
                        await log_action(session, user.id, "view_otp", True, account_id=acc.id)
                        code_html = format_otp_display(code)
                        msg_text = (
                            f"{emoji} <b>{safe_label}</b> (Counter #{acc.hotp_counter})\n\n"
                            f"{code_html}\n\n"
                            "Tap kode di atas untuk menyalin ke clipboard.\n\n"
                            f"⏱️ <i>Pesan ini akan otomatis dihapus dalam {auto_del_secs} detik.</i>"
                        )
                        kb = InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔢 Generate Kode Berikutnya", callback_data=f"view:refresh:{account_id}")],
                            [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")],
                        ])
                        try:
                            await query.edit_message_text(msg_text, reply_markup=kb, parse_mode=ParseMode.HTML)
                            await query.answer("🔢 Kode HOTP berikutnya dibuat!")
                        except Exception as e:
                            if "Message is not modified" in str(e):
                                await query.answer()
                        return
        else:
            # TOTP
            code = generate_totp_code(secret, digits=digits, interval=period)
            remaining_sec = get_totp_remaining_seconds(interval=period)
            countdown_bar = render_countdown_bar(remaining_sec, total_period=period)
            code_html = format_otp_display(code)
            msg_text = (
                f"{emoji} <b>{safe_label}</b>\n\n"
                f"{code_html}\n\n"
                f"{countdown_bar}\n\n"
                "Tap kode di atas untuk menyalin ke clipboard.\n\n"
                f"⏱️ <i>Pesan ini akan otomatis dihapus dalam {auto_del_secs} detik.</i>"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh Kode", callback_data=f"view:refresh:{account_id}")],
                [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")],
            ])
            try:
                await query.edit_message_text(msg_text, reply_markup=kb, parse_mode=ParseMode.HTML)
                await query.answer("🔄 Kode OTP diperbarui!")
            except Exception as e:
                if "Message is not modified" in str(e):
                    await query.answer("🔄 Kode masih sama (periode belum berganti).")
                else:
                    await query.answer()
            return

    # If session expired or missing, cancel any lingering jobs and prompt for PIN
    await query.answer("⏱️ Sesi telah berakhir. Masukkan PIN kembali.", show_alert=False)
    chat_id = update.effective_chat.id if update.effective_chat else None
    msg_id = query.message.message_id if query.message else None
    if chat_id and msg_id:
        cancel_view_code_jobs(context, chat_id, msg_id)
    context.user_data.pop("active_view", None)
    await handle_select_account_for_code(update, context, account_id)


async def handle_view_code_menu(
    update: Update, context: ContextTypes.DEFAULT_TYPE, favorites_only: bool = False
) -> None:
    """Display list of accounts to generate OTP code."""
    query = update.callback_query
    if query:
        await query.answer()
        if query.data == "menu:favorite_accounts":
            favorites_only = True
        if query.message and update.effective_chat:
            cancel_view_code_jobs(context, update.effective_chat.id, query.message.message_id)
            from handlers.view_all_codes import cancel_view_all_jobs
            cancel_view_all_jobs(context, update.effective_chat.id, query.message.message_id)
            context.user_data.pop("active_view", None)
            context.user_data.pop("active_view_all", None)

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

                if favorites_only:
                    acc_stmt = (
                        select(Account)
                        .where(Account.user_id == user.id, Account.is_favorite == True)
                        .order_by(Account.label.asc())
                    )
                else:
                    acc_stmt = (
                        select(Account)
                        .where(Account.user_id == user.id)
                        .order_by(Account.is_favorite.desc(), Account.label.asc())
                    )
                accounts = list((await session.execute(acc_stmt)).scalars().all())

    buttons = []
    display_accounts = accounts[:25]
    for acc in display_accounts:
        emoji = get_issuer_emoji(acc.issuer)
        fav = " ⭐" if acc.is_favorite else ""
        text = f"{emoji} {acc.label}{fav}"
        buttons.append([InlineKeyboardButton(text, callback_data=f"view:select:{acc.id}")])

    if not favorites_only and accounts:
        buttons.insert(0, [InlineKeyboardButton("👁️ Lihat Semua Kode Sekaligus", callback_data="menu:view_all_codes")])
    if not favorites_only and len(accounts) > 8:
        buttons.insert(0, [InlineKeyboardButton("🔍 Cari Akun", callback_data="menu:search_account")])

    buttons.append([InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu:back_to_main")])
    markup = InlineKeyboardMarkup(buttons)

    limit_note = "\n\n_(Menampilkan 25 akun pertama. Gunakan menu Cari Akun jika akun Anda belum terlihat)_" if len(accounts) > 25 else ""

    if favorites_only:
        msg_text = f"⭐ **Akun Favorit**\n\nPilih akun untuk melihat kode autentikasi:{limit_note}"
        if not accounts:
            msg_text = "⭐ **Akun Favorit**\n\nBelum ada akun favorit. Anda dapat menambahkan tanda bintang pada menu *✏️ Kelola Akun*."
    else:
        msg_text = f"🔑 **Lihat Kode OTP**\n\nPilih akun untuk melihat kode autentikasi:{limit_note}"
        if not accounts:
            msg_text = "🔑 **Lihat Kode OTP**\n\nBelum ada akun tersimpan. Gunakan menu *➕ Tambah Akun* terlebih dahulu."

    if query:
        try:
            await query.edit_message_text(msg_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            if "Message is not modified" not in str(e):
                pass
    elif update.message:
        await update.message.reply_text(msg_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_select_account_for_code(
    update: Update, context: ContextTypes.DEFAULT_TYPE, account_id: int
) -> None:
    """Prompt user for PIN before decrypting and showing code."""
    query = update.callback_query
    if query:
        await query.answer()
        if query.message and update.effective_chat:
            cancel_view_code_jobs(context, update.effective_chat.id, query.message.message_id)
            context.user_data.pop("active_view", None)

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    account_label = "Akun"
    if session_factory:
        async with session_factory() as session:
            user_stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(user_stmt)).scalars().first()
            if not user:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                ])
                if query:
                    await query.edit_message_text("❌ User tidak terdaftar.", reply_markup=kb)
                return

            is_locked, remaining_seconds = check_lockout(user)
            if is_locked:
                mins, secs = divmod(remaining_seconds, 60)
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                ])
                if query:
                    await query.edit_message_text(
                        f"🔒 **Akun Terkunci!** Coba lagi dalam {mins}m {secs}s.",
                        reply_markup=kb,
                        parse_mode=ParseMode.MARKDOWN,
                    )
                return

            stmt = select(Account).where(Account.id == account_id, Account.user_id == user.id)
            acc = (await session.execute(stmt)).scalars().first()
            if not acc:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")]
                ])
                if query:
                    await query.edit_message_text("❌ Akun tidak ditemukan.", reply_markup=kb)
                return
            account_label = acc.label

    context.user_data["view_account_id"] = account_id
    clear_keypad_buffer(context.user_data, "view_pin")

    pin_len = get_pin_length(context)
    safe_account_label = escape_markdown(account_label, version=1)
    text = (
        f"🔑 **Buka Kode: {safe_account_label}**\n\n"
        f"Masukkan PIN {pin_len} digit Anda:\n\n"
        f"`{render_pin_display(0, max_length=pin_len)}`"
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
    pin_len = get_pin_length(context)
    buf, is_complete, is_cancel = handle_keypad_press(
        context.user_data, "view_pin", key_val, max_length=pin_len
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
            clear_keypad_buffer(context.user_data, "view_pin")
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
            ])
            await query.edit_message_text("❌ Database tidak tersedia.", reply_markup=kb)
            return

        async with session_factory() as session:
            user_stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(user_stmt)).scalars().first()
            if not user:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                ])
                await query.edit_message_text("❌ User tidak terdaftar.", reply_markup=kb)
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

            if not await async_verify_pin(buf, user.pin_hash_salt, user.pin_hash):
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
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")]
                ])
                await query.edit_message_text("❌ Akun tidak ditemukan.", reply_markup=kb)
                clear_keypad_buffer(context.user_data, "view_pin")
                return

            # Decrypt secret
            key = await async_derive_encryption_key(buf, user.kdf_salt)
            clear_keypad_buffer(context.user_data, "view_pin")
            context.user_data.pop("view_account_id", None)

            try:
                secret = decrypt_secret(key, account.secret_encrypted, account.nonce)
            except Exception:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                ])
                await query.edit_message_text("❌ Gagal mendekripsi secret akun.", reply_markup=kb)
                return

            emoji = get_issuer_emoji(account.issuer)
            safe_label = html.escape(account.label)
            settings = context.bot_data.get("settings")
            auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90

            if account.type == "hotp":
                account.hotp_counter += 1
                code = generate_hotp_code(secret, account.hotp_counter, digits=account.digits)
                await session.commit()
                await log_action(session, user.id, "view_code", True, account_id=account.id)

                code_html = format_otp_display(code)
                msg_text = (
                    f"{emoji} <b>{safe_label}</b> (Counter #{account.hotp_counter})\n\n"
                    f"{code_html}\n\n"
                    "Tap kode di atas untuk menyalin ke clipboard.\n\n"
                    f"⏱️ <i>Pesan ini akan otomatis dihapus dalam {auto_del_secs} detik.</i>"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔢 Generate Kode Berikutnya", callback_data=f"view:refresh:{account.id}")],
                    [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")],
                ])
            else:
                code = generate_totp_code(secret, digits=account.digits, interval=account.period)
                await log_action(session, user.id, "view_code", True, account_id=account.id)

                remaining_sec = get_totp_remaining_seconds(interval=account.period)
                countdown_bar = render_countdown_bar(remaining_sec, total_period=account.period)
                code_html = format_otp_display(code)

                msg_text = (
                    f"{emoji} <b>{safe_label}</b>\n\n"
                    f"{code_html}\n\n"
                    f"{countdown_bar}\n\n"
                    "Tap kode di atas untuk menyalin ke clipboard.\n\n"
                    f"⏱️ <i>Pesan ini akan otomatis dihapus dalam {auto_del_secs} detik.</i>"
                )
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Refresh Kode", callback_data=f"view:refresh:{account.id}")],
                    [InlineKeyboardButton("🔙 Daftar Akun", callback_data="menu:view_code")],
                ])

            await query.edit_message_text(
                msg_text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
            )

            # Schedule auto-deletion and repeating countdown updater
            if context.job_queue and update.effective_chat:
                chat_id = update.effective_chat.id
                msg_id = query.message.message_id
                cancel_view_code_jobs(context, chat_id, msg_id)

                context.user_data["active_view"] = {
                    "account_id": account.id,
                    "secret": secret,
                    "type": account.type,
                    "period": account.period,
                    "digits": account.digits,
                    "label": account.label,
                    "emoji": emoji,
                    "expires_at": time.time() + auto_del_secs,
                    "chat_id": chat_id,
                    "message_id": msg_id,
                }

                context.job_queue.run_once(
                    view_code_auto_delete_job,
                    when=auto_del_secs,
                    chat_id=chat_id,
                    user_id=update.effective_user.id if update.effective_user else None,
                    data=msg_id,
                    name=f"autodel_{chat_id}_{msg_id}",
                )
                if account.type == "totp":
                    job_data = {
                        "chat_id": chat_id,
                        "message_id": msg_id,
                        "secret": secret,
                        "period": account.period,
                        "digits": account.digits,
                        "label": account.label,
                        "emoji": emoji,
                        "code_html": code_html,
                        "account_id": account.id,
                        "expires_at": time.time() + auto_del_secs,
                    }
                    context.job_queue.run_repeating(
                        view_code_countdown_job,
                        interval=10,
                        first=10,
                        data=job_data,
                        chat_id=chat_id,
                        name=f"countdown_{chat_id}_{msg_id}",
                    )

    else:
        text = (
            "🔑 **Buka Kode Akun**\n\n"
            f"Masukkan PIN {pin_len} digit Anda:\n\n"
            f"`{render_pin_display(len(buf), max_length=pin_len)}`"
        )
        markup = build_keypad_keyboard("view_pin", show_cancel=True)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            if "Message is not modified" not in str(e):
                pass
