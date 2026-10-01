import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

from aiohttp import web
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import get_settings
from crypto.cipher import decrypt_secret, encrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt, hash_pin, verify_pin
from db.models import Account, AccessLog, User
from mini_app.crypto_utils import MiniAppSessionManager, validate_telegram_init_data
from services.icon_service import get_issuer_info
from services.lockout_service import (
    check_lockout,
    record_failed_pin_attempt,
    record_successful_pin_attempt,
)
from services.log_service import format_local_timestamp, log_action
from services.otp_service import (
    clean_base32_secret,
    generate_hotp_code,
    generate_totp_code,
    get_totp_remaining_seconds,
)

logger = logging.getLogger("mini_app.server")

STATIC_DIR = Path(__file__).parent / "static"


def security_headers() -> Dict[str, str]:
    """Strict HTTP security headers for Mini App serving with anti-caching."""
    return {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "clipboard-write=(self), clipboard-read=(self)",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
        "Content-Security-Policy": (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://telegram.org; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https://cdn.simpleicons.org; "
            "connect-src 'self'; "
            "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org tg:;"
        ),
    }


def cors_headers() -> Dict[str, str]:
    headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Session-Token, X-Telegram-Init-Data",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "clipboard-write=(self), clipboard-read=(self)",
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }
    return headers


def json_response(data: Any, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, headers=cors_headers())


async def handle_options(request: web.Request) -> web.Response:
    return web.Response(status=204, headers=cors_headers())


class MiniAppHandler:
    def __init__(
        self,
        bot_token: str,
        session_factory: async_sessionmaker[AsyncSession],
        session_manager: Optional[MiniAppSessionManager] = None,
    ) -> None:
        self.bot_token = bot_token
        self.session_factory = session_factory
        self.session_manager = session_manager or MiniAppSessionManager(default_ttl_seconds=300)

    def _extract_session(self, request: web.Request) -> Optional[Dict[str, Any]]:
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        if not token:
            token = request.headers.get("X-Session-Token", "").strip()
        if not token and "token" in request.query:
            token = request.query["token"]
        if not token:
            return None
        return self.session_manager.get_session(token)

    async def handle_index(self, request: web.Request) -> web.StreamResponse:
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            return web.Response(text="Mini App frontend static file not found.", status=404)

        import re, time
        v = int(time.time())
        try:
            content = index_file.read_text(encoding="utf-8")
            content = re.sub(r'/static/app\.js(\?[^"]*)?', f'/static/app.js?v={v}', content)
            content = re.sub(r'/static/style\.css(\?[^"]*)?', f'/static/style.css?v={v}', content)
            headers = security_headers()
            return web.Response(text=content, content_type="text/html", headers=headers)
        except Exception:
            return web.FileResponse(index_file, headers=security_headers())

    async def handle_status(self, request: web.Request) -> web.Response:
        settings = get_settings()
        return json_response({
            "status": "ok",
            "name": "Telegram 2FA Authenticator Mini App",
            "version": "1.0.0",
            "pin_length": settings.pin_length,
        })

    async def handle_init(self, request: web.Request) -> web.Response:
        """
        Verify Telegram WebApp initData and check if the user is registered in the bot.
        """
        try:
            body = await request.json()
        except Exception:
            return json_response({"error": "Invalid JSON body"}, status=400)

        init_data = body.get("init_data") or request.headers.get("X-Telegram-Init-Data", "")
        if not init_data:
            return json_response({"error": "Missing init_data"}, status=400)

        user_info = validate_telegram_init_data(init_data, self.bot_token)
        if not user_info:
            return json_response({"error": "Invalid or expired Telegram WebApp authentication"}, status=401)

        telegram_id = user_info.get("id")
        if not telegram_id:
            return json_response({"error": "Missing user ID in init_data"}, status=400)

        async with self.session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == telegram_id)
            user = (await session.execute(stmt)).scalars().first()

            if not user:
                return json_response({
                    "registered": False,
                    "telegram_id": telegram_id,
                    "first_name": user_info.get("first_name", ""),
                    "message": "Akun belum terdaftar. Silakan buka bot dan jalankan /start terlebih dahulu.",
                })

            is_locked, remaining_lockout = check_lockout(user)
            settings = get_settings()

            return json_response({
                "registered": True,
                "telegram_id": telegram_id,
                "first_name": user_info.get("first_name", ""),
                "pin_length": settings.pin_length,
                "is_locked": is_locked,
                "lockout_seconds": remaining_lockout,
            })

    async def handle_auth_pin(self, request: web.Request) -> web.Response:
        """
        Authenticate user with PIN inside Mini App and issue an active session token.
        """
        try:
            body = await request.json()
        except Exception:
            return json_response({"error": "Invalid JSON body"}, status=400)

        init_data = body.get("init_data")
        pin = str(body.get("pin", "")).strip()

        if not init_data or not pin:
            return json_response({"error": "init_data and pin are required"}, status=400)

        settings = get_settings()
        if len(pin) != settings.pin_length:
            return json_response({
                "success": False,
                "error": f"PIN harus terdiri dari {settings.pin_length} digit.",
            }, status=400)
        if not pin.isdigit():
            return json_response({
                "success": False,
                "error": "PIN harus berupa angka.",
            }, status=400)

        user_info = validate_telegram_init_data(init_data, self.bot_token)
        if not user_info:
            return json_response({"error": "Invalid Telegram authentication"}, status=401)

        telegram_id = user_info.get("id")

        async with self.session_factory() as session:
            stmt = select(User).where(User.telegram_user_id == telegram_id)
            user = (await session.execute(stmt)).scalars().first()

            if not user:
                return json_response({"error": "User not registered in bot"}, status=404)

            is_locked, remaining = check_lockout(user)
            if is_locked:
                return json_response({
                    "success": False,
                    "is_locked": True,
                    "lockout_seconds": remaining,
                    "error": f"Akun terkunci karena terlalu banyak kesalahan PIN. Tunggu {remaining} detik lagi.",
                }, status=403)

            is_valid_pin = verify_pin(pin, user.pin_hash_salt, user.pin_hash)
            if not is_valid_pin:
                await record_failed_pin_attempt(session, user)
                await log_action(session, user.id, "miniapp_login", success=False)
                locked_now, rem_now = check_lockout(user)
                return json_response({
                    "success": False,
                    "is_locked": locked_now,
                    "lockout_seconds": rem_now,
                    "error": "PIN salah. Silakan coba lagi.",
                }, status=401)

            await record_successful_pin_attempt(session, user)
            derived_key = derive_encryption_key(pin, user.kdf_salt)
            await log_action(session, user.id, "miniapp_login", success=True)

            token = self.session_manager.create_session(user.id, derived_key, ttl_seconds=300)

            return json_response({
                "success": True,
                "token": token,
                "ttl_seconds": 300,
                "first_name": user_info.get("first_name", ""),
            })

    async def handle_get_accounts(self, request: web.Request) -> web.Response:
        """
        List all 2FA accounts for the authenticated session with live OTP codes and Simple Icons metadata.
        """
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized or session expired"}, status=401)

        user_id = client_session["user_id"]
        derived_key = client_session["derived_key"]

        async with self.session_factory() as session:
            stmt = (
                select(Account)
                .where(Account.user_id == user_id)
                .order_by(Account.is_favorite.desc(), Account.sort_order.asc(), Account.created_at.asc())
            )
            accounts = (await session.execute(stmt)).scalars().all()

            results = []
            for acc in accounts:
                try:
                    decrypted_secret = decrypt_secret(derived_key, acc.secret_encrypted, acc.nonce)
                except Exception:
                    decrypted_secret = ""

                if acc.type == "hotp":
                    code = generate_hotp_code(decrypted_secret, acc.hotp_counter, acc.digits)
                    rem_sec = 0
                else:
                    code = generate_totp_code(decrypted_secret, acc.digits, acc.period)
                    rem_sec = get_totp_remaining_seconds(acc.period)

                issuer_meta = get_issuer_info(acc.issuer)

                results.append({
                    "id": acc.id,
                    "label": acc.label,
                    "issuer": acc.issuer or "",
                    "type": acc.type,
                    "digits": acc.digits,
                    "period": acc.period,
                    "hotp_counter": acc.hotp_counter,
                    "is_favorite": acc.is_favorite,
                    "code": code,
                    "remaining_seconds": rem_sec,
                    "secret": decrypted_secret,
                    "emoji": issuer_meta["emoji"],
                    "slug": issuer_meta["slug"],
                    "icon_url": issuer_meta["icon_url"],
                })

            await log_action(session, user_id, "miniapp_view_codes", success=True)
            return json_response({"accounts": results})

    async def handle_add_account(self, request: web.Request) -> web.Response:
        """
        Add a new 2FA account from the Mini App.
        """
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized or session expired"}, status=401)

        user_id = client_session["user_id"]
        derived_key = client_session["derived_key"]

        try:
            body = await request.json()
        except Exception:
            return json_response({"error": "Invalid JSON"}, status=400)

        label = str(body.get("label", "")).strip()
        secret_raw = str(body.get("secret", "")).strip()
        issuer = str(body.get("issuer", "")).strip() or None
        acc_type = str(body.get("type", "totp")).strip().lower()
        if acc_type not in ("totp", "hotp"):
            acc_type = "totp"

        digits = int(body.get("digits", 6))
        if digits not in (6, 8):
            digits = 6

        period = int(body.get("period", 30))
        if period not in (15, 30, 60):
            period = 30

        if not label:
            return json_response({"error": "Nama / Label akun tidak boleh kosong"}, status=400)

        cleaned_secret = clean_base32_secret(secret_raw)
        if not cleaned_secret:
            return json_response({"error": "Secret Key tidak valid (harus karakter Base32 valid)"}, status=400)

        try:
            generate_totp_code(cleaned_secret, digits, period)
        except Exception:
            return json_response({"error": "Secret Key tidak dapat digunakan untuk OTP"}, status=400)

        ciphertext, nonce = encrypt_secret(derived_key, cleaned_secret)

        async with self.session_factory() as session:
            new_acc = Account(
                user_id=user_id,
                label=label,
                issuer=issuer,
                secret_encrypted=ciphertext,
                nonce=nonce,
                type=acc_type,
                digits=digits,
                period=period,
                hotp_counter=0,
                is_favorite=False,
            )
            session.add(new_acc)
            await session.commit()
            await session.refresh(new_acc)

            await log_action(session, user_id, "miniapp_add_account", success=True, account_id=new_acc.id)

            issuer_meta = get_issuer_info(new_acc.issuer)
            if new_acc.type == "hotp":
                acc_code = generate_hotp_code(cleaned_secret, 0, digits)
                rem_sec = 0
            else:
                acc_code = generate_totp_code(cleaned_secret, digits, period)
                rem_sec = get_totp_remaining_seconds(period)

            return json_response({
                "success": True,
                "account": {
                    "id": new_acc.id,
                    "label": new_acc.label,
                    "issuer": new_acc.issuer or "",
                    "type": new_acc.type,
                    "digits": new_acc.digits,
                    "period": new_acc.period,
                    "hotp_counter": new_acc.hotp_counter,
                    "is_favorite": new_acc.is_favorite,
                    "code": acc_code,
                    "remaining_seconds": rem_sec,
                    "secret": cleaned_secret,
                    "emoji": issuer_meta["emoji"],
                    "slug": issuer_meta["slug"],
                    "icon_url": issuer_meta["icon_url"],
                },
            }, status=201)

    async def handle_toggle_favorite(self, request: web.Request) -> web.Response:
        """Toggle favorite status of an account."""
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        try:
            acc_id = int(request.match_info["id"])
        except (ValueError, KeyError):
            return json_response({"error": "Invalid account ID"}, status=400)
        user_id = client_session["user_id"]

        async with self.session_factory() as session:
            stmt = select(Account).where(Account.id == acc_id, Account.user_id == user_id)
            acc = (await session.execute(stmt)).scalars().first()
            if not acc:
                return json_response({"error": "Account not found"}, status=404)

            acc.is_favorite = not acc.is_favorite
            await session.commit()
            return json_response({"success": True, "is_favorite": acc.is_favorite})

    async def handle_delete_account(self, request: web.Request) -> web.Response:
        """Delete an account from the Mini App."""
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        try:
            acc_id = int(request.match_info["id"])
        except (ValueError, KeyError):
            return json_response({"error": "Invalid account ID"}, status=400)
        user_id = client_session["user_id"]

        async with self.session_factory() as session:
            stmt = select(Account).where(Account.id == acc_id, Account.user_id == user_id)
            acc = (await session.execute(stmt)).scalars().first()
            if not acc:
                return json_response({"error": "Account not found"}, status=404)

            await session.delete(acc)
            await session.commit()
            await log_action(session, user_id, "miniapp_delete_account", success=True, account_id=None)
            return json_response({"success": True})

    async def handle_hotp_next(self, request: web.Request) -> web.Response:
        """Increment HOTP counter and return the next code."""
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        try:
            acc_id = int(request.match_info["id"])
        except (ValueError, KeyError):
            return json_response({"error": "Invalid account ID"}, status=400)
        user_id = client_session["user_id"]
        derived_key = client_session["derived_key"]

        async with self.session_factory() as session:
            stmt = select(Account).where(Account.id == acc_id, Account.user_id == user_id)
            acc = (await session.execute(stmt)).scalars().first()
            if not acc:
                return json_response({"error": "Account not found"}, status=404)
            if acc.type != "hotp":
                return json_response({"error": "Account is not HOTP"}, status=400)

            acc.hotp_counter += 1
            decrypted_secret = decrypt_secret(derived_key, acc.secret_encrypted, acc.nonce)
            new_code = generate_hotp_code(decrypted_secret, acc.hotp_counter, acc.digits)
            await session.commit()
            await log_action(session, user_id, "miniapp_hotp_next", success=True, account_id=acc.id)

            return json_response({
                "success": True,
                "hotp_counter": acc.hotp_counter,
                "code": new_code,
            })

    async def handle_update_account(self, request: web.Request) -> web.Response:
        """Update account label and issuer."""
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        try:
            acc_id = int(request.match_info["id"])
        except (ValueError, KeyError):
            return json_response({"error": "Invalid account ID"}, status=400)
        user_id = client_session["user_id"]
        try:
            body = await request.json()
        except Exception:
            return json_response({"error": "Invalid JSON body"}, status=400)

        new_label = str(body.get("label", "")).strip()
        new_issuer = str(body.get("issuer", "")).strip()
        if not new_label:
            return json_response({"error": "Label cannot be empty"}, status=400)

        async with self.session_factory() as session:
            stmt = select(Account).where(Account.id == acc_id, Account.user_id == user_id)
            acc = (await session.execute(stmt)).scalars().first()
            if not acc:
                return json_response({"error": "Account not found"}, status=404)

            acc.label = new_label
            acc.issuer = new_issuer or None
            await session.commit()
            await log_action(session, user_id, "miniapp_edit_account", success=True, account_id=acc.id)
            meta = get_issuer_info(acc.issuer)
            return json_response({
                "success": True,
                "account": {
                    "id": acc.id,
                    "label": acc.label,
                    "issuer": acc.issuer or "",
                    "emoji": meta["emoji"],
                    "slug": meta["slug"],
                    "icon_url": meta["icon_url"],
                },
            })

    async def handle_change_pin(self, request: web.Request) -> web.Response:
        """Change Master PIN from within Mini App and re-encrypt all credentials."""
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        user_id = client_session["user_id"]
        derived_key = client_session["derived_key"]
        try:
            body = await request.json()
        except Exception:
            return json_response({"error": "Invalid JSON body"}, status=400)

        old_pin = str(body.get("old_pin", "")).strip()
        new_pin = str(body.get("new_pin", "")).strip()
        settings = get_settings()

        if len(new_pin) != settings.pin_length:
            return json_response({
                "success": False,
                "error": f"PIN baru harus terdiri dari {settings.pin_length} digit.",
            }, status=400)
        if not new_pin.isdigit():
            return json_response({
                "success": False,
                "error": "PIN baru harus berupa angka.",
            }, status=400)

        async with self.session_factory() as session:
            stmt = select(User).where(User.id == user_id)
            user = (await session.execute(stmt)).scalars().first()
            if not user:
                return json_response({"error": "User not found"}, status=404)

            if not verify_pin(old_pin, user.pin_hash_salt, user.pin_hash):
                await log_action(session, user_id, "miniapp_change_pin", success=False)
                return json_response({"success": False, "error": "PIN lama salah."}, status=401)

            new_pin_salt = generate_salt()
            new_kdf_salt = generate_salt()
            new_pin_hash = hash_pin(new_pin, new_pin_salt)
            new_derived_key = derive_encryption_key(new_pin, new_kdf_salt)

            acc_stmt = select(Account).where(Account.user_id == user_id)
            accounts = (await session.execute(acc_stmt)).scalars().all()
            for acc in accounts:
                secret = decrypt_secret(derived_key, acc.secret_encrypted, acc.nonce)
                new_enc, new_nonce = encrypt_secret(new_derived_key, secret)
                acc.secret_encrypted = new_enc
                acc.nonce = new_nonce

            user.pin_hash = new_pin_hash
            user.pin_hash_salt = new_pin_salt
            user.kdf_salt = new_kdf_salt
            await session.commit()
            await log_action(session, user_id, "miniapp_change_pin", success=True)

            client_session["derived_key"] = new_derived_key
            return json_response({"success": True, "message": "Master PIN berhasil diperbarui."})

    async def handle_get_audit_logs(self, request: web.Request) -> web.Response:
        """Fetch latest 15 audit logs for the user."""
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        user_id = client_session["user_id"]
        async with self.session_factory() as session:
            stmt = (
                select(AccessLog)
                .where(AccessLog.user_id == user_id)
                .order_by(AccessLog.created_at.desc())
                .limit(15)
            )
            logs = (await session.execute(stmt)).scalars().all()
            results = [
                {
                    "id": l.id,
                    "action": l.action,
                    "success": l.success,
                    "timestamp": format_local_timestamp(l.created_at, "%d/%m/%Y %H:%M:%S"),
                }
                for l in logs
            ]
            return json_response({"logs": results})

    async def handle_export_backup(self, request: web.Request) -> web.Response:
        """
        Export accounts backup.
        If passphrase is provided (min 4 characters), encrypts payload using AES-256-GCM + Argon2id
        compatible with Telegram Bot backup standard.
        """
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        user_id = client_session["user_id"]
        derived_key = client_session["derived_key"]

        passphrase = ""
        if request.method == "POST":
            try:
                body = await request.json()
                passphrase = str(body.get("passphrase", "")).strip()
            except Exception:
                passphrase = ""
        elif request.method == "GET":
            passphrase = str(request.query.get("passphrase", "")).strip()

        if not passphrase:
            return json_response({
                "success": False,
                "error": "Passphrase Enkripsi Backup wajib diisi (minimal 4 karakter).",
            }, status=400)

        if len(passphrase) < 4:
            return json_response({
                "success": False,
                "error": "Passphrase enkripsi minimal 4 karakter.",
            }, status=400)

        async with self.session_factory() as session:
            stmt = select(Account).where(Account.user_id == user_id).order_by(Account.created_at.asc())
            accounts = (await session.execute(stmt)).scalars().all()

            if not accounts:
                return json_response({"success": False, "error": "Belum ada akun tersimpan untuk diekspor."}, status=400)

            backup_items = []
            for acc in accounts:
                try:
                    sec = decrypt_secret(derived_key, acc.secret_encrypted, acc.nonce)
                except Exception:
                    sec = ""
                backup_items.append({
                    "label": acc.label,
                    "issuer": acc.issuer or "",
                    "secret": sec,
                    "type": acc.type,
                    "digits": acc.digits,
                    "period": acc.period,
                    "hotp_counter": acc.hotp_counter,
                    "is_favorite": acc.is_favorite,
                })

            from datetime import datetime
            from services.backup_service import export_accounts_backup
            import json

            filename = f"telegram_2fa_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

            try:
                backup_bytes = export_accounts_backup(backup_items, passphrase)
                envelope_data = json.loads(backup_bytes.decode("utf-8"))
            except Exception as e:
                return json_response({
                    "success": False,
                    "error": f"Gagal mengenkripsi cadangan: {e}",
                }, status=500)

            await log_action(session, user_id, "miniapp_export_backup", success=True)
            return json_response({
                "success": True,
                "is_encrypted": True,
                "total": len(backup_items),
                "filename": filename,
                "exported_at": format_local_timestamp(datetime.now(), "%Y-%m-%d %H:%M:%S"),
                "backup": envelope_data,
            })

    async def handle_import_backup(self, request: web.Request) -> web.Response:
        """Import accounts backup from JSON payload (encrypted envelope or accounts array)."""
        client_session = self._extract_session(request)
        if not client_session:
            return json_response({"error": "Unauthorized"}, status=401)

        user_id = client_session["user_id"]
        derived_key = client_session["derived_key"]

        try:
            body = await request.json()
        except Exception:
            return json_response({"error": "Invalid JSON body"}, status=400)

        passphrase = str(body.get("passphrase", "")).strip()
        raw_backup = body.get("backup")

        # If backup was sent as raw string (e.g. from textarea or file reader)
        if isinstance(raw_backup, str):
            try:
                import json
                raw_backup = json.loads(raw_backup.strip())
            except Exception:
                return json_response({"success": False, "error": "Format data cadangan JSON tidak valid."}, status=400)

        # If root body itself is the backup dictionary
        if raw_backup is None:
            if isinstance(body, dict) and ("ciphertext" in body or "accounts" in body):
                raw_backup = body

        accounts_to_import = []
        if isinstance(raw_backup, dict) and "ciphertext" in raw_backup:
            if not passphrase:
                return json_response({
                    "success": False,
                    "error": "Passphrase diperlukan untuk mendekripsi file cadangan terenkripsi.",
                }, status=400)

            from services.backup_service import import_accounts_backup
            import json
            try:
                backup_bytes = json.dumps(raw_backup).encode("utf-8")
                accounts_to_import = import_accounts_backup(backup_bytes, passphrase)
            except Exception:
                return json_response({
                    "success": False,
                    "error": "Passphrase salah atau file cadangan rusak / tidak valid.",
                }, status=400)
        elif isinstance(raw_backup, dict) and "accounts" in raw_backup and isinstance(raw_backup["accounts"], list):
            accounts_to_import = raw_backup["accounts"]
        elif isinstance(raw_backup, list):
            accounts_to_import = raw_backup
        elif isinstance(body.get("accounts"), list):
            accounts_to_import = body["accounts"]
        else:
            return json_response({"success": False, "error": "Format data cadangan tidak dikenali."}, status=400)

        if not accounts_to_import:
            return json_response({"success": False, "error": "Tidak ada akun valid yang ditemukan dalam cadangan."}, status=400)

        imported_count = 0
        async with self.session_factory() as session:
            for item in accounts_to_import:
                if not isinstance(item, dict):
                    continue
                sec_raw = str(item.get("secret", "")).strip()
                cleaned_sec = clean_base32_secret(sec_raw)
                if not cleaned_sec:
                    continue
                lbl = str(item.get("label", "Akun")).strip()[:64] or "Akun"
                iss = str(item.get("issuer", "")).strip()[:64] or None
                acc_t = str(item.get("type", "totp")).strip().lower()
                if acc_t not in ("totp", "hotp"):
                    acc_t = "totp"
                dig = 8 if item.get("digits") == 8 else 6
                try:
                    per = int(item.get("period", 30))
                except Exception:
                    per = 30
                try:
                    cnt = max(0, int(item.get("hotp_counter", item.get("counter", 0))))
                except Exception:
                    cnt = 0
                is_fav = bool(item.get("is_favorite", False))

                ciph, nonc = encrypt_secret(derived_key, cleaned_sec)
                new_acc = Account(
                    user_id=user_id,
                    label=lbl,
                    issuer=iss,
                    secret_encrypted=ciph,
                    nonce=nonc,
                    type=acc_t,
                    digits=dig,
                    period=per,
                    hotp_counter=cnt,
                    is_favorite=is_fav,
                )
                session.add(new_acc)
                imported_count += 1

            if imported_count > 0:
                await session.commit()
                await log_action(session, user_id, "miniapp_import_backup", success=True)
                return json_response({
                    "success": True,
                    "imported": imported_count,
                    "message": f"Berhasil mengimpor {imported_count} akun.",
                })
            else:
                return json_response({"success": False, "error": "Tidak ada akun valid yang dapat diimpor."}, status=400)


def create_mini_app(
    bot_token: str,
    session_factory: async_sessionmaker[AsyncSession],
    session_manager: Optional[MiniAppSessionManager] = None,
) -> web.Application:
    """Create and configure the aiohttp Web Application for Telegram Mini App."""
    @web.middleware
    async def security_middleware(request: web.Request, handler) -> web.StreamResponse:
        response = await handler(request)
        for k, v in security_headers().items():
            if k not in response.headers:
                response.headers[k] = v
        return response

    app = web.Application(middlewares=[security_middleware])
    handler = MiniAppHandler(bot_token, session_factory, session_manager)

    # Routes
    app.router.add_get("/", handler.handle_index)
    app.router.add_get("/api/status", handler.handle_status)
    app.router.add_post("/api/init", handler.handle_init)
    app.router.add_post("/api/auth/pin", handler.handle_auth_pin)
    app.router.add_get("/api/accounts", handler.handle_get_accounts)
    app.router.add_post("/api/accounts", handler.handle_add_account)
    app.router.add_post("/api/accounts/{id}/favorite", handler.handle_toggle_favorite)
    app.router.add_post("/api/accounts/{id}/hotp_next", handler.handle_hotp_next)
    app.router.add_put("/api/accounts/{id}", handler.handle_update_account)
    app.router.add_post("/api/accounts/{id}/update", handler.handle_update_account)
    app.router.add_delete("/api/accounts/{id}", handler.handle_delete_account)
    app.router.add_post("/api/settings/change_pin", handler.handle_change_pin)
    app.router.add_get("/api/settings/logs", handler.handle_get_audit_logs)
    app.router.add_get("/api/settings/backup", handler.handle_export_backup)
    app.router.add_post("/api/settings/backup", handler.handle_export_backup)
    app.router.add_post("/api/settings/import", handler.handle_import_backup)

    # Preflight OPTIONS
    app.router.add_route("OPTIONS", "/{tail:.*}", handle_options)

    # Static assets
    if STATIC_DIR.exists():
        app.router.add_static("/static", path=STATIC_DIR, name="static")

    return app


async def start_mini_app_server(
    bot_token: str,
    session_factory: async_sessionmaker[AsyncSession],
    host: str = "0.0.0.0",
    port: int = 8080,
) -> web.AppRunner:
    """Start the aiohttp web server asynchronously."""
    app = create_mini_app(bot_token, session_factory)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    logger.info("Telegram Mini App server listening on http://%s:%d", host, port)
    return runner
