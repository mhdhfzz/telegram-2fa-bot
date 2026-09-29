import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import parse_qsl


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 3600,
) -> Optional[Dict[str, Any]]:
    """
    Validate initData string received from Telegram WebApp.
    Implements official Telegram WebApp HMAC-SHA256 signature verification:
    1. Parse query string and extract 'hash'.
    2. Sort remaining key-value pairs alphabetically and join with newlines.
    3. Generate secret_key = HMAC_SHA256("WebAppData", bot_token).
    4. Compute expected_hash = HMAC_SHA256(secret_key, data_check_string).
    5. Check timestamp freshness (auth_date).
    6. Return parsed user dictionary if valid, None otherwise.
    """
    if not init_data or not bot_token:
        return None

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        if "hash" not in parsed:
            return None

        received_hash = parsed.pop("hash")

        # Verify timestamp freshness
        auth_date_str = parsed.get("auth_date")
        if not auth_date_str:
            return None
        auth_date = int(auth_date_str)
        if time.time() - auth_date > max_age_seconds:
            return None

        # Build data-check-string (sorted key=value joined by \n)
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

        # Secret key = HMAC-SHA256(key=b"WebAppData", data=bot_token)
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=bot_token.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()

        # Calculated HMAC = HMAC-SHA256(key=secret_key, data=data_check_string)
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash.lower(), received_hash.lower()):
            return None

        # Extract user data
        user_json = parsed.get("user")
        if not user_json:
            return None

        user_data = json.loads(user_json)
        return user_data

    except Exception:
        return None


class MiniAppSessionManager:
    """
    In-memory session manager for authenticated Mini App clients.
    Stores the derived encryption key and user identity for a temporary TTL,
    avoiding repeated expensive Argon2id hashes while ensuring automatic expiry.
    """

    def __init__(self, default_ttl_seconds: int = 300) -> None:
        self.default_ttl = default_ttl_seconds
        # session_token -> {"user_id": int, "derived_key": bytes, "expires_at": float}
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def create_session(self, user_id: int, derived_key: bytes, ttl_seconds: Optional[int] = None) -> str:
        self.cleanup_expired()
        token = secrets.token_urlsafe(32)
        ttl = ttl_seconds if ttl_seconds is not None else self.default_ttl
        self._sessions[token] = {
            "user_id": user_id,
            "derived_key": derived_key,
            "expires_at": time.time() + ttl,
        }
        return token

    def get_session(self, token: str) -> Optional[Dict[str, Any]]:
        self.cleanup_expired()
        session = self._sessions.get(token)
        if not session:
            return None
        if time.time() > session["expires_at"]:
            self._sessions.pop(token, None)
            return None
        return session

    def touch_session(self, token: str, extension_seconds: Optional[int] = None) -> bool:
        session = self.get_session(token)
        if not session:
            return False
        ext = extension_seconds if extension_seconds is not None else self.default_ttl
        session["expires_at"] = time.time() + ext
        return True

    def invalidate_session(self, token: str) -> None:
        self._sessions.pop(token, None)

    def cleanup_expired(self) -> None:
        now = time.time()
        expired_keys = [k for k, v in self._sessions.items() if v["expires_at"] < now]
        for k in expired_keys:
            self._sessions.pop(k, None)
