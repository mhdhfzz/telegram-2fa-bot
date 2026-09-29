import time
import pytest
from services.otp_service import (
    generate_totp_code,
    get_totp_remaining_seconds,
    generate_hotp_code,
    parse_otpauth_uri,
    format_otp_display,
    render_countdown_bar,
)
from services.icon_service import get_issuer_emoji
from services.qr_service import encode_qr_image, decode_qr_image


def test_rfc6238_totp_generation():
    # Standard base32 secret
    secret = "JBSWY3DPEHPK3PXP"
    code = generate_totp_code(secret, digits=6, interval=30)
    assert len(code) == 6
    assert code.isdigit()
    assert " " not in code  # No space in code


def test_rfc4226_hotp_generation():
    # RFC 4226 test secret: '12345678901234567890' in base32 is 'GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ'
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    # RFC 4226 known expected values:
    # count 0 -> 755224
    # count 1 -> 287082
    # count 2 -> 359152
    assert generate_hotp_code(secret, counter=0, digits=6) == "755224"
    assert generate_hotp_code(secret, counter=1, digits=6) == "287082"
    assert generate_hotp_code(secret, counter=2, digits=6) == "359152"


def test_format_otp_display():
    code = "123456"
    formatted = format_otp_display(code)
    assert formatted == "<code>123456</code>"
    assert " " not in formatted


def test_countdown_bar():
    bar = render_countdown_bar(15, total_period=30)
    assert "⏳" in bar
    assert "15 detik lagi" in bar
    assert "■" in bar
    assert "□" in bar


def test_parse_otpauth_uri():
    uri_totp = "otpauth://totp/GitHub:zifahx?secret=JBSWY3DPEHPK3PXP&issuer=GitHub&digits=6&period=30"
    parsed = parse_otpauth_uri(uri_totp)
    assert parsed["secret"] == "JBSWY3DPEHPK3PXP"
    assert parsed["issuer"] == "GitHub"
    assert parsed["label"] == "zifahx"
    assert parsed["type"] == "totp"
    assert parsed["digits"] == 6
    assert parsed["period"] == 30

    uri_hotp = "otpauth://hotp/Example:alice?secret=JBSWY3DPEHPK3PXP&counter=5"
    parsed_hotp = parse_otpauth_uri(uri_hotp)
    assert parsed_hotp["type"] == "hotp"
    assert parsed_hotp["counter"] == 5


def test_issuer_emoji():
    assert get_issuer_emoji("GitHub") == "🐙"
    assert get_issuer_emoji("google") == "🔵"
    assert get_issuer_emoji("Discord") == "👾"
    assert get_issuer_emoji("UnknownApp") == "🔐"
    assert get_issuer_emoji(None) == "🔐"


def test_qr_encode_and_decode():
    data = "otpauth://totp/Test:User?secret=JBSWY3DPEHPK3PXP&issuer=Test"
    png_bytes = encode_qr_image(data)
    assert len(png_bytes) > 0
    decoded = decode_qr_image(png_bytes)
    assert decoded == data


def test_parse_otpauth_uri_sanitization():
    # Test zero or negative period, invalid digits, negative counter
    uri_malformed = "otpauth://totp/Test:User?secret=JBSWY3DPEHPK3PXP&period=0&digits=15&counter=-3"
    parsed = parse_otpauth_uri(uri_malformed)
    assert parsed["period"] == 30  # Sanitized to 30 to prevent ZeroDivisionError
    assert parsed["digits"] == 6   # Sanitized to 6
    assert parsed["counter"] == 0  # Sanitized to 0


def test_parse_otpauth_uri_invalid_secret():
    import pytest
    uri_invalid_b32 = "otpauth://totp/Test:User?secret=INVALID_BASE32_1890!@#&period=30"
    with pytest.raises(ValueError, match="Secret key tidak valid"):
        parse_otpauth_uri(uri_invalid_b32)


def test_otp_service_defensive_parameters():
    # Test zero and negative intervals in TOTP code generation
    code = generate_totp_code("JBSWY3DPEHPK3PXP", digits=6, interval=0)
    assert len(code) == 6
    assert code.isdigit()

    code_neg = generate_totp_code("JBSWY3DPEHPK3PXP", digits=99, interval=-10)
    assert len(code_neg) == 6
    assert code_neg.isdigit()

    # Test remaining seconds with invalid intervals
    rem = get_totp_remaining_seconds(interval=0)
    assert 1 <= rem <= 30

    rem_neg = get_totp_remaining_seconds(interval=-5)
    assert 1 <= rem_neg <= 30

    # Test HOTP negative counter and invalid digits
    hotp_code = generate_hotp_code("JBSWY3DPEHPK3PXP", counter=-1, digits=10)
    assert len(hotp_code) == 6
    assert hotp_code.isdigit()

    # Test countdown bar with zero/negative total_period
    bar_zero = render_countdown_bar(15, total_period=0)
    assert "15 detik lagi" in bar_zero

    bar_neg = render_countdown_bar(10, total_period=-10)
    assert "10 detik lagi" in bar_neg

