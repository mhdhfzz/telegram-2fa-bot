from typing import Optional

ISSUER_EMOJI_MAP = {
    "github": "🐙",
    "gitlab": "🦊",
    "google": "🔵",
    "gmail": "✉️",
    "microsoft": "🟦",
    "outlook": "📧",
    "apple": "🍏",
    "discord": "👾",
    "twitter": "🐦",
    "x": "🐦",
    "telegram": "✈️",
    "facebook": "👤",
    "instagram": "📸",
    "steam": "🎮",
    "binance": "🪙",
    "coinbase": "🪙",
    "crypto": "🪙",
    "amazon": "📦",
    "aws": "☁️",
    "cloudflare": "🟠",
    "digitalocean": "🌊",
    "linode": "🟢",
    "dropbox": "📁",
    "notion": "📝",
    "slack": "💬",
    "reddit": "🤖",
    "spotify": "🎵",
    "uber": "🚗",
    "grab": "🛵",
    "gojek": "🛵",
    "tokopedia": "🛒",
    "shopee": "🛍️",
}


def get_issuer_emoji(issuer: Optional[str]) -> str:
    """Return an emoji representation for the given issuer, default to lock emoji."""
    if not issuer:
        return "🔐"
    normalized = issuer.strip().lower()
    for key, emoji in ISSUER_EMOJI_MAP.items():
        if key in normalized:
            return emoji
    return "🔐"
