import pytest
from services.backup_service import export_accounts_backup, import_accounts_backup


def test_export_and_import_roundtrip():
    accounts_data = [
        {
            "label": "GitHub",
            "issuer": "GitHub",
            "secret": "JBSWY3DPEHPK3PXP",
            "type": "totp",
            "digits": 6,
            "period": 30,
        },
        {
            "label": "Google Workspace",
            "issuer": "Google",
            "secret": "HXDMVJECJJWSRB3HWIZR4IFUGFTMXBOZ",
            "type": "totp",
            "digits": 6,
            "period": 30,
        },
    ]
    passphrase = "MySecretPassphrase123!"

    backup_bytes = export_accounts_backup(accounts_data, passphrase)
    assert isinstance(backup_bytes, bytes)
    assert len(backup_bytes) > 0

    imported_accounts = import_accounts_backup(backup_bytes, passphrase)
    assert len(imported_accounts) == 2
    assert imported_accounts[0]["label"] == "GitHub"
    assert imported_accounts[0]["secret"] == "JBSWY3DPEHPK3PXP"
    assert imported_accounts[1]["issuer"] == "Google"


def test_import_with_wrong_passphrase():
    accounts_data = [{"label": "Test", "secret": "ABCDEF123456", "type": "totp"}]
    backup_bytes = export_accounts_backup(accounts_data, "correct_passphrase")

    with pytest.raises(ValueError, match="Invalid passphrase or corrupted backup"):
        import_accounts_backup(backup_bytes, "wrong_passphrase")


def test_import_tampered_payload():
    accounts_data = [{"label": "Test", "secret": "ABCDEF123456", "type": "totp"}]
    backup_bytes = export_accounts_backup(accounts_data, "correct_passphrase")

    # Tamper with the raw backup bytes
    tampered_bytes = bytearray(backup_bytes)
    # Flip a byte near the end
    tampered_bytes[-10] ^= 0xFF

    with pytest.raises(ValueError, match="Invalid passphrase or corrupted backup"):
        import_accounts_backup(bytes(tampered_bytes), "correct_passphrase")


def test_import_invalid_payload_structure():
    # Payload with no secrets or empty dicts
    accounts_data = [{"label": "NoSecret", "type": "totp"}]
    backup_bytes = export_accounts_backup(accounts_data, "valid_passphrase")

    with pytest.raises(ValueError, match="Invalid passphrase or corrupted backup"):
        import_accounts_backup(backup_bytes, "valid_passphrase")

