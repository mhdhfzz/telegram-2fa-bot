import math
import time
from urllib.parse import parse_qs, unquote, urlparse
import pyotp


def clean_base32_secret(secret: str) -> str:
    """Strip spaces and hyphens and uppercase the base32 secret."""
    return secret.replace(" ", "").replace("-", "").strip().upper()


def generate_totp_code(secret: str, digits: int = 6, interval: int = 30) -> str:
    """Generate current TOTP code without spaces."""
    cleaned = clean_base32_secret(secret)
    totp = pyotp.TOTP(cleaned, digits=digits, interval=interval)
    return str(totp.now())


def get_totp_remaining_seconds(interval: int = 30) -> int:
    """Get remaining seconds in the current TOTP interval."""
    current_timestamp = time.time()
    return int(interval - (current_timestamp % interval))


def generate_hotp_code(secret: str, counter: int, digits: int = 6) -> str:
    """Generate HOTP code at counter without spaces."""
    cleaned = clean_base32_secret(secret)
    hotp = pyotp.HOTP(cleaned, digits=digits)
    return str(hotp.at(counter))


def format_otp_display(code: str) -> str:
    """Format code in monospace HTML tag without spaces for Telegram tap-to-copy."""
    return f"<code>{code.strip()}</code>"


def render_countdown_bar(remaining_seconds: int, total_period: int = 30) -> str:
    """
    Render visual progress bar for countdown.
    Example: ⏳ [■■■■■■□□□□] 18 detik lagi
    """
    total_blocks = 10
    remaining_seconds = max(0, min(remaining_seconds, total_period))
    filled_blocks = int(math.ceil((remaining_seconds / total_period) * total_blocks))
    filled_blocks = max(0, min(filled_blocks, total_blocks))
    empty_blocks = total_blocks - filled_blocks

    bar = "■" * filled_blocks + "□" * empty_blocks
    return f"⏳ [{bar}] {remaining_seconds} detik lagi"


def parse_otpauth_uri(uri: str) -> dict:
    """
    Parse an otpauth:// URI into its constituent parameters.
    Format: otpauth://[totp|hotp]/[issuer:]label?secret=...&issuer=...
    """
    parsed_url = urlparse(uri)
    if parsed_url.scheme.lower() != "otpauth":
        raise ValueError("Invalid URI scheme: must be 'otpauth'")

    otp_type = parsed_url.netloc.lower()
    if otp_type not in ("totp", "hotp"):
        raise ValueError(f"Unsupported OTP type: {otp_type}")

    raw_path = unquote(parsed_url.path.lstrip("/"))
    query_params = parse_qs(parsed_url.query)

    secret = query_params.get("secret", [None])[0]
    if not secret:
        raise ValueError("Missing 'secret' parameter in URI")
    secret = clean_base32_secret(secret)

    # Extract issuer and label
    issuer_from_query = query_params.get("issuer", [None])[0]
    if ":" in raw_path:
        path_issuer, path_label = raw_path.split(":", 1)
        issuer = issuer_from_query or path_issuer.strip()
        label = path_label.strip()
    else:
        issuer = issuer_from_query
        label = raw_path.strip()

    if not label:
        label = issuer or "Akun Baru"

    digits = int(query_params.get("digits", [6])[0])
    period = int(query_params.get("period", [30])[0])
    counter = int(query_params.get("counter", [0])[0])

    return {
        "secret": secret,
        "issuer": issuer,
        "label": label,
        "type": otp_type,
        "digits": digits,
        "period": period,
        "counter": counter,
    }
