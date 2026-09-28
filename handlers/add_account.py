import re
from typing import Optional
from sqlalchemy import select
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from crypto.cipher import encrypt_secret
from crypto.kdf import derive_encryption_key, verify_pin
from db.models import Account, User
from handlers.keypad import (
    build_keypad_keyboard,
    clear_keypad_buffer,
    handle_keypad_press,
    render_pin_display,
)
from services.icon_service import get_issuer_emoji
from services.lockout_service import record_failed_pin_attempt, record_successful_pin_attempt
from services.log_service import log_action
from services.otp_service import clean_base32_secret, parse_otpauth_uri
from services.qr_service import decode_qr_image


async def handle_add_account_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query:
        await query.answer()

    text = (
        "➕ **Tambah Akun 2FA Baru**\n\n"
        "Pilih metode penambahan akun yang Anda inginkan:\n\n"
        "• **📷 Scan QR**: Kirim foto / screenshot QR code dari layanan terkait.\n"
        "• **⌨️ Input Manual**: Masukkan Secret Key Base32 secara langsung."
    )
    keyboard = [
        [
            InlineKeyboardButton("📷 Scan QR", callback_data="add_acc:scan_qr"),
            InlineKeyboardButton("⌨️ Input Manual", callback_data="add_acc:manual"),
        ],
        [InlineKeyboardButton("🔙 Kembali ke Menu Utama", callback_data="menu:back_to_main")],
    ]
    markup = InlineKeyboardMarkup(keyboard)

    if query:
        await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.message:
        await update.message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_choose_scan_qr(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    context.user_data["add_state"] = "awaiting_qr"
    text = (
        "📷 **Kirim Foto QR Code**\n\n"
        "Silakan kirimkan foto atau screenshot QR code authenticator Anda ke chat ini.\n\n"
        "Bot akan otomatis membaca data URI `otpauth://` dari gambar tersebut."
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Batal", callback_data="menu:back_to_main")]
    ])
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_qr_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("add_state") != "awaiting_qr":
        return

    photos = update.message.photo
    if not photos:
        return

    highest_res_photo = photos[-1]
    photo_file = await highest_res_photo.get_file()
    photo_bytes = await photo_file.download_as_bytearray()

    decoded_uri = decode_qr_image(bytes(photo_bytes))
    if not decoded_uri:
        fail_text = (
            "❌ **QR Code Tidak Terdeteksi**\n\n"
            "Gambar tidak memuat QR code yang jelas atau formatnya tidak didukung. "
            "Pastikan gambar terang dan tidak terpotong, atau coba gunakan **Input Manual**."
        )
        markup = InlineKeyboardMarkup([
            [InlineKeyboardButton("⌨️ Coba Input Manual", callback_data="add_acc:manual")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
        ])
        await update.message.reply_text(fail_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        return

    try:
        parsed = parse_otpauth_uri(decoded_uri)
    except Exception as exc:
        await update.message.reply_text(f"❌ Format URI OTP tidak valid: {str(exc)}")
        return

    context.user_data["pending_account"] = parsed
    context.user_data["add_state"] = "awaiting_pin"
    clear_keypad_buffer(context.user_data, "add_acc_pin")

    emoji = get_issuer_emoji(parsed.get("issuer"))
    prompt_text = (
        f"📷 **QR Code Berhasil Terdeteksi!**\n\n"
        f"{emoji} **Akun**: {parsed['label']}\n"
        f"• **Issuer**: {parsed.get('issuer') or '-'}\n"
        f"• **Tipe**: {parsed['type'].upper()}\n\n"
        "Masukkan **PIN 6 digit** Anda untuk mengenkripsi dan menyimpan akun ini:\n\n"
        f"`{render_pin_display(0)}`"
    )
    markup = build_keypad_keyboard("add_acc_pin", show_cancel=True)
    await update.message.reply_text(prompt_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_choose_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    context.user_data["add_state"] = "awaiting_manual_secret"
    text = (
        "⌨️ **Input Secret Key Manual**\n\n"
        "Ketik dan kirimkan **Secret Key** (Base32) dari layanan Anda:\n"
        "Contoh: `JBSWY3DPEHPK3PXP`"
    )
    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Batal", callback_data="menu:back_to_main")]
    ])
    await query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_manual_secret_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("add_state") != "awaiting_manual_secret":
        return

    raw_secret = update.message.text or ""
    cleaned_secret = clean_base32_secret(raw_secret)

    if not cleaned_secret or not re.match(r"^[A-Z2-7=]+$", cleaned_secret):
        await update.message.reply_text(
            "❌ **Secret Key tidak valid!**\n\n"
            "Secret key Base32 hanya boleh berisi huruf A-Z dan angka 2-7 (tanpa spasi). "
            "Silakan ketik ulang Secret Key yang benar:"
        )
        return

    context.user_data["manual_secret"] = cleaned_secret
    context.user_data["add_state"] = "awaiting_manual_label"

    prompt_text = (
        "✅ **Secret Key Valid.**\n\n"
        "Sekarang, masukkan nama **Label / Layanan** untuk akun ini:\n"
        "Contoh: `GitHub: alice` atau `Google Work`"
    )
    await update.message.reply_text(prompt_text, parse_mode=ParseMode.MARKDOWN)


async def handle_manual_label_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if context.user_data.get("add_state") != "awaiting_manual_label":
        return

    label = (update.message.text or "").strip()
    if not label:
        await update.message.reply_text("Silakan masukkan nama label yang tidak kosong:")
        return

    secret = context.user_data.get("manual_secret")
    if not secret:
        await update.message.reply_text("Terjadi kesalahan sesi. Silakan ulangi dari menu Tambah Akun.")
        return

    if ":" in label:
        issuer = label.split(":", 1)[0].strip()
    else:
        issuer = label.split(" ", 1)[0].strip()

    context.user_data["pending_account"] = {
        "secret": secret,
        "label": label,
        "issuer": issuer,
        "type": "totp",
        "digits": 6,
        "period": 30,
        "counter": 0,
    }
    context.user_data["add_state"] = "awaiting_pin"
    clear_keypad_buffer(context.user_data, "add_acc_pin")

    emoji = get_issuer_emoji(issuer)
    prompt_text = (
        f"📝 **Konfirmasi Akun Baru**\n\n"
        f"{emoji} **Akun**: {label}\n"
        f"• **Issuer**: {issuer or '-'}\n"
        f"• **Tipe**: TOTP (30s)\n\n"
        "Masukkan **PIN 6 digit** Anda untuk mengenkripsi dan menyimpan akun ini:\n\n"
        f"`{render_pin_display(0)}`"
    )
    markup = build_keypad_keyboard("add_acc_pin", show_cancel=True)
    await update.message.reply_text(prompt_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_add_account_pin_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    key_val = parts[2]
    buf, is_complete, is_cancel = handle_keypad_press(
        context.user_data, "add_acc_pin", key_val, max_length=6
    )

    if is_cancel:
        clear_keypad_buffer(context.user_data, "add_acc_pin")
        context.user_data.pop("pending_account", None)
        context.user_data.pop("add_state", None)
        from handlers.menu import show_main_menu
        await show_main_menu(update, context)
        return

    if is_complete:
        pending = context.user_data.get("pending_account")
        if not pending:
            await query.edit_message_text("❌ Data akun tidak ditemukan. Silakan ulangi.")
            return

        session_factory = context.bot_data.get("session_factory")
        user_id = update.effective_user.id

        if session_factory:
            async with session_factory() as session:
                user_stmt = select(User).where(User.telegram_user_id == user_id)
                user = (await session.execute(user_stmt)).scalars().first()
                if not user:
                    await query.edit_message_text("❌ Pengguna tidak terdaftar.")
                    return

                if not verify_pin(buf, user.pin_hash_salt, user.pin_hash):
                    await record_failed_pin_attempt(session, user)
                    await log_action(session, user.id, "add_account", False)
                    clear_keypad_buffer(context.user_data, "add_acc_pin")

                    fail_text = (
                        "❌ **PIN Salah!**\n\n"
                        "Penyimpanan akun dibatalkan demi keamanan."
                    )
                    kb = InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")]
                    ])
                    await query.edit_message_text(fail_text, reply_markup=kb, parse_mode=ParseMode.MARKDOWN)
                    return

                await record_successful_pin_attempt(session, user)
                enc_key = derive_encryption_key(buf, user.kdf_salt)
                ciphertext, nonce = encrypt_secret(enc_key, pending["secret"])

                new_acc = Account(
                    user_id=user.id,
                    label=pending["label"],
                    issuer=pending.get("issuer"),
                    secret_encrypted=ciphertext,
                    nonce=nonce,
                    type=pending.get("type", "totp"),
                    digits=pending.get("digits", 6),
                    period=pending.get("period", 30),
                    hotp_counter=pending.get("counter", 0),
                )
                session.add(new_acc)
                await session.commit()
                await session.refresh(new_acc)

                await log_action(session, user.id, "add_account", True, account_id=new_acc.id)

        clear_keypad_buffer(context.user_data, "add_acc_pin")
        context.user_data.pop("pending_account", None)
        context.user_data.pop("add_state", None)
        context.user_data.pop("manual_secret", None)

        emoji = get_issuer_emoji(pending.get("issuer"))
        success_text = (
            f"✅ **Akun Berhasil Ditambahkan!**\n\n"
            f"{emoji} **{pending['label']}** telah dienkripsi dengan standar AES-256-GCM "
            f"dan tersimpan dengan aman."
        )
        success_kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔑 Lihat Kode", callback_data="menu:view_code")],
            [InlineKeyboardButton("🔙 Menu Utama", callback_data="menu:back_to_main")],
        ])
        await query.edit_message_text(success_text, reply_markup=success_kb, parse_mode=ParseMode.MARKDOWN)
    else:
        pending = context.user_data.get("pending_account", {})
        label = pending.get("label", "Akun Baru")
        prompt_text = (
            f"Masukkan **PIN 6 digit** Anda untuk mengenkripsi dan menyimpan **{label}**:\n\n"
            f"`{render_pin_display(len(buf))}`"
        )
        markup = build_keypad_keyboard("add_acc_pin", show_cancel=True)
        await query.edit_message_text(prompt_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
