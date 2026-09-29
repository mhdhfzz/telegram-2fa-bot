import html
import math
import time
from typing import List, Optional, Tuple
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
)


def cancel_view_all_jobs(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    """Cancel any active countdown or auto-delete jobs associated with view all codes."""
    if not context.job_queue:
        return
    for name in [f"view_all_cd_{chat_id}_{message_id}", f"view_all_del_{chat_id}_{message_id}"]:
        jobs = context.job_queue.get_jobs_by_name(name)
        for job in jobs:
            job.schedule_removal()


def render_view_all_page(
    accounts_slice: List[dict],
    page: int = 1,
    total_pages: int = 1,
    auto_del_secs: int = 90,
    start_index: int = 1,
) -> Tuple[str, InlineKeyboardMarkup]:
    """Render a 10-account page formatted with 1 account per line and pagination keyboard."""
    lines = [
        f"🔑 <b>Semua Kode OTP (Halaman {page}/{total_pages})</b>",
        f"⏱️ <i>Auto-refresh tiap 5 detik • Dihapus dalam {auto_del_secs} detik.</i>\n",
    ]

    for idx, acc in enumerate(accounts_slice, start=start_index):
        emoji = acc.get("emoji") or get_issuer_emoji(acc.get("issuer"))
        safe_label = html.escape(acc.get("label", "Akun"))
        secret = acc.get("secret", "")
        acc_type = acc.get("type", "totp")
        digits = acc.get("digits", 6)
        period = acc.get("period", 30)

        if acc_type == "hotp":
            counter = acc.get("hotp_counter", 0)
            try:
                code = generate_hotp_code(secret, counter=counter, digits=digits)
            except Exception:
                code = "ERROR"
            status_text = f"(HOTP #{counter})"
        else:
            try:
                code = generate_totp_code(secret, digits=digits, interval=period)
            except Exception:
                code = "ERROR"
            rem_sec = get_totp_remaining_seconds(interval=period)
            status_text = f"(⏳ {rem_sec}s)"

        code_html = format_otp_display(code)
        lines.append(f"{idx}. {emoji} <b>{safe_label}</b>: {code_html} {status_text}")

    lines.append("\nTap kode di atas untuk menyalin ke clipboard.")
    text = "\n".join(lines)

    keyboard = []
    if total_pages > 1:
        prev_page = max(1, page - 1)
        next_page = min(total_pages, page + 1)
        pagination_row = [
            InlineKeyboardButton("◀️ Sebelumnya", callback_data=f"view_all:page:{prev_page}"),
            InlineKeyboardButton(f"{page} / {total_pages}", callback_data=f"view_all:page:{page}"),
            InlineKeyboardButton("Selanjutnya ▶️", callback_data=f"view_all:page:{next_page}"),
        ]
        keyboard.append(pagination_row)

    keyboard.append([
        InlineKeyboardButton("🔄 Refresh Semua", callback_data="view_all:refresh"),
        InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main"),
    ])

    return text, InlineKeyboardMarkup(keyboard)


async def handle_view_all_codes_start(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Prompt user for PIN before opening all OTP codes."""
    query = update.callback_query
    if query:
        await query.answer()
        if query.message and update.effective_chat:
            cancel_view_all_jobs(context, update.effective_chat.id, query.message.message_id)
            from handlers.view_code import cancel_view_code_jobs
            cancel_view_code_jobs(context, update.effective_chat.id, query.message.message_id)
            context.user_data.pop("active_view", None)
            context.user_data.pop("active_view_all", None)

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    if not session_factory:
        if query:
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
            ])
            await query.edit_message_text("❌ Database tidak tersedia.", reply_markup=kb)
        return

    async with session_factory() as session:
        user_stmt = select(User).where(User.telegram_user_id == user_id)
        user = (await session.execute(user_stmt)).scalars().first()
        if not user:
            if query:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                ])
                await query.edit_message_text("❌ User tidak terdaftar.", reply_markup=kb)
            return

        is_locked, remaining_seconds = check_lockout(user)
        if is_locked:
            mins, secs = divmod(remaining_seconds, 60)
            text = f"🔒 **Akun Terkunci!** Coba lagi dalam {mins}m {secs}s."
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
            ])
            if query:
                await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
            return

        acc_stmt = select(Account).where(Account.user_id == user.id)
        accounts_count = len((await session.execute(acc_stmt)).scalars().all())
        if accounts_count == 0:
            text = "🔑 **Semua Kode OTP**\n\nBelum ada akun tersimpan. Gunakan menu *➕ Tambah Akun* terlebih dahulu."
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
            ])
            if query:
                await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
            return

    pin_len = get_pin_length(context)
    clear_keypad_buffer(context.user_data, "view_all_pin")
    text = (
        f"🔑 **Buka Semua Kode OTP ({accounts_count} Akun)**\n\n"
        f"Masukkan PIN {pin_len} digit Anda:\n\n"
        f"`{render_pin_display(0, max_length=pin_len)}`"
    )
    markup = build_keypad_keyboard("view_all_pin", show_cancel=True)

    if query:
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            if "Message is not modified" not in str(e):
                pass
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_view_all_pin_keypad(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Process keypad entry for opening all OTP codes."""
    query = update.callback_query
    if not query:
        return
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    key_val = parts[2]
    pin_len = get_pin_length(context)
    buf, is_complete, is_cancel = handle_keypad_press(
        context.user_data, "view_all_pin", key_val, max_length=pin_len
    )

    if is_cancel:
        clear_keypad_buffer(context.user_data, "view_all_pin")
        from handlers.menu import show_main_menu
        await show_main_menu(update, context)
        return

    if is_complete:
        session_factory = context.bot_data.get("session_factory")
        user_id = update.effective_user.id

        if not session_factory:
            clear_keypad_buffer(context.user_data, "view_all_pin")
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

            is_locked, remaining_seconds = check_lockout(user)
            if is_locked:
                mins, secs = divmod(remaining_seconds, 60)
                await query.edit_message_text(
                    f"🔒 **Akun Terkunci!** Coba lagi dalam {mins}m {secs}s.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN,
                )
                clear_keypad_buffer(context.user_data, "view_all_pin")
                return

            if not verify_pin(buf, user.pin_hash_salt, user.pin_hash):
                locked_now, rem = await record_failed_pin_attempt(session, user)
                await log_action(session, user.id, "view_all_pin_fail", False)
                clear_keypad_buffer(context.user_data, "view_all_pin")

                if locked_now:
                    mins, secs = divmod(rem, 60)
                    fail_msg = f"🔒 **Akun Terkunci!** Terlalu banyak percobaan PIN salah. Coba lagi dalam {mins}m {secs}s."
                else:
                    attempts_left = max(0, 5 - user.failed_pin_attempts)
                    fail_msg = f"❌ **PIN Salah!** Sisa percobaan sebelum terkunci: {attempts_left} kali."

                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Coba Lagi", callback_data="menu:view_all_codes")],
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
                ])
                await query.edit_message_text(fail_msg, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                return

            # PIN correct: Reset lockout
            await record_successful_pin_attempt(session, user)

            acc_stmt = (
                select(Account)
                .where(Account.user_id == user.id)
                .order_by(Account.is_favorite.desc(), Account.label.asc())
            )
            accounts = list((await session.execute(acc_stmt)).scalars().all())
            if not accounts:
                clear_keypad_buffer(context.user_data, "view_all_pin")
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                ])
                await query.edit_message_text("❌ Tidak ada akun tersimpan.", reply_markup=kb)
                return

            key = derive_encryption_key(buf, user.kdf_salt)
            clear_keypad_buffer(context.user_data, "view_all_pin")

            decrypted_accounts = []
            for acc in accounts:
                try:
                    sec = decrypt_secret(key, acc.secret_encrypted, acc.nonce)
                    decrypted_accounts.append({
                        "id": acc.id,
                        "label": acc.label,
                        "issuer": acc.issuer,
                        "type": acc.type,
                        "digits": acc.digits,
                        "period": acc.period,
                        "secret": sec,
                        "hotp_counter": acc.hotp_counter,
                        "emoji": get_issuer_emoji(acc.issuer),
                    })
                except Exception:
                    continue

            if not decrypted_accounts:
                kb = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                ])
                await query.edit_message_text("❌ Gagal mendekripsi secret akun.", reply_markup=kb)
                return

            await log_action(session, user.id, "view_all_codes", True)

        settings = context.bot_data.get("settings")
        auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90
        total_pages = max(1, math.ceil(len(decrypted_accounts) / 10))
        chat_id = update.effective_chat.id if update.effective_chat else 0
        msg_id = query.message.message_id if query.message else 0

        # Cancel any previous jobs on this message
        cancel_view_all_jobs(context, chat_id, msg_id)
        from handlers.view_code import cancel_view_code_jobs
        cancel_view_code_jobs(context, chat_id, msg_id)

        context.user_data["active_view_all"] = {
            "accounts": decrypted_accounts,
            "page": 1,
            "total_pages": total_pages,
            "expires_at": time.time() + auto_del_secs,
            "chat_id": chat_id,
            "message_id": msg_id,
        }

        # Render Page 1
        page_1_accounts = decrypted_accounts[:10]
        text, markup = render_view_all_page(
            page_1_accounts,
            page=1,
            total_pages=total_pages,
            auto_del_secs=auto_del_secs,
            start_index=1,
        )

        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception as e:
            if "Message is not modified" not in str(e):
                pass

        if context.job_queue and chat_id and msg_id:
            # Auto delete job
            context.job_queue.run_once(
                view_all_auto_delete_job,
                when=auto_del_secs,
                chat_id=chat_id,
                user_id=update.effective_user.id if update.effective_user else None,
                data=msg_id,
                name=f"view_all_del_{chat_id}_{msg_id}",
            )
            # Periodic countdown job every 5 seconds
            job_data = {
                "chat_id": chat_id,
                "message_id": msg_id,
                "user_id": update.effective_user.id,
            }
            context.job_queue.run_repeating(
                view_all_countdown_job,
                interval=5,
                first=5,
                chat_id=chat_id,
                user_id=update.effective_user.id if update.effective_user else None,
                data=job_data,
                name=f"view_all_cd_{chat_id}_{msg_id}",
            )
    else:
        text = (
            "🔑 **Buka Semua Kode OTP**\n\n"
            f"Masukkan PIN {pin_len} digit Anda:\n\n"
            f"`{render_pin_display(len(buf), max_length=pin_len)}`"
        )
        markup = build_keypad_keyboard("view_all_pin", show_cancel=True)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception as e:
            if "Message is not modified" not in str(e):
                pass


async def handle_view_all_page(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int
) -> None:
    """Handle switching pages in View All Codes without re-entering PIN."""
    query = update.callback_query
    if not query:
        return

    active_session = context.user_data.get("active_view_all")
    if not active_session or time.time() >= active_session.get("expires_at", 0):
        try:
            await query.answer("⏱️ Sesi telah berakhir. Masukkan PIN kembali.", show_alert=True)
        except Exception:
            pass
        await handle_view_all_codes_start(update, context)
        return

    try:
        await query.answer()
    except Exception:
        pass

    accounts = active_session.get("accounts", [])
    total_pages = active_session.get("total_pages", 1)
    page = max(1, min(page, total_pages))
    active_session["page"] = page

    start_idx = (page - 1) * 10
    end_idx = start_idx + 10
    accounts_slice = accounts[start_idx:end_idx]

    settings = context.bot_data.get("settings")
    auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90

    text, markup = render_view_all_page(
        accounts_slice,
        page=page,
        total_pages=total_pages,
        auto_del_secs=auto_del_secs,
        start_index=start_idx + 1,
    )

    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except Exception as e:
        if "Message is not modified" not in str(e):
            pass


async def handle_view_all_refresh(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Manually refresh all OTP codes on the current page."""
    query = update.callback_query
    if not query:
        return

    active_session = context.user_data.get("active_view_all")
    if not active_session or time.time() >= active_session.get("expires_at", 0):
        await query.answer("⏱️ Sesi telah berakhir. Masukkan PIN kembali.", show_alert=True)
        await handle_view_all_codes_start(update, context)
        return

    page = active_session.get("page", 1)
    accounts = active_session.get("accounts", [])
    total_pages = active_session.get("total_pages", 1)

    start_idx = (page - 1) * 10
    end_idx = start_idx + 10
    accounts_slice = accounts[start_idx:end_idx]

    settings = context.bot_data.get("settings")
    auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90

    text, markup = render_view_all_page(
        accounts_slice,
        page=page,
        total_pages=total_pages,
        auto_del_secs=auto_del_secs,
        start_index=start_idx + 1,
    )

    try:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        await query.answer("🔄 Semua kode OTP diperbarui!")
    except Exception as e:
        if "Message is not modified" in str(e):
            await query.answer("🔄 Kode masih sama (periode belum berganti).")
        else:
            await query.answer()


async def view_all_countdown_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Periodic job updating codes and remaining seconds every 5 seconds."""
    job = context.job
    data = job.data or {}
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")
    user_id = data.get("user_id")

    active_session = None
    if context.user_data:
        active_session = context.user_data.get("active_view_all")
    elif user_id and hasattr(context, "application") and context.application and hasattr(context.application, "user_data") and context.application.user_data:
        active_session = context.application.user_data.get(user_id, {}).get("active_view_all")

    if not active_session or time.time() >= active_session.get("expires_at", 0):
        job.schedule_removal()
        return

    page = active_session.get("page", 1)
    accounts = active_session.get("accounts", [])
    total_pages = active_session.get("total_pages", 1)

    start_idx = (page - 1) * 10
    end_idx = start_idx + 10
    accounts_slice = accounts[start_idx:end_idx]

    settings = context.bot_data.get("settings")
    auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90

    text, markup = render_view_all_page(
        accounts_slice,
        page=page,
        total_pages=total_pages,
        auto_del_secs=auto_del_secs,
        start_index=start_idx + 1,
    )

    try:
        await context.bot.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=markup,
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        if "Message is not modified" in str(e):
            return
        job.schedule_removal()


async def view_all_auto_delete_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete view all codes message upon expiry and restore main menu."""
    job = context.job
    chat_id = job.chat_id if job else None
    message_id = job.data if job else None
    user_id = job.user_id if hasattr(job, "user_id") and job.user_id else None

    if chat_id and message_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        except Exception:
            pass

    if context.user_data:
        context.user_data.pop("active_view_all", None)
        clear_keypad_buffer(context.user_data, "view_all_pin")
    if user_id and hasattr(context, "application") and context.application and hasattr(context.application, "user_data") and context.application.user_data:
        u_data = context.application.user_data.get(user_id, {})
        u_data.pop("active_view_all", None)
        clear_keypad_buffer(u_data, "view_all_pin")

    if chat_id and message_id:
        cancel_view_all_jobs(context, chat_id, message_id)

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
