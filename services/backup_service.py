import json
from typing import Any, Dict, List
from crypto.cipher import decrypt_secret, encrypt_secret
from crypto.kdf import derive_encryption_key, generate_salt


def export_accounts_backup(accounts_data: List[Dict[str, Any]], export_passphrase: str) -> bytes:
    if not export_passphrase or len(export_passphrase) < 4:
        raise ValueError("Passphrase must be at least 4 characters")

    raw_json = json.dumps(accounts_data, ensure_ascii=False)
    salt = generate_salt()
    key = derive_encryption_key(export_passphrase, salt)
    ciphertext, nonce = encrypt_secret(key, raw_json)

    envelope = {
        "version": 1,
        "format": "telegram_2fa_backup",
        "salt": salt,
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex(),
    }
    return json.dumps(envelope, indent=2).encode("utf-8")


def import_accounts_backup(backup_bytes: bytes, export_passphrase: str) -> List[Dict[str, Any]]:
    try:
        envelope = json.loads(backup_bytes.decode("utf-8"))
        salt = envelope["salt"]
        nonce = bytes.fromhex(envelope["nonce"])
        ciphertext = bytes.fromhex(envelope["ciphertext"])
    except Exception as exc:
        raise ValueError("Invalid passphrase or corrupted backup") from exc

    try:
        key = derive_encryption_key(export_passphrase, salt)
        decrypted_json = decrypt_secret(key, ciphertext, nonce)
        accounts_data = json.loads(decrypted_json)
        if not isinstance(accounts_data, list):
            raise ValueError("Corrupted payload structure")
        valid_accounts = [
            item for item in accounts_data
            if isinstance(item, dict) and item.get("secret")
        ]
        if not valid_accounts:
            raise ValueError("Corrupted payload structure: no valid accounts found")
        return valid_accounts
    except Exception as exc:
        raise ValueError("Invalid passphrase or corrupted backup") from exc
