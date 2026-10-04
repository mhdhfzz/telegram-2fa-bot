"""
Admin management and broadcast handlers for Telegram 2FA Authenticator Bot.
Provides dashboard control, bot statistics, and safe multi-recipient broadcasting with throttling.
"""

import asyncio
import logging
import os
import time
from typing import Optional, Set
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import ContextTypes
from sqlalchemy import distinct, func, select

from config import get_settings, is_admin_user
from db.models import Account, User

logger = logging.getLogger(__name__)


def check_admin_access(update: Update) -> bool:
    """Verify if the user initiating the command/callback is an authorized administrator."""
    user = update.effective_user
    if not user or not is_admin_user(user.id):
        return False
    return True


async def reject_unauthorized(update: Update) -> None:
    """Send access denied notification to unauthorized users."""
    text = (
        "⛔ **Akses Ditolak**\n\n"
        "Perintah ini hanya dapat diakses oleh Administrator Bot yang terdaftar."
    )
    if update.callback_query:
        try:
            await update.callback_query.answer("⛔ Akses ditolak: Khusus Administrator", show_alert=True)
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass
    elif update.effective_message:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def handle_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Display Admin Dashboard containing the list of all admin commands and quick interactive buttons.
    """
    if not check_admin_access(update):
        await reject_unauthorized(update)
        return

    # Clear any lingering admin workflow state
    context.user_data.pop("admin_state", None)
    context.user_data.pop("broadcast_draft", None)

    settings = get_settings()
    admin_id = update.effective_user.id if update.effective_user else "N/A"

    text = (
        "🛠️ **PANEL KONTROL ADMINISTRATOR**\n\n"
        f"Halo Admin (`ID: {admin_id}`)! Anda memiliki hak akses penuh ke manajemen bot.\n\n"
        "📋 **Daftar Perintah Admin (Command List):**\n"
        "• **/admin** - Buka panel kontrol & bantuan admin ini\n"
        "• **/broadcast** - Kirim pengumuman pesan ke seluruh pengguna bot\n"
        "• **/stats** - Lihat ringkasan metrik pengguna & database server\n"
        "• **/cancel** - Batalkan alur input/broadcast yang sedang aktif\n"
        "• **/menu** - Buka menu utama akun 2FA pribadi Anda\n\n"
        "💡 *Tips: Tekan tombol interaktif di bawah untuk eksekusi cepat tanpa repot mengetik perintah.*"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Kirim Broadcast", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("📊 Lihat Statistik", callback_data="admin:stats")],
        [
            InlineKeyboardButton("🔄 Refresh", callback_data="admin:menu"),
            InlineKeyboardButton("📱 Menu Utama", callback_data="menu:back_to_main"),
        ],
    ])

    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Display comprehensive bot and database usage statistics.
    """
    if not check_admin_access(update):
        await reject_unauthorized(update)
        return

    session_factory = context.bot_data.get("session_factory")
    settings = get_settings()

    total_users = 0
    total_accounts = 0
    active_users = 0

    if session_factory:
        async with session_factory() as session:
            total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0
            total_accounts = (await session.execute(select(func.count(Account.id)))).scalar() or 0
            active_users = (await session.execute(select(func.count(distinct(Account.user_id))))).scalar() or 0

    # Check database file size
    db_size_str = "N/A"
    if os.path.exists(settings.db_path):
        size_bytes = os.path.getsize(settings.db_path)
        if size_bytes < 1024:
            db_size_str = f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            db_size_str = f"{size_bytes / 1024:.1f} KB"
        else:
            db_size_str = f"{size_bytes / (1024 * 1024):.2f} MB"

    mini_app_status = "Aktif ✅" if settings.mini_app_enabled else "Nonaktif ❌"
    mini_app_url_info = settings.mini_app_url or f"http://{settings.mini_app_host}:{settings.mini_app_port}"

    text = (
        "📊 **STATISTIK SISTEM & PENGGUNA BOT**\n\n"
        "👥 **Metrik Pengguna & Akun:**\n"
        f"• Total Pengguna Terdaftar: **{total_users:,}** user\n"
        f"• Pengguna Aktif (Ada Akun): **{active_users:,}** user\n"
        f"• Total Akun 2FA Terenkripsi: **{total_accounts:,}** akun\n"
        f"• Rata-rata Akun per User Aktif: **{(total_accounts / active_users):.1f}**\n\n" if active_users > 0 else (
            f"• Total Pengguna Terdaftar: **{total_users:,}** user\n"
            f"• Pengguna Aktif (Ada Akun): **{active_users:,}** user\n"
            f"• Total Akun 2FA Terenkripsi: **{total_accounts:,}** akun\n\n"
        )
    )
    text += (
        "⚙️ **Konfigurasi & Server:**\n"
        f"• Panjang Master PIN: **{settings.pin_length} digit**\n"
        f"• Auto-Delete Timer: **{settings.auto_delete_seconds} detik**\n"
        f"• Ukuran Database ({os.path.basename(settings.db_path)}): **{db_size_str}**\n"
        f"• Status Mini App: **{mini_app_status}**\n"
        f"• Endpoint Mini App: `{mini_app_url_info}`\n"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Buat Pesan Broadcast", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("🔙 Kembali ke Panel Admin", callback_data="admin:menu")],
    ])

    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Prompt admin to write/send the broadcast message content.
    """
    if not check_admin_access(update):
        await reject_unauthorized(update)
        return

    session_factory = context.bot_data.get("session_factory")
    total_users = 0
    if session_factory:
        async with session_factory() as session:
            total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0

    context.user_data["admin_state"] = "awaiting_broadcast_content"
    context.user_data.pop("broadcast_draft", None)

    text = (
        "📢 **KIRIM PESAN BROADCAST KE SELURUH PENGGUNA**\n\n"
        f"👥 **Jumlah Target:** **{total_users:,}** pengguna terdaftar.\n\n"
        "Silakan **ketik atau kirimkan teks pesan** yang ingin Anda siarkan sekarang.\n"
        "Anda dapat menggunakan format teks tebal, miring, monospace, emoji, atau link.\n\n"
        "⚠️ *Pesan TIDAK AKAN langsung dikirim. Bot akan menampilkan pratinjau (preview) terlebih dahulu untuk persetujuan Anda.*\n\n"
        "Ketik **/cancel** atau tekan tombol di bawah untuk membatalkan."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Batalkan", callback_data="admin:broadcast_cancel")]
    ])

    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_broadcast_content_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Receive the broadcast content from admin and display a preview with confirmation buttons.
    """
    if not check_admin_access(update):
        await reject_unauthorized(update)
        return

    content = (update.effective_message.text or "").strip()
    if not content:
        await update.effective_message.reply_text(
            "⚠️ Pesan broadcast tidak boleh kosong. Silakan kirimkan teks pesan Anda:"
        )
        return

    context.user_data["broadcast_draft"] = content

    session_factory = context.bot_data.get("session_factory")
    total_users = 0
    if session_factory:
        async with session_factory() as session:
            total_users = (await session.execute(select(func.count(User.id)))).scalar() or 0

    preview_text = (
        "📢 **PRATINJAU BROADCAST (PREVIEW)**\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{content}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 **Target Pengiriman:** **{total_users:,}** pengguna terdaftar\n\n"
        "Apakah Anda yakin ingin mengirimkan pesan ini ke seluruh pengguna sekarang?"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Konfirmasi & Kirim Sekarang", callback_data="admin:broadcast_confirm")],
        [InlineKeyboardButton("✏️ Tulis Ulang Pesan", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="admin:broadcast_cancel")],
    ])

    await update.effective_message.reply_text(preview_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Execute broadcast loop to all users with throttling and error handling.
    """
    if not check_admin_access(update):
        await reject_unauthorized(update)
        return

    query = update.callback_query
    if query:
        await query.answer()

    draft = context.user_data.get("broadcast_draft")
    if not draft:
        if query:
            await query.edit_message_text(
                "⚠️ Draf pesan broadcast tidak ditemukan atau sesi telah berakhir.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Panel Admin", callback_data="admin:menu")]
                ]),
            )
        return

    session_factory = context.bot_data.get("session_factory")
    user_ids = []
    if session_factory:
        async with session_factory() as session:
            stmt = select(User.telegram_user_id)
            user_ids = [uid for uid in (await session.execute(stmt)).scalars().all()]

    total_target = len(user_ids)
    if total_target == 0:
        if query:
            await query.edit_message_text(
                "ℹ️ Belum ada pengguna lain yang terdaftar di database untuk menerima broadcast.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Kembali ke Panel Admin", callback_data="admin:menu")]
                ]),
            )
        return

    # Update message to show sending status
    status_msg = None
    if query:
        status_msg = await query.edit_message_text(
            f"⏳ **Mengirimkan Broadcast...**\n"
            f"Memproses pengiriman ke {total_target} pengguna.\n"
            "Mohon jangan tutup obrolan hingga laporan selesai.",
            parse_mode=ParseMode.MARKDOWN,
        )

    start_time = time.time()
    success_count = 0
    blocked_count = 0
    failed_count = 0

    outbound_text = f"📢 **PENGUMUMAN DARI ADMIN**\n\n{draft}"

    for target_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text=outbound_text,
                parse_mode=ParseMode.MARKDOWN,
                disable_web_page_preview=True,
            )
            success_count += 1
        except Forbidden:
            # User blocked the bot or account deleted
            blocked_count += 1
            logger.info("Broadcast skipped for user %s: Bot blocked/deactivated", target_id)
        except BadRequest as e:
            # Formatting error fallback: send as plain text
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=f"📢 PENGUMUMAN DARI ADMIN\n\n{draft}",
                    disable_web_page_preview=True,
                )
                success_count += 1
            except Exception:
                failed_count += 1
                logger.warning("Broadcast failed for user %s: %s", target_id, e)
        except Exception as exc:
            failed_count += 1
            logger.warning("Broadcast error for user %s: %s", target_id, exc)

        # Anti-flood throttling (25-30 msg/sec limit safety)
        await asyncio.sleep(0.04)

    duration = round(time.time() - start_time, 1)

    # Clean up admin workflow state
    context.user_data.pop("admin_state", None)
    context.user_data.pop("broadcast_draft", None)

    report_text = (
        "🎉 **BROADCAST SELESAI DIKIRIMKAN!**\n\n"
        "📊 **Laporan Statistik Pengiriman:**\n"
        f"• 👥 Total Target: **{total_target:,}** pengguna\n"
        f"• ✅ Berhasil Terkirim: **{success_count:,}**\n"
        f"• 🚫 Diblokir / Akun Nonaktif: **{blocked_count:,}**\n"
        f"• ⚠️ Gagal Lainnya: **{failed_count:,}**\n"
        f"• ⏱️ Durasi Waktu: **{duration} detik**\n"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Buat Broadcast Baru", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("🔙 Kembali ke Panel Admin", callback_data="admin:menu")],
    ])

    if status_msg:
        try:
            await status_msg.edit_text(report_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(report_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    elif update.effective_message:
        await update.effective_message.reply_text(report_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)


async def handle_broadcast_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Cancel current broadcast flow and return to admin dashboard.
    """
    context.user_data.pop("admin_state", None)
    context.user_data.pop("broadcast_draft", None)

    text = "❌ Pengiriman broadcast telah dibatalkan."

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Panel Admin", callback_data="admin:menu")],
        [InlineKeyboardButton("📱 Menu Utama", callback_data="menu:back_to_main")],
    ])

    if update.callback_query:
        try:
            await update.callback_query.answer("Broadcast dibatalkan")
            await update.callback_query.edit_message_text(text, reply_markup=markup)
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup)
