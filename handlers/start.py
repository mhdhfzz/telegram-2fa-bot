from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from crypto.kdf import generate_salt, hash_pin
from crypto.recovery import generate_recovery_phrase, hash_recovery_phrase
from db.models import User
from handlers.keypad import (
    build_keypad_keyboard,
    clear_keypad_buffer,
    handle_keypad_press,
    render_pin_display,
)


async def auto_delete_message_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = context.job.chat_id
        message_id = context.job.data
        if chat_id and message_id:
            await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def handle_start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    session_factory = context.bot_data.get("session_factory")
    user_id = update.effective_user.id

    if session_factory:
        async with session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == user_id)
            res = await session.execute(stmt)
            user = res.scalars().first()
            if user:
                from handlers.menu import show_main_menu
                await show_main_menu(update, context)
                return

    context.user_data["setup_step"] = "pin1"
    context.user_data["setup_pin_1"] = ""
    clear_keypad_buffer(context.user_data, "setup_pin_2")

    text = (
        "🔐 **Selamat datang di Telegram 2FA Authenticator!**\n\n"
        "Data akun Anda akan dienkripsi dengan standar AES-256-GCM menggunakan PIN pribadi Anda.\n\n"
        "Silakan buat **PIN 6 digit** Anda menggunakan keypad di bawah:\n\n"
        f"`{render_pin_display(0)}`"
    )
    keyboard = build_keypad_keyboard("setup_pin", show_cancel=False)

    if update.message:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )
    elif update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN,
        )


async def handle_setup_pin_keypad(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    data = query.data or ""
    parts = data.split(":")
    if len(parts) < 3:
        return

    prefix, _, key_val = parts[0], parts[1], parts[2]

    if prefix == "setup_pin":
        buf, is_complete, _ = handle_keypad_press(
            context.user_data, "setup_pin_1", key_val, max_length=6
        )
        if is_complete:
            context.user_data["setup_step"] = "pin2"
            context.user_data["setup_pin_2"] = ""
            confirm_text = (
                "Silakan **konfirmasi ulang** PIN 6 digit Anda:\n\n"
                f"`{render_pin_display(0)}`"
            )
            confirm_kb = build_keypad_keyboard("setup_confirm", show_cancel=False)
            await query.edit_message_text(
                confirm_text,
                reply_markup=confirm_kb,
                parse_mode=ParseMode.MARKDOWN,
            )
        else:
            text = (
                "Silakan buat **PIN 6 digit** Anda menggunakan keypad di bawah:\n\n"
                f"`{render_pin_display(len(buf))}`"
            )
            kb = build_keypad_keyboard("setup_pin", show_cancel=False)
            await query.edit_message_text(
                text,
                reply_markup=kb,
                parse_mode=ParseMode.MARKDOWN,
            )

    elif prefix == "setup_confirm":
        buf2, is_complete2, _ = handle_keypad_press(
            context.user_data, "setup_pin_2", key_val, max_length=6
        )
        if is_complete2:
            pin1 = context.user_data.get("setup_pin_1", "")
            if buf2 != pin1:
                context.user_data["setup_step"] = "pin1"
                clear_keypad_buffer(context.user_data, "setup_pin_1")
                clear_keypad_buffer(context.user_data, "setup_pin_2")

                mismatch_text = (
                    "❌ **PIN tidak cocok!**\n\n"
                    "Silakan buat PIN kembali dari awal:\n\n"
                    f"`{render_pin_display(0)}`"
                )
                kb = build_keypad_keyboard("setup_pin", show_cancel=False)
                await query.edit_message_text(
                    mismatch_text,
                    reply_markup=kb,
                    parse_mode=ParseMode.MARKDOWN,
                )
                return

            session_factory = context.bot_data.get("session_factory")
            pin_salt = generate_salt()
            kdf_salt = generate_salt()
            pin_hash_val = hash_pin(pin1, pin_salt)

            phrase = generate_recovery_phrase(language="en")
            phrase_hash_val = hash_recovery_phrase(phrase)

            if session_factory:
                async with session_factory() as session:
                    new_user = User(
                        telegram_user_id=update.effective_user.id,
                        pin_hash=pin_hash_val,
                        pin_hash_salt=pin_salt,
                        kdf_salt=kdf_salt,
                        recovery_phrase_hash=phrase_hash_val,
                    )
                    session.add(new_user)
                    await session.commit()

            clear_keypad_buffer(context.user_data, "setup_pin_1")
            clear_keypad_buffer(context.user_data, "setup_pin_2")
            context.user_data.pop("setup_step", None)

            phrase_formatted = " ".join(phrase)
            success_text = (
                "✅ **PIN Berhasil Dibuat!**\n\n"
                "⚠️ **PENTING: Simpan 12 Kata Recovery Phrase Ini!**\n"
                "Kata-kata ini hanya ditampilkan **SEKALI** untuk memulihkan akun jika Anda lupa PIN. "
                "Jika PIN dan Recovery Phrase hilang, data akun Anda **TIDAK BISA** dipulihkan.\n\n"
                f"`{phrase_formatted}`\n\n"
                "⏱️ *Pesan ini akan otomatis dihapus dalam 30 detik demi keamanan.*"
            )
            confirm_markup = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Saya Sudah Mencatat", callback_data="confirm_phrase")]
            ])

            await query.edit_message_text(
                success_text,
                reply_markup=confirm_markup,
                parse_mode=ParseMode.MARKDOWN,
            )

            if context.job_queue and update.effective_chat:
                context.job_queue.run_once(
                    auto_delete_message_job,
                    when=30,
                    chat_id=update.effective_chat.id,
                    data=query.message.message_id,
                )
        else:
            confirm_text = (
                "Silakan **konfirmasi ulang** PIN 6 digit Anda:\n\n"
                f"`{render_pin_display(len(buf2))}`"
            )
            confirm_kb = build_keypad_keyboard("setup_confirm", show_cancel=False)
            await query.edit_message_text(
                confirm_text,
                reply_markup=confirm_kb,
                parse_mode=ParseMode.MARKDOWN,
            )


async def handle_confirm_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()

    try:
        await query.message.delete()
    except Exception:
        pass

    from handlers.menu import show_main_menu
    await show_main_menu(update, context)
