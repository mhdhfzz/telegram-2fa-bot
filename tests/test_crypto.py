import pytest
from crypto.kdf import (
    generate_salt,
    hash_pin,
    verify_pin,
    derive_encryption_key,
)
from crypto.cipher import encrypt_secret, decrypt_secret
from crypto.recovery import (
    generate_recovery_phrase,
    hash_recovery_phrase,
    normalize_phrase,
    verify_recovery_phrase,
)


def test_salt_generation():
    salt1 = generate_salt()
    salt2 = generate_salt()
    assert len(salt1) == 32  # 16 bytes in hex
    assert len(salt2) == 32
    assert salt1 != salt2


def test_pin_hashing_and_verification():
    pin = "123456"
    salt = generate_salt()
    pin_hash = hash_pin(pin, salt)

    assert isinstance(pin_hash, str)
    assert len(pin_hash) > 0
    # Correct PIN verifies
    assert verify_pin(pin, salt, pin_hash) is True
    # Wrong PIN fails
    assert verify_pin("654321", salt, pin_hash) is False
    assert verify_pin("12345", salt, pin_hash) is False


def test_key_derivation_determinism_and_independence():
    pin = "482910"
    salt1 = generate_salt()
    salt2 = generate_salt()

    key1 = derive_encryption_key(pin, salt1)
    key1_again = derive_encryption_key(pin, salt1)
    key2 = derive_encryption_key(pin, salt2)

    assert len(key1) == 32
    assert key1 == key1_again  # Deterministic
    assert key1 != key2  # Unique per salt


def test_aes_gcm_encrypt_decrypt():
    key = derive_encryption_key("887766", generate_salt())
    secret = "JBSWY3DPEHPK3PXP"

    ciphertext, nonce = encrypt_secret(key, secret)

    assert len(nonce) == 12
    assert ciphertext != secret.encode()
    assert len(ciphertext) > len(secret)  # includes 16-byte GCM tag

    decrypted = decrypt_secret(key, ciphertext, nonce)
    assert decrypted == secret


def test_aes_gcm_tamper_proofing():
    key = derive_encryption_key("887766", generate_salt())
    wrong_key = derive_encryption_key("112233", generate_salt())
    secret = "JBSWY3DPEHPK3PXP"

    ciphertext, nonce = encrypt_secret(key, secret)

    # Wrong key raises ValueError
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_secret(wrong_key, ciphertext, nonce)

    # Tampered ciphertext raises ValueError
    tampered_bytes = bytearray(ciphertext)
    tampered_bytes[0] ^= 0xFF
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_secret(key, bytes(tampered_bytes), nonce)

    # Wrong nonce raises ValueError
    wrong_nonce = bytearray(nonce)
    wrong_nonce[0] ^= 0xFF
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_secret(key, ciphertext, bytes(wrong_nonce))


def test_recovery_phrase_generation_and_verification():
    # English BIP-39
    phrase_en = generate_recovery_phrase(language="en")
    assert len(phrase_en) == 12
    assert all(isinstance(w, str) and len(w) > 0 for w in phrase_en)

    hash_en = hash_recovery_phrase(phrase_en)
    assert verify_recovery_phrase(phrase_en, hash_en) is True

    # Mutated phrase fails
    mutated = phrase_en.copy()
    mutated[0] = "abandon" if mutated[0] != "abandon" else "ability"
    assert verify_recovery_phrase(mutated, hash_en) is False

    # Indonesian wordlist
    phrase_id = generate_recovery_phrase(language="id")
    assert len(phrase_id) == 12
    hash_id = hash_recovery_phrase(phrase_id)
    assert verify_recovery_phrase(phrase_id, hash_id) is True

    # Test normalize_phrase with str, list, whitespace, empty, and None
    assert normalize_phrase("  Alpha   BETA  gamma  ") == "alpha beta gamma"
    assert normalize_phrase(["  Alpha ", "BETA  ", "gamma"]) == "alpha beta gamma"
    assert normalize_phrase("") == ""
    assert normalize_phrase(None) == ""

    # Test generate_recovery_phrase with None/invalid language
    assert len(generate_recovery_phrase(None)) == 12  # type: ignore
    assert len(generate_recovery_phrase(123)) == 12  # type: ignore

    # Test verify_recovery_phrase with None/invalid expected_hash and empty phrase
    assert verify_recovery_phrase(phrase_en, None) is False  # type: ignore
    assert verify_recovery_phrase(phrase_en, 12345) is False  # type: ignore
    assert verify_recovery_phrase([], hash_en) is False
    assert verify_recovery_phrase(None, hash_en) is False  # type: ignore


def test_crypto_defensive_parameters():
    key = b"0" * 32

    # derive_raw_argon2 defensive tests
    from crypto.kdf import derive_raw_argon2
    with pytest.raises(TypeError, match="secret must be a string"):
        derive_raw_argon2(None, "aabb")  # type: ignore
    with pytest.raises(TypeError, match="salt_hex must be a string"):
        derive_raw_argon2("123456", None)  # type: ignore

    # verify_pin defensive tests
    assert verify_pin(None, "salt", "hash") is False  # type: ignore
    assert verify_pin("123456", None, "hash") is False  # type: ignore
    assert verify_pin("123456", "invalid_hex", "hash") is False
    assert verify_pin("123456", "aabb", None) is False  # type: ignore

    # encrypt_secret defensive tests
    with pytest.raises(ValueError, match="Key must be 32 bytes"):
        encrypt_secret(None, "secret")  # type: ignore
    with pytest.raises(ValueError, match="Key must be 32 bytes"):
        encrypt_secret(b"short_key", "secret")
    with pytest.raises(ValueError, match="Plaintext must be a string"):
        encrypt_secret(key, None)  # type: ignore

    # decrypt_secret defensive tests
    with pytest.raises(ValueError, match="Key must be 32 bytes"):
        decrypt_secret(b"short", b"cipher", b"nonce")
    with pytest.raises(ValueError, match="Ciphertext and nonce must be bytes"):
        decrypt_secret(key, None, b"nonce")  # type: ignore
    with pytest.raises(ValueError, match="Ciphertext and nonce must be bytes"):
        decrypt_secret(key, b"cipher", None)  # type: ignore


