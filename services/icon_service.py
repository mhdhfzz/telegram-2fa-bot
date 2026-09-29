from typing import Optional

ISSUER_EMOJI_MAP = {
    # Developer & Code Hosting
    "github": "🐙",
    "gitlab": "🦊",
    "bitbucket": "🪣",
    "gitea": "🍵",
    "sourceforge": "🔥",
    "codeberg": "⛰️",

    # Google Ecosystem (Composite keys first)
    "google cloud": "☁️",
    "google": "🔵",
    "gmail": "✉️",
    "youtube music": "🎵",
    "youtube": "▶️",
    "firebase": "🔥",
    "android": "🤖",

    # Microsoft Ecosystem
    "microsoft": "🪟",
    "outlook": "📧",
    "azure": "🔷",
    "xbox": "🎮",
    "onedrive": "☁️",
    "teams": "👥",
    "office": "📄",
    "windows": "🪟",
    "skype": "🔵",
    "bing": "🔍",

    # Apple Ecosystem
    "apple": "🍎",
    "icloud": "☁️",
    "itunes": "🎵",

    # Social Media
    "facebook": "🔵",
    "instagram": "📸",
    "whatsapp": "💬",
    "messenger": "💬",
    "twitter": "🐦",
    "x.com": "✖️",
    " x ": "✖️",
    "tiktok": "🎵",
    "snapchat": "👻",
    "pinterest": "📌",
    "linkedin": "🔗",
    "reddit": "🤖",
    "tumblr": "📓",
    "mastodon": "🐘",
    "bluesky": "🦋",
    "threads": "🧵",
    "vk": "🔵",
    "line": "💚",
    "wechat": "💚",
    "weibo": "🔴",
    "telegram": "✈️",
    "signal": "🔒",
    "discord": "👾",
    "twitch": "🟣",
    "spotify": "🟢",
    "soundcloud": "🟠",
    "deezer": "🎧",
    "pandora": "🎧",
    "lastfm": "🎸",
    "bandcamp": "🎵",

    # Cloud & Hosting (Composite keys first)
    "amazon web services": "☁️",
    "aws": "☁️",
    "amazon": "📦",
    "cloudflare": "🟠",
    "digitalocean": "🌊",
    "linode": "🟢",
    "akamai": "🔵",
    "vultr": "🔵",
    "hetzner": "🔴",
    "ovh": "🔵",
    "netlify": "🟢",
    "vercel": "⚫",
    "heroku": "🟣",
    "render": "🟣",
    "railway": "🚂",
    "fly.io": "✈️",
    "supabase": "🟢",
    "planetscale": "⚫",

    # Storage & Files
    "dropbox": "📁",
    "box": "📦",
    "mega": "🔴",
    "pcloud": "☁️",
    "backblaze": "🔴",

    # Productivity & Design
    "notion": "📝",
    "obsidian": "💎",
    "evernote": "🐘",
    "onenote": "📓",
    "confluence": "🔵",
    "jira": "🔵",
    "trello": "🟦",
    "asana": "🔴",
    "monday": "🔴",
    "clickup": "🟣",
    "todoist": "✅",
    "airtable": "🟡",
    "miro": "🟡",
    "figma": "🎨",
    "canva": "🎨",
    "adobe": "🔴",
    "sketch": "🟡",

    # Communication & Collaboration
    "slack": "💬",
    "zoom": "🔵",
    "meet": "🟢",
    "webex": "🔵",

    # E-Commerce & Finance
    "paypal": "🔵",
    "stripe": "🟣",
    "square": "⬛",
    "shopify": "🟢",
    "woocommerce": "🟣",
    "etsy": "🟠",
    "ebay": "🛍️",
    "alibaba": "🟠",
    "aliexpress": "🔴",
    "tokopedia": "🟢",
    "shopee": "🟠",
    "lazada": "🟣",
    "bukalapak": "🔴",
    "gojek": "🟢",
    "grab": "🟢",
    "ovo": "🟣",
    "dana": "🔵",
    "gopay": "🟢",
    "linkaja": "🔴",
    "qris": "🔲",
    "flip": "🔵",

    # Crypto & Web3
    "binance": "🟡",
    "coinbase": "🔵",
    "kraken": "🟣",
    "bybit": "🟡",
    "okx": "⬛",
    "kucoin": "🟢",
    "huobi": "🔵",
    "bitfinex": "🟢",
    "crypto.com": "🔵",
    "metamask": "🦊",
    "ledger": "⬛",
    "trezor": "🔒",
    "coinjar": "🪙",
    "indodax": "🔵",
    "tokocrypto": "🟡",
    "crypto": "🪙",
    "bitcoin": "🟠",
    "ethereum": "💎",
    "blockchain": "🔗",

    # Gaming (Composite keys first)
    "steam": "🎮",
    "epic games": "🕹️",
    "epic": "🕹️",
    "ea": "🎮",
    "ubisoft": "🕹️",
    "blizzard": "🎮",
    "riot": "⚔️",
    "playstation": "🎮",
    "nintendo": "🔴",
    "battlenet": "🔵",
    "genshin": "🌸",
    "valorant": "🔫",
    "roblox": "🧱",

    # VPN & Security (Composite keys first)
    "nordvpn": "🛡️",
    "expressvpn": "🔴",
    "surfshark": "🦈",
    "protonmail": "✉️",
    "proton": "🔵",
    "bitwarden": "🛡️",
    "1password": "🔑",
    "lastpass": "🔑",
    "dashlane": "🔑",
    "authy": "🔐",
    "duo": "🔐",
    "okta": "🔵",
    "auth0": "🔐",

    # Developer Tools
    "docker": "🐳",
    "kubernetes": "⎈",
    "jenkins": "🤖",
    "circleci": "🔵",
    "travis": "🔵",
    "grafana": "🟠",
    "datadog": "🐶",
    "sentry": "🔴",
    "postman": "🟠",
    "npm": "🔴",
    "pypi": "🐍",
    "conda": "🐍",
    "python": "🐍",
    "rust": "🦀",
    "golang": "🐹",
    "terraform": "🟣",
    "ansible": "🔴",
    "vagrant": "🔵",
    "sonarqube": "🔵",
    "jfrog": "🐸",
    "nexus": "🔵",
    "jetbrains": "🔴",

    # Domains & DNS
    "namecheap": "🔴",
    "godaddy": "🟢",
    "porkbun": "🐷",
    "dynadot": "🔵",
    "route53": "☁️",
    "dnsmadeeasy": "🟢",

    # Email Services
    "zoho": "🔵",
    "fastmail": "🔵",
    "mailchimp": "🟡",
    "sendgrid": "🔵",
    "mailgun": "🔴",

    # Education
    "coursera": "🔵",
    "udemy": "🟣",
    "duolingo": "🟢",
    "khan": "🟢",
    "edx": "🔴",

    # Travel & Transport
    "airbnb": "🔴",
    "booking": "🔵",
    "tiket": "🔵",
    "traveloka": "🔵",

    # Telco & ISP
    "telkomsel": "🔴",
    "indosat": "🟡",
    "xl": "🔵",
    "smartfren": "🔴",
    " 3 ": "🔵",

    # Indonesian & Global Banking
    "bca": "🔵",
    "mandiri": "🟡",
    "bni": "🟠",
    "bri": "🔵",
    "cimb": "🔴",
    "bsi": "🟢",
    "permata": "🔵",
    "ocbc": "🔴",
    "jago": "🔵",
    "jenius": "🔵",
    "bank": "🏦",
    "payoneer": "🟡",
    "wise": "🟢",
    "revolut": "⬛",
    "skrill": "🟣",
    "neteller": "🟢",

    # Streaming & Media
    "netflix": "🔴",
    "disney": "🔵",
    "hbo": "🟣",
    "prime video": "🔵",
    "hulu": "🟢",
    "paramount": "⭐",
    "apple tv": "⬛",
    "vidio": "🔵",
    "viu": "🟡",
    "iflix": "🔴",

    # Artificial Intelligence & Search
    "openai": "🤖",
    "chatgpt": "🤖",
    "anthropic": "🟠",
    "claude": "🟠",
    "huggingface": "🤗",
    "midjourney": "⛵",

    # Generic & Fallbacks
    "yahoo": "🟣",
    "wordpress": "🔵",
    "wix": "⬛",
    "squarespace": "⬛",
    "cpanel": "🟠",
    "plesk": "🔵",
    "cloudinary": "🔵",
    "twilio": "🔴",
    "zapier": "🟠",
    "ifttt": "⬛",
    "mail": "✉️",
    "email": "✉️",
}


ISSUER_SLUG_MAP = {
    # Developer & Code Hosting
    "github": "github",
    "gitlab": "gitlab",
    "bitbucket": "bitbucket",
    "gitea": "gitea",
    "sourceforge": "sourceforge",
    "codeberg": "codeberg",

    # Google Ecosystem
    "google cloud": "googlecloud",
    "google": "google",
    "gmail": "gmail",
    "youtube music": "youtubemusic",
    "youtube": "youtube",
    "firebase": "firebase",
    "android": "android",

    # Microsoft Ecosystem
    "microsoft": "microsoft",
    "outlook": "microsoftoutlook",
    "azure": "microsoftazure",
    "xbox": "xbox",
    "onedrive": "microsoftonedrive",
    "teams": "microsoftteams",
    "windows": "windows",
    "skype": "skype",
    "bing": "microsoftbing",

    # Apple Ecosystem
    "apple": "apple",
    "icloud": "icloud",
    "itunes": "applemusic",

    # Social Media
    "facebook": "facebook",
    "instagram": "instagram",
    "whatsapp": "whatsapp",
    "messenger": "messenger",
    "twitter": "x",
    "x.com": "x",
    "tiktok": "tiktok",
    "snapchat": "snapchat",
    "pinterest": "pinterest",
    "linkedin": "linkedin",
    "reddit": "reddit",
    "tumblr": "tumblr",
    "mastodon": "mastodon",
    "bluesky": "bluesky",
    "threads": "threads",
    "vk": "vk",
    "line": "line",
    "wechat": "wechat",
    "weibo": "sinaweibo",
    "telegram": "telegram",
    "signal": "signal",
    "discord": "discord",
    "twitch": "twitch",
    "spotify": "spotify",
    "soundcloud": "soundcloud",
    "deezer": "deezer",

    # Cloud & Hosting
    "amazon web services": "amazonwebservices",
    "aws": "amazonwebservices",
    "amazon": "amazon",
    "cloudflare": "cloudflare",
    "digitalocean": "digitalocean",
    "linode": "linode",
    "akamai": "akamai",
    "vultr": "vultr",
    "hetzner": "hetzner",
    "ovh": "ovh",
    "netlify": "netlify",
    "vercel": "vercel",
    "heroku": "heroku",
    "render": "render",
    "railway": "railway",
    "supabase": "supabase",

    # Storage & Productivity
    "dropbox": "dropbox",
    "box": "box",
    "notion": "notion",
    "obsidian": "obsidian",
    "evernote": "evernote",
    "onenote": "microsoftonenote",
    "confluence": "confluence",
    "jira": "jira",
    "trello": "trello",
    "asana": "asana",
    "monday": "mondaydotcom",
    "clickup": "clickup",
    "todoist": "todoist",
    "airtable": "airtable",
    "miro": "miro",
    "figma": "figma",
    "canva": "canva",
    "adobe": "adobe",

    # Communication
    "slack": "slack",
    "zoom": "zoom",
    "meet": "googlemeet",
    "webex": "ciscowebex",

    # E-Commerce & Finance
    "paypal": "paypal",
    "stripe": "stripe",
    "square": "square",
    "shopify": "shopify",
    "woocommerce": "woocommerce",
    "etsy": "etsy",
    "ebay": "ebay",
    "alibaba": "alibaba",
    "aliexpress": "aliexpress",
    "tokopedia": "tokopedia",
    "shopee": "shopee",
    "bukalapak": "bukalapak",
    "gojek": "gojek",
    "grab": "grab",

    # Crypto & Web3
    "binance": "binance",
    "coinbase": "coinbase",
    "kraken": "kraken",
    "bybit": "bybit",
    "okx": "okx",
    "kucoin": "kucoin",
    "bitfinex": "bitfinex",
    "crypto.com": "cryptodotcom",
    "metamask": "metamask",
    "ledger": "ledger",
    "trezor": "trezor",
    "bitcoin": "bitcoin",
    "ethereum": "ethereum",

    # Gaming
    "steam": "steam",
    "epic games": "epicgames",
    "epic": "epicgames",
    "ea": "ea",
    "ubisoft": "ubisoft",
    "blizzard": "blizzard",
    "riot": "riotgames",
    "playstation": "playstation",
    "nintendo": "nintendoswitch",
    "battlenet": "battlenet",
    "roblox": "roblox",

    # VPN & Security
    "nordvpn": "nordvpn",
    "expressvpn": "expressvpn",
    "surfshark": "surfshark",
    "protonmail": "proton",
    "proton": "proton",
    "bitwarden": "bitwarden",
    "1password": "1password",
    "lastpass": "lastpass",
    "dashlane": "dashlane",
    "authy": "authy",
    "duo": "duo",
    "okta": "okta",
    "auth0": "auth0",

    # DevOps & Languages
    "docker": "docker",
    "kubernetes": "kubernetes",
    "jenkins": "jenkins",
    "circleci": "circleci",
    "travis": "travisci",
    "grafana": "grafana",
    "datadog": "datadog",
    "sentry": "sentry",
    "postman": "postman",
    "npm": "npm",
    "pypi": "pypi",
    "python": "python",
    "rust": "rust",
    "terraform": "terraform",
    "ansible": "ansible",
    "vagrant": "vagrant",
    "sonarqube": "sonarqube",
    "jfrog": "jfrog",
    "jetbrains": "jetbrains",

    # Streaming & AI
    "netflix": "netflix",
    "disney": "disneyplus",
    "hbo": "hbo",
    "hulu": "hulu",
    "openai": "openai",
    "chatgpt": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "huggingface": "huggingface",
}


def _match_issuer_key(issuer_normalized: str, key: str) -> bool:
    """
    Check if a normalized issuer string matches a dictionary key.
    - Keys with spaces (e.g. ' x ', ' 3 ') match space-delimited boundary.
    - Short keys (<= 2 chars, e.g. 'ea', '3', 'vk', 'xl') require full word/token match.
    - Multi-character keys (>= 3 chars) match as substrings.
    """
    if not key or not issuer_normalized:
        return False

    clean_key = key.strip()
    if issuer_normalized == clean_key:
        return True

    if key.startswith(" ") or key.endswith(" "):
        return key in f" {issuer_normalized} "

    if len(clean_key) <= 2:
        words = (
            issuer_normalized.replace(".", " ")
            .replace("-", " ")
            .replace("_", " ")
            .replace("/", " ")
            .split()
        )
        return clean_key in words

    return clean_key in issuer_normalized


def get_issuer_emoji(issuer: Optional[str]) -> str:
    """
    Return the emoji that best represents the given issuer brand.
    Falls back to 🔐.
    """
    if not issuer or not isinstance(issuer, str):
        return "🔐"
    normalized = issuer.strip().lower()
    for key, emoji in ISSUER_EMOJI_MAP.items():
        if _match_issuer_key(normalized, key):
            return emoji
    return "🔐"


def get_issuer_slug(issuer: Optional[str]) -> Optional[str]:
    """
    Return the official Simple Icons slug for the issuer brand,
    or None if no matching platform icon is found.
    """
    if not issuer or not isinstance(issuer, str):
        return None
    normalized = issuer.strip().lower()
    for key, slug in ISSUER_SLUG_MAP.items():
        if _match_issuer_key(normalized, key):
            return slug
    return None


def get_issuer_icon_url(issuer: Optional[str], color: Optional[str] = None) -> Optional[str]:
    """
    Return the CDN URL for the issuer's lightweight SVG from simpleicons.org.
    Example: https://cdn.simpleicons.org/github
    """
    slug = get_issuer_slug(issuer)
    if not slug:
        return None
    if color:
        return f"https://cdn.simpleicons.org/{slug}/{color.lstrip('#')}"
    return f"https://cdn.simpleicons.org/{slug}"


def get_issuer_info(issuer: Optional[str]) -> dict:
    """
    Return metadata dictionary with emoji, slug, and SVG CDN URL.
    """
    emoji = get_issuer_emoji(issuer)
    slug = get_issuer_slug(issuer)
    return {
        "issuer": issuer,
        "emoji": emoji,
        "slug": slug,
        "icon_url": f"https://cdn.simpleicons.org/{slug}" if slug else None,
    }
