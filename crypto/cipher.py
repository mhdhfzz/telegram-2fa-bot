import os
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def encrypt_secret(key: bytes, plaintext: str) -> tuple[bytes, bytes]:
    """
    Encrypt plaintext using AES-256-GCM.
    Returns:
        (ciphertext_with_tag, nonce)
    """
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise ValueError("Key must be 32 bytes for AES-256-GCM")
    if not isinstance(plaintext, str):
        raise ValueError("Plaintext must be a string")
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), associated_data=None)
    return ciphertext, nonce


def decrypt_secret(key: bytes, ciphertext: bytes, nonce: bytes) -> str:
    """
    Decrypt ciphertext using AES-256-GCM and verify tag.
    Raises ValueError on tampering or invalid key/tag.
    """
    if not isinstance(key, (bytes, bytearray)) or len(key) != 32:
        raise ValueError("Key must be 32 bytes for AES-256-GCM")
    if not isinstance(ciphertext, (bytes, bytearray)) or not isinstance(nonce, (bytes, bytearray)):
        raise ValueError("Ciphertext and nonce must be bytes")
    aesgcm = AESGCM(key)
    try:
        decrypted_bytes = aesgcm.decrypt(nonce, ciphertext, associated_data=None)
        return decrypted_bytes.decode("utf-8")
    except (InvalidTag, Exception) as exc:
        raise ValueError("Decryption failed: invalid key or tampered data") from exc
