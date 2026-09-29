from datetime import datetime, timezone
import pytest
from services.backup_service import export_accounts_backup, import_accounts_backup
from services.log_service import format_local_timestamp


def test_format_local_timestamp():
    # Test None / empty
    assert format_local_timestamp(None) == ""

    # Test UTC datetime
    utc_dt = datetime(2026, 9, 30, 12, 0, 0, tzinfo=timezone.utc)
    formatted = format_local_timestamp(utc_dt, "%Y-%m-%d")
    assert formatted.startswith("2026-09-")

    # Test naive datetime
    naive_dt = datetime(2026, 9, 30, 12, 0, 0)
    formatted_naive = format_local_timestamp(naive_dt, "%H:%M")
    assert len(formatted_naive) == 5


def test_backup_service_preserves_hotp_and_favorite():
    accounts = [
        {
            "label": "My HOTP",
            "issuer": "GitHub",
            "secret": "JBSWY3DPEHPK3PXP",
            "type": "hotp",
            "digits": 6,
            "period": 30,
            "hotp_counter": 42,
            "is_favorite": True,
        }
    ]

    passphrase = "supersecretpassphrase"
    backup_bytes = export_accounts_backup(accounts, passphrase)
    assert len(backup_bytes) > 0

    restored = import_accounts_backup(backup_bytes, passphrase)
    assert len(restored) == 1
    acc = restored[0]
    assert acc["label"] == "My HOTP"
    assert acc["hotp_counter"] == 42
    assert acc["is_favorite"] is True
