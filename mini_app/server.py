import asyncio
import html
import json
import logging
import os
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from aiohttp import web
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import get_settings
from crypto.cipher import decrypt_secret, encrypt_secret
from crypto.kdf import derive_encryption_key, verify_pin
from db.models import Account, User
from mini_app.crypto_utils import MiniAppSessionManager, validate_telegram_init_data
from services.icon_service import get_issuer_emoji, get_issuer_info, get_issuer_slug
from services.lockout_service import (
    check_lockout,
    record_failed_pin_attempt,
    record_successful_pin_attempt,
)
from services.log_service import log_action
from services.otp_service import (
    clean_base32_secret,
    generate_hotp_code,
    generate_totp_code,
    get_totp_remaining_seconds,
)

logger = logging.getLogger("mini_app.server")

STATIC_DIR = Path(__file__).parent / "static"


def cors_headers() -> Dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Session-Token, X-Telegram-Init-Data",
    }


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

    async def handle_index(self, request: web.Request) -> web.FileResponse:
        index_file = STATIC_DIR / "index.html"
        if not index_file.exists():
            return web.Response(text="Mini App frontend static file not found.", status=404)
        return web.FileResponse(index_file)

    async def handle_status(self, request: web.Request) -> web.Response:
        return json_response({
            "status": "ok",
            "name": "Telegram 2FA Authenticator Mini App",
            "version": "1.0.0",
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

            # PIN correct
            await record_successful_pin_attempt(session, user)
            derived_key = derive_encryption_key(pin, user.kdf_salt)
            await log_action(session, user.id, "miniapp_login", success=True)

            # Create session
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

                # Generate live OTP code
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
                    # Secret is included to allow zero-latency client-side ticker
                    "secret": decrypted_secret,
                    # Rich Simple Icons metadata
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

        # Verify key works
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
            return json_response({
                "success": True,
                "account": {
                    "id": new_acc.id,
                    "label": new_acc.label,
                    "issuer": new_acc.issuer or "",
                    "type": new_acc.type,
                    "digits": new_acc.digits,
                    "period": new_acc.period,
                    "is_favorite": new_acc.is_favorite,
                    "code": generate_totp_code(cleaned_secret, digits, period),
                    "remaining_seconds": get_totp_remaining_seconds(period),
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

        acc_id = int(request.match_info["id"])
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

        acc_id = int(request.match_info["id"])
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


def create_mini_app(
    bot_token: str,
    session_factory: async_sessionmaker[AsyncSession],
    session_manager: Optional[MiniAppSessionManager] = None,
) -> web.Application:
    """Create and configure the aiohttp Web Application for Telegram Mini App."""
    app = web.Application()
    handler = MiniAppHandler(bot_token, session_factory, session_manager)

    # Routes
    app.router.add_get("/", handler.handle_index)
    app.router.add_get("/api/status", handler.handle_status)
    app.router.add_post("/api/init", handler.handle_init)
    app.router.add_post("/api/auth/pin", handler.handle_auth_pin)
    app.router.add_get("/api/accounts", handler.handle_get_accounts)
    app.router.add_post("/api/accounts", handler.handle_add_account)
    app.router.add_post("/api/accounts/{id}/favorite", handler.handle_toggle_favorite)
    app.router.add_delete("/api/accounts/{id}", handler.handle_delete_account)

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
