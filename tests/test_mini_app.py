import hashlib
import hmac
import json
import time
from urllib.parse import urlencode

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from config import get_settings
from crypto.cipher import encrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt, hash_pin
from db.models import Account, Base, User
from db.session import get_async_engine, get_session_factory
from mini_app.crypto_utils import MiniAppSessionManager, validate_telegram_init_data
from mini_app.server import create_mini_app
from services.icon_service import get_issuer_emoji, get_issuer_icon_url, get_issuer_info, get_issuer_slug


def generate_mock_init_data(bot_token: str, user_dict: dict, auth_date: int = None) -> str:
    """Generate a cryptographically valid Telegram WebApp initData string."""
    if auth_date is None:
        auth_date = int(time.time())

    params = {
        "auth_date": str(auth_date),
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user_dict, separators=(",", ":")),
    }

    # Data check string: alphabetical key=value separated by \n
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))

    # Secret key = HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    hash_val = hmac.new(secret_key, data_check_string.encode("utf-8"), hashlib.sha256).hexdigest()

    params["hash"] = hash_val
    return urlencode(params)


def test_simple_icons_mapping():
    """Verify Simple Icons slug mapping and metadata generation."""
    # Direct slug matches
    assert get_issuer_slug("Google") == "google"
    assert get_issuer_slug("GitHub") == "github"
    assert get_issuer_slug("Discord") == "discord"
    assert get_issuer_slug("Amazon Web Services") == "amazonwebservices"
    assert get_issuer_slug("Steam") == "steam"
    assert get_issuer_slug("Binance") == "binance"
    assert get_issuer_slug("NonExistentBrand12345") is None
    assert get_issuer_slug(None) is None

    # Icon URL generation
    url = get_issuer_icon_url("GitHub")
    assert url == "https://cdn.simpleicons.org/github"
    url_colored = get_issuer_icon_url("Google", color="white")
    assert url_colored == "https://cdn.simpleicons.org/google/white"
    assert get_issuer_icon_url("UnknownXYZ") is None

    # Unified info
    info = get_issuer_info("GitHub")
    assert info["slug"] == "github"
    assert info["emoji"] == "🐙"
    assert info["icon_url"] == "https://cdn.simpleicons.org/github"

    unknown_info = get_issuer_info("MysteriousApp")
    assert unknown_info["slug"] is None
    assert unknown_info["emoji"] == "🔐"
    assert unknown_info["icon_url"] is None


def test_telegram_init_data_validation():
    bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    user_data = {"id": 987654321, "first_name": "Antigravity", "username": "agytester"}

    # 1. Valid signature
    valid_init_data = generate_mock_init_data(bot_token, user_data)
    result = validate_telegram_init_data(valid_init_data, bot_token)
    assert result is not None
    assert result["id"] == 987654321
    assert result["first_name"] == "Antigravity"

    # 2. Tampered token/secret
    result_bad_token = validate_telegram_init_data(valid_init_data, "WRONG_TOKEN")
    assert result_bad_token is None

    # 3. Tampered data
    tampered_data = valid_init_data.replace("Antigravity", "Hacker")
    result_tampered = validate_telegram_init_data(tampered_data, bot_token)
    assert result_tampered is None

    # 4. Expired auth_date (older than 86400s)
    old_time = int(time.time()) - 90000
    expired_init_data = generate_mock_init_data(bot_token, user_data, auth_date=old_time)
    result_expired = validate_telegram_init_data(expired_init_data, bot_token, max_age_seconds=86400)
    assert result_expired is None

    # 5. Empty or missing hash
    assert validate_telegram_init_data("", bot_token) is None
    assert validate_telegram_init_data("query_id=123", bot_token) is None


def test_session_manager():
    sm = MiniAppSessionManager(default_ttl_seconds=2)
    key = b"0" * 32
    token = sm.create_session(user_id=1, derived_key=key, ttl_seconds=2)
    assert token is not None

    sess = sm.get_session(token)
    assert sess is not None
    assert sess["user_id"] == 1
    assert sess["derived_key"] == key

    # Test touch
    assert sm.touch_session(token, extension_seconds=5) is True

    # Test invalidation
    sm.invalidate_session(token)
    assert sm.get_session(token) is None


@pytest.mark.asyncio
async def test_mini_app_server_flow():
    bot_token = "123456:TEST_BOT_TOKEN_FOR_MINI_APP"
    engine = get_async_engine(":memory:")
    session_factory = get_session_factory(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed a registered user
    pin = "123456"
    pin_salt = generate_salt()
    kdf_salt = generate_salt()
    pin_hash = hash_pin(pin, pin_salt)
    user_id_tg = 999111222

    async with session_factory() as session:
        user = User(
            telegram_user_id=user_id_tg,
            pin_hash=pin_hash,
            pin_hash_salt=pin_salt,
            kdf_salt=kdf_salt,
            failed_pin_attempts=0,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        user_db_id = user.id

    # Create app and test client
    session_mgr = MiniAppSessionManager(default_ttl_seconds=300)
    app = create_mini_app(bot_token, session_factory, session_mgr)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # 1. Status endpoint
        resp = await client.get("/api/status")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert data["pin_length"] == 6

        # 2. Init check endpoint
        user_info = {"id": user_id_tg, "first_name": "TestUser"}
        init_data = generate_mock_init_data(bot_token, user_info)

        resp_init = await client.post("/api/init", json={"init_data": init_data})
        assert resp_init.status == 200
        data_init = await resp_init.json()
        assert data_init["registered"] is True
        assert data_init["telegram_id"] == user_id_tg
        assert data_init["pin_length"] == 6

        # 3. Auth with wrong PIN length (e.g. 4 digits when expecting 6)
        resp_bad_len = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": "1234"})
        assert resp_bad_len.status == 400
        data_bad_len = await resp_bad_len.json()
        assert data_bad_len["success"] is False
        assert "PIN harus terdiri dari 6 digit" in data_bad_len["error"]

        # 4. Auth with wrong PIN
        resp_wrong = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": "000000"})
        assert resp_wrong.status == 401
        data_wrong = await resp_wrong.json()
        assert data_wrong["success"] is False

        # 5. Auth with correct PIN
        resp_auth = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": pin})
        assert resp_auth.status == 200
        data_auth = await resp_auth.json()
        assert data_auth["success"] is True
        token = data_auth["token"]
        assert token

        # 5. List accounts (currently empty)
        headers = {"Authorization": f"Bearer {token}"}
        resp_accs = await client.get("/api/accounts", headers=headers)
        assert resp_accs.status == 200
        data_accs = await resp_accs.json()
        assert data_accs["accounts"] == []

        # 6. Add account via Mini App
        new_acc_payload = {
            "label": "My GitHub",
            "issuer": "GitHub",
            "secret": "JBSWY3DPEHPK3PXP",
            "type": "totp",
            "digits": 6,
            "period": 30,
        }
        resp_add = await client.post("/api/accounts", json=new_acc_payload, headers=headers)
        assert resp_add.status == 201
        data_add = await resp_add.json()
        assert data_add["success"] is True
        created_acc = data_add["account"]
        assert created_acc["label"] == "My GitHub"
        assert created_acc["slug"] == "github"
        assert created_acc["emoji"] == "🐙"
        acc_id = created_acc["id"]

        # 7. List accounts again (now contains 1 account)
        resp_accs2 = await client.get("/api/accounts", headers=headers)
        data_accs2 = await resp_accs2.json()
        assert len(data_accs2["accounts"]) == 1
        item = data_accs2["accounts"][0]
        assert len(item["code"]) == 6
        assert item["code"].isdigit()
        assert item["icon_url"] == "https://cdn.simpleicons.org/github"

        # 8. Toggle favorite
        resp_fav = await client.post(f"/api/accounts/{acc_id}/favorite", headers=headers)
        assert resp_fav.status == 200
        data_fav = await resp_fav.json()
        assert data_fav["is_favorite"] is True

        # 9. Delete account
        resp_del = await client.delete(f"/api/accounts/{acc_id}", headers=headers)
        assert resp_del.status == 200

        resp_accs3 = await client.get("/api/accounts", headers=headers)
        data_accs3 = await resp_accs3.json()
        assert len(data_accs3["accounts"]) == 0

    finally:
        await client.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_mini_app_dynamic_pin_length(monkeypatch):
    """Verify that Mini App dynamically adheres to PIN_LENGTH configured in environment (e.g. 4 digits)."""
    monkeypatch.setenv("PIN_LENGTH", "4")
    get_settings.cache_clear()

    bot_token = "123456:DYNAMIC_PIN_TOKEN"
    engine = get_async_engine(":memory:")
    session_factory = get_session_factory(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed user with 4-digit PIN
    pin = "7890"
    pin_salt = generate_salt()
    kdf_salt = generate_salt()
    pin_hash = hash_pin(pin, pin_salt)
    user_id_tg = 777888999

    async with session_factory() as session:
        user = User(
            telegram_user_id=user_id_tg,
            pin_hash=pin_hash,
            pin_hash_salt=pin_salt,
            kdf_salt=kdf_salt,
            failed_pin_attempts=0,
        )
        session.add(user)
        await session.commit()

    session_mgr = MiniAppSessionManager(default_ttl_seconds=300)
    app = create_mini_app(bot_token, session_factory, session_mgr)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        # Status returns pin_length = 4
        resp = await client.get("/api/status")
        data = await resp.json()
        assert data["pin_length"] == 4

        # Init returns pin_length = 4
        init_data = generate_mock_init_data(bot_token, {"id": user_id_tg, "first_name": "DynamicUser"})
        resp_init = await client.post("/api/init", json={"init_data": init_data})
        data_init = await resp_init.json()
        assert data_init["pin_length"] == 4

        # 6-digit pin rejected with 400
        resp_6dig = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": "123456"})
        assert resp_6dig.status == 400
        data_6dig = await resp_6dig.json()
        assert data_6dig["error"] == "PIN harus terdiri dari 4 digit."

        # Correct 4-digit pin accepted
        resp_auth = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": pin})
        assert resp_auth.status == 200
        data_auth = await resp_auth.json()
        assert data_auth["success"] is True
        assert data_auth["token"]

    finally:
        await client.close()
        await engine.dispose()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_mini_app_advanced_chat_features():
    """Verify HOTP next counter, Edit account, Change Master PIN, Audit Logs, and Backup export in Mini App."""
    bot_token = "123456:ADVANCED_FEATURES_TOKEN"
    engine = get_async_engine(":memory:")
    session_factory = get_session_factory(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    pin = "112233"
    pin_salt = generate_salt()
    kdf_salt = generate_salt()
    pin_hash = hash_pin(pin, pin_salt)
    user_id_tg = 555666777

    async with session_factory() as session:
        user = User(
            telegram_user_id=user_id_tg,
            pin_hash=pin_hash,
            pin_hash_salt=pin_salt,
            kdf_salt=kdf_salt,
            failed_pin_attempts=0,
        )
        session.add(user)
        await session.commit()

    session_mgr = MiniAppSessionManager(default_ttl_seconds=300)
    app = create_mini_app(bot_token, session_factory, session_mgr)

    server = TestServer(app)
    client = TestClient(server)
    await client.start_server()

    try:
        init_data = generate_mock_init_data(bot_token, {"id": user_id_tg, "first_name": "AdvUser"})
        resp_auth = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": pin})
        assert resp_auth.status == 200
        token = (await resp_auth.json())["token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Add HOTP account
        hotp_payload = {
            "label": "My Router",
            "issuer": "OpenWRT",
            "secret": "JBSWY3DPEHPK3PXP",
            "type": "hotp",
            "digits": 6,
        }
        resp_add = await client.post("/api/accounts", json=hotp_payload, headers=headers)
        assert resp_add.status == 201
        acc_data = (await resp_add.json())["account"]
        acc_id = acc_data["id"]

        # 2. Advance HOTP counter (+1)
        resp_next = await client.post(f"/api/accounts/{acc_id}/hotp_next", headers=headers)
        assert resp_next.status == 200
        data_next = await resp_next.json()
        assert data_next["success"] is True
        assert data_next["hotp_counter"] == 1
        assert len(data_next["code"]) == 6

        # 3. Edit account label & issuer
        resp_edit = await client.put(f"/api/accounts/{acc_id}", json={"label": "Office Router", "issuer": "Google"}, headers=headers)
        assert resp_edit.status == 200
        data_edit = await resp_edit.json()
        assert data_edit["account"]["label"] == "Office Router"
        assert data_edit["account"]["issuer"] == "Google"
        assert data_edit["account"]["slug"] == "google"

        # 4. View Audit Logs
        resp_logs = await client.get("/api/settings/logs", headers=headers)
        assert resp_logs.status == 200
        data_logs = await resp_logs.json()
        assert len(data_logs["logs"]) >= 1
        actions = [l["action"] for l in data_logs["logs"]]
        assert "miniapp_hotp_next" in actions
        assert "miniapp_edit_account" in actions

        # 5. Export Backup
        resp_backup = await client.get("/api/settings/backup", headers=headers)
        assert resp_backup.status == 200
        data_backup = await resp_backup.json()
        assert data_backup["total"] == 1
        assert data_backup["accounts"][0]["label"] == "Office Router"
        assert data_backup["accounts"][0]["secret"] == "JBSWY3DPEHPK3PXP"

        # 6. Change Master PIN
        # Wrong old pin
        resp_chg_fail = await client.post("/api/settings/change_pin", json={"old_pin": "999999", "new_pin": "654321"}, headers=headers)
        assert resp_chg_fail.status == 401

        # Correct old pin
        resp_chg_ok = await client.post("/api/settings/change_pin", json={"old_pin": pin, "new_pin": "654321"}, headers=headers)
        assert resp_chg_ok.status == 200

        # Verify old pin fails on login, new pin succeeds
        resp_old_login = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": pin})
        assert resp_old_login.status == 401

        resp_new_login = await client.post("/api/auth/pin", json={"init_data": init_data, "pin": "654321"})
        assert resp_new_login.status == 200
        new_token = (await resp_new_login.json())["token"]

        # Verify accounts still decrypt cleanly with new pin
        resp_verify_accs = await client.get("/api/accounts", headers={"Authorization": f"Bearer {new_token}"})
        assert resp_verify_accs.status == 200
        accs = (await resp_verify_accs.json())["accounts"]
        assert len(accs) == 1
        assert accs[0]["secret"] == "JBSWY3DPEHPK3PXP"

    finally:
        await client.close()
        await engine.dispose()


