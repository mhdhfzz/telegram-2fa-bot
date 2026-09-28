import io
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from crypto.cipher import decrypt_secret, encrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt, hash_pin, verify_pin
from crypto.recovery import generate_recovery_phrase, hash_recovery_phrase
from db.models import Account, User
from handlers.keypad import (
    build_keypad_keyboard,
    clear_keypad_buffer,
    handle_keypad_press,
    render_pin_display,
)
from services.backup_service import export_accounts_backup, import_accounts_backup
from services.lockout_service import record_failed_pin_attempt, record_successful_pin_attempt
from services.log_service import get_user_logs, log_action


async def auto_delete_phrase_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = context.job.chat_id
        message_id = context.job.data
        if chat_id and message_id:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def handle_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()

    text = (
        "⚙️ **Pengaturan & Keamanan**\n\n"
        "Kelola PIN autentikasi, cadangkan atau pulihkan data akun, dan periksa riwayat akses Anda:"
    )
    keyboard = [
        [InlineKeyboardButton("🔑 Ganti PIN", callback_data="settings:change_pin")],
        [
            InlineKeyboardButton("📤 Export Backup", callback_data="settings:export"),
            InlineKeyboardButton("📥 Import Backup", callback_data="settings:import"),
        ],
        [InlineKeyboardButton("📜 Lihat Log Akses", callback_data="settings:logs:1")],
        [InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu:back_to_main")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_change_pin_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    context.user_data["ch_pin_step"] = "old"
    clear_keypad_buffer(context.user_data, "ch_pin_old")
    clear_keypad_buffer(context.user_data, "ch_pin_new1")
    clear_keypad_buffer(context.user_data, "ch_pin_new2")

    text = (
        "🔑 **Ganti PIN - Langkah 1/3**\n\n"
        "Masukkan **PIN Lama** Anda:\n\n"
        f"`{render_pin_display(0)}`"
    )
    markup = build_keypad_keyboard("ch_pin_old", show_cancel=True)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_change_pin_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    prefix, _, key_val = parts[0], parts[1], parts[2]

    if prefix == "ch_pin_old":
        buf, is_complete, is_cancel = handle_keypad_press(
            context.user_data, "ch_pin_old", key_val, max_length=6
        )
        if is_cancel:
            await handle_settings_menu(update, context)
            return

        if is_complete:
            session_factory = context.bot_data.get("session_factory")
            user_id = update.effective_user.id
            if session_factory:
                async with session_factory() as session:
                    stmt = select(User).where(User.telegram_user_id == user_id)
                    user = (await session.execute(stmt)).scalars().first()
                    if not user or not verify_pin(buf, user.pin_hash_salt, user.pin_hash):
                        await record_failed_pin_attempt(session, user)
                        await log_action(session, user.id, "pin_change", False)
                        clear_keypad_buffer(context.user_data, "ch_pin_old")
                        await query.edit_message_text(
                            "❌ **PIN Lama Salah!** Proses ganti PIN dibatalkan.",
                            reply_markup=InlineKeyboardMarkup([
                                [InlineKeyboardButton("🔙 Pengaturan", callback_data="menu:settings")]
                            ]),
                            parse_mode=ParseMode.MARKDOWN,
                        )
                        return

            context.user_data["verified_old_pin"] = buf
            context.user_data["ch_pin_step"] = "new1"
            clear_keypad_buffer(context.user_data, "ch_pin_new1")

            text = (
                "🔑 **Ganti PIN - Langkah 2/3**\n\n"
                "Masukkan **PIN Baru 6 digit** Anda:\n\n"
                f"`{render_pin_display(0)}`"
            )
            markup = build_keypad_keyboard("ch_pin_new1", show_cancel=True)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        else:
            text = (
                "🔑 **Ganti PIN - Langkah 1/3**\n\n"
                "Masukkan **PIN Lama** Anda:\n\n"
                f"`{render_pin_display(len(buf))}`"
            )
            markup = build_keypad_keyboard("ch_pin_old", show_cancel=True)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

    elif prefix == "ch_pin_new1":
        buf, is_complete, is_cancel = handle_keypad_press(
            context.user_data, "ch_pin_new1", key_val, max_length=6
        )
        if is_cancel:
            await handle_settings_menu(update, context)
            return

        if is_complete:
            context.user_data["temp_new_pin"] = buf
            context.user_data["ch_pin_step"] = "new2"
            clear_keypad_buffer(context.user_data, "ch_pin_new2")

            text = (
                "🔑 **Ganti PIN - Langkah 3/3**\n\n"
                "Silakan **konfirmasi ulang** PIN Baru Anda:\n\n"
                f"`{render_pin_display(0)}`"
            )
            markup = build_keypad_keyboard("ch_pin_new2", show_cancel=True)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        else:
            text = (
                "🔑 **Ganti PIN - Langkah 2/3**\n\n"
                "Masukkan **PIN Baru 6 digit** Anda:\n\n"
                f"`{render_pin_display(len(buf))}`"
            )
            markup = build_keypad_keyboard("ch_pin_new1", show_cancel=True)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

    elif prefix == "ch_pin_new2":
        buf, is_complete, is_cancel = handle_keypad_press(
            context.user_data, "ch_pin_new2", key_val, max_length=6
        )
        if is_cancel:
            await handle_settings_menu(update, context)
            return

        if is_complete:
            new_pin = context.user_data.get("temp_new_pin", "")
            old_pin = context.user_data.get("verified_old_pin", "")

            if buf != new_pin:
                clear_keypad_buffer(context.user_data, "ch_pin_new1")
                clear_keypad_buffer(context.user_data, "ch_pin_new2")
                context.user_data["ch_pin_step"] = "new1"
                text = (
                    "❌ **Konfirmasi PIN baru tidak cocok!**\n\n"
                    "Silakan masukkan PIN Baru kembali:\n\n"
                    f"`{render_pin_display(0)}`"
                )
                markup = build_keypad_keyboard("ch_pin_new1", show_cancel=True)
                await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
                return

            session_factory = context.bot_data.get("session_factory")
            user_id = update.effective_user.id
            phrase = generate_recovery_phrase(language="en")

            if session_factory:
                async with session_factory() as session:
                    stmt = select(User).where(User.telegram_user_id == user_id)
                    user = (await session.execute(stmt)).scalars().first()
                    if user:
                        old_key = derive_encryption_key(old_pin, user.kdf_salt)

                        new_kdf_salt = generate_salt()
                        new_pin_salt = generate_salt()
                        new_key = derive_encryption_key(new_pin, new_kdf_salt)

                        acc_stmt = select(Account).where(Account.user_id == user.id)
                        accounts = list((await session.execute(acc_stmt)).scalars().all())

                        for acc in accounts:
                            decrypted_secret = decrypt_secret(
                                old_key, acc.secret_encrypted, acc.nonce
                            )
                            new_cipher, new_nonce = encrypt_secret(new_key, decrypted_secret)
                            acc.secret_encrypted = new_cipher
                            acc.nonce = new_nonce

                        user.kdf_salt = new_kdf_salt
                        user.pin_hash_salt = new_pin_salt
                        user.pin_hash = hash_pin(new_pin, new_pin_salt)
                        user.recovery_phrase_hash = hash_recovery_phrase(phrase)
                        await record_successful_pin_attempt(session, user)
                        await log_action(session, user.id, "pin_change", True)
                        await session.commit()

            clear_keypad_buffer(context.user_data, "ch_pin_old")
            clear_keypad_buffer(context.user_data, "ch_pin_new1")
            clear_keypad_buffer(context.user_data, "ch_pin_new2")
            context.user_data.pop("verified_old_pin", None)
            context.user_data.pop("temp_new_pin", None)
            context.user_data.pop("ch_pin_step", None)

            phrase_str = " ".join(phrase)
            success_text = (
                "✅ **PIN Berhasil Diubah!**\n\n"
                "Seluruh data akun telah dienkripsi ulang dengan kunci baru Anda.\n\n"
                "⚠️ **Recovery Phrase Baru Anda:**\n"
                f"`{phrase_str}`\n\n"
                "⏱️ *Pesan ini akan otomatis dihapus dalam 30 detik demi keamanan.*"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Selesai & Kembali", callback_data="menu:settings")]
            ])
            await query.edit_message_text(success_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

            if context.job_queue and update.effective_chat:
                context.job_queue.run_once(
                    auto_delete_phrase_job,
                    when=30,
                    chat_id=update.effective_chat.id,
                    data=query.message.message_id,
                )
        else:
            text = (
                "🔑 **Ganti PIN - Langkah 3/3**\n\n"
                "Silakan **konfirmasi ulang** PIN Baru Anda:\n\n"
                f"`{render_pin_display(len(buf))}`"
            )
            markup = build_keypad_keyboard("ch_pin_new2", show_cancel=True)
            await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_export_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    clear_keypad_buffer(context.user_data, "export_pin")
    text = (
        "📤 **Ekspor Cadangan (Backup)**\n\n"
        "Masukkan PIN 6 digit Anda untuk mengonfirmasi pembuatan file cadangan:\n\n"
        f"`{render_pin_display(0)}`"
    )
    markup = build_keypad_keyboard("export_pin", show_cancel=True)
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_export_pin_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    key_val = parts[2]
    buf, is_complete, is_cancel = handle_keypad_press(
        context.user_data, "export_pin", key_val, max_length=6
    )

    if is_cancel:
        clear_keypad_buffer(context.user_data, "export_pin")
        await handle_settings_menu(update, context)
        return

    if is_complete:
        session_factory = context.bot_data.get("session_factory")
        user_id = update.effective_user.id

        if session_factory:
            async with session_factory() as session:
                stmt = select(User).where(User.telegram_user_id == user_id)
                user = (await session.execute(stmt)).scalars().first()
                if not user or not verify_pin(buf, user.pin_hash_salt, user.pin_hash):
                    await record_failed_pin_attempt(session, user)
                    await log_action(session, user.id, "export", False)
                    clear_keypad_buffer(context.user_data, "export_pin")
                    await query.edit_message_text(
                        "❌ **PIN Salah!** Ekspor cadangan dibatalkan.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Pengaturan", callback_data="menu:settings")]
                        ]),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return

                context.user_data["export_auth_pin"] = buf
                context.user_data["settings_state"] = "awaiting_export_passphrase"
                clear_keypad_buffer(context.user_data, "export_pin")

                prompt_text = (
                    "🔐 **Tentukan Passphrase Enkripsi Backup**\n\n"
                    "Ketik dan kirimkan **Passphrase** mandiri untuk mengenkripsi file cadangan ini.\n\n"
                    "⚠️ *PENTING: Jangan gunakan PIN login Anda! Buat passphrase yang kuat (minimal 4 karakter).*"
                )
                await query.edit_message_text(prompt_text, parse_mode=ParseMode.MARKDOWN)
    else:
        text = (
            "📤 **Ekspor Cadangan (Backup)**\n\n"
            "Masukkan PIN 6 digit Anda:\n\n"
            f"`{render_pin_display(len(buf))}`"
        )
        markup = build_keypad_keyboard("export_pin", show_cancel=True)
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_export_passphrase_message(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if context.user_data.get("settings_state") != "awaiting_export_passphrase":
        return

    passphrase = (update.message.text or "").strip()
    if len(passphrase) < 4:
        await update.message.reply_text("Passphrase terlalu pendek. Minimal 4 karakter:")
        return

    pin = context.user_data.pop("export_auth_pin", None)
    context.user_data.pop("settings_state", None)

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    if session_factory and pin:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                key = derive_encryption_key(pin, user.kdf_salt)
                acc_stmt = select(Account).where(Account.user_id == user.id)
                accounts = list((await session.execute(acc_stmt)).scalars().all())

                accounts_data = []
                for acc in accounts:
                    decrypted = decrypt_secret(key, acc.secret_encrypted, acc.nonce)
                    accounts_data.append({
                        "label": acc.label,
                        "issuer": acc.issuer,
                        "secret": decrypted,
                        "type": acc.type,
                        "digits": acc.digits,
                        "period": acc.period,
                    })

                backup_bytes = export_accounts_backup(accounts_data, passphrase)
                await log_action(session, user.id, "export", True)

                date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"2fa_backup_{date_str}.json"
                doc = io.BytesIO(backup_bytes)
                doc.name = filename

                caption = (
                    "📦 **File Cadangan 2FA Terenkripsi**\n\n"
                    f"Berisi {len(accounts_data)} akun terenkripsi AES-256-GCM.\n"
                    "Simpan file ini dan passphrase Anda di tempat aman terpisah."
                )
                await update.message.reply_document(
                    document=doc,
                    caption=caption,
                    parse_mode=ParseMode.MARKDOWN,
                )


async def handle_view_logs_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()

    data = query.data or "settings:logs:1"
    parts = data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 1

    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    logs = []
    total_pages = 1
    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if user:
                logs, total_pages = await get_user_logs(session, user.id, page=page, page_size=10)

    log_lines = []
    action_names = {
        "view_code": "Lihat Kode",
        "add_account": "Tambah Akun",
        "delete_account": "Hapus Akun",
        "pin_fail": "PIN Salah",
        "lockout": "Lockout",
        "export": "Ekspor Cadangan",
        "import": "Impor Cadangan",
        "pin_change": "Ganti PIN",
        "manage_account": "Kelola Akun",
    }

    for log in logs:
        time_str = log.created_at.strftime("%Y-%m-%d %H:%M")
        status = "✅ Sukses" if log.success else "❌ Gagal"
        action = action_names.get(log.action, log.action)
        log_lines.append(f"• `{time_str}` {action} ({status})")

    body = "\n".join(log_lines) if log_lines else "_Belum ada riwayat aktivitas._"
    header = f"📜 **Log Akses & Keamanan (Hal {page}/{total_pages})**\n\n"
    text = header + body

    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton("◀️ Prev", callback_data=f"settings:logs:{page - 1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton("Next ▶️", callback_data=f"settings:logs:{page + 1}"))

    keyboard = []
    if nav_buttons:
        keyboard.append(nav_buttons)
    keyboard.append([InlineKeyboardButton("🔙 Pengaturan", callback_data="menu:settings")])

    markup = InlineKeyboardMarkup(keyboard)
    if query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
