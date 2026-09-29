from typing import Optional

# Emoji map keyed by lowercase keyword substring.
# Ordered from most-specific to most-generic to avoid false positives.
# Emoji chosen to best resemble the brand color/logo per Simple Icons (simpleicons.org).
ISSUER_EMOJI_MAP = {
    # ── Developer / Code Hosting ─────────────────────────────────────────────
    "github": "🐙",           # Octocat
    "gitlab": "🦊",           # Fox logo (orange)
    "bitbucket": "🪣",        # Blue bucket
    "gitea": "☕",
    "sourceforge": "🔥",
    "codeberg": "⛰️",

    # ── Google Ecosystem ─────────────────────────────────────────────────────
    "google": "🔵",           # Blue G
    "gmail": "✉️",
    "youtube": "▶️",          # Red play button
    "google cloud": "☁️",
    "firebase": "🔥",         # Orange flame
    "android": "🤖",          # Green robot

    # ── Microsoft Ecosystem ──────────────────────────────────────────────────
    "microsoft": "🟦",        # Blue square
    "outlook": "📧",
    "azure": "🔷",            # Blue diamond
    "xbox": "🎮",
    "onedrive": "☁️",
    "teams": "💼",
    "office": "📄",
    "windows": "🪟",          # Window squares
    "skype": "🔵",
    "bing": "🔍",

    # ── Apple Ecosystem ──────────────────────────────────────────────────────
    "apple": "🍎",            # Red apple
    "icloud": "☁️",
    "itunes": "🎵",

    # ── Social Media ─────────────────────────────────────────────────────────
    "facebook": "🔵",         # Blue
    "instagram": "📸",        # Camera
    "whatsapp": "💬",         # Green chat
    "messenger": "💬",
    "twitter": "🐦",          # Bird
    "x.com": "✖️",
    " x ": "✖️",              # standalone X (avoid matching "fox", "xbox" etc.)
    "tiktok": "🎵",           # Music note (black/teal)
    "snapchat": "👻",         # Ghost
    "pinterest": "📌",        # Red pin
    "linkedin": "🔗",         # Chain / professional
    "reddit": "🤖",           # Robot face (Snoo)
    "tumblr": "📓",
    "mastodon": "🐘",         # Elephant
    "bluesky": "🦋",          # Butterfly
    "threads": "🧵",          # Thread spool
    "vk": "🔵",
    "line": "💚",
    "wechat": "💚",
    "weibo": "🔴",
    "telegram": "✈️",         # Paper plane / blue
    "signal": "🔒",           # Lock (private)
    "discord": "👾",          # Clyde / Alien mascot (classic)
    "twitch": "🟣",           # Purple
    "youtube music": "🎵",
    "spotify": "🟢",          # Green circle
    "soundcloud": "🟠",       # Orange
    "deezer": "🎧",
    "pandora": "🎧",
    "lastfm": "🎸",
    "bandcamp": "🎵",

    # ── Cloud & Hosting ──────────────────────────────────────────────────────
    "aws": "☁️",
    "amazon": "📦",           # Orange arrow box
    "cloudflare": "🟠",       # Orange
    "digitalocean": "🌊",     # Blue wave
    "linode": "🟢",
    "akamai": "🔵",
    "vultr": "🔵",
    "hetzner": "🔴",
    "ovh": "🔵",
    "netlify": "🟢",
    "vercel": "⚫",           # Black triangle
    "heroku": "🟣",           # Purple
    "render": "🟣",
    "railway": "🚂",
    "fly.io": "✈️",
    "supabase": "🟢",
    "planetscale": "⚫",

    # ── Storage & Files ──────────────────────────────────────────────────────
    "dropbox": "📁",          # Blue box/folder
    "box": "📦",
    "mega": "🔴",
    "pcloud": "☁️",
    "backblaze": "🔴",

    # ── Productivity & Notes ─────────────────────────────────────────────────
    "notion": "📝",           # Blank page
    "obsidian": "💎",         # Purple gem
    "evernote": "🐘",         # Green elephant
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
    "figma": "🎨",            # Design (colorful logo)
    "canva": "🎨",
    "adobe": "🔴",            # Red
    "sketch": "🟡",

    # ── Communication & Collaboration ────────────────────────────────────────
    "slack": "💬",
    "zoom": "🔵",
    "meet": "🟢",
    "webex": "🔵",

    # ── E-Commerce & Finance ─────────────────────────────────────────────────
    "paypal": "🔵",           # Blue
    "stripe": "🟣",           # Indigo/purple
    "square": "⬛",
    "shopify": "🟢",          # Green bag
    "woocommerce": "🟣",
    "etsy": "🟠",             # Orange
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

    # ── Crypto & Web3 ────────────────────────────────────────────────────────
    "binance": "🟡",          # Yellow/gold
    "coinbase": "🔵",         # Blue
    "kraken": "🟣",           # Purple
    "bybit": "🟡",
    "okx": "⬛",
    "kucoin": "🟢",
    "huobi": "🔵",
    "bitfinex": "🟢",
    "crypto.com": "🔵",
    "metamask": "🦊",         # Fox logo
    "ledger": "⬛",
    "trezor": "🔒",
    "coinjar": "🪙",
    "indodax": "🔵",
    "tokocrypto": "🟡",
    "crypto": "🪙",
    "bitcoin": "🟠",          # BTC orange
    "ethereum": "💎",
    "blockchain": "🔗",

    # ── Gaming ───────────────────────────────────────────────────────────────
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

    # ── VPN & Security ───────────────────────────────────────────────────────
    "nordvpn": "🛡️",
    "expressvpn": "🔴",
    "surfshark": "🦈",
    "proton": "🔵",
    "protonmail": "✉️",
    "bitwarden": "🛡️",
    "1password": "🔑",
    "lastpass": "🔑",
    "dashlane": "🔑",
    "authy": "🔐",
    "duo": "🔐",
    "okta": "🔵",
    "auth0": "🔐",

    # ── Dev Tools ────────────────────────────────────────────────────────────
    "docker": "🐳",           # Whale
    "kubernetes": "⎈",        # Helm wheel
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
    "terraform": "🟣",
    "ansible": "🔴",
    "vagrant": "🔵",
    "sonarqube": "🔵",
    "jfrog": "🐸",
    "nexus": "🔵",
    "jetbrains": "🔴",

    # ── Domains & DNS ────────────────────────────────────────────────────────
    "namecheap": "🔴",
    "godaddy": "🟢",
    "porkbun": "🐷",
    "dynadot": "🔵",
    "route53": "☁️",
    "dnsmadeeasy": "🟢",

    # ── Email Services ───────────────────────────────────────────────────────
    "zoho": "🔵",
    "protonmail": "🔵",
    "fastmail": "🔵",
    "mailchimp": "🟡",
    "sendgrid": "🔵",
    "mailgun": "🔴",

    # ── Education ────────────────────────────────────────────────────────────
    "coursera": "🔵",
    "udemy": "🟣",
    "duolingo": "🟢",
    "khan": "🟢",
    "edx": "🔴",

    # ── Travel & Transport ───────────────────────────────────────────────────
    "airbnb": "🔴",
    "booking": "🔵",
    "tiket": "🔵",
    "traveloka": "🔵",

    # ── Telco & ISP ──────────────────────────────────────────────────────────
    "telkomsel": "🔴",
    "indosat": "🟡",
    "xl": "🔵",
    "smartfren": "🔴",
    "3 ": "🔵",               # Tri / 3 Indonesia

    # ── Banking & Finance ────────────────────────────────────────────────────
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

    # ── Media & Streaming ────────────────────────────────────────────────────
    "netflix": "🔴",          # Red N
    "disney": "🔵",
    "hbo": "🟣",
    "prime video": "🔵",
    "hulu": "🟢",
    "paramount": "⭐",
    "apple tv": "⬛",
    "vidio": "🔵",
    "viu": "🟡",
    "iflix": "🔴",

    # ── Misc / Generic fallbacks ─────────────────────────────────────────────
    "yahoo": "🟣",
    "linkedin": "🔵",
    "wordpress": "🔵",
    "wix": "⬛",
    "squarespace": "⬛",
    "cpanel": "🟠",
    "plesk": "🔵",
    "cloudinary": "🔵",
    "twilio": "🔴",
    "zapier": "🟠",
    "ifttt": "⬛",
    "openai": "⬛",
    "anthropic": "🟠",
    "huggingface": "🤗",

    # ── Email / generic ──────────────────────────────────────────────────────
    "mail": "✉️",
    "email": "✉️",
}


def get_issuer_emoji(issuer: Optional[str]) -> str:
    """
    Return an emoji that best represents the given issuer brand.
    Matches by substring (case-insensitive). Falls back to 🔐.
    """
    if not issuer or not isinstance(issuer, str):
        return "🔐"
    normalized = issuer.strip().lower()
    for key, emoji in ISSUER_EMOJI_MAP.items():
        if key.strip() in normalized:
            return emoji
    return "🔐"


# ── Simple Icons (simpleicons.org) Slug & Brand Mapping ───────────────────────
# Maps issuer substrings to official Simple Icons SVG slugs.
# CDN URL format: https://cdn.simpleicons.org/{slug}/{color}
ISSUER_SLUG_MAP = {
    # Developer / Code Hosting
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

    # Productivity & Notes
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
    "proton": "proton",
    "bitwarden": "bitwarden",
    "1password": "1password",
    "lastpass": "lastpass",
    "dashlane": "dashlane",
    "authy": "authy",
    "duo": "duo",
    "okta": "okta",
    "auth0": "auth0",

    # DevOps & Tools
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
    "anthropic": "anthropic",
    "huggingface": "huggingface",
}


def get_issuer_slug(issuer: Optional[str]) -> Optional[str]:
    """
    Return the official Simple Icons slug for the issuer brand,
    or None if no matching platform icon is found.
    """
    if not issuer or not isinstance(issuer, str):
        return None
    normalized = issuer.strip().lower()
    for key, slug in ISSUER_SLUG_MAP.items():
        if key in normalized:
            return slug
    return None


def get_issuer_icon_url(issuer: Optional[str], color: Optional[str] = None) -> Optional[str]:
    """
    Return the CDN URL for the issuer's lightweight SVG from simpleicons.org.
    If color is specified (e.g. 'white' or hex '1877F2'), the SVG will be rendered in that color.
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
    Return a unified metadata dictionary containing the best-match emoji,
    Simple Icons slug, and SVG CDN URL. Perfect for API and Telegram Mini App consumption.
    """
    emoji = get_issuer_emoji(issuer)
    slug = get_issuer_slug(issuer)
    return {
        "issuer": issuer,
        "emoji": emoji,
        "slug": slug,
        "icon_url": f"https://cdn.simpleicons.org/{slug}" if slug else None,
    }

