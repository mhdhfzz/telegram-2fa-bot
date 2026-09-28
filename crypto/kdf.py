import hmac
import os
from argon2.low_level import Type, hash_secret_raw

# Argon2id parameters
TIME_COST = 2
MEMORY_COST = 65536  # 64 MB
PARALLELISM = 1
HASH_LEN = 32


def generate_salt() -> str:
    """Generate a random 16-byte salt returned as a 32-character hex string."""
    return os.urandom(16).hex()


def derive_raw_argon2(secret: str, salt_hex: str, hash_len: int = HASH_LEN) -> bytes:
    """Derive raw bytes using Argon2id with standard security parameters."""
    secret_bytes = secret.encode("utf-8")
    salt_bytes = bytes.fromhex(salt_hex)
    return hash_secret_raw(
        secret=secret_bytes,
        salt=salt_bytes,
        time_cost=TIME_COST,
        memory_cost=MEMORY_COST,
        parallelism=PARALLELISM,
        hash_len=hash_len,
        type=Type.ID,
    )


def hash_pin(pin: str, salt_hex: str) -> str:
    """Hash a PIN using Argon2id with pin_hash_salt, returning hex string."""
    raw_hash = derive_raw_argon2(pin, salt_hex)
    return raw_hash.hex()


def verify_pin(pin: str, salt_hex: str, expected_hash_hex: str) -> bool:
    """Verify PIN in constant time."""
    computed_hash = hash_pin(pin, salt_hex)
    return hmac.compare_digest(computed_hash, expected_hash_hex)


def derive_encryption_key(pin: str, salt_hex: str) -> bytes:
    """Derive a 256-bit (32-byte) AES key from PIN and user's kdf_salt."""
    return derive_raw_argon2(pin, salt_hex, hash_len=32)
