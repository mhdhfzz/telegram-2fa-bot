"""
Admin management and broadcast handlers for Telegram 2FA Authenticator Bot.
Provides dashboard control, bot statistics, and safe multi-recipient broadcasting with Telegram HTML support and throttling.
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
        "⛔ <b>Akses Ditolak</b>\n\n"
        "Perintah ini hanya dapat diakses oleh Administrator Bot yang terdaftar."
    )
    if update.callback_query:
        try:
            await update.callback_query.answer("⛔ Akses ditolak: Khusus Administrator", show_alert=True)
            await update.callback_query.edit_message_text(text, parse_mode=ParseMode.HTML)
        except Exception:
            pass
    elif update.effective_message:
        await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)


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

    admin_id = update.effective_user.id if update.effective_user else "N/A"

    text = (
        "🛠️ <b>PANEL KONTROL ADMINISTRATOR</b>\n\n"
        f"Halo Admin (<code>ID: {admin_id}</code>)! Anda memiliki hak akses penuh ke manajemen bot.\n\n"
        "📋 <b>Daftar Perintah Admin (Command List):</b>\n"
        "• <b>/admin</b> — Buka panel kontrol & bantuan admin ini\n"
        "• <b>/broadcast</b> — Kirim pengumuman pesan ke seluruh pengguna bot (Support HTML & Plain)\n"
        "• <b>/stats</b> — Lihat ringkasan metrik pengguna & database server\n"
        "• <b>/cancel</b> — Batalkan alur input/broadcast yang sedang aktif\n"
        "• <b>/menu</b> — Buka menu utama akun 2FA pribadi Anda\n\n"
        "💡 <i>Tips: Tekan tombol interaktif di bawah untuk eksekusi cepat tanpa repot mengetik perintah.</i>"
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
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "entity" in str(e).lower() or "parse" in str(e).lower():
                await update.callback_query.edit_message_text(text, reply_markup=markup)
            else:
                raise
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup)
    elif update.effective_message:
        try:
            await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "entity" in str(e).lower() or "parse" in str(e).lower():
                await update.effective_message.reply_text(text, reply_markup=markup)
            else:
                raise


async def handle_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Display comprehensive bot and database usage statistics using Telegram HTML formatting.
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
    db_filename = os.path.basename(settings.db_path)

    text = (
        "📊 <b>STATISTIK SISTEM & PENGGUNA BOT</b>\n\n"
        "👥 <b>Metrik Pengguna & Akun:</b>\n"
        f"• Total Pengguna Terdaftar: <b>{total_users:,}</b> user\n"
        f"• Pengguna Aktif (Ada Akun): <b>{active_users:,}</b> user\n"
        f"• Total Akun 2FA Terenkripsi: <b>{total_accounts:,}</b> akun\n"
    )
    if active_users > 0:
        text += f"• Rata-rata Akun per User: <b>{(total_accounts / active_users):.1f}</b>\n\n"
    else:
        text += "\n"

    text += (
        "⚙️ <b>Konfigurasi & Server:</b>\n"
        f"• Panjang Master PIN: <b>{settings.pin_length} digit</b>\n"
        f"• Auto-Delete Timer: <b>{settings.auto_delete_seconds} detik</b>\n"
        f"• Ukuran Database (<code>{db_filename}</code>): <b>{db_size_str}</b>\n"
        f"• Status Mini App: <b>{mini_app_status}</b>\n"
        f"• Endpoint Mini App: <code>{mini_app_url_info}</code>\n"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Buat Pesan Broadcast", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("🔙 Kembali ke Panel Admin", callback_data="admin:menu")],
    ])

    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "entity" in str(e).lower() or "parse" in str(e).lower():
                await update.callback_query.edit_message_text(text, reply_markup=markup)
            else:
                raise
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup)
    elif update.effective_message:
        try:
            await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except BadRequest as e:
            if "entity" in str(e).lower() or "parse" in str(e).lower():
                await update.effective_message.reply_text(text, reply_markup=markup)
            else:
                raise


async def handle_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Prompt admin to write/send the broadcast message content with Telegram HTML syntax guide.
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
        "📢 <b>KIRIM PESAN BROADCAST KE SELURUH PENGGUNA</b>\n\n"
        f"👥 <b>Jumlah Target:</b> <b>{total_users:,}</b> pengguna terdaftar.\n\n"
        "Silakan <b>ketik atau kirimkan teks pesan</b> yang ingin Anda siarkan sekarang.\n\n"
        "✨ <b>Dukungan Format HTML Telegram & Emoji:</b>\n"
        "• <code>&lt;b&gt;teks tebal&lt;/b&gt;</code> → <b>teks tebal</b>\n"
        "• <code>&lt;i&gt;teks miring&lt;/i&gt;</code> → <i>teks miring</i>\n"
        "• <code>&lt;code&gt;kode monospace&lt;/code&gt;</code> → <code>kode monospace</code>\n"
        "• <code>&lt;a href=\"https://link.com\"&gt;nama link&lt;/a&gt;</code> → tautan link\n"
        "• <code>&lt;tg-spoiler&gt;teks sensor&lt;/tg-spoiler&gt;</code> → sensor spoiler\n\n"
        "⚠️ <i>Pesan TIDAK AKAN langsung dikirim. Bot akan menampilkan pratinjau (preview) terlebih dahulu untuk persetujuan Anda.</i>\n\n"
        "Ketik <b>/cancel</b> atau tekan tombol di bawah untuk membatalkan."
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("❌ Batalkan", callback_data="admin:broadcast_cancel")]
    ])

    if update.callback_query:
        try:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif update.effective_message:
        await update.effective_message.reply_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


async def handle_broadcast_content_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Receive the broadcast content from admin and display a preview supporting Telegram HTML.
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
        "📢 <b>PRATINJAU BROADCAST (PREVIEW)</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        f"{content}\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        f"👥 <b>Target Pengiriman:</b> <b>{total_users:,}</b> pengguna terdaftar\n\n"
        "Apakah Anda yakin ingin mengirimkan pesan ini ke seluruh pengguna sekarang?"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Konfirmasi & Kirim Sekarang", callback_data="admin:broadcast_confirm")],
        [InlineKeyboardButton("✏️ Tulis Ulang Pesan", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("❌ Batalkan", callback_data="admin:broadcast_cancel")],
    ])

    # Try HTML first, fallback to Markdown, then Plain Text
    try:
        await update.effective_message.reply_text(preview_text, reply_markup=markup, parse_mode=ParseMode.HTML)
    except BadRequest:
        try:
            await update.effective_message.reply_text(preview_text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
        except BadRequest:
            await update.effective_message.reply_text(preview_text, reply_markup=markup)


async def handle_broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Execute broadcast loop to all users with Telegram HTML support, throttling, and graceful fallbacks.
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
            f"⏳ <b>Mengirimkan Broadcast...</b>\n"
            f"Memproses pengiriman ke {total_target} pengguna.\n"
            "Mohon jangan tutup obrolan hingga laporan selesai.",
            parse_mode=ParseMode.HTML,
        )

    start_time = time.time()
    success_count = 0
    blocked_count = 0
    failed_count = 0

    outbound_html = f"📢 <b>PENGUMUMAN DARI ADMIN</b>\n\n{draft}"
    outbound_md = f"📢 **PENGUMUMAN DARI ADMIN**\n\n{draft}"
    outbound_plain = f"📢 PENGUMUMAN DARI ADMIN\n\n{draft}"

    for target_id in user_ids:
        try:
            # 1. Try sending with HTML format
            await context.bot.send_message(
                chat_id=target_id,
                text=outbound_html,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
            success_count += 1
        except Forbidden:
            # User blocked the bot or account deleted
            blocked_count += 1
            logger.info("Broadcast skipped for user %s: Bot blocked/deactivated", target_id)
        except BadRequest as e:
            # 2. If HTML failed, try Markdown format
            try:
                await context.bot.send_message(
                    chat_id=target_id,
                    text=outbound_md,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
                success_count += 1
            except BadRequest:
                # 3. If Markdown also failed, fallback to plain text
                try:
                    await context.bot.send_message(
                        chat_id=target_id,
                        text=outbound_plain,
                        disable_web_page_preview=True,
                    )
                    success_count += 1
                except Exception:
                    failed_count += 1
                    logger.warning("Broadcast failed for user %s: %s", target_id, e)
            except Exception:
                failed_count += 1
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
        "🎉 <b>BROADCAST SELESAI DIKIRIMKAN!</b>\n\n"
        "📊 <b>Laporan Statistik Pengiriman:</b>\n"
        f"• 👥 Total Target: <b>{total_target:,}</b> pengguna\n"
        f"• ✅ Berhasil Terkirim: <b>{success_count:,}</b>\n"
        f"• 🚫 Diblokir / Akun Nonaktif: <b>{blocked_count:,}</b>\n"
        f"• ⚠️ Gagal Lainnya: <b>{failed_count:,}</b>\n"
        f"• ⏱️ Durasi Waktu: <b>{duration} detik</b>\n"
    )

    markup = InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Buat Broadcast Baru", callback_data="admin:broadcast_start")],
        [InlineKeyboardButton("🔙 Kembali ke Panel Admin", callback_data="admin:menu")],
    ])

    if status_msg:
        try:
            await status_msg.edit_text(report_text, reply_markup=markup, parse_mode=ParseMode.HTML)
        except Exception:
            if update.effective_message:
                await update.effective_message.reply_text(report_text, reply_markup=markup, parse_mode=ParseMode.HTML)
    elif update.effective_message:
        await update.effective_message.reply_text(report_text, reply_markup=markup, parse_mode=ParseMode.HTML)


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
