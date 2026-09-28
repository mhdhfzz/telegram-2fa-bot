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
            settings = context.bot_data.get("settings")
            auto_del_secs = getattr(settings, "auto_delete_seconds", 90) if settings else 90

            success_text = (
                "✅ **PIN Berhasil Diubah!**\n\n"
                "Seluruh data akun telah dienkripsi ulang dengan kunci baru Anda.\n\n"
                "⚠️ **Recovery Phrase Baru Anda:**\n"
                f"`{phrase_str}`\n\n"
                f"⏱️ *Pesan ini akan otomatis dihapus dalam {auto_del_secs} detik demi keamanan.*"
            )
            markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Saya Sudah Mencatat", callback_data="settings:confirm_phrase")]
            ])
            await query.edit_message_text(success_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)

            if context.job_queue and update.effective_chat:
                context.job_queue.run_once(
                    auto_delete_phrase_job,
                    when=auto_del_secs,
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


async def handle_confirm_phrase_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete recovery phrase message and return to settings menu cleanly."""
    query = update.callback_query
    if query:
        await query.answer()
        try:
            await query.message.delete()
        except Exception:
            pass
    await handle_settings_menu(update, context)


async def handle_import_backup_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt user to upload a backup json file."""
    query = update.callback_query
    if query:
        await query.answer()

    context.user_data["settings_state"] = "awaiting_import_file"
    text = (
        "📥 **Impor Cadangan (Backup)**\n\n"
        "Silakan kirimkan file cadangan (`.json`) yang sebelumnya Anda ekspor dari bot ini.\n\n"
        "⚠️ *Pastikan Anda hanya mengimpor file backup dari sumber tepercaya.*"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Batal", callback_data="menu:settings")]
    ])
    if query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_import_file_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Receive uploaded backup document file."""
    if context.user_data.get("settings_state") != "awaiting_import_file":
        return

    doc = update.message.document
    if not doc:
        return

    file = await doc.get_file()
    file_bytes = await file.download_as_bytearray()

    context.user_data["import_file_bytes"] = bytes(file_bytes)
    context.user_data["settings_state"] = "awaiting_import_passphrase"

    text = (
        "🔐 **Masukkan Passphrase Cadangan**\n\n"
        "File backup diterima! Sekarang, ketik dan kirimkan **Passphrase** "
        "yang Anda buat saat mengekspor file ini:"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_import_passphrase_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Decrypt backup payload with provided passphrase and prompt PIN."""
    if context.user_data.get("settings_state") != "awaiting_import_passphrase":
        return

    passphrase = (update.message.text or "").strip()
    backup_bytes = context.user_data.get("import_file_bytes")

    if not backup_bytes:
        await update.message.reply_text("Sesi impor kedaluwarsa. Silakan ulangi dari Pengaturan.")
        context.user_data.pop("settings_state", None)
        return

    try:
        accounts_data = import_accounts_backup(backup_bytes, passphrase)
    except Exception:
        await update.message.reply_text(
            "❌ **Passphrase salah atau file rusak!**\n\n"
            "Gagal mendekripsi file cadangan. Silakan ketik ulang Passphrase yang benar:"
        )
        return

    context.user_data["import_accounts_data"] = accounts_data
    context.user_data.pop("import_file_bytes", None)
    context.user_data.pop("settings_state", None)
    clear_keypad_buffer(context.user_data, "import_pin")

    text = (
        f"✅ **File Berhasil Didekripsi!**\n\n"
        f"Ditemukan **{len(accounts_data)} akun** dalam file cadangan.\n\n"
        "Masukkan **PIN 6 digit** Anda untuk mengenkripsi dan menyimpan akun-akun ini ke database:\n\n"
        f"`{render_pin_display(0)}`"
    )
    markup = build_keypad_keyboard("import_pin", show_cancel=True)
    await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_import_pin_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process keypad entry to re-encrypt and save imported accounts."""
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    key_val = parts[2]
    buf, is_complete, is_cancel = handle_keypad_press(
        context.user_data, "import_pin", key_val, max_length=6
    )

    if is_cancel:
        clear_keypad_buffer(context.user_data, "import_pin")
        context.user_data.pop("import_accounts_data", None)
        await handle_settings_menu(update, context)
        return

    if is_complete:
        accounts_data = context.user_data.get("import_accounts_data", [])
        session_factory = context.bot_data.get("session_factory")
        user_id = update.effective_user.id

        if session_factory:
            async with session_factory() as session:
                user_stmt = select(User).where(User.telegram_user_id == user_id)
                user = (await session.execute(user_stmt)).scalars().first()
                if not user or not verify_pin(buf, user.pin_hash_salt, user.pin_hash):
                    await record_failed_pin_attempt(session, user)
                    await log_action(session, user.id, "import", False)
                    clear_keypad_buffer(context.user_data, "import_pin")
                    await query.edit_message_text(
                        "❌ **PIN Salah!** Impor akun dibatalkan demi keamanan.",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Pengaturan", callback_data="menu:settings")]
                        ]),
                        parse_mode=ParseMode.MARKDOWN,
                    )
                    return

                await record_successful_pin_attempt(session, user)
                key = derive_encryption_key(buf, user.kdf_salt)

                for acc_item in accounts_data:
                    ciph, nonce = encrypt_secret(key, acc_item["secret"])
                    new_acc = Account(
                        user_id=user.id,
                        label=acc_item.get("label", "Akun"),
                        issuer=acc_item.get("issuer"),
                        secret_encrypted=ciph,
                        nonce=nonce,
                        type=acc_item.get("type", "totp"),
                        digits=acc_item.get("digits", 6),
                        period=acc_item.get("period", 30),
                        hotp_counter=acc_item.get("counter", 0),
                    )
                    session.add(new_acc)

                await session.commit()
                await log_action(session, user.id, "import", True)

        clear_keypad_buffer(context.user_data, "import_pin")
        context.user_data.pop("import_accounts_data", None)

        success_text = (
            f"✅ **Impor Berhasil Selesai!**\n\n"
            f"Sebanyak **{len(accounts_data)} akun** telah berhasil diimpor dan diamankan dengan PIN Anda."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Lihat Kode OTP", callback_data="menu:view_code")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
        ])
        await query.edit_message_text(success_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    else:
        accounts_data = context.user_data.get("import_accounts_data", [])
        text = (
            f"🔑 **Konfirmasi Impor ({len(accounts_data)} Akun)**\n\n"
            "Masukkan PIN 6 digit Anda:\n\n"
            f"`{render_pin_display(len(buf))}`"
        )
        markup = build_keypad_keyboard("import_pin", show_cancel=True)
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
